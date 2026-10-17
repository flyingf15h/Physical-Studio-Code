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
