"""Rebuilds the 3D models (final.glb, step-N.glb) of the ready-made breadboard guides from their stored
scenes, after a change to bench/geometry.py or bench/looks.py. The step text and pictures stay as they are.

    uv run python examples/ready_models.py
"""

import json
from pathlib import Path

from physical_studio.bench.geometry import build
from physical_studio.bench.planner import step_models
from physical_studio.bench.spec import Spec, validate

READY = Path(__file__).resolve().parent.parent / "physical_studio" / "bench" / "ready"

for folder in sorted(READY.iterdir()):
    data = json.loads((folder / "build.json").read_text())
    plan = (data.get("internal") or {}).get("plan") or {}
    if "scene" not in plan:
        continue  # CAD guides (the pendulum) have their own script
    scene = validate(Spec.model_validate(plan["scene"]))
    (folder / "final.glb").write_bytes(build(scene)[0])
    for n, m in enumerate(step_models(scene, plan["steps"], validate, build), 1):
        if m and (folder / f"step-{n}.glb").exists():
            (folder / f"step-{n}.glb").write_bytes(m["glb"])
    print("rebuilt", folder.name)
