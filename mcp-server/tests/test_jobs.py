import json
from pathlib import Path
from types import SimpleNamespace as NS

import httpx2
import openai
from starlette.testclient import TestClient

from physical_studio import jobs
from physical_studio.jobs import DesignJob, JobManager
from physical_studio.server import Studio, mcp

REPO = Path(__file__).resolve().parents[2]


def client():
    return TestClient(mcp.http_app(path="/mcp"))


def test_parts_endpoint_lists_the_library():
    parts = client().get("/api/parts").json()
    uno = next(p for p in parts if p["id"] == "arduino-uno")
    assert uno["body_size"] == [68.6, 53.4, 1.6] and uno["category"] == "board"


def test_design_needs_a_key_and_a_prompt(monkeypatch):
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    c = client()
    assert c.post("/api/design", json={"prompt": "x"}).status_code == 400
    r = c.post("/api/design", json={"prompt": "Simon game for an Arduino Uno"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["error"]
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


def test_providers_follow_the_order_and_skip_missing_keys(monkeypatch):
    monkeypatch.setenv("DESIGN_PROVIDERS", "deepseek,openai,anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert JobManager.providers() == ["deepseek", "openai"]


def fn_call(id, name, args):
    return NS(type="function_call", call_id=id, name=name, arguments=json.dumps(args))


def test_openai_designs_then_deepseek_carries_on_when_quota_runs_out(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    quota = openai.RateLimitError("insufficient_quota", response=httpx2.Response(429, request=httpx2.Request("POST", "http://x")), body=None)
    openai_script = [
        NS(id="r1", output_text="Placing the Uno first.", output=[
            fn_call("c1", "get_part", {"part_id": "arduino-uno"}),
            fn_call("c2", "place_part", {"part_id": "arduino-uno", "position": [0, 0, 0], "id": "uno"}),
            fn_call("c3", "create_enclosure", {}),
            fn_call("c4", "render_preview", {"view": "top"}),
        ]),
        quota,
    ]
    deepseek_script = [NS(choices=[NS(finish_reason="stop", message=NS(content="Built a case for the Uno.", tool_calls=None))])]
    seen = []

    def step(script, record):
        seen.append(record)
        nxt = script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    class FakeClient:
        def __init__(self, api_key, base_url):
            self.responses = NS(create=lambda **kw: step(openai_script, ("OpenAI", kw["model"], kw["input"], kw["previous_response_id"])))
            self.chat = NS(completions=NS(create=lambda **kw: step(deepseek_script, ("DeepSeek", kw["model"], kw["messages"], None))))

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    job = DesignJob("job2", "Uno case", tmp_path / "job2", lambda: Studio(REPO / "parts", tmp_path))
    tools = [{"name": "get_part", "description": "", "input_schema": {"type": "object"}}]
    job.run(tools, ["openai", "deepseek"])
    snap = job.snapshot()
    assert snap["status"] == "done", snap["error"]
    assert snap["designer"] == "DeepSeek" and snap["design"] == "out/job2"
    assert [r[:2] for r in seen] == [("OpenAI", "gpt-6.1-sol"), ("OpenAI", "gpt-6.1-sol"), ("DeepSeek", "deepseek-flash")]
    outputs = seen[1][2]  # OpenAI's second turn: the four tool results, chained to the first response
    assert seen[1][3] == "r1" and [o["call_id"] for o in outputs] == ["c1", "c2", "c3", "c4"]
    assert outputs[3]["output"][0]["image_url"].startswith("data:image/png;base64,")
    opening = seen[2][2][1]["content"][0]["text"]  # DeepSeek starts from the design's current state
    assert "Carry on from there" in opening and '"uno"' in opening
    notes = [e["text"] for e in snap["events"] if e["kind"] == "note"]
    assert any("OpenAI stopped" in n and "DeepSeek carries on" in n for n in notes)
    assert (tmp_path / "job2" / "design.steps.json").exists()


def test_deepseek_gets_previews_as_a_user_image(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    calls = [
        NS(id="c0", function=NS(name="place_part", arguments='{"part_id": "arduino-uno", "position": [0, 0, 0], "id": "uno"}')),
        NS(id="c1", function=NS(name="render_preview", arguments='{"view": "top"}')),
    ]
    script = [
        NS(choices=[NS(finish_reason="tool_calls", message=NS(content=None, tool_calls=calls, reasoning_content="r"))]),
        NS(choices=[NS(finish_reason="stop", message=NS(content="Done.", tool_calls=None))]),
    ]
    seen = []

    class FakeClient:
        def __init__(self, api_key, base_url):
            self.chat = NS(completions=NS(create=lambda **kw: (seen.append(json.loads(json.dumps(kw["messages"]))), script.pop(0))[1]))

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    job = DesignJob("job3", "Uno case", tmp_path / "job3", lambda: Studio(REPO / "parts", tmp_path))
    job.run([], ["deepseek"])
    assert job.snapshot()["status"] == "done", job.snapshot()["error"]
    history = seen[1]
    assert history[2]["reasoning_content"] == "r" and [m["role"] for m in history[3:5]] == ["tool", "tool"]
    assert history[5]["role"] == "user" and history[5]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


PNG_1PX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_design_validates_attachments(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    c = client()
    prompt = "Simon game for an Arduino Uno"
    r = c.post("/api/design", json={"prompt": prompt, "images": ["data:text/html;base64,PGI+"]})
    assert r.status_code == 400 and "PNG" in r.json()["error"]
    r = c.post("/api/design", json={"prompt": prompt, "images": [PNG_1PX] * 5})
    assert r.status_code == 400 and "at most 4" in r.json()["error"]
    r = c.post("/api/design", json={"prompt": prompt, "links": ["file:///etc/passwd"]})
    assert r.status_code == 400 and "http" in r.json()["error"]


def test_links_to_private_addresses_are_refused():
    from physical_studio import attachments

    for url in ("http://127.0.0.1:8000/api/parts", "http://169.254.169.254/latest/meta-data", "http://localhost/", "http://10.0.0.1/"):
        link = attachments.fetch_link(url)
        assert link.error and link.text is None and link.image is None, url
    text = attachments.page_text("<html><title>Uno &amp; LEDs</title><script>x()</script><p>Four <b>buttons</b></p></html>")
    assert text == "Title: Uno & LEDs\nUno & LEDs Four buttons"


def test_attached_images_reach_the_model_and_the_page(tmp_path, monkeypatch):
    from physical_studio import attachments

    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setattr(attachments, "fetch_link", lambda url: attachments.Link(url, text="Simon game box, 4 buttons in a square"))
    seen = []

    class FakeClient:
        def __init__(self, api_key, base_url):
            self.responses = NS(create=lambda **kw: (seen.append(kw["input"]), NS(id="r1", output_text="Done.", output=[]))[1])

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    images = attachments.parse_images([PNG_1PX])
    job = DesignJob("job4", "Simon game", tmp_path / "job4", lambda: Studio(REPO / "parts", tmp_path), images, ["https://example.com/simon"])
    job.studio.new_design("x")
    job.studio.place_part("arduino-uno", (0, 0, 0), id="uno")  # so the final export has something
    monkeypatch.setattr(job.studio, "new_design", lambda *a: None)
    job.run([], ["openai"])
    snap = job.snapshot()
    assert snap["status"] == "done", snap["error"]
    content = seen[0][0]["content"]
    assert "attached 1 image" in content[0]["text"] and "Simon game box, 4 buttons" in content[0]["text"]
    assert content[1] == {"type": "input_image", "image_url": PNG_1PX}
    assert snap["attachments"] == {"images": ["/out/job4/input-1.png"], "links": [{"url": "https://example.com/simon", "error": None}]}
    assert (tmp_path / "job4" / "input-1.png").exists()
