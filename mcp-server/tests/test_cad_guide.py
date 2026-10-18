import json
import runpy
import sys

import pytest

pytest.importorskip("physical_studio.library")

from test_bench import app, photo  # noqa: E402

from physical_studio.bench import cad_guide, routes  # noqa: E402


@pytest.fixture(scope="module")
def ready_dir(tmp_path_factory):
    """The traffic light's CAD design written out as a ready-made hardware build, with sections."""
    sys.argv = ["traffic_light.py", str(tmp_path_factory.mktemp("export"))]
    studio = runpy.run_path("examples/traffic_light.py", run_name="__main__")["studio"]
    for n, step in enumerate(studio.design.steps, 1):
        step.section = "Case and board" if n <= 3 else "Lights and wiring"
    ready = tmp_path_factory.mktemp("ready")
    cad_guide.write_build(studio, ready / "cad-light", "cad-light", "A traffic light", "Three LEDs and a button in a printed case.", "2026-10-18T00:00:00+00:00")
    return ready


def test_a_cad_design_becomes_a_build_with_sections_pictures_and_models(ready_dir):
    folder = ready_dir / "cad-light"
    b = json.loads((folder / "build.json").read_text())
    plan = b["plan"]
    assert plan["kind"] == "cad" and b["internal"]["plan"]["kind"] == "cad" and plan["summary"].startswith("Three LEDs")
    steps = plan["steps"]
    assert [s["section"] for s in steps[:4]] == ["Case and board"] * 3 + ["Lights and wiring"]
    s1 = steps[0]
    assert s1["picture"] == "/out/build-cad-light/step-01.png" and s1["model"]["glb"] == "/out/build-cad-light/step-1.glb"
    assert (folder / "step-01.png").stat().st_size > 1000 and (folder / "step-1.glb").stat().st_size > 1000
    assert len(steps[-1]["model"]["labels"]) >= len(steps[0]["model"]["labels"])  # the model grows step by step
    wires = [m for s in steps for m in s["markers"] if m[2].startswith("from ")]
    assert wires and all(" to " in m[2] for m in wires)
    assert any(s["tools"] for s in steps) and plan["parts"] and plan["part_guide"]


def test_cad_builds_are_checked_against_their_reference_picture_and_take_a_new_summary(ready_dir, tmp_path, monkeypatch):
    seen = {}

    def fake_check(plan, i, photos, note, folder):
        seen.update(kind=plan["kind"], reference=(folder / plan["steps"][i]["reference"]).exists())
        return {"verdict": {"observation": "The red LED is in.", "status": "problem", "problem": "It is backwards.", "fix": "Turn it around.",
                            "next": "Turn the red LED around, then check again.", "confidence": 0.8}, "model": None, "guide": {}}

    monkeypatch.setattr(cad_guide, "commit_step", fake_check)
    monkeypatch.setattr(routes, "READY_DIR", ready_dir)
    c = app(tmp_path, monkeypatch)
    ready = c.get("/api/build/cad-light").json()
    assert ready["ready"] and ready["plan"]["kind"] == "cad"
    assert c.post("/api/build/cad-light/summary", json={"summary": "Mine now"}).status_code == 403
    bid = c.post("/api/build/cad-light/copy").json()["id"]
    r = c.post(f"/api/build/{bid}/commit", json={"step": 1, "photos": [photo()]})
    assert r.status_code == 200 and r.json()["verdict"]["next"].startswith("Turn") and seen == {"kind": "cad", "reference": True}

    assert c.post(f"/api/build/{bid}/summary", json={"summary": "x"}).status_code == 400
    assert c.post(f"/api/build/{bid}/summary", json={"summary": "y" * 300}).status_code == 400
    r = c.post(f"/api/build/{bid}/summary", json={"summary": "  My   light for the\nfront window.  "})
    assert r.status_code == 200 and r.json() == {"summary": "My light for the front window."}
    assert c.get(f"/api/build/{bid}").json()["plan"]["summary"] == "My light for the front window."
    assert json.loads((tmp_path / f"build-{bid}" / "build.json").read_text())["plan"]["summary"] == "My light for the front window."
