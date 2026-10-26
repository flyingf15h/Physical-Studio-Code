"""Redraws the step pictures (step-N.svg) and their numbered markers of the ready-made breadboard guides from
their stored plans, after a change to bench/diagram.py. The step text and 3D models stay as they are.

    uv run python examples/ready_pictures.py
"""

import json
import re
from pathlib import Path

from physical_studio.bench import diagram, planner

READY = Path(__file__).resolve().parent.parent / "physical_studio" / "bench" / "ready"
planner.configure(Path(__file__).resolve().parents[2] / "parts")
uno = planner.LIBRARY["arduino-uno"]

for folder in sorted(READY.iterdir()):
    text = (folder / "build.json").read_text()
    data = json.loads(text)
    plan = (data.get("internal") or {}).get("plan") or {}
    if "scene" not in plan:
        continue  # CAD guides (the pendulum) have rendered pictures
    for i, step in enumerate(data["plan"]["steps"]):
        if not (folder / f"step-{i + 1}.svg").exists():
            continue
        page, markers = diagram.step_svg(plan, i, uno)
        (folder / f"step-{i + 1}.svg").write_text(re.search(r"<svg.*</svg>", page, re.S)[0])
        step["markers"] = [list(m) for m in markers]
    pretty = text.startswith("{\n")  # keep each file's own layout
    (folder / "build.json").write_text(json.dumps(data, indent=1 if pretty else None) + ("\n" if text.endswith("\n") else ""))
    print("redrew", folder.name)
