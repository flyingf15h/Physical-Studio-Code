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


def test_wiring_steps_name_every_connection_pin_to_pin(ready_dir):
    steps = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]["steps"]
    wired = [s for s in steps if any(m[2].startswith("from ") for m in s["markers"])]
    assert wired
    for s in wired:
        lines = [line for line in s["instruction"].splitlines() if "→" in line]
        assert len(lines) == sum(m[2].startswith("from ") for m in s["markers"])  # one line per wire
        assert all(line.endswith(" wire)") and " → " in line for line in lines)
        assert not any(" d13" in line or "_" in line for line in lines)  # printed labels, not pin ids


def test_connection_lines_use_printed_labels_and_colours_with_the_wired_part_first():
    lib = {"as5600-board": {"pins": [{"id": "sda", "label": "SDA"}, {"id": "dir", "label": "DIR"}, {"id": "gnd", "label": "GND"}]},
           "teensy-41": {"pins": [{"id": "d18", "label": "18 / SDA"}]},
           "buck-12v-3v3": {"pins": [{"id": "out_n", "label": "OUT-"}]}}
    by_id = {"enc": {"name": "Cart encoder", "part": "as5600-board"}, "teensy": {"name": "Teensy 4.1", "part": "teensy-41"},
             "reg": {"name": "3.3 V regulator", "part": "buck-12v-3v3"}}
    wires = [{"from": {"placement": "teensy", "pin": "d18"}, "to": {"placement": "enc", "pin": "sda"}, "color": "#3a9d4f"},
             {"from": {"placement": "reg", "pin": "out_n"}, "to": {"placement": "enc", "pin": "gnd"}, "color": "#2b2b2b"},
             {"from": {"placement": "enc", "pin": "dir"}, "to": {"placement": "enc", "pin": "gnd"}, "color": "#2b2b2b"}]
    lines = cad_guide.connection_lines(wires, by_id, lib)
    assert lines == ["Cart encoder SDA → Teensy 4.1 pin 18 / SDA (green wire)",
                     "Cart encoder GND → 3.3 V regulator OUT- (black wire)",
                     "Cart encoder DIR → GND on the same board (black wire)"]
    # the designer's own arrow lines are replaced by the ones from the wires; the sentence stays
    assert cad_guide.wiring_text("Connect the cart encoder.\nSDA → pin 18", lines) == "\n".join(["Connect the cart encoder.", *lines])
    assert cad_guide.wiring_text("Fit the rail.", []) == "Fit the rail."


def test_steps_without_a_check_get_one_from_their_parts_and_wires():
    rail, block = {"id": "rail", "name": "MGN12 rail"}, {"id": "block", "name": "MGN12H block"}
    assert cad_guide.default_check([rail], []).startswith("MGN12 rail sits where the highlighted parts are")
    assert cad_guide.default_check([rail, block], []).startswith("MGN12 rail and MGN12H block sit where")
    assert "Each of the 3 wires goes pin to pin" in cad_guide.default_check([], [{}, {}, {}])
    assert cad_guide.default_check([], [{}]).startswith("The wire goes pin to pin")
    assert cad_guide.default_check([], []) == ""


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


def test_every_wire_can_be_clicked_in_the_picture_and_the_3d_model(ready_dir):
    plan = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]
    wires = plan["wires"]
    assert wires
    for w in wires.values():
        assert w["from"]["part"] and w["from"]["pin"] and w["to"]["part"] and w["to"]["pin"]
        assert len(w["ends"]) == 2 and all(len(p) == 3 for p in w["ends"])
    drawn = [l for s in plan["steps"] for l in s["picture_wires"]]
    assert drawn and {l["id"] for l in drawn} <= set(wires)
    assert all(len(l["points"]) > 2 and all(-0.5 < c < 1.5 for p in l["points"] for c in p) for l in drawn)
    assert all(s["picture_view"] for s in plan["steps"])
