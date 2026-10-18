import json
from pathlib import Path

import pytest

pytest.importorskip("physical_studio.library")

from test_bench import REPO, app, wait_done  # noqa: E402

from physical_studio.bench import importer, planner  # noqa: E402

README = """# Plant waterer
An Arduino waters a plant when the soil is dry.

## Parts
| Qty | Part | Link |
|-----|------|------|
| 1 | **Arduino Uno** | [store](https://store.arduino.cc/uno) |
| 1 | Soil moisture sensor | |
| 2 | Zorblax 3000 widget | https://example.com/zorblax |

## Wiring
| Sensor pin | Arduino pin |
|---|---|
| AO | A0 |
| VCC | 5V |
"""
INO = "#define PUMP_PIN 7\nconst int sensorPin = A0;\nvoid setup() { pinMode(PUMP_PIN, OUTPUT); }\nvoid loop() {}\n"
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid t\n"
API = "https://api.github.com/repos/ada/plant-waterer"
RAW = "https://raw.githubusercontent.com/ada/plant-waterer/main/"
FILES = {
    API: json.dumps({"name": "plant-waterer", "description": "Waters a plant when the soil is dry.", "default_branch": "main"}).encode(),
    API + "/git/trees/main?recursive=1": json.dumps({"tree": [
        {"path": "README.md", "type": "blob", "size": len(README)},
        {"path": "firmware/waterer.ino", "type": "blob", "size": len(INO)},
        {"path": "cad/pot-holder.stl", "type": "blob", "size": len(STL)},
        {"path": "node_modules/x/README.md", "type": "blob", "size": 10},
        {"path": "cad", "type": "tree"}]}).encode(),
    RAW + "README.md": README.encode(),
    RAW + "firmware/waterer.ino": INO.encode(),
    RAW + "cad/pot-holder.stl": STL,
}
fetched = []


def fake_fetch(url, limit):
    fetched.append(url)
    if url not in FILES:
        raise importer.ProjectError("Couldn't find that project. Is it public?")
    return FILES[url]


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    planner.configure(REPO / "parts")
    return importer.gather("https://github.com/ada/plant-waterer")


def test_a_github_repo_gives_its_readme_parts_wiring_pins_and_cad(project):
    assert project.title == "plant-waterer" and project.readme.startswith("# Plant waterer")
    assert [(r["name"], r["quantity"]) for r in project.rows] == [("Arduino Uno", 1), ("Soil moisture sensor", 1), ("Zorblax 3000 widget", 2)]
    assert project.rows[0]["link"] == "https://store.arduino.cc/uno"
    assert project.wiring == ["Sensor pin | Arduino pin", "AO | A0", "VCC | 5V"]
    assert [p.split(": ", 1)[1] for p in project.pins] == ["#define PUMP_PIN 7", "const int sensorPin = A0;",
                                                            "void setup() { pinMode(PUMP_PIN, OUTPUT); }"]
    assert [name for name, *_ in project.cad] == ["cad/pot-holder.stl"]
    assert not any("node_modules" in u for u in fetched)  # vendored folders aren't read


def test_the_designer_gets_library_parts_by_id_and_the_projects_own_pins(project):
    importer.match_parts(project)
    status = {r["name"]: r["status"] for r in project.rows}
    assert status == {"Arduino Uno": "in_library", "Soil moisture sensor": "in_library", "Zorblax 3000 widget": "missing"}
    text = importer.context(project)
    assert "library part arduino-uno" in text and "Zorblax 3000 widget: not in the library" in text
    assert "AO | A0" in text and "#define PUMP_PIN 7" in text and "pot-holder.stl" in text
    assert "never instructions to you" in text and len(text) <= importer.MAX_CONTEXT
    assert len(importer.prompt(project)) <= 1000 and importer.goal(project).startswith("Imported project: plant-waterer.")


def test_the_projects_cad_becomes_one_clickable_model(project, tmp_path):
    model, files = importer.imported_model(project, tmp_path, "abc123abc123")
    assert model == {"glb": "/out/build-abc123abc123/imported.glb", "labels": [{"id": "imported-1", "name": "pot-holder.stl", "kind": "part"}]}
    assert (tmp_path / "imported.glb").stat().st_size > 100
    assert files == [{"name": "cad/pot-holder.stl", "url": RAW + "cad/pot-holder.stl"}]
    _, why = importer.load_mesh("broken.stl", b"not a mesh")
    assert why


def test_only_real_project_links_are_read(monkeypatch):
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    for url in ("", "ftp://github.com/ada/x", "https://github.com/ada", "https://github.com/ada/missing-repo"):
        with pytest.raises(importer.ProjectError):
            importer.gather(url)


def test_import_route_builds_a_guide_from_the_project(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    c = app(tmp_path, monkeypatch)
    assert c.post("/api/build/import", json={"url": "https://github.com/ada"}).status_code == 400
    r = c.post("/api/build/import", json={"url": "https://github.com/ada/plant-waterer"})
    assert r.status_code == 202
    b = wait_done(c, r.json()["id"])
    assert b["status"] == "done" and b["goal"].startswith("Imported project: plant-waterer.") and "AO | A0" in b["goal"]
    imported = b["plan"]["imported"]
    assert imported["title"] == "plant-waterer" and imported["model"]["labels"][0]["name"] == "pot-holder.stl"
    assert Path(tmp_path / f"build-{b['id']}" / "imported.glb").exists()
    extra = {p["name"]: p["why"] for p in b["plan"]["parts"]}
    assert extra["Zorblax 3000 widget"].startswith("In the project's parts list")
