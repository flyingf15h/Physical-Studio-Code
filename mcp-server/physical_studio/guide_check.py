"""check_guide: does the assembly guide read like a good IKEA-style manual a camera can check?

Works on the plain Design (steps, placements, wires) and the parts library, so it runs before export
and the design job can fix what it reports. `problems` must be fixed; `tips` make the guide better.
The bar is the hand-made double inverted pendulum guide (viewer/public/double-pendulum): one part per
step, each part moving into place, the tool named for every screw, wiring grouped by part, and a
check line that says what the camera should see.
"""

from __future__ import annotations

import re

from .design import Design
from .electrical import check_wiring

VAGUE_CHECKS = re.compile(r"\b(works?|working|functions?|correct(ly)?|properly|fine|ok(ay)?|done|complete[ds]?|as shown)\b", re.I)
SCREW_WORDS = re.compile(r"\b(screw|bolt|tighten|set screw|nut|hex|allen)", re.I)
ORIENTATION_WORDS = re.compile(r"\b(facing|faces|upside|flange|teeth|polarity|longer leg|flat side|stripe|chip side|pin 1|arrow|towards?)\b", re.I)
ID_LIKE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$")
POWER_PARTS = re.compile(r"psu|adapter|battery|buck|supply", re.I)
# Steps that stand in for a design the job didn't finish ("Stage the X motor... it is not attached: the
# library has no suitable motor mount"), or that send the builder off to make what the model lacks.
PLACEHOLDER = re.compile(r"\b(stage (the|an?|it|them|both)|staged|staging|layout only|incomplete (layout|design|build)|(is|are) not (attached|included|fitted|mounted|fastened|secured)"
                         r"|not yet (fastened|attached|mounted|secured)|(no|without) (suitable|supporting) \w+|the library (has|had) no|(not|isn't) in the library"
                         r"|not (supplied|modell?ed|generated)|unmodell?ed|still (needed|required)|missing (mechanics|parts?|mounts?|hardware)"
                         r"|drill (and file )?(an?|the) (hole|opening)|hand-finish\w*|manual (finishing|mount)|not (yet )?designed)\b", re.I)
MAX_WIRES_PER_STEP = 8
MAX_TEXT = 240


def sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def check_guide(design: Design, library: dict[str, dict] | None = None) -> dict:
    """With the parts library, also checks the wiring itself (electrical.check_wiring: shorts, mixed
    voltages, two same-address I2C devices on one line)."""
    problems: list[str] = []
    tips: list[str] = []
    if library is not None:
        wiring = check_wiring(design, library)
        problems += wiring["problems"]
        tips += wiring["tips"]
    steps = design.steps
    if not steps:
        return {"ok": False, "problems": problems + ["No steps yet: write the guide with add_step (one step per part, then wiring)."], "tips": tips, "stats": {}}

    added_at: dict[str, int] = {}
    for n, s in enumerate(steps, 1):
        for pid in s.add:
            added_at.setdefault(pid, n)
    missing = [pid for pid in design.all_ids() if pid not in added_at]
    if missing:
        problems.append(f"Never added in any step: {missing}. Every part, screw and wire needs a step.")

    names: dict[str, list[str]] = {}
    for p in design.placements.values():
        if p.kind == "part":
            names.setdefault(p.name.strip().lower(), []).append(p.id)
            if ID_LIKE.match(p.name.strip()):
                problems.append(f"{p.id} is named {p.name!r}, which reads like an id. Give it a name a beginner would say.")
    for name, ids in names.items():
        if len(ids) > 1:
            problems.append(f"{ids} share the name {name!r}. Name each copy by where it goes (\"Left distance sensor\").")

    callouts = 0
    for n, s in enumerate(steps, 1):
        where = f"Step {n} ({s.title!r})"
        parts = [design.placements[i] for i in s.add if i in design.placements and design.placements[i].kind == "part"]
        fasteners = [design.placements[i] for i in s.add if i in design.placements and design.placements[i].kind == "fastener"]
        wires = [design.wires[i] for i in s.add if i in design.wires]
        callouts += len(s.callouts)

        if not s.check or not s.check.strip():
            problems.append(f"{where} has no check line. Say what the camera should see when it's right.")
        elif VAGUE_CHECKS.search(s.check) and not wires:
            problems.append(f"{where}'s check {s.check!r} can't be seen in a photo. Describe where the part sits and which way it faces.")
        named = " ".join([s.title, s.text, s.check or ""] + [p.name for p in parts] + [str(c.get("text", "")) for c in s.callouts])
        placeholder = PLACEHOLDER.search(named)
        if placeholder:
            problems.append(f"{where} reads like a placeholder ({placeholder.group(0)!r}): every step fits real parts for good. If the "
                            "library lacks a part the mechanism needs, search_parts for one that does the job (corner brackets, mounts, "
                            "couplers, idlers), give the step a part that fixes it in place, or leave it out of the steps and say so only "
                            "in your final message.")
        if len(s.text) > MAX_TEXT or sentences(s.text) > 3:
            problems.append(f"{where}'s text is too long ({sentences(s.text)} sentences, {len(s.text)} characters). Keep it to one or two short sentences, or split the step.")
        elif sentences(s.text) == 3:
            tips.append(f"{where}'s text has three sentences. Two short ones read better.")

        if len(parts) > 2:
            problems.append(f"{where} adds {len(parts)} parts ({[p.name for p in parts]}). Give each part its own step.")
        elif len(parts) == 2:
            tips.append(f"{where} adds two parts ({parts[0].name}, {parts[1].name}). Fine for a sensor on its bracket; otherwise split it.")
        # One part and its own wires is fine ("press the LED in and wire it"); anything more gets split.
        if parts and wires and (len(parts) > 1 or any(parts[0].id not in (w.a[0], w.b[0]) for w in wires)):
            problems.append(f"{where} mixes parts with wires that aren't theirs. Put that wiring in its own steps, after the parts are in.")

        if (fasteners or SCREW_WORDS.search(s.text)) and not s.tools:
            problems.append(f"{where} screws something in but names no tool. Add tools: [{{\"name\": \"Phillips screwdriver\", \"for\": \"...\"}}].")
        for f in fasteners:
            board = f.attached_to
            if board and added_at.get(board, 0) > n:
                problems.append(f"{where} adds screw {f.id} before its part {board} (step {added_at[board]}).")

        for w in wires:
            for end in (w.a, w.b):
                at = added_at.get(end[0])
                if at is None or at > n:
                    problems.append(f"{where} wires {w.id} to {end[0]}, which isn't in place yet.")
        if len(wires) > MAX_WIRES_PER_STEP:
            problems.append(f"{where} has {len(wires)} wires. Split it, a few wires per step, grouped by part (\"Wire the motor\").")

        moving = {m.get("placement") for m in s.motion}
        stray = moving - set(s.add)
        if stray:
            problems.append(f"{where}'s motion moves {sorted(stray)}, which this step doesn't add.")
        if n > 1 and parts and not (moving & {p.id for p in parts}):
            tips.append(f"{where}: add motion (from_offset, e.g. [0, 0, 40]) so {parts[0].name} moves into place in the viewer.")
        if ORIENTATION_WORDS.search(s.text) and not s.callouts:
            tips.append(f"{where} depends on which way something faces. Add a callout on that part pointing it out.")

    if callouts == 0 and len(steps) > 3:
        tips.append("No callouts anywhere. Add them where a beginner could get it backwards (LED legs, gear teeth, a chip facing a magnet).")

    power = [p for p in design.placements.values() if p.kind == "part" and POWER_PARTS.search(p.part_id + " " + p.name)]
    if power and design.wires and not any(re.search(r"unplug|not plugged|leave .* off|power off", (s.text + " " + (s.check or "")), re.I) for s in steps):
        tips.append("There's a power supply. Tell the builder to keep it unplugged until the wiring is finished.")

    stats = {
        "steps": len(steps),
        "parts": sum(1 for p in design.placements.values() if p.kind == "part"),
        "fasteners": sum(1 for p in design.placements.values() if p.kind == "fastener"),
        "wires": len(design.wires),
        "steps_with_motion": sum(1 for s in steps if s.motion),
        "steps_with_tools": sum(1 for s in steps if s.tools),
        "callouts": callouts,
    }
    return {"ok": not problems, "problems": problems, "tips": tips, "stats": stats}
