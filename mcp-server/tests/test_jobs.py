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
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    c = client()
    assert c.post("/api/design", json={"prompt": "x"}).status_code == 400
    r = c.post("/api/design", json={"prompt": "Traffic light for an Arduino Uno"})
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


def test_the_page_can_pick_which_model_goes_first(monkeypatch):
    monkeypatch.delenv("DESIGN_PROVIDERS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("GEMINI_API_KEYS", "g1, g2")
    for key in ("DEEPSEEK_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert JobManager.providers() == ["openai", "gemini"]
    assert JobManager.providers("gemini") == ["gemini", "openai"]
    assert JobManager.providers("deepseek") == ["openai", "gemini"]  # no key: ignored
    c = client()
    assert c.get("/api/design/providers").json() == [{"id": "openai", "label": "OpenAI"}, {"id": "gemini", "label": "Gemini"}]
    r = c.post("/api/design", json={"prompt": "Traffic light for an Arduino Uno", "model": "gpt-2"})
    assert r.status_code == 400 and "model must be one of" in r.json()["error"]


def test_gemini_keys_take_turns_and_a_rate_limited_key_hands_over(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "g1,g2")
    monkeypatch.setenv("GEMINI_API_KEY", "g1")  # duplicates count once
    monkeypatch.setattr(jobs, "_gemini_turn", 0)
    assert jobs.provider_keys("gemini") == ["g1", "g2"]
    assert jobs.provider_keys("gemini", rotate=True) == ["g1", "g2"]
    assert jobs.provider_keys("gemini", rotate=True) == ["g2", "g1"]
    limited = openai.RateLimitError("RESOURCE_EXHAUSTED", response=httpx2.Response(429, request=httpx2.Request("POST", "http://x")), body=None)
    used = []
    place = NS(id="c0", function=NS(name="place_part", arguments='{"part_id": "arduino-uno", "position": [0, 0, 0], "id": "uno"}'),
               extra_content={"google": {"thought_signature": "sig"}})
    sent = []
    script = [
        NS(choices=[NS(finish_reason="tool_calls", message=NS(content=None, tool_calls=[place]))]),
        NS(choices=[NS(finish_reason="stop", message=NS(content="Done.", tool_calls=None))]),
    ]

    class FakeClient:
        def __init__(self, api_key, base_url):
            def create(**kw):
                used.append((api_key, base_url, kw["model"]))
                if api_key == "g1":
                    raise limited
                sent.append(list(kw["messages"]))
                return script.pop(0)

            self.chat = NS(completions=NS(create=create))

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    job = DesignJob("job3", "Uno case", tmp_path / "job3", lambda: Studio(REPO / "parts", tmp_path))
    job.run([{"name": "get_part", "description": "", "input_schema": {"type": "object"}}], ["gemini"])
    snap = job.snapshot()
    assert snap["status"] == "done", snap["error"]
    assert snap["designer"] == "Gemini"
    assert [u[0] for u in used] == ["g1", "g2", "g2"]
    assert used[0][1].startswith("https://generativelanguage.googleapis.com/") and used[0][2] == "gemini-3.8-flash"
    echoed = next(m for m in sent[1] if m.get("tool_calls"))["tool_calls"][0]
    assert echoed["extra_content"] == {"google": {"thought_signature": "sig"}}  # Gemini needs it back
    assert any("Gemini carries on with another key" in e["text"] for e in snap["events"] if e["kind"] == "note")


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
    prompt = "Traffic light for an Arduino Uno"
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
    monkeypatch.setattr(attachments, "fetch_link", lambda url: attachments.Link(url, text="Traffic light box, 3 LEDs in a column"))
    seen = []

    class FakeClient:
        def __init__(self, api_key, base_url):
            self.responses = NS(create=lambda **kw: (seen.append(kw["input"]), NS(id="r1", output_text="Done.", output=[]))[1])

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    images = attachments.parse_images([PNG_1PX])
    job = DesignJob("job4", "Traffic light", tmp_path / "job4", lambda: Studio(REPO / "parts", tmp_path), images, ["https://example.com/traffic-light"])
    job.studio.new_design("x")
    job.studio.place_part("arduino-uno", (0, 0, 0), id="uno")  # so the final export has something
    monkeypatch.setattr(job.studio, "new_design", lambda *a: None)
    job.run([], ["openai"])
    snap = job.snapshot()
    assert snap["status"] == "done", snap["error"]
    content = seen[0][0]["content"]
    assert "attached 1 image" in content[0]["text"] and "Traffic light box, 3 LEDs" in content[0]["text"]
    assert content[1] == {"type": "input_image", "image_url": PNG_1PX}
    assert snap["attachments"] == {"images": ["/out/job4/input-1.png"], "links": [{"url": "https://example.com/traffic-light", "error": None}]}
    assert (tmp_path / "job4" / "input-1.png").exists()


def test_export_sends_a_weak_guide_back_once(tmp_path):
    job = DesignJob("job9", "Uno case", tmp_path / "job9", lambda: Studio(REPO / "parts", tmp_path))
    s = job.studio
    s.new_design("Uno case")
    s.place_part("arduino-uno", (0, 0, 0), id="uno")
    s.add_step("Board", "Put the board down.", ["uno"], check="It works.")
    first = json.loads(job.run_tool("export", {}))
    assert first["exported"] is False and any("can't be seen" in p for p in first["problems"])
    assert not job.exported
    job.run_tool("export", {})  # the second try goes through, so a stubborn model can't loop forever
    assert job.exported


def test_a_failed_design_is_tried_again_with_the_failure_fed_back(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.setattr(jobs, "DESIGN_RETRIES", 1)
    place = NS(id="c0", function=NS(name="place_part", arguments='{"part_id": "arduino-uno", "position": [0, 0, 0], "id": "uno"}'))
    step = NS(id="c1", function=NS(name="add_step", arguments=json.dumps(
        {"title": "Place the Uno", "text": "Set the Arduino Uno on the desk.", "add": ["uno"], "check": "The USB port faces you."})))
    stop = NS(choices=[NS(finish_reason="stop", message=NS(content="Done.", tool_calls=None))])
    script = [  # the first try never writes a step; the second does
        NS(choices=[NS(finish_reason="tool_calls", message=NS(content=None, tool_calls=[place]))]), stop,
        NS(choices=[NS(finish_reason="tool_calls", message=NS(content=None, tool_calls=[step]))]), stop,
    ]
    seen = []

    class FakeClient:
        def __init__(self, api_key, base_url):
            self.chat = NS(completions=NS(create=lambda **kw: (seen.append(json.loads(json.dumps(kw["messages"]))), script.pop(0))[1]))

    monkeypatch.setattr(jobs.openai, "OpenAI", FakeClient)
    job = DesignJob("job4", "Uno stand", tmp_path / "job4", lambda: Studio(REPO / "parts", tmp_path), need_steps=True)
    job.run([], ["deepseek"])
    snap = job.snapshot()
    assert snap["status"] == "done", snap["error"]
    assert len(job.studio.design.steps) == 1 and not script
    retry = seen[2][1]["content"][0]["text"]
    assert "no assembly steps" in retry and "Carry on from there" in retry and '"uno"' in retry
    assert any("trying again" in e["text"] for e in snap["events"] if e["kind"] == "note")


def test_a_design_fails_after_its_retries_and_a_refusal_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.setattr(jobs, "DESIGN_RETRIES", 1)
    calls = []

    def broken(**kw):
        calls.append(1)
        raise ValueError("the model sent nonsense")

    monkeypatch.setattr(jobs.openai, "OpenAI", lambda api_key, base_url: NS(chat=NS(completions=NS(create=broken))))
    job = DesignJob("job5", "Uno stand", tmp_path / "job5", lambda: Studio(REPO / "parts", tmp_path))
    job.run([], ["deepseek"])
    assert job.snapshot()["status"] == "error" and "nonsense" in job.snapshot()["error"] and len(calls) == 2

    declined = NS(choices=[NS(finish_reason="content_filter", message=NS(content=None, tool_calls=None))])
    calls.clear()
    monkeypatch.setattr(jobs.openai, "OpenAI", lambda api_key, base_url: NS(chat=NS(completions=NS(
        create=lambda **kw: (calls.append(1), declined)[1]))))
    job = DesignJob("job6", "Uno stand", tmp_path / "job6", lambda: Studio(REPO / "parts", tmp_path))
    job.run([], ["deepseek"])
    assert job.snapshot()["status"] == "error" and "declined" in job.snapshot()["error"] and len(calls) == 1
