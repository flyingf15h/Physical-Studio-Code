"""BOM upload: a signed-in user's bill of materials becomes parts in their own library.

Rows the shared parts library already has are used as they are ("in_library"); only the others are
looked up and added ("added"). The Dashboard's "Parts I have" box uploads BOMs here.

POST /api/bom {text} takes a CSV/TSV file's text or a pasted table ("Name  Link  Price" rows, the
way a shop basket or a spreadsheet copies). Each row is looked up on the web (the same searches as
find_part_looks: OpenAI web search, then Gemini with Google Search on each team key) for its size,
category and pins, and saved as a parts/*.json-style entry under <OUT_DIR>/.accounts/parts-<user>/.
Those parts are unverified ("verified": false, source "From your BOM: <link>"). GET /api/parts
lists them for their owner, and the breadboard planner (bench/) uses them for that owner's builds.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from .library import CATEGORIES
from .looks import LookError, search_gemini, search_openai
from .users import user_from_request

MAX_ROWS = 30
MAX_TEXT = 20000
URL = re.compile(r"https?://\S+")
PRICE = re.compile(r"(?:[$€£]|CAD|USD)?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:CAD|USD|\$)?$", re.I)
QTY = re.compile(r"^(\d{1,3})\s*[x×]\s+", re.I)

_dir: Path | None = None
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bom")


# --- reading the table ---------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    if line.count(",") >= 1 and not re.search(r"\s{2,}", line):
        return [c.strip() for c in next(csv.reader(io.StringIO(line)))]
    return [c.strip() for c in re.split(r"\s{2,}", line.strip())]


def parse_bom(text: str) -> list[dict]:
    """Rows of {name, link, price, quantity}. A header row (name/item/part, link/url, price, qty) is
    used when there is one; otherwise the URL is the link, a trailing number the price, the rest the
    name, and a leading "2x" the quantity."""
    lines = [line for line in text[:MAX_TEXT].splitlines() if line.strip()]
    if not lines:
        return []
    head = [c.lower() for c in _cells(lines[0])]
    has_header = any(re.search(r"\b(name|item|part|description)\b", c) for c in head) and not URL.search(lines[0])
    rows = []
    for line in lines[1:] if has_header else lines:
        cells = [c for c in _cells(line) if c]
        if not cells:
            continue
        link = next((m.group(0) for c in cells if (m := URL.search(c))), "")
        rest = [c for c in cells if not URL.search(c)]
        price = ""
        if len(rest) > 1 and PRICE.fullmatch(rest[-1]):
            price = rest.pop()
        name = " ".join(rest).strip(" -,")
        if not name:
            continue
        qty = 1
        if m := QTY.match(name):
            qty, name = int(m[1]), name[m.end() :]
        rows.append({"name": name[:120], "link": link[:500], "price": price, "quantity": qty})
    return rows[:MAX_ROWS]


# --- looking a row up ----------------------------------------------------------------------------


def part_prompt(row: dict) -> str:
    return (
        "Find the real physical part a maker bought, so a design tool can place it with real dimensions.\n"
        f"Shopping-list name: {row['name']}\nListing: {row['link'] or '(none)'}\n\n"
        "Answer with one JSON object and nothing else:\n"
        '{"name": "plain name, e.g. \'Teensy 4.1\' or \'DRV8874 motor driver board\'",'
        ' "category": "board | input | output | misc",'
        ' "size_mm": [length, width, height] of the body in mm from the datasheet or listing,'
        ' "pins": [{"id": "short_id", "label": "what is printed on the board"}] (empty for mechanical parts),'
        ' "notes": "one or two sentences: what it is and what to know when wiring or mounting it",'
        ' "source": "URL of the page the dimensions came from"}'
    )


def parse_part(text: str, row: dict) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LookError("the search didn't return a part")
    raw = json.loads(text[start : end + 1])
    size = [float(v) for v in raw.get("size_mm") or []]
    if len(size) != 3 or not all(0.1 <= v <= 2000 for v in size):
        raise LookError("no usable dimensions found")
    category = str(raw.get("category", "misc")).lower()
    name = str(raw.get("name") or row["name"])[:80]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "part"
    pid = f"{slug}-{hashlib.sha1((row['name'] + row['link']).encode()).hexdigest()[:6]}"
    pins = [
        {"id": re.sub(r"[^a-z0-9_]+", "_", str(p.get("id", "")).lower())[:20] or f"p{i + 1}", "label": str(p.get("label", ""))[:40]}
        for i, p in enumerate(raw.get("pins") or [])
        if isinstance(p, dict)
    ][:60]
    return {
        "id": pid,
        "name": name,
        "category": category if category in CATEGORIES - {"fastener"} else "misc",
        "source": f"From your BOM: {row['link'] or row['name']} (dimensions: {str(raw.get('source', 'web search'))[:200]})",
        "step_file": None,
        "body": {"size": size},
        "pins": [{**p, "position": [0, 0, size[2]], "direction": [0, 0, 1]} for p in pins],
        "notes": str(raw.get("notes", ""))[:400],
        "bom": {"name": row["name"], "link": row["link"], "price": row["price"], "quantity": row["quantity"]},
        "verified": False,
        "verified_by": None,
        "verified_on": None,
    }


def find_part(row: dict) -> dict:
    import os

    prompt, errors = part_prompt(row), []
    searches = []
    if os.environ.get("OPENAI_API_KEY"):
        searches.append(("OpenAI", lambda: search_openai(prompt)))
    keys = [k.strip() for k in [*os.environ.get("GEMINI_API_KEYS", "").split(","), os.environ.get("GEMINI_API_KEY", "")] if k.strip()]
    for i, key in enumerate(dict.fromkeys(keys)):
        searches.append((f"Gemini key {i + 1}", lambda key=key: search_gemini(prompt, key)))
    if not searches:
        raise LookError("the server has no search keys")
    for name, search in searches:
        try:
            return parse_part(search(), row)
        except Exception as e:  # quota, outage, or no usable answer: try the next one
            errors.append(f"{name}: {e if isinstance(e, LookError) else type(e).__name__}")
    raise LookError("couldn't find it (" + "; ".join(errors[:3]) + ")")


# --- storage and jobs ----------------------------------------------------------------------------


def _parts_dir(user_id: str) -> Path:
    assert _dir is not None and re.fullmatch(r"[0-9a-f]{16}", user_id)
    return _dir / ".accounts" / f"parts-{user_id}"


def user_parts(user_id: str) -> list[dict]:
    """The user's BOM parts, in the same shape as parts/*.json."""
    if _dir is None or not re.fullmatch(r"[0-9a-f]{16}", user_id or ""):
        return []
    folder = _parts_dir(user_id)
    out = []
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            out.append(json.loads(f.read_text()))
        except ValueError:
            pass
    return out


def in_library(name: str) -> dict | None:
    """The shared library part a BOM row names (the breadboard planner's matcher), or None."""
    try:
        from .bench import planner

        return planner.library_part(name)
    except Exception:
        return None


def own_part(user_id: str, name: str) -> dict | None:
    """One of the user's BOM parts that a typed name means: same name, or the BOM row it came from."""
    key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    key = re.sub(r"^\d+\s*(x\s+)?", "", key)  # "2 x VL53L0X" -> "vl53l0x"
    if not key:
        return None
    for p in user_parts(user_id):
        names = [p["name"], (p.get("bom") or {}).get("name", "")]
        for n in names:
            n = re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()
            if n and (n == key or key in n or n in key):
                return p
    return None


def _run(job: dict, user_id: str) -> None:
    folder = _parts_dir(user_id)
    folder.mkdir(parents=True, exist_ok=True)

    def one(row: dict) -> None:
        known = in_library(row["name"])
        if known:  # already in the parts library: use it, no lookup
            row.update(status="in_library", part_id=known["id"], part_name=known["name"],
                       size=" × ".join(f"{v:g}" for v in known["body"]["size"]) + " mm")
            return
        try:
            part = find_part(row)
            (folder / f"{part['id']}.json").write_text(json.dumps(part, indent=2))
            row.update(status="added", part_id=part["id"], part_name=part["name"], size=" × ".join(f"{v:g}" for v in part["body"]["size"]) + " mm")
        except Exception as e:
            row.update(status="failed", error=str(e)[:200])

    list(_pool.map(one, job["rows"]))
    job["status"] = "done"


def register_bom_routes(mcp, out_dir: Path) -> None:
    global _dir
    _dir = out_dir

    def fail(message: str, status: int = 400):
        return JSONResponse({"error": message}, status_code=status)

    @mcp.custom_route("/api/bom", methods=["POST"])
    async def upload(request: Request):
        user = user_from_request(request)
        if not user:
            return fail("Log in to upload a BOM.", 401)
        try:
            text = str((await request.json()).get("text", ""))
        except Exception:
            text = ""
        rows = parse_bom(text)
        if not rows:
            return fail("Paste a table or upload a CSV with one part per row (a name, and a link if you have one).")
        with _lock:
            if any(j["user"] == user["id"] and j["status"] == "working" for j in _jobs.values()):
                return fail("Your last BOM is still being looked up. Wait for it to finish.", 409)
            job = {"id": secrets.token_hex(6), "user": user["id"], "status": "working",
                   "rows": [{**r, "status": "looking"} for r in rows]}
            _jobs[job["id"]] = job
        threading.Thread(target=_run, args=(job, user["id"]), daemon=True).start()
        return JSONResponse({"id": job["id"]}, status_code=202)

    @mcp.custom_route("/api/bom/{bom_id}", methods=["GET"])
    async def status(request: Request):
        user = user_from_request(request)
        job = _jobs.get(request.path_params["bom_id"])
        if not user or not job or job["user"] != user["id"]:
            return fail("No such BOM.", 404)
        return JSONResponse({k: job[k] for k in ("id", "status", "rows")})
