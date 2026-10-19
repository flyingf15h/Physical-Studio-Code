"""Design jobs: a model designs a project from a prompt, using the same tools as the MCP server.

The web app's screen 2 starts a job with POST /api/design and polls GET /api/design/<id>. Each job
runs in a thread with its own Studio (so it never touches the MCP clients' design) and writes to
OUT_DIR/<id>, which the viewer serves as /out/<id>/. Tool calls become progress events: parts found,
parts placed, case built, wires, fit checks, fixes, previews, steps.

Models: OpenAI (Responses API), DeepSeek and Gemini (Chat Completions; Gemini through its
OpenAI-compatible endpoint), all through the OpenAI SDK, or Claude. DESIGN_PROVIDERS (default
"openai,deepseek,gemini,anthropic") is the order to try; providers without a key are skipped, and the
page can pick one to go first ("model" in POST /api/design). If one runs out of quota or goes down
mid-design, the next one carries on from the design's current state; Gemini tries each of its keys
first. Claude only runs when it comes first.

Env: OPENAI_API_KEY, OPENAI_DESIGN_MODEL (gpt-6.1-sol), DEEPSEEK_API_KEY, DEEPSEEK_DESIGN_MODEL
(deepseek-flash, which reads images), GEMINI_API_KEY and/or GEMINI_API_KEYS (k1,k2,... taken in
turn), GEMINI_DESIGN_MODEL (gemini-3.8-flash), ANTHROPIC_API_KEY, DESIGN_MODEL (claude-opus-5-5), DEMO_CODE
(required in x-demo-code when set), DESIGNS_PER_HOUR (per client IP, 4), DESIGN_MAX_RUNNING (1).
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
import openai
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import attachments, checks, library

MODEL = os.environ.get("DESIGN_MODEL", "claude-opus-5-5")
# OpenAI-compatible providers: (label shown on the page, key env, base URL, model env, default model)
COMPATIBLE = {
    "openai": ("OpenAI", "OPENAI_API_KEY", None, "OPENAI_DESIGN_MODEL", "gpt-6.1-sol"),
    "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com", "DEEPSEEK_DESIGN_MODEL", "deepseek-flash"),
    "gemini": (
        "Gemini",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_DESIGN_MODEL",
        "gemini-3.8-flash",
    ),
}
LABELS = {**{name: c[0] for name, c in COMPATIBLE.items()}, "anthropic": "Claude"}
DEFAULT_PROVIDERS = "openai,deepseek,gemini,anthropic"
_gemini_turn = 0


def provider_keys(name: str, rotate: bool = False) -> list[str]:
    """API keys for a provider. Gemini can have several (GEMINI_API_KEYS); with rotate=True (once per
    design) the list starts one key further on each time, so the quota is shared out."""
    global _gemini_turn
    if name == "gemini":
        raw = [*os.environ.get("GEMINI_API_KEYS", "").split(","), os.environ.get("GEMINI_API_KEY", "")]
    else:
        raw = [os.environ.get(COMPATIBLE[name][1] if name in COMPATIBLE else "ANTHROPIC_API_KEY", "")]
    keys = list(dict.fromkeys(k.strip() for k in raw if k.strip()))
    if rotate and len(keys) > 1:
        start = _gemini_turn % len(keys)
        _gemini_turn += 1
        keys = keys[start:] + keys[:start]
    return keys


# Errors worth handing the design to the next provider for: quota, bad key, outages.
SWITCH_ERRORS = (
    openai.RateLimitError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
MAX_TURNS = 80
# A design that fails (an API error, a crash, or no assembly steps when the caller needs them) gets this many
# more tries, each carrying on from the design's state with the failure in the opening message.
DESIGN_RETRIES = int(os.environ.get("DESIGN_RETRIES", "1"))
DESIGNS_PER_HOUR = int(os.environ.get("DESIGNS_PER_HOUR", "4"))
MAX_RUNNING = int(os.environ.get("DESIGN_MAX_RUNNING", "1"))
DESIGN_GUIDE = Path(__file__).with_name("design_guide.md").read_text(encoding="utf-8")
SKIP_TOOLS = {"new_design"}  # the job names the design itself

SYSTEM = """You design hardware projects for Physical Studio out of real, measured parts, plus a
step-by-step IKEA-style assembly guide that a beginner follows while a camera checks each step.

There are two kinds of build. Pick one from the request:
- A case build (a gadget in a box: buttons, LEDs, a small board): a 3D-printed case from
  create_enclosure around the parts.
- A mechanism build (motors, rails, gears, shafts, bearings, arms, frames, sensors on brackets): no
  case. Lay out a base or frame part first, then the moving parts in the order they're assembled,
  then the boards on the base, then wiring. Skip create_enclosure unless the request asks for a box.

Rules:
- Never invent a dimension. Find parts with search_parts and read every number you use from
  get_part. Use only parts in the library. Before deciding a part is missing, search_parts for
  what does its job (frame corners: bracket-2020-corner; shaft to shaft: a coupler; a belt return:
  an idler; a sensor on a rail: its bracket). If it still isn't there, design without it and say so
  in your final message only: steps never "stage" parts loose, never say "not attached", "not
  included" or "layout only", and never tell the builder to drill, file or glue what the model
  lacks. Every step fits a real part for good.
- Lid controls are parts with a lid_mount in get_part (tactile-button-12mm, not push-button-6mm),
  so create_enclosure cuts their holes.
- Units are mm, +Z up. Place the main board at the origin first.
- Parts that poke through the lid (buttons, LEDs) have a lid_mount: place them so their lid mounts
  are level; create_enclosure warns how far to raise any that are low.
- Screw each board's mounting holes with add_fastener, unless check_interference shows a screw
  head clashing with a component; then remove_part that screw.
- Wire every electrical connection with add_wire using pin ids from get_part (black for ground,
  red for power, an inline "220 ohm resistor" on LED anodes). Daisy-chain grounds when the board
  has fewer ground pins than parts need.
- Give every placed part a clear name ("Red LED", "Start button").
- Loop until it's clean: check_interference, check_clearance and render_preview (iso with the lid
  hidden, and top). Fix what they report with move_part (screws move with their board) or
  remove_part (e.g. a screw whose head clashes), and check again.
- Then write the guide with add_step, one part per step, in the order a person really assembles it.
  Case build: base, board, screws, parts under the lid, wiring, close the lid. Mechanism build: base
  or frame, then each moving part in assembly order (rail, carriage, plate, motor, gear, bearings,
  shafts, arms), then sensors and their mounts, then boards, then wiring, power last.
  Every step that adds a part gets motion ({placement, from_offset}) so the viewer moves it into
  place; every screw, set screw or press-fit names its tool in tools; every place a beginner could
  get it backwards (LED legs, gear teeth meshing, a chip facing a magnet, a flange side) gets a
  callout. Wiring goes in its own steps grouped by part ("Wire the motor"), at most 8 wires each.
  A wiring step's text names every connection pin to pin, one per line, with the boards' printed
  pin labels and the wire colour ("Cart encoder SDA → Teensy 4.1 pin 18 / SDA (green wire)"),
  never just "wire the encoder".
  Each step's check line says what a camera sees when it's right: where the part is and which way
  it faces.
- Call check_guide and fix every problem it lists before you export.
- Before exporting, call find_part_looks once with every placed part id that has no `appearance`
  in get_part, so the guide shows the real parts (product photos, colours, metal finishes).
- Finish with export(["glb", "stl", "step"]). Your final message: two sentences on what you built.

The user may attach images (photos, sketches, screenshots) and links. Use them to understand what
they want: the layout, the look, which parts go where. Never take a dimension from an image or a
web page; every number still comes from get_part.

Before each phase, write a short progress note (one sentence, plain words) about what you're
doing and why.

""" + DESIGN_GUIDE


class JobError(Exception):
    pass


class Declined(JobError):
    """The model refused the request: trying again won't help."""


class DesignJob:
    def __init__(self, job_id: str, prompt: str, out_dir: Path, studio_factory, images=(), links=(), context: str = "",
                 need_steps: bool = False):
        self.id = job_id
        self.prompt = prompt
        self.context = context  # more material for the designer, e.g. an imported project's README and parts list
        self.need_steps = need_steps  # the Build page turns the steps into its guide: a design without any has failed
        self.images: list[attachments.Image] = list(images)
        self.link_urls: list[str] = list(links)
        self.links: list[attachments.Link] = []
        self.inputs: list[str] = []  # urls of the attached images, for the page
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
        self.guide_sent_back = False  # export refused once for guide problems; the next try goes through
        self.designer: str | None = None
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
                "designer": self.designer,
                "attachments": {
                    "images": list(self.inputs),
                    "links": [{"url": u, "error": next((k.error for k in self.links if k.url == u), None)} for u in self.link_urls],
                },
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
            guide = s.check_guide()
            if s.design.steps and guide["problems"] and not self.guide_sent_back:  # no steps: export writes default ones
                self.guide_sent_back = True
                self.event("guide", f"Fixing {len(guide['problems'])} guide problem{'s' if len(guide['problems']) != 1 else ''} before export")
                return json.dumps({"exported": False, "why": "The guide isn't ready. Fix these with add_step (or by renaming parts), then export again.",
                                   "problems": guide["problems"], "tips": guide["tips"]})
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
        elif name == "check_guide":
            n = len(result["problems"])
            self.event("guide", "Guide check: " + (f"{n} problem{'s' if n != 1 else ''} to fix" if n else "clean"))
        elif name in ("place_part", "add_fastener"):
            n = len(s.design.placements)
            self.event("place", f"Placed {n} part{'s' if n != 1 else ''}")
        elif name == "create_enclosure" and isinstance(result, dict) and result.get("outer"):
            w, d, h = size = result["outer"]["size"]
            bed = checks.DEFAULT_BED
            fits = all(a <= b for a, b in zip(sorted(size[:2]), sorted(bed[:2]))) and size[2] <= bed[2]
            self.printer = {"ok": fits, "size_mm": size}
            self.event("case", f"Built the case: {w:.0f} × {d:.0f} × {h:.0f} mm")
        elif name == "find_part_looks" and isinstance(result, dict):
            found = [x for x in result.get("looks", []) if "error" not in x]
            photos = sum(1 for x in found if x.get("top_image"))
            self.event("note", f"Looked up how {len(found)} part{'s' if len(found) != 1 else ''} really look"
                       + (f" ({photos} with a product photo)" if photos else ""))
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

    def run(self, tools: list[dict], providers: list[str]):
        self.status = "running"
        title = re.sub(r"\s+", " ", self.prompt).strip()[:60]
        self.studio.new_design(title, self.prompt)
        self.title = title
        self.prepare_attachments()
        failure = None
        for attempt in range(DESIGN_RETRIES + 1):
            try:
                if providers[0] == "anthropic":
                    self.run_claude(tools, failure)
                else:
                    self.run_compatible(tools, providers, failure)
                if not self.exported:
                    self.run_tool("export", {})
                failure = None
                if self.need_steps and not self.studio.design.steps:
                    failure = "the design has no assembly steps (add_step was never called)"
            except Declined as e:
                return self.fail(str(e))
            except Exception as e:
                failure = self.failure_text(e)
            if failure is None:
                self.status = "done"
                return
            if attempt < DESIGN_RETRIES:
                print("[jobs] design", self.id, "failed, trying again:", failure[:300], flush=True)
                self.event("note", f"The design stopped ({failure}); trying again from where it got to.")
                self.exported = self.guide_sent_back = False
        self.fail(failure)

    def failure_text(self, e: Exception) -> str:
        if isinstance(e, openai.APIStatusError):
            return f"{self.designer} API error {e.status_code}: {e.message}"
        if isinstance(e, openai.APIConnectionError):
            return f"Couldn't reach the {self.designer} API"
        if isinstance(e, anthropic.APIStatusError):
            return f"Claude API error {e.status_code}: {e.message}"
        if isinstance(e, anthropic.APIConnectionError):
            return "Couldn't reach the Claude API"
        return str(e) or type(e).__name__

    def run_compatible(self, tools: list[dict], providers: list[str], failure: str | None = None):
        """The OpenAI-compatible providers in turn. failure: why the last attempt stopped (a retry)."""
        # One entry per key, so a rate-limited Gemini key hands over to the next before another provider.
        queue = [(p, key) for p in providers if p in COMPATIBLE for key in provider_keys(p, rotate=True)]
        resume = failure is not None
        while True:
            name, key = queue.pop(0)
            label, _, base_url, model_env, default_model = COMPATIBLE[name]
            self.designer = label
            client = openai.OpenAI(api_key=key, base_url=base_url)
            model = os.environ.get(model_env, default_model)
            loop = self.run_openai if name == "openai" else self.run_chat
            try:
                return loop(client, model, tools, self.opening(resume, failure))
            except SWITCH_ERRORS as e:
                if not queue:
                    raise
                nxt = COMPATIBLE[queue[0][0]][0]
                carries = f"{nxt} carries on with another key" if queue[0][0] == name else f"{nxt} carries on with the design"
                self.event("note", f"{label} stopped ({type(e).__name__}); {carries}.")
                resume = True

    def prepare_attachments(self):
        """Saves the attached images where the page can show them and reads the links."""
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
        if self.images:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(self.images, 1):
            name = f"input-{i}.{ext[img.media_type]}"
            (self.out_dir / name).write_bytes(base64.b64decode(img.data))
            self.inputs.append(f"/out/{self.id}/{name}")
        self.links = [attachments.fetch_link(u) for u in self.link_urls]
        if self.links:
            read = sum(1 for k in self.links if not k.error)
            self.event("note", f"Read {read} of {len(self.links)} link{'s' if len(self.links) != 1 else ''}"
                       + "".join(f"; {k.url}: {k.error}" for k in self.links if k.error))

    def opening_images(self) -> list[attachments.Image]:
        return self.images + [k.image for k in self.links if k.image]

    def opening(self, resume: bool, failure: str | None = None) -> str:
        text = f"Design this project: {self.prompt}"
        if self.context:
            text += f"\n\n{self.context}"
        if self.images:
            text += f"\n\nThe user attached {len(self.images)} image{'s' if len(self.images) != 1 else ''} (below)."
        for k in self.links:
            if k.text:
                text += f"\n\nLinked page {k.url}:\n{k.text}"
            elif k.image:
                text += f"\n\nLinked image {k.url} (below)."
            else:
                text += f"\n\nLinked {k.url} (couldn't read it: {k.error})."
        if resume or failure:
            state = json.dumps(self.studio.describe_design(), default=str)
            why = (f"An earlier attempt at this design stopped partway with this problem: {failure}. Avoid it this time."
                   if failure else "Another model started this design and stopped partway.")
            text += (
                f"\n\n{why} Its current state "
                f"(describe_design):\n{state}\nCarry on from there; don't start over. Make sure the guide has its "
                "add_step steps, check_guide is clean and you finish with export."
            )
        return text

    def tool_output(self, name: str, raw_args: str):
        """Runs a tool call from an OpenAI-style model: a string, or render_preview's PNG as base64."""
        try:
            content = self.run_tool(name, json.loads(raw_args or "{}"))
        except Exception as e:  # tool errors go back to the model so it can correct course
            return f"Error: {e}"
        if isinstance(content, list):
            return next(b["source"]["data"] for b in content if b.get("type") == "image"), True
        return content

    def run_openai(self, client, model: str, tools: list[dict], opening: str):
        """OpenAI's Responses API: the only way its reasoning models take function tools."""
        defs = [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["input_schema"]} for t in tools]
        previous = None
        pending: list[dict] = [{"role": "user", "content": [
            {"type": "input_text", "text": opening},
            *({"type": "input_image", "image_url": img.data_url} for img in self.opening_images()),
        ]}]
        for _ in range(MAX_TURNS):
            response = client.responses.create(
                model=model, instructions=SYSTEM, tools=defs, input=pending, previous_response_id=previous, reasoning={"effort": "medium"}
            )
            previous = response.id
            if response.output_text and response.output_text.strip():
                self.event("note", response.output_text.strip())
            calls = [o for o in response.output if o.type == "function_call"]
            if not calls:
                return
            pending = []
            for call in calls:
                out = self.tool_output(call.name, call.arguments)
                if isinstance(out, tuple):
                    out = [{"type": "input_image", "image_url": f"data:image/png;base64,{out[0]}"}]
                pending.append({"type": "function_call_output", "call_id": call.call_id, "output": out})

    def run_chat(self, client, model: str, tools: list[dict], opening: str):
        """Chat Completions (DeepSeek, Gemini). Tool messages carry text only, so previews follow as a user message."""
        defs = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        messages: list[dict] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": [
            {"type": "text", "text": opening},
            *({"type": "image_url", "image_url": {"url": img.data_url}} for img in self.opening_images()),
        ]}]
        for _ in range(MAX_TURNS):
            choice = client.chat.completions.create(model=model, messages=messages, tools=defs).choices[0]
            msg = choice.message
            if msg.content and msg.content.strip():
                self.event("note", msg.content.strip())
            if choice.finish_reason == "content_filter":
                raise Declined(f"{self.designer} declined this request")
            turn: dict = {"role": "assistant", "content": msg.content or ""}
            if getattr(msg, "reasoning_content", None):
                turn["reasoning_content"] = msg.reasoning_content  # DeepSeek wants it back during tool calls
            calls = msg.tool_calls or []
            if calls:
                turn["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments},
                        # Gemini puts a thought signature here and rejects the next turn without it.
                        **({"extra_content": extra} if (extra := getattr(c, "extra_content", None)) else {}),
                    }
                    for c in calls
                ]
            messages.append(turn)
            if choice.finish_reason == "length":
                messages.append({"role": "user", "content": "Continue."})
                continue
            if not calls:
                return
            images = []
            for call in calls:
                out = self.tool_output(call.function.name, call.function.arguments)
                if isinstance(out, tuple):
                    images.append(out[0])
                    out = "Rendered; the image is in the next message."
                messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
            if images:
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": "The preview you rendered:"},
                    *({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}} for data in images),
                ]})

    def run_claude(self, tools: list[dict], failure: str | None = None):
        self.designer = "Claude"
        client = anthropic.Anthropic()
        messages: list[dict] = [{"role": "user", "content": [
            {"type": "text", "text": self.opening(False, failure)},
            *({"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": img.data}} for img in self.opening_images()),
        ]}]
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
                raise Declined("Claude declined this request")
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

    @staticmethod
    def providers(first: str | None = None) -> list[str]:
        """Providers to try, in order, that have a key set. `first` (the page's pick) goes to the front."""
        order = [p.strip() for p in os.environ.get("DESIGN_PROVIDERS", DEFAULT_PROVIDERS).split(",")]
        available = [p for p in order if p in LABELS and provider_keys(p)]
        if first in available:
            available.remove(first)
            available.insert(0, first)
        return available

    def running(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))

    async def start(self, prompt: str, ip: str, images=(), links=(), model: str | None = None, context: str = "",
                    need_steps: bool = False) -> DesignJob:
        providers = self.providers(model)
        if not providers:
            raise JobError(
                "The server has no OPENAI_API_KEY, DEEPSEEK_API_KEY or GEMINI_API_KEY (or ANTHROPIC_API_KEY); set one to design."
            )
        now = time.time()
        self.recent[ip] = [t for t in self.recent[ip] if now - t < 3600]
        if len(self.recent[ip]) >= DESIGNS_PER_HOUR:
            raise JobError("You've started a lot of designs; try again in a while.")
        if self.running() >= MAX_RUNNING:
            raise JobError("Another design is running; try again in a minute.")
        self.recent[ip].append(now)
        job_id = uuid.uuid4().hex[:10]
        job = DesignJob(job_id, prompt, self.out_dir / job_id, self.studio_factory, images, links, context, need_steps)
        self.jobs[job_id] = job
        tools = await self.tool_defs()
        threading.Thread(target=job.run, args=(tools, providers), daemon=True).start()
        return job


def register_routes(mcp, manager: JobManager, parts_dir: Path):
    def code_ok(request: Request) -> bool:
        code = os.environ.get("DEMO_CODE")
        return not code or request.headers.get("x-demo-code") == code

    @mcp.custom_route("/api/parts", methods=["GET"])
    async def parts(request: Request):
        from .boms import user_parts
        from .users import user_from_request

        lib = library.load_library(parts_dir)
        user = user_from_request(request)
        mine = [{**library.summary(p), "source": p.get("source", ""), "mine": True} for p in user_parts(user["id"])] if user else []
        return JSONResponse(mine + [{**library.summary(p), "source": p.get("source", "")} for p in lib.values()])

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
        try:
            images = attachments.parse_images(body.get("images"))
            links = attachments.parse_links(body.get("links"))
        except attachments.AttachmentError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        model = body.get("model") or None
        if model is not None and model not in LABELS:
            return JSONResponse({"error": f"model must be one of {sorted(LABELS)}"}, status_code=400)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        try:
            job = await manager.start(prompt, ip, images, links, model)
        except JobError as e:
            return JSONResponse({"error": str(e)}, status_code=429 if "try again" in str(e) else 503)
        return JSONResponse({"id": job.id}, status_code=202)

    # Registered before /api/design/{job_id} so "providers" isn't taken for a job id.
    @mcp.custom_route("/api/design/providers", methods=["GET"])
    async def providers(request: Request):
        """The models the page can offer: only providers this server has a key for, default first."""
        return JSONResponse([{"id": p, "label": LABELS[p]} for p in manager.providers()])

    @mcp.custom_route("/api/design/{job_id}", methods=["GET"])
    async def status(request: Request):
        job = manager.jobs.get(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"error": "No such design (the server may have restarted)."}, status_code=404)
        return JSONResponse(job.snapshot())
