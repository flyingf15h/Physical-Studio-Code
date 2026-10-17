"""Design jobs: Claude designs a project from a prompt, using the same tools as the MCP server.

The web app's screen 2 starts a job with POST /api/design and polls GET /api/design/<id>. Each job
runs in a thread with its own Studio (so it never touches the MCP clients' design) and writes to
OUT_DIR/<id>, which the viewer serves as /out/<id>/. Tool calls become progress events: parts found,
parts placed, case built, wires, fit checks, fixes, previews, steps.

Env: ANTHROPIC_API_KEY, DESIGN_MODEL (claude-opus-5-5), DEMO_CODE (required in x-demo-code when
set), DESIGNS_PER_HOUR (per client IP, 4), DESIGN_MAX_RUNNING (1).
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import anthropic
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import checks, library

MODEL = os.environ.get("DESIGN_MODEL", "claude-opus-5-5")
MAX_TURNS = 80
DESIGNS_PER_HOUR = int(os.environ.get("DESIGNS_PER_HOUR", "4"))
MAX_RUNNING = int(os.environ.get("DESIGN_MAX_RUNNING", "1"))
SKIP_TOOLS = {"new_design"}  # the job names the design itself

SYSTEM = """You design hardware projects for Physical Studio: a 3D-printed case built around real,
measured parts, plus a step-by-step assembly guide that a beginner follows while a camera checks
each step.

Rules:
- Never invent a dimension. Find parts with search_parts and read every number you use from
  get_part. Use only parts in the library; if the request needs a part that isn't there, design
  without it and say so in your final message.
- Units are mm, +Z up. Place the main board at the origin first.
- Parts that poke through the lid (buttons, LEDs) have a lid_mount: place them so their lid mounts
  are level; create_enclosure warns how far to raise any that are low.
- Screw each board's mounting holes with add_fastener, unless check_interference shows a screw
  head clashing with a component; then leave that hole out.
- Wire every electrical connection with add_wire using pin ids from get_part (black for ground,
  red for power, an inline "220 ohm resistor" on LED anodes). Daisy-chain grounds when the board
  has fewer ground pins than parts need.
- Give every placed part a clear name ("Red LED", "Start button").
- Loop until it's clean: check_interference, check_clearance and render_preview (iso with the lid
  hidden, and top). Fix what they report and check again.
- Then write the guide with add_step: base, board, screws, parts under the lid, wiring (one step
  per part), close the lid. Each step needs a one-sentence check line a camera can verify.
- Finish with export(["glb", "stl", "step"]). Your final message: two sentences on what you built.

Before each phase, write a short progress note (one sentence, plain words) about what you're
doing and why."""


class JobError(Exception):
    pass


class DesignJob:
    def __init__(self, job_id: str, prompt: str, out_dir: Path, studio_factory):
        self.id = job_id
        self.prompt = prompt
        self.out_dir = out_dir
        self.studio = studio_factory()
        self.started = time.time()
        self.status = "queued"
        self.title: str | None = None
        self.events: list[dict] = []
        self.preview: str | None = None
        self.design: str | None = None
        self.error: str | None = None
        self.last_interference: dict | None = None
        self.last_clearance: dict | None = None
        self.printer: dict | None = None
        self.parts_seen: dict[str, str] = {}
        self.previews = 0
        self.exported = False
        self.lock = threading.Lock()

    # --- state for the web page -----------------------------------------------------------

    def event(self, kind: str, text: str, image: str | None = None):
        with self.lock:
            self.events.append({"t": round(time.time() - self.started, 1), "kind": kind, "text": text, **({"image": image} if image else {})})

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "prompt": self.prompt,
                "status": self.status,
                "title": self.title,
                "events": list(self.events),
                "preview": self.preview,
                "design": self.design,
                "checks": {
                    "interference": None
                    if self.last_interference is None
                    else {"ok": self.last_interference["ok"], "problems": len(self.last_interference["problems"])},
                    "clearance": None
                    if self.last_clearance is None
                    else {"ok": self.last_clearance["ok"], "notes": self.last_clearance["notes"]},
                    "printer": self.printer,
                },
                "error": self.error,
            }

    # --- tools --------------------------------------------------------------------------------

    def run_tool(self, name: str, args: dict):
        """Runs one tool on this job's Studio. Returns tool_result content."""
        s = self.studio
        if name == "render_preview":
            png = s.render_preview(args.get("view", "iso"), args.get("step"), args.get("exploded", False), args.get("hide"))
            self.previews += 1
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / f"preview-{self.previews}.png").write_bytes(png)
            url = f"/out/{self.id}/preview-{self.previews}.png"
            self.preview = url
            self.event("preview", f"Rendered the {args.get('view', 'iso')} view", image=url)
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}}]
        if name == "export":
            result = s.export(["glb", "stl", "step"], str(self.out_dir))
            self.exported = True
            self.design = f"out/{self.id}"
            self.event("done", "Exported the case files and the assembly guide")
            return json.dumps(result)

        method = getattr(s, name, None)
        if method is None or name.startswith("_"):
            raise JobError(f"unknown tool {name}")
        result = method(**args)

        if name == "get_part":
            self.parts_seen[result["id"]] = result.get("name", result["id"])
            self.event("parts", "Found parts: " + ", ".join(self.parts_seen.values()))
        elif name in ("place_part", "add_fastener"):
            n = len(s.design.placements)
            self.event("place", f"Placed {n} part{'s' if n != 1 else ''}")
        elif name == "create_enclosure" and isinstance(result, dict) and result.get("outer"):
            w, d, h = size = result["outer"]["size"]
            bed = checks.DEFAULT_BED
            fits = all(a <= b for a, b in zip(sorted(size[:2]), sorted(bed[:2]))) and size[2] <= bed[2]
            self.printer = {"ok": fits, "size_mm": size}
            self.event("case", f"Built the case: {w:.0f} × {d:.0f} × {h:.0f} mm")
        elif name == "add_wire":
            n = len(s.design.wires)
            self.event("wire", f"Wired {n} connection{'s' if n != 1 else ''}")
        elif name == "check_interference":
            before = self.last_interference
            self.last_interference = result
            if result["ok"]:
                if before and not before["ok"]:
                    first = before["problems"][0]
                    what = first.get("issue") or f"{first['a']} hit {first['b']}"
                    self.event("fix", f"Fixed a problem: {what}")
                self.event("check", "Nothing collides")
            else:
                self.event("check", f"{len(result['problems'])} collision{'s' if len(result['problems']) != 1 else ''} to fix")
        elif name == "check_clearance":
            self.last_clearance = result
            self.event("check", "Ports reachable, everything fits the printer" if result["ok"] else "Clearance: " + "; ".join(
                [*(f"{t['a']} / {t['b']} {t['gap_mm']} mm apart" for t in result["too_close"]), *result["notes"]][:3]))
        elif name == "add_step":
            self.event("steps", f"Wrote {len(s.design.steps)} assembly step{'s' if len(s.design.steps) != 1 else ''}")
        return json.dumps(result, default=str)

    # --- the loop ----------------------------------------------------------------------------

    def run(self, tools: list[dict]):
        self.status = "running"
        title = re.sub(r"\s+", " ", self.prompt).strip()[:60]
        self.studio.new_design(title, self.prompt)
        self.title = title
        client = anthropic.Anthropic()
        messages: list[dict] = [{"role": "user", "content": f"Design this project: {self.prompt}"}]
        try:
            for _ in range(MAX_TURNS):
                response = client.beta.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=SYSTEM,
                    tools=tools,
                    messages=messages,
                    thinking={"type": "adaptive", "display": "updates"},
                    output_config={"effort": "high"},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18"],
                    fallbacks="default",
                )
                for block in response.content:
                    note = getattr(block, "thinking", None) if block.type == "thinking" else getattr(block, "text", None) if block.type == "text" else None
                    if note and note.strip():
                        self.event("note", note.strip())
                if response.stop_reason == "refusal":
                    raise JobError("Claude declined this request")
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason == "pause_turn":
                    continue
                if response.stop_reason == "max_tokens":
                    messages.append({"role": "user", "content": "Continue."})
                    continue
                calls = [b for b in response.content if b.type == "tool_use"]
                if not calls:
                    break
                results = []
                for call in calls:
                    try:
                        content = self.run_tool(call.name, dict(call.input))
                        results.append({"type": "tool_result", "tool_use_id": call.id, "content": content})
                    except Exception as e:  # tool errors go back to Claude so it can correct course
                        results.append({"type": "tool_result", "tool_use_id": call.id, "content": f"Error: {e}", "is_error": True})
                messages.append({"role": "user", "content": results})
            if not self.exported:
                self.run_tool("export", {})
            self.status = "done"
        except anthropic.APIStatusError as e:
            self.fail(f"Claude API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            self.fail("Couldn't reach the Claude API")
        except Exception as e:
            self.fail(str(e))

    def fail(self, message: str):
        self.error = message
        self.status = "error"
        self.event("error", message)


class JobManager:
    def __init__(self, out_dir: Path, studio_factory, list_tools):
        self.out_dir = out_dir
        self.studio_factory = studio_factory
        self.list_tools = list_tools  # async () -> MCP tool objects
        self.jobs: dict[str, DesignJob] = {}
        self.recent: dict[str, list[float]] = defaultdict(list)
        self.tools: list[dict] | None = None

    async def tool_defs(self) -> list[dict]:
        if self.tools is None:
            self.tools = [
                {"name": t.name, "description": t.description or "", "input_schema": t.parameters}
                for t in await self.list_tools()
                if t.name not in SKIP_TOOLS
            ]
        return self.tools

    def running(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))

    async def start(self, prompt: str, ip: str) -> DesignJob:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise JobError("The server has no ANTHROPIC_API_KEY; set it to let Claude design.")
        now = time.time()
        self.recent[ip] = [t for t in self.recent[ip] if now - t < 3600]
        if len(self.recent[ip]) >= DESIGNS_PER_HOUR:
            raise JobError("You've started a lot of designs; try again in a while.")
        if self.running() >= MAX_RUNNING:
            raise JobError("Claude is busy with another design; try again in a minute.")
        self.recent[ip].append(now)
        job_id = uuid.uuid4().hex[:10]
        job = DesignJob(job_id, prompt, self.out_dir / job_id, self.studio_factory)
        self.jobs[job_id] = job
        tools = await self.tool_defs()
        threading.Thread(target=job.run, args=(tools,), daemon=True).start()
        return job


def register_routes(mcp, manager: JobManager, parts_dir: Path):
    def code_ok(request: Request) -> bool:
        code = os.environ.get("DEMO_CODE")
        return not code or request.headers.get("x-demo-code") == code

    @mcp.custom_route("/api/parts", methods=["GET"])
    async def parts(request: Request):
        lib = library.load_library(parts_dir)
        return JSONResponse([{**library.summary(p), "source": p.get("source", "")} for p in lib.values()])

    @mcp.custom_route("/api/design", methods=["POST"])
    async def start(request: Request):
        if not code_ok(request):
            return JSONResponse({"error": "Wrong or missing demo code."}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        prompt = str(body.get("prompt", "")).strip()
        if not 3 <= len(prompt) <= 1000:
            return JSONResponse({"error": "Describe the project in 3 to 1000 characters."}, status_code=400)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        try:
            job = await manager.start(prompt, ip)
        except JobError as e:
            return JSONResponse({"error": str(e)}, status_code=429 if "try again" in str(e) else 503)
        return JSONResponse({"id": job.id}, status_code=202)

    @mcp.custom_route("/api/design/{job_id}", methods=["GET"])
    async def status(request: Request):
        job = manager.jobs.get(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"error": "No such design (the server may have restarted)."}, status_code=404)
        return JSONResponse(job.snapshot())
