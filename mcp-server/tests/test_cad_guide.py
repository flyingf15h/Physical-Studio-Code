import json
import runpy
import sys

import pytest

pytest.importorskip("physical_studio.library")

from test_bench import app, photo  # noqa: E402

from physical_studio.bench import cad_guide, routes, sketch  # noqa: E402


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as m:
        yield m


@pytest.fixture(scope="module")
def ready_dir(tmp_path_factory, monkeypatch_module):
    """The traffic light's CAD design written out as a ready-made hardware build, with sections."""
    prompts = []
    monkeypatch_module.setattr(cad_guide, "ask_firmware", lambda prompt: prompts.append(prompt) or "void setup() {}\nvoid loop() {}")
    monkeypatch_module.setattr(sketch, "compile_result", lambda code, fqbn: ("ok", ""))
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


def test_steps_carry_their_motion_frames_for_the_page(ready_dir):
    folder = ready_dir / "cad-light"
    steps = json.loads((folder / "build.json").read_text())["plan"]["steps"]
    moving = [s for s in steps if s.get("picture_frames")]
    assert moving and all(s["picture_frames"]["src"] == s["picture"].replace(".png", "-motion.png") for s in moving)
    assert all((folder / s["picture_frames"]["file"]).is_file() and s["picture_frames"]["count"] >= 1 for s in moving)


def test_wiring_steps_name_every_connection_pin_to_pin(ready_dir):
    steps = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]["steps"]
    wired = [s for s in steps if any(m[2].startswith("from ") for m in s["markers"])]
    assert wired
    for s in wired:
        lines = [line for line in s["instruction"].splitlines() if "→" in line]
        assert len(lines) == sum(m[2].startswith("from ") for m in s["markers"])  # one line per wire
        assert all(line.endswith(" wire)") and " → " in line for line in lines)
        assert not any(" d13" in line or "_" in line for line in lines)  # printed labels, not pin ids


def test_screws_say_which_mounting_hole_they_go_in(ready_dir):
    steps = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]["steps"]
    screws = [m for s in steps for m in s["markers"] if "screw" in m[1].lower()]
    assert screws and all(m[2] != "the highlighted part in the 3D model" for m in screws)
    holes = [m[2] for m in screws if m[2].endswith("mounting hole")]
    assert holes and len(set(holes)) == len(holes)  # each screw its own corner
    assert cad_guide.default_check([{"id": "s1", "name": "M3 screw"}], [], {"s1": "Uno's front-left mounting hole"}) == \
        "A screw head sits flat in Uno's front-left mounting hole."


def test_the_pin_map_lists_every_wired_board_pin_for_the_firmware(ready_dir):
    plan = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]
    uno = plan["pin_map"][0]  # the controller: most connections first
    assert "Arduino" in uno["board"]
    assert all(e["to"] and e["colour"] for e in uno["pins"])
    assert any("through a" in t and "resistor" in t for e in uno["pins"] for t in e["to"])  # LED anodes via 220 ohm
    listed = sum(len(e["to"]) for b in plan["pin_map"] for e in b["pins"])
    boards = {b["board"] for b in plan["pin_map"]}
    on_boards = sum(1 for w in plan["wires"].values() for end in (w["from"], w["to"]) if end["part"] in boards)
    assert listed == on_boards  # every wire end on a board is listed once


def test_numbered_pins_say_pin_but_supply_pins_do_not():
    assert [cad_guide.pin_name(l) for l in ("18 / SDA", "2 (PWM)", "13", "3.3V", "5V", "3V3", "GND")] == \
        ["pin 18 / SDA", "pin 2 (PWM)", "pin 13", "3.3V", "5V", "3V3", "GND"]


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


def test_the_build_ships_a_compiled_sketch_for_its_board(ready_dir):
    plan = json.loads((ready_dir / "cad-light" / "build.json").read_text())["plan"]
    assert plan["code"].startswith("void setup")
    assert plan["checks"]["compiled"] is True and "Arduino" in plan["checks"]["board"]
    assert not any("compile" in p for p in plan["checks"]["problems"])


PINS = [{"board": "Arduino Uno", "pins": [{"pin": "pin 9", "to": ["Red LED anode"], "colour": "red"}]}]


def test_compile_errors_are_fed_back_up_to_two_times(monkeypatch):
    prompts = []
    monkeypatch.setattr(sketch, "compile_result", lambda code, fqbn: ("ok", "") if "fixed" in code else ("error", "sketch.ino: 'x' was not declared"))

    def ask(prompt):
        prompts.append(prompt)
        return "fixed" if len(prompts) == 3 else "broken"

    code, status, _ = cad_guide.make_firmware("Light", "Blink", "", PINS, "Arduino Uno", "arduino:avr:uno", ask=ask)
    assert (code, status, len(prompts)) == ("fixed", "ok", 3)
    assert "pin 9 -> Red LED anode" in prompts[0] and "was not declared" in prompts[1] and "broken" in prompts[1]
    prompts.clear()
    code, status, msg = cad_guide.make_firmware("Light", "Blink", "", PINS, "Arduino Uno", "arduino:avr:uno", ask=lambda p: prompts.append(p) or "broken")
    assert (code, status, len(prompts)) == ("broken", "error", 3) and "not declared" in msg  # gives up after 2 fixes


def test_a_sketch_that_never_compiles_is_a_problem_and_a_missing_compiler_is_not_a_pass(tmp_path, monkeypatch):
    sys.argv = ["traffic_light.py", str(tmp_path / "export")]
    studio = runpy.run_path("examples/traffic_light.py", run_name="__main__")["studio"]
    monkeypatch.setattr(cad_guide, "ask_firmware", lambda prompt: "broken")
    monkeypatch.setattr(sketch, "compile_result", lambda code, fqbn: ("error", "sketch.ino:1: oops"))
    b = cad_guide.write_build(studio, tmp_path / "bad", "bad", "A light", "s", "2026-10-18T00:00:00+00:00")
    checks = b["plan"]["checks"]
    assert b["plan"]["code"] == "broken" and checks["compiled"] is False and not checks["passed"]
    assert any("doesn't compile" in p and "oops" in p for p in checks["problems"])
    monkeypatch.setattr(sketch, "compile_result", lambda code, fqbn: ("skipped", "arduino-cli is not installed"))
    checks = cad_guide.write_build(studio, tmp_path / "skip", "skip", "A light", "s", "2026-10-18T00:00:00+00:00")["plan"]["checks"]
    assert checks["compiled"] is None and checks["board"]


def test_a_model_failure_or_fenced_reply_and_boardless_designs(tmp_path, monkeypatch):
    def boom(prompt):
        raise RuntimeError("all models busy")

    assert cad_guide.make_firmware("L", "g", "", PINS, "Arduino Uno", "arduino:avr:uno", ask=boom)[:2] == ("", "skipped")
    assert cad_guide.fence_free("Here:\n```cpp\nvoid loop() {}\n```") == "void loop() {}"
    assert sketch.fqbn_of("Teensy 4.1") == "teensy:avr:teensy41" and sketch.fqbn_of("Mystery board") is None
