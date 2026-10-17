"""Part looks found online: set_part_look fetches a product photo for a part's top face.

The designing AI looks a part up (manufacturer or shop page), then passes the URL of a flat top-view
photo. The server downloads it with care, since anyone with a key can ask it to: http(s) only, no
private or local addresses (checked on every redirect), at most 4 MB, and it must decode as an image.
The photo is trimmed to the part (background removed) and kept with the design, not the library.
"""

from __future__ import annotations

import io
import ipaddress
import json
import os
import re
import socket
import urllib.parse
import urllib.request

from PIL import Image, ImageChops

MAX_BYTES = 4 * 1024 * 1024
MAX_SIDE = 1024
TIMEOUT_S = 10
MAX_REDIRECTS = 3


class LookError(ValueError):
    pass


def _check_host(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LookError("image_url must be an http(s) URL")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise LookError(f"can't resolve {parts.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise LookError("image_url must point at a public address")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # followed by hand in fetch_image, so each hop's host is checked


_opener = urllib.request.build_opener(_NoRedirect)


def fetch_image(url: str) -> Image.Image:
    for _ in range(MAX_REDIRECTS + 1):
        _check_host(url)
        req = urllib.request.Request(url, headers={"User-Agent": "PhysicalStudio/1.0 (part photo lookup)"})
        try:
            res = _opener.open(req, timeout=TIMEOUT_S)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise LookError(f"image download failed: HTTP {e.code}") from e
        except OSError as e:
            raise LookError(f"image download failed: {e}") from e
        data = res.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise LookError("image is larger than 4 MB")
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as e:
            raise LookError("that URL isn't an image (use the photo file itself, e.g. .jpg/.png)") from e
        return trim(img.convert("RGB"))
    raise LookError("too many redirects")


def trim(img: Image.Image, tolerance: int = 40) -> Image.Image:
    """Crop away a plain background (the colour of the top-left corner), then cap the size."""
    background = Image.new("RGB", img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, background).convert("L").point(lambda v: 255 if v > tolerance else 0)
    box = diff.getbbox()
    if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.2 * img.size[0] * img.size[1]:
        img = img.crop(box)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


# --- finding a look on the web (find_part_looks) ---------------------------------------------------
# For designers that can't browse (the site's own design jobs) and for any MCP client: the server
# searches the web itself. OpenAI's web search first (OPENAI_API_KEY, LOOK_MODEL), then Gemini with
# Google Search grounding on each of the team's keys (GEMINI_API_KEYS).

LOOK_FIELDS = ("color", "metallic", "roughness", "top_image_url", "source")


def look_prompt(part: dict) -> str:
    size = " x ".join(f"{v:g}" for v in part["body"]["size"])
    return (
        "Find what this real part looks like, for a realistic 3D render.\n"
        f"Part: {part['name']} ({part['category']}), {size} mm.\n"
        f"Notes: {part.get('notes', '')}\nDimension source: {part.get('source', '')}\n\n"
        "Answer with one JSON object and nothing else:\n"
        '{"color": "#rrggbb, the main colour you see (a PCB\'s solder mask, the metal, the plastic)",'
        ' "metallic": 0..1 (bare steel about 0.9, PCB or plastic 0),'
        ' "roughness": 0..1 (polished 0.2, PCB 0.5, matte plastic 0.8),'
        ' "top_image_url": "direct URL of an image file (.jpg/.png/.webp) showing the part straight from'
        ' above, a product photo from the manufacturer or a shop; null if you can\'t find one",'
        ' "source": "URL of the page you took this from"}'
    )


def parse_look(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LookError("the search didn't return a look")
    raw = json.loads(text[start : end + 1])
    look = {k: raw.get(k) for k in LOOK_FIELDS if raw.get(k) not in (None, "", "null")}
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(look.get("color", ""))):
        look.pop("color", None)
    for k in ("metallic", "roughness"):
        if k in look:
            try:
                look[k] = min(1.0, max(0.0, float(look[k])))
            except (TypeError, ValueError):
                look.pop(k)
    return look


def search_openai(prompt: str) -> str:
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90)
    model = os.environ.get("LOOK_MODEL", os.environ.get("OPENAI_DESIGN_MODEL", "gpt-6.1-sol"))
    return client.responses.create(model=model, tools=[{"type": "web_search"}], input=prompt).output_text


def search_gemini(prompt: str, key: str) -> str:
    model = os.environ.get("GEMINI_LOOK_MODEL", os.environ.get("GEMINI_DESIGN_MODEL", "gemini-3.8-flash"))
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=90) as res:
        data = json.loads(res.read())
    return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])


def find_look(part: dict) -> dict:
    """The part's look from a web search: color, metallic, roughness, top_image_url, source."""
    prompt, errors = look_prompt(part), []
    searches = []
    if os.environ.get("OPENAI_API_KEY"):
        searches.append(("OpenAI", lambda: search_openai(prompt)))
    keys = [k.strip() for k in [*os.environ.get("GEMINI_API_KEYS", "").split(","), os.environ.get("GEMINI_API_KEY", "")] if k.strip()]
    for i, key in enumerate(dict.fromkeys(keys)):
        searches.append((f"Gemini key {i + 1}", lambda key=key: search_gemini(prompt, key)))
    if not searches:
        raise LookError("the server has no OPENAI_API_KEY or GEMINI_API_KEY(S) to search with")
    for name, search in searches:
        try:
            return parse_look(search())
        except Exception as e:  # quota, outage, unparseable answer: try the next one
            errors.append(f"{name}: {type(e).__name__}")
    raise LookError("couldn't look it up (" + "; ".join(errors) + ")")
