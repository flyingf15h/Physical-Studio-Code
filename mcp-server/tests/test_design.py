import asyncio
import json
import shutil
from pathlib import Path

import pytest
from build123d import Vector

pytest.importorskip("physical_studio.library")

from physical_studio.server import Studio, mcp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "schemas" / "steps.schema.json"
SCREW = {
    "id": "test-m3-screw",
    "name": "M3 x 6 screw",
    "category": "fastener",
    "source": "test fixture",
    "step_file": None,
    "body": {"size": [5.5, 5.5, 9.0]},
    "fastener": {"thread": "M3", "length": 6, "head_diameter": 5.5, "head_height": 3.0},
    "mounting_holes": [],
    "connectors": [],
    "keep_out": [],
    "verified": False,
}


@pytest.fixture
def studio(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    shutil.copy(REPO / "parts" / "arduino-uno.json", parts)
    (parts / "test-m3-screw.json").write_text(json.dumps(SCREW))
    s = Studio(parts, tmp_path / "out")
    s.new_design("Uno box")
    s.place_part("arduino-uno", (0, 0, 0), id="uno")
    return s


def test_enclosure_has_standoffs_and_usb_cutout(studio):
    info = studio.create_enclosure()
    assert info["warnings"] == []
    cavity_min = info["cavity"]["min"]
    base = studio.build().pieces["base"].shape
    wall_x = cavity_min[0] - 1  # middle of the 2 mm -x wall
    assert not base.is_inside(Vector(wall_x, 38.1, 7.05))  # USB-B opening
    assert not base.is_inside(Vector(wall_x, 7.6, 7.1))  # barrel jack opening
    assert base.is_inside(Vector(wall_x, 22, 7))  # wall between them stays
    for x, y in [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)]:
        assert base.is_inside(Vector(x + 2.2, y, -2))  # standoff wall
        assert not base.is_inside(Vector(x, y, -2))  # pilot hole


def test_far_connector_warns_instead_of_cutting(studio):
    studio.place_part("arduino-uno", (120, 0, 0), id="uno2")  # its USB faces -x but the -x wall is 120 mm away
    warnings = studio.create_enclosure()["warnings"]
    assert any(w.startswith("uno2/usb_b") for w in warnings)
    assert not any(w.startswith("uno/") for w in warnings)


def test_fasteners_sit_on_the_board(studio):
    out = studio.add_fastener("test-m3-screw", "uno", "h2")
    assert out["position"] == [15.24, 50.8, 1.6]
    with pytest.raises(ValueError):
        studio.add_fastener("test-m3-screw", "uno", "h9")


def test_export_writes_valid_steps_and_named_glb_nodes(studio, tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    for hole in ("h1", "h2", "h3", "h4"):
        studio.add_fastener("test-m3-screw", "uno", hole)
    studio.create_enclosure()
    result = studio.export(["glb", "stl"], str(tmp_path / "export"))
    steps = json.loads((tmp_path / "export" / "design.steps.json").read_text())
    jsonschema.validate(steps, json.loads(SCHEMA.read_text()))
    ids = [p["id"] for p in steps["placements"]]
    assert ids[0] == "base" and ids[-1] == "lid" and "uno" in ids
    glb = (tmp_path / "export" / "design.glb").read_bytes()
    gltf = json.loads(glb[20 : 20 + int.from_bytes(glb[12:16], "little")])
    root = gltf["nodes"][gltf["scenes"][0]["nodes"][0]]
    assert root["name"] == "design"
    assert sorted(gltf["nodes"][i]["name"] for i in root["children"]) == sorted(ids)
    assert any(f.endswith("design-base.stl") for f in result["files"])


def test_add_step_rejects_unknown_and_repeated_ids(studio):
    studio.create_enclosure()
    studio.add_step("Base", "Put the base down.", ["base"])
    with pytest.raises(ValueError):
        studio.add_step("Again", "x", ["base"])
    with pytest.raises(ValueError):
        studio.add_step("Ghost", "x", ["nope"])


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {
        "search_parts", "get_part", "place_part", "create_enclosure", "add_fastener", "add_step",
        "check_interference", "check_clearance", "render_preview", "export",
    } <= names


def test_check_interference_flags_long_screws_and_accepts_standoff_threads(studio):
    for hole in ("h1", "h4"):
        studio.add_fastener("test-m3-screw", "uno", hole)
    studio.create_enclosure()
    result = studio.check_interference()
    assert result["ok"]
    assert {e["why"] for e in result["expected"]} == {"screw threads into its standoff"}
    studio.create_enclosure(standoff_min=3.0, margin=1.0)  # 1.6 mm board + 3 mm standoff < 6 mm screw
    problems = studio.check_interference()["problems"]
    assert any("bottoms out" in p.get("issue", "") for p in problems)


def test_check_clearance_reports_tight_gaps_and_bed_size(studio):
    studio.create_enclosure()
    assert studio.check_clearance()["ok"]
    studio.create_enclosure(margin=0.5)
    assert any(t["b"] == "base" or t["a"] == "base" for t in studio.check_clearance()["too_close"])
    notes = studio.check_clearance(bed=(60, 60, 60))["notes"]
    assert any("print bed" in n for n in notes)


def test_render_preview_returns_png(studio):
    studio.create_enclosure()
    png = studio.render_preview("iso", hide=["lid"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert studio.render_preview("top", step=1)[:4] == b"\x89PNG"
    with pytest.raises(ValueError):
        studio.render_preview("iso", step=99)


LED = {
    "id": "test-led",
    "name": "Test LED",
    "category": "output",
    "source": "test fixture",
    "step_file": None,
    "body": {"size": [5.0, 5.0, 8.6]},
    "connectors": [{"id": "lens", "face": "+z", "center": [2.5, 2.5, 8.6], "size": [5.0, 5.0]}],
    "pins": [
        {"id": "anode", "label": "+", "position": [3.77, 2.5, -1.0], "direction": [0, 0, -1]},
        {"id": "cathode", "label": "-", "position": [1.23, 2.5, -1.0], "direction": [0, 0, -1]},
    ],
    "verified": False,
}


def test_wires_route_between_pins_and_export(studio, tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    (studio.parts_dir / "test-led.json").write_text(json.dumps(LED))
    studio.place_part("test-led", (30, 25, 14), id="led")
    out = studio.add_wire("uno", "d8", "led", "anode", color="red", inline="220 ohm resistor")
    assert out["id"] == "wire-led-anode" and out["length_mm"] > 10
    studio.add_wire("led", "cathode", "uno", "gnd3", color="black")
    with pytest.raises(ValueError, match="pins: anode, cathode"):
        studio.add_wire("uno", "d9", "led", "leg")
    studio.create_enclosure()
    assert studio.check_interference()["ok"]  # wires are left out of fit checks
    studio.export(["glb"], str(tmp_path / "w"))
    steps = json.loads((tmp_path / "w" / "design.steps.json").read_text())
    jsonschema.validate(steps, json.loads(SCHEMA.read_text()))
    wire = next(p for p in steps["placements"] if p["id"] == "wire-led-anode")
    assert wire["kind"] == "wire" and wire["from"] == {"placement": "uno", "pin": "d8"}
    assert wire["inline"] == "220 ohm resistor"
    assert any(s["title"] == "Wire the Test LED" for s in steps["steps"])
    assert studio.render_preview("iso", hide=["lid"])[:4] == b"\x89PNG"


BUTTON = {
    "id": "test-button",
    "name": "Test button",
    "category": "input",
    "source": "test fixture (12x12 tactile, 3.5 mm housing + plunger to 7.3 mm)",
    "step_file": None,
    "body": {"size": [12.0, 12.0, 7.3]},
    "envelope": {"min": [-0.5, 0.0, -3.5], "max": [12.5, 12.0, 7.3]},
    "lid_mount": {"z": 3.5},
    "connectors": [{"id": "plunger", "face": "+z", "center": [6.0, 6.0, 7.3], "size": [7.0, 7.0], "protrusion": 0.0}],
    "verified": False,
}


def test_lid_mounted_parts_poke_through_the_lid(studio):
    (studio.parts_dir / "test-button.json").write_text(json.dumps(BUTTON))
    studio.place_part("test-button", (20, 20, 20), id="btn-hi")
    studio.place_part("test-button", (40, 20, 18), id="btn-lo")  # 2 mm too low
    info = studio.create_enclosure()
    assert info["cavity"]["max"][2] == 23.5  # lid underside at btn-hi's housing top (20 + 3.5)
    assert any(w.startswith("btn-lo") and "z + 2.00" in w for w in info["warnings"])
    studio.place_part("test-button", (40, 20, 20), id="btn-ok")
    studio.design.placements.pop("btn-lo")
    assert studio.check_interference()["ok"]
    assert studio.check_clearance()["ok"]
    built = studio.build()
    lid = built.pieces["lid"].shape
    plunger_in_lid = Vector(26, 26, 24.5)  # inside the 2 mm lid, over btn-hi's plunger
    assert not lid.is_inside(plunger_in_lid)  # the opening is cut
    assert lid.is_inside(Vector(20.5, 20.5, 24.5))  # the housing's corner stays under solid lid
    assert built.cavity[1][2] + 2.0 < 20 + 7.3 + 0.01  # plunger top (27.3) reaches above the lid top (25.5)


def test_connector_clearance_overrides_the_cutout_clearance(studio):
    tight = json.loads(json.dumps(BUTTON))
    tight["id"] = "test-button-tight"
    tight["connectors"][0]["clearance"] = 0.1
    (studio.parts_dir / "test-button.json").write_text(json.dumps(BUTTON))
    (studio.parts_dir / "test-button-tight.json").write_text(json.dumps(tight))
    studio.place_part("test-button", (20, 20, 20), id="btn")
    studio.place_part("test-button-tight", (50, 20, 20), id="btn-tight")
    studio.create_enclosure()
    lid = studio.build().pieces["lid"].shape
    # Plungers are 7 mm wide: the default 0.5 mm per side opens to 8 mm, 0.1 mm to 7.2 mm.
    assert not lid.is_inside(Vector(26 + 3.8, 26, 24.5))
    assert lid.is_inside(Vector(56 + 3.8, 26, 24.5))


def test_move_part_takes_its_screws_and_remove_part_cleans_up(studio):
    shutil.copy(REPO / "parts" / "led-5mm.json", studio.parts_dir)
    studio.place_part("led-5mm", (30, 20, 20), id="led")
    studio.add_fastener("test-m3-screw", "uno", "h1", id="screw-h1")
    studio.add_fastener("test-m3-screw", "uno", "h2", id="screw-h2")
    studio.add_wire("led", "anode", "uno", "d8", id="w-led")
    studio.add_step("Board", "Drop in the Uno.", ["uno", "screw-h1", "screw-h2"])
    studio.add_step("LED", "Add the LED.", ["led", "w-led"])
    before = studio.design.placements["screw-h1"].position
    studio.move_part("uno", (5, 0, 0))
    after = studio.design.placements["screw-h1"].position
    assert after[0] == pytest.approx(before[0] + 5) and after[1:] == before[1:]
    assert studio.remove_part("screw-h2") == {"removed": ["screw-h2"]}
    assert studio.design.steps[0].add == ["uno", "screw-h1"]
    assert studio.remove_part("led")["removed"] == ["led", "w-led"]
    assert [s.title for s in studio.design.steps] == ["Board"]  # the LED step was left empty
    with pytest.raises(ValueError, match="remove it and add it again"):
        studio.move_part("screw-h1", (0, 0, 0))
