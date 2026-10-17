from pathlib import Path

from starlette.testclient import TestClient

from physical_studio.jobs import DesignJob
from physical_studio.server import Studio, mcp

REPO = Path(__file__).resolve().parents[2]


def client():
    return TestClient(mcp.http_app(path="/mcp"))


def test_parts_endpoint_lists_the_library():
    parts = client().get("/api/parts").json()
    uno = next(p for p in parts if p["id"] == "arduino-uno")
    assert uno["body_size"] == [68.6, 53.4, 1.6] and uno["category"] == "board"


def test_design_needs_a_key_and_a_prompt(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = client()
    assert c.post("/api/design", json={"prompt": "x"}).status_code == 400
    r = c.post("/api/design", json={"prompt": "Simon game for an Arduino Uno"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["error"]
    assert c.get("/api/design/nope").status_code == 404


def test_tool_calls_become_progress_events(tmp_path):
    job = DesignJob("job1", "Uno case", tmp_path / "job1", lambda: Studio(REPO / "parts", tmp_path))
    job.studio.new_design("Uno case")
    job.run_tool("get_part", {"part_id": "arduino-uno"})
    job.run_tool("place_part", {"part_id": "arduino-uno", "position": [0, 0, 0], "id": "uno"})
    job.run_tool("create_enclosure", {})
    job.run_tool("check_interference", {})
    image = job.run_tool("render_preview", {"view": "top"})
    job.run_tool("export", {})
    snap = job.snapshot()
    kinds = [e["kind"] for e in snap["events"]]
    assert kinds == ["parts", "place", "case", "check", "preview", "done"]
    assert snap["checks"]["printer"]["ok"] and snap["checks"]["interference"]["ok"]
    assert image[0]["type"] == "image" and snap["preview"] == "/out/job1/preview-1.png"
    assert (tmp_path / "job1" / "preview-1.png").exists() and (tmp_path / "job1" / "design.steps.json").exists()
    assert snap["design"] == "out/job1"
