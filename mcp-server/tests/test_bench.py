"""The Build helper port (physical_studio/bench): the checks on fixed scenes, per-step models, and the
/api/build routes with the AI calls replaced by fixed answers. No network."""
import base64
import copy
import io
import json
import sys
import time
import types
from pathlib import Path

from fastmcp import FastMCP
from PIL import Image
from starlette.testclient import TestClient

from physical_studio.bench import planner, routes
from physical_studio.bench.geometry import build
from physical_studio.bench.spec import Spec, validate

REPO = Path(__file__).resolve().parents[2]
PlanModel = planner.plan_model(Spec)


def P(id, name, kind, holes=(), terms=()):
    return dict(id=id, name=name, kind=kind, color="#ff0000", center_mm=[0, 0, 5], size_mm=[5, 5, 5], mount_board="bb" if holes else "",
                mount_holes=list(holes), terminals=[dict(name=t, pin_index=i + 1) for i, t in enumerate(terms)], evidence="")


def W(id, fp, ft, tp, tt):
    return dict(id=id, name=id, from_part=fp, from_terminal=ft, to_part=tp, to_terminal=tt, color="#000000", connection_note="")


def traffic_light(n_leds=3, rows=(10, 20, 30, 40), cols="eeee", span=4):
    """GND to the ground rail, then per LED: anode e(A), cathode e(A+1), resistor d(A+1)-d(A+1+span),
    GPIO to a(A), ground wire from a(A+1+span) up to the rail. Steps place one thing each."""
    pins = ["d11", "d10", "d9", "d8"]
    parts = [P("bb", "Breadboard", "breadboard"), P("esp", "ESP32", "development_board", terms=pins + ["gnd"])]
    wires = [W("w_gnd", "esp", "gnd", "bb", "rail_1_24.14_1")]
    steps = []
    for n in range(n_leds):
        a, c, r2 = rows[n], cols[n], rows[n] + 1 + span
        parts += [P(f"led{n}", f"LED {n}", "led", [f"{c}{a}", f"{c}{a + 1}"]), P(f"r{n}", f"220 ohm resistor {n}", "resistor", [f"d{a + 1}", f"d{r2}"])]
        wires += [W(f"w_sig{n}", "esp", pins[n], "bb", f"a{a}"), W(f"w_g{n}", "bb", f"a{r2}", "bb", f"rail_1_24.14_{r2}")]
        for pid, holes in ((f"led{n}", [f"{c}{a}", f"{c}{a + 1}"]), (f"r{n}", [f"d{a + 1}", f"d{r2}"]),
                           (f"w_sig{n}", [f"pin:{pins[n]}", f"a{a}"]), (f"w_g{n}", [f"a{r2}", f"rail_1_24.14_{r2}"])):
            text = f"Put the longer leg in {holes[0]} and the shorter leg in {holes[1]}." if pid.startswith("led") else "x"
            steps.append(dict(number=len(steps) + 1, title=f"Place {pid}", part_ids=[pid], instruction=text,
                              placements=[dict(what="end", hole=h, where="x") for h in holes], check="x"))
    steps.insert(0, dict(number=0, title="Ground wire", part_ids=["w_gnd"], instruction="x",
                         placements=[dict(what="end", hole=h, where="x") for h in ("pin:gnd", "rail_1_24.14_1")], check="x"))
    for k, s in enumerate(steps, 1):
        s["number"] = k
    return dict(title="Traffic light", summary="s", parts=[dict(name="5 mm LED", quantity=n_leds, why="light", user_has_it=True)],
                scene=dict(parts=parts, wires=wires, assumptions=[]), part_guide=[dict(id="led0", what_it_is="The red LED.")],
                steps=steps, final_result="f", code="", safety=[])


def bench(raw, ids):
    return Spec.model_validate(dict(parts=[p for p in raw["scene"]["parts"] if p["id"] in ids],
                                    wires=[w for w in raw["scene"]["wires"] if w["id"] in ids], assumptions=[]))


# ---- checks ------------------------------------------------------------------------------------------

def test_a_correct_traffic_light_passes_every_check():
    plan = PlanModel.model_validate(traffic_light())
    assert planner.check_plan(plan) == []
    assert planner.check_layout(plan) == []
    assert planner.led_pins(plan.scene) == {"led0": ["d11"], "led1": ["d10"], "led2": ["d9"]}


def test_the_circuit_check_catches_each_wiring_mistake():
    good = PlanModel.model_validate(traffic_light()).scene
    same_row = copy.deepcopy(good)
    same_row.wires[2].to_terminal = "b15"  # the wire after the resistor stays in its own row
    problems = planner.check_circuit(same_row)
    assert any("connects nothing" in p for p in problems) and any("never reaches ground" in p for p in problems)
    no_gnd = copy.deepcopy(good)
    no_gnd.wires = no_gnd.wires[1:]
    assert any("GND pin to the ground rail" in p for p in planner.check_circuit(no_gnd))
    no_signal = copy.deepcopy(good)
    no_signal.wires = [w for w in no_signal.wires if w.id != "w_sig2"]
    assert any("not wired to a board pin" in p for p in planner.check_circuit(no_signal))


def test_plans_build_on_the_bench_without_redoing_it():
    raw = traffic_light()
    start = bench(raw, {"bb", "esp", "w_gnd", "led0", "r0", "w_sig0", "w_g0"})
    redo = PlanModel.model_validate(raw)  # its steps place the bench parts again
    assert any("already on the bench" in p for p in planner.check_plan(redo, None, start))
    ok = copy.deepcopy(raw)
    ok["steps"] = [s for s in ok["steps"] if s["part_ids"][0] not in {p.id for p in start.parts} | {w.id for w in start.wires}]
    assert planner.check_plan(PlanModel.model_validate(ok), None, start) == []
    moved = copy.deepcopy(ok)
    moved["scene"]["parts"][2]["mount_holes"] = ["e50", "e51"]
    assert any("moved it" in p for p in planner.check_plan(PlanModel.model_validate(moved), None, start))
    extra = copy.deepcopy(ok)
    extra["scene"]["wires"].append(W("w_gnd2", "esp", "gnd", "bb", "rail_1_24.14_60"))
    extra["steps"].append(dict(number=99, title="Another ground wire", part_ids=["w_gnd2"], instruction="x",
                               placements=[dict(what="end", hole="rail_1_24.14_60", where="x")], check="x"))
    assert any("already connected" in p for p in planner.check_plan(PlanModel.model_validate(extra), None, start))


def test_a_requested_fourth_led_is_allowed_and_usb_steps_are_not():
    plan = PlanModel.model_validate(traffic_light(4))
    assert planner.check_plan(plan) == [] and len(planner.led_pins(plan.scene)) == 4
    usb = copy.deepcopy(traffic_light())
    usb["steps"].append(dict(number=99, title="Plug in the USB cable", part_ids=[], instruction="Plug the board into your computer and upload the code.", placements=[], check="x"))
    assert any("not a placement" in p for p in planner.check_plan(PlanModel.model_validate(usb)))


def test_layout_is_judged_for_looks_only():
    messy = PlanModel.model_validate(traffic_light(rows=(10, 17, 33), cols="ece"))
    assert planner.check_circuit(messy.scene) == []  # still works
    assert len(planner.check_layout(messy)) >= 2  # but doesn't line up
    assert planner.led_pins(messy.scene) == planner.led_pins(PlanModel.model_validate(traffic_light()).scene)


def test_step_models_start_from_the_bench_and_end_with_the_whole_build():
    raw = traffic_light()
    have = {"bb", "esp", "w_gnd", "led0", "r0", "w_sig0", "w_g0"}
    raw["steps"] = [s for s in raw["steps"] if s["part_ids"][0] not in have]
    plan = PlanModel.model_validate(raw)
    models = planner.step_models(validate(plan.scene), plan.model_dump()["steps"], validate, build, list(have))
    first = {l["id"] for l in models[0]["labels"]}
    assert have <= first and models[0]["new"] == ["led1"]
    assert len(models[-1]["labels"]) == len(plan.scene.parts) + len(plan.scene.wires)


# ---- routes ------------------------------------------------------------------------------------------

def photo():
    b = io.BytesIO()
    Image.new("RGB", (80, 60), "gray").save(b, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


PLANNED_WITH = {}  # goal -> the own_parts the planner was given


def fake_make_plan(goal, have="", known="", photos=(), stage=lambda *a: None, own_parts=()):
    PLANNED_WITH[goal] = list(own_parts)
    stage("planning", "Choosing the parts you still need and writing your steps.")
    plan = PlanModel.model_validate(traffic_light())
    scene = validate(plan.scene)
    glb, labels = build(scene)
    dumped = plan.model_dump()
    return {"plan": dumped, "model": {"glb": glb, "labels": labels}, "steps3d": planner.step_models(scene, dumped["steps"], validate, build),
            "problems": [], "scan": None, "start_model": None}


def fake_commit_step(plan, i, photos, note):
    return {"verdict": {"observation": "The yellow LED is in.", "status": "problem", "problem": "It is backwards.", "fix": "Turn it around.", "confidence": 0.8},
            "model": fake_make_plan("x")["model"], "guide": {"led0": "The red LED."}}


def app(tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "make_plan", fake_make_plan)
    monkeypatch.setattr(planner, "commit_step", fake_commit_step)
    monkeypatch.delenv("DEMO_CODE", raising=False)
    mcp = FastMCP("bench-test")
    routes.register_build_routes(mcp, tmp_path, REPO / "parts")
    return TestClient(mcp.http_app(path="/mcp"))


def wait_done(c, bid):
    for _ in range(100):
        b = c.get(f"/api/build/{bid}").json()
        if b["status"] in ("done", "error"):
            return b
        time.sleep(0.1)
    raise AssertionError("build never finished")


def test_build_routes_follow_the_contract(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    assert c.post("/api/build", json={"goal": "x"}).status_code == 400
    assert c.post("/api/build", json={"goal": "Traffic light", "photos": ["not a photo"]}).status_code == 400
    assert c.get("/api/build/0123456789ab").status_code == 404
    r = c.post("/api/build", json={"goal": "Traffic light with 3 LEDs", "photos": [photo()]})
    assert r.status_code == 202
    b = wait_done(c, r.json()["id"])
    assert b["status"] == "done" and b["error"] is None and "internal" not in b
    plan = b["plan"]
    assert set(plan) >= {"title", "summary", "final_result", "code", "safety", "parts", "part_guide", "model", "steps"}
    assert plan["parts"][0]["size"] and plan["part_guide"] == {"led0": "The red LED."}
    assert plan["model"]["glb"] == f"/out/build-{b['id']}/final.glb"
    s1 = plan["steps"][0]
    assert s1["picture"] == f"/out/build-{b['id']}/step-1.svg" and s1["model"]["glb"].endswith("step-1.glb") and s1["markers"][0][0] == 1
    folder = tmp_path / f"build-{b['id']}"
    assert (folder / "step-1.svg").read_text().startswith("<svg") and (folder / "final.glb").stat().st_size > 1000
    start = b["commits"][0]
    assert start["kind"] == "start" and start["step"] is None and start["images"] == [f"/out/build-{b['id']}/img-start-1.jpg"]


def test_step_commits_are_checked_saved_and_survive_a_restart(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    bid = c.post("/api/build", json={"goal": "Traffic light with 3 LEDs"}).json()["id"]
    wait_done(c, bid)
    assert c.post(f"/api/build/{bid}/commit", json={"step": 99, "photos": [photo()]}).status_code == 400
    assert c.post(f"/api/build/{bid}/commit", json={"step": 2, "photos": []}).status_code == 400
    r = c.post(f"/api/build/{bid}/commit", json={"step": 2, "photos": [photo()], "note": "Placed the yellow LED"})
    assert r.status_code == 200
    commit = r.json()
    assert commit["kind"] == "step" and commit["step"] == 2 and commit["verdict"]["status"] == "problem"
    assert commit["model"]["glb"] == f"/out/build-{bid}/commit-{commit['id']}.glb" and commit["parent"]
    saved = json.loads((tmp_path / f"build-{bid}" / "build.json").read_text())
    assert [x["kind"] for x in saved["commits"]] == ["start", "step"]
    again = TestClient(app_again(tmp_path)).get(f"/api/build/{bid}").json()  # a fresh server reads build.json
    assert again["status"] == "done" and len(again["commits"]) == 2


def app_again(tmp_path):
    mcp = FastMCP("bench-test-2")
    routes.register_build_routes(mcp, tmp_path, REPO / "parts")
    return mcp.http_app(path="/mcp")


USERS = {"sess_ada": {"id": "u-ada", "email": "ada@example.com", "name": "Ada"},
         "sess_bob": {"id": "u-bob", "email": "bob@example.com", "name": "Bob"}}
ADA, BOB = {"Authorization": "Bearer sess_ada"}, {"Authorization": "Bearer sess_bob"}
BOM_PART = {"id": "bom-oled", "name": "0.96 inch OLED display", "body": {"size": [27, 27, 4]}, "pins": [{"id": "sda", "label": "SDA"}],
            "notes": "I2C.", "verified": False, "source": "From your BOM: https://example.com/oled"}


def fake_user(request):
    auth = request.headers.get("authorization", "")
    return USERS.get(auth[7:]) if auth.startswith("Bearer ") else None


def test_owned_builds_hide_the_owner_and_only_take_their_commits(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "user_from_request", fake_user)
    bid = c.post("/api/build", json={"goal": "Ada's traffic light"}, headers=ADA).json()["id"]
    b = wait_done(c, bid)
    assert b["owner_name"] == "Ada" and b["mine"] is False and "owner" not in b
    assert "u-ada" not in json.dumps(b) and "ada@example.com" not in json.dumps(b)
    assert c.get(f"/api/build/{bid}", headers=ADA).json()["mine"] is True
    assert c.get(f"/api/build/{bid}", headers=BOB).json()["mine"] is False
    for headers in ({}, BOB):
        r = c.post(f"/api/build/{bid}/commit", json={"step": 2, "photos": [photo()]}, headers=headers)
        assert r.status_code == 403 and r.json() == {"error": routes.NOT_OWNER}
    assert c.post(f"/api/build/{bid}/commit", json={"step": 2, "photos": [photo()]}, headers=ADA).status_code == 200
    assert json.loads((tmp_path / f"build-{bid}" / "build.json").read_text())["owner"] == "u-ada"  # kept on disk

    anon = wait_done(c, c.post("/api/build", json={"goal": "Anonymous light"}).json()["id"])
    assert anon["mine"] is True and anon["owner_name"] is None
    assert c.get(f"/api/build/{anon['id']}", headers=BOB).json()["mine"] is True
    assert c.post(f"/api/build/{anon['id']}/commit", json={"step": 2, "photos": [photo()]}, headers=BOB).status_code == 200


def test_the_owners_bom_parts_reach_the_planner(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "user_from_request", fake_user)
    boms = types.ModuleType("physical_studio.boms")
    boms.user_parts = lambda user_id: [BOM_PART] if user_id == "u-ada" else []
    monkeypatch.setitem(sys.modules, "physical_studio.boms", boms)
    wait_done(c, c.post("/api/build", json={"goal": "Ada's OLED clock"}, headers=ADA).json()["id"])
    wait_done(c, c.post("/api/build", json={"goal": "Someone's OLED clock"}).json()["id"])
    assert PLANNED_WITH["Ada's OLED clock"] == [BOM_PART] and PLANNED_WITH["Someone's OLED clock"] == []
    brief = planner.library_brief([BOM_PART])
    assert "THE USER'S OWN PARTS" in brief and "0.96 inch OLED display: body 27 x 27 x 4 mm" in brief and "From your BOM: https://example.com/oled" in brief
    assert "OWN PARTS" not in planner.library_brief() and "no size" in planner.library_brief([{"name": "Mystery sensor", "notes": "no size"}])


def test_a_missing_or_broken_bom_module_doesnt_stop_a_build(monkeypatch):
    monkeypatch.setitem(sys.modules, "physical_studio.boms", None)  # import raises ImportError
    assert routes.owner_parts("u-ada") == []
    broken = types.ModuleType("physical_studio.boms")
    broken.user_parts = lambda user_id: 1 / 0
    monkeypatch.setitem(sys.modules, "physical_studio.boms", broken)
    assert routes.owner_parts("u-ada") == [] and routes.owner_parts(None) == []


def test_a_failed_build_shows_a_plain_error(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)

    def broken(*a, **k):
        raise RuntimeError("model said no, key AIza-secret")

    monkeypatch.setattr(planner, "make_plan", broken)
    b = wait_done(c, c.post("/api/build", json={"goal": "Traffic light"}).json()["id"])
    assert b["status"] == "error" and b["error"] == routes.FAILED and "secret" not in json.dumps(b)


def test_ready_made_guides_are_view_only_and_can_be_copied(tmp_path, monkeypatch):
    c = app(tmp_path / "first", monkeypatch)
    bid = c.post("/api/build", json={"goal": "Traffic light with 3 LEDs"}).json()["id"]
    wait_done(c, bid)
    # Turn that finished build into a ready-made guide, the way bench/ready/<name>/ ships one.
    ready = tmp_path / "ready" / "traffic-light"
    ready.mkdir(parents=True)
    for f in (tmp_path / "first" / f"build-{bid}").iterdir():
        data = f.read_bytes()
        (ready / f.name).write_bytes(data.replace(f"/out/build-{bid}/".encode(), b"/out/build-traffic-light/") if f.suffix == ".json" else data)
    monkeypatch.setattr(routes, "READY_DIR", tmp_path / "ready")
    c = app(tmp_path / "site", monkeypatch)
    b = c.get("/api/build/traffic-light").json()
    assert b["ready"] and not b["mine"] and b["owner_name"] == "Physical Studio"
    assert b["plan"]["steps"][0]["picture"] == "/out/build-traffic-light/step-1.svg"
    assert (tmp_path / "site" / "build-traffic-light" / "step-1.svg").exists()
    r = c.post("/api/build/traffic-light/commit", json={"step": 0, "photos": [photo()]})
    assert r.status_code == 403 and "ready-made" in r.json()["error"]
    new = c.post("/api/build/traffic-light/copy").json()["id"]
    mine = c.get(f"/api/build/{new}").json()
    assert mine["mine"] and not mine.get("ready") and mine["plan"]["title"] == b["plan"]["title"]
    assert mine["plan"]["steps"][0]["picture"] == f"/out/build-{new}/step-1.svg"
    assert (tmp_path / "site" / f"build-{new}" / "step-1.svg").exists()
    assert len(mine["commits"]) == 1 and mine["commits"][0]["kind"] == "start"
    assert c.post(f"/api/build/{new}/commit", json={"step": 0, "photos": [photo()]}).status_code == 200


def test_parts_i_have_are_matched_to_the_library(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    items = c.post("/api/build/match", json={"items": ["Arduino Uno", "3 red LEDs", "220 ohm resistors", "SG90 servo", "jumper wires"]}).json()["items"]
    assert [i["part"] and i["part"]["id"] for i in items] == ["arduino-uno", "led-5mm", "resistor-220", "servo-sg90", None]
    assert items[0]["part"]["size"] == "68.6 × 53.4 × 1.6 mm"
    assert c.post("/api/build/match", json={"items": "nope"}).status_code == 400


def glb_shape(data):
    """What a GLB draws, without the float noise: node names and each mesh's vertex counts."""
    n = int.from_bytes(data[12:16], "little")
    doc = json.loads(data[20:20 + n])
    counts = [[doc["accessors"][p["attributes"]["POSITION"]]["count"] for p in m["primitives"]] for m in doc.get("meshes", [])]
    return sorted(x.get("name", "") for x in doc.get("nodes", [])), counts


def test_the_ready_made_traffic_light_renders_the_same_as_before():
    # The breadboard flow must not change: rebuilding the shipped traffic-light plan gives the same models.
    ready = routes.READY_DIR / "traffic-light"
    saved = json.loads((ready / "build.json").read_text())
    plan = PlanModel.model_validate(saved["internal"]["plan"])
    scene = validate(plan.scene)
    glb, labels = build(scene)
    assert labels == saved["plan"]["model"]["labels"]
    assert glb_shape(glb) == glb_shape((ready / "final.glb").read_bytes())
    models = planner.step_models(scene, plan.model_dump()["steps"], validate, build)
    assert len(models) == len(saved["plan"]["steps"])
    for n, (m, s) in enumerate(zip(models, saved["plan"]["steps"]), 1):
        if not s["model"]:
            assert not m
            continue
        assert m["labels"] == s["model"]["labels"] and m["new"] == s["model"]["new"]
        assert glb_shape(m["glb"]) == glb_shape((ready / f"step-{n}.glb").read_bytes())


def test_the_parts_brief_details_what_the_build_mentions():
    planner.configure(REPO / "parts")
    brief = planner.library_brief((), "ESP32, SG90 servo and an OLED")
    assert "Micro servo SG90" in brief and "ESP32 DevKit" in brief and "ALSO IN THE LIBRARY" in brief
    assert planner.split_items("Arduino Uno, 3 LEDs and a breadboard") == ["Arduino Uno", "3 LEDs", "a breadboard"]


def test_hardware_prompts_go_to_cad_and_circuits_stay_on_the_breadboard():
    assert routes.needs_cad("A double inverted pendulum on a rack and pinion cart")
    assert routes.needs_cad("A pen plotter with two NEMA 17 steppers on 2020 extrusion")
    assert not routes.needs_cad("A traffic light with red, yellow and green LEDs and a crosswalk button")


def test_enclosures_cases_and_motors_always_route_to_cad():
    # The "case with a lid" prompt from Kelly's demo run went to the breadboard once and to CAD once: the
    # route must come from the prompt alone, every time.
    for goal in ("Traffic light on an Arduino Uno in a printed case with a lid",
                 "A traffic light in a case with a lid", "Put my traffic light in a box", "An enclosure for an ESP32 weather station",
                 "A housing for the Uno with a hinged lid", "A fan controller with a 12V DC motor", "Two SG90 servos waving a flag",
                 "A night light with mounting holes and M3 screws", "A turntable driven by a gearmotor"):
        assert all(routes.needs_cad(goal) for _ in range(3)), goal
    for goal in ("Blink an LED on pin 13", "A showcase of RGB LED colours on an ESP32", "A fancy LED chaser with 8 LEDs",
                 "Add a pull-down resistor just in case the button floats",
                 json.loads((routes.READY_DIR / "traffic-light" / "build.json").read_text())["goal"]):
        assert not routes.needs_cad(goal), goal


class FakeJob:
    def __init__(self, status, steps=()):
        from types import SimpleNamespace as NS
        self.id, self.status, self.error, self.events = "job1", status, "nope" if status == "error" else None, [{"text": "Placing the rail"}]
        self.studio = NS(design=NS(steps=list(steps)))


class FakeJobs:
    def __init__(self, job):
        self.job, self.prompts = job, []

    async def start(self, prompt, ip, *a, **k):
        self.prompts.append(prompt)
        return self.job


def jobs_app(tmp_path, monkeypatch, job):
    monkeypatch.setattr(planner, "make_plan", fake_make_plan)
    monkeypatch.delenv("DEMO_CODE", raising=False)
    jobs = FakeJobs(job)
    mcp = FastMCP("bench-cad-test")
    routes.register_build_routes(mcp, tmp_path, REPO / "parts", jobs=jobs)
    return TestClient(mcp.http_app(path="/mcp")), jobs


def test_a_hardware_prompt_is_designed_in_cad_and_written_as_a_build(tmp_path, monkeypatch):
    def fake_write_build(studio, folder, bid, goal, summary, created):
        return {"plan": {"kind": "cad", "title": "Pendulum cart", "summary": summary, "steps": [], "parts": [], "part_guide": {},
                         "model": {"glb": f"/out/build-{bid}/final.glb", "labels": []}, "final_result": "", "code": "", "safety": []},
                "internal": {"plan": {"kind": "cad", "title": "Pendulum cart", "steps": []}}, "commits": [{"kind": "start", "id": "c0"}]}
    monkeypatch.setattr(routes.cad_guide, "write_build", fake_write_build)
    c, jobs = jobs_app(tmp_path, monkeypatch, FakeJob("done", steps=["one"]))
    b = wait_done(c, c.post("/api/build", json={"goal": "A cart on a linear rail driven by a rack and pinion", "have": "Teensy 4.1"}).json()["id"])
    assert b["status"] == "done" and b["plan"]["kind"] == "cad" and "Teensy 4.1" in jobs.prompts[0]


def test_a_failed_cad_job_is_an_error_not_a_breadboard_build(tmp_path, monkeypatch):
    c, jobs = jobs_app(tmp_path, monkeypatch, FakeJob("error"))
    b = wait_done(c, c.post("/api/build", json={"goal": "A robot arm with a servo on a bracket"}).json()["id"])
    assert b["status"] == "error" and b["error"] == routes.CAD_FAILED and not b.get("plan") and jobs.prompts
    c2, jobs2 = jobs_app(tmp_path, monkeypatch, FakeJob("done"))
    wait_done(c2, c2.post("/api/build", json={"goal": "A traffic light with three LEDs"}).json()["id"])
    assert jobs2.prompts == []  # circuits never start a CAD job


def test_a_busy_designer_is_an_error_not_a_breadboard_build(tmp_path, monkeypatch):
    c, jobs = jobs_app(tmp_path, monkeypatch, FakeJob("done"))

    async def busy(prompt, ip, *a, **k):
        jobs.prompts.append(prompt)
        raise RuntimeError("Another design is running; try again in a minute.")
    jobs.start = busy
    r = c.post("/api/build", json={"goal": "A traffic light in a printed case with a lid"})
    assert r.status_code == 503 and r.json()["error"] == routes.CAD_BUSY and jobs.prompts
    # A server with no design key has no CAD pipeline: hardware prompts are planned on the breadboard there.
    jobs.providers = lambda first=None: []
    b = wait_done(c, c.post("/api/build", json={"goal": "A traffic light in a printed case with a lid"}).json()["id"])
    assert b["status"] == "done" and len(jobs.prompts) == 1


def test_photo_checks_forgive_small_hole_offsets_but_not_real_mistakes():
    def p(problem):
        return {"status": "problem", "observation": "o", "problem": problem, "fix": "", "confidence": 0.7}
    assert planner.lenient(p("The red LED is in e11 and e12 instead of e10 and e11."))["status"] == "done"
    for real in ("Both legs are in row 10, the same strip.",
                 "The wire is on pin D9 instead of D10.", "The resistor is missing.", "The LED is across the centre gap in f10."):
        assert planner.lenient(p(real))["status"] == "problem", real
    assert "HOLES IN PHOTOS" in open(planner.__file__).read()


def test_photo_checks_ignore_led_colours():
    def p(problem):
        return {"status": "problem", "observation": "o", "problem": problem, "fix": "", "confidence": 0.7}
    assert planner.lenient(p("The LED in e30 is red, but this step needs a blue LED."))["status"] == "done"
    assert planner.lenient(p("Wrong colour: a green LED is in the yellow LED's spot."))["status"] == "done"
    assert planner.lenient(p("The blue LED is missing from e30 and e31."))["status"] == "problem"
    assert "LED COLOURS DON'T MATTER" in open(planner.__file__).read()


def test_polarity_is_never_checked():
    def p(problem):
        return {"status": "problem", "observation": "o", "problem": problem, "fix": "", "confidence": 0.7}
    for polarity in ("The yellow LED is backwards: its long leg is in c21.", "The LED's flat side faces the wrong way.",
                     "The capacitor's stripe is on the wrong side.", "The shorter leg is in e10 where the longer leg should go."):
        assert planner.lenient(p(polarity))["status"] == "done", polarity
    assert planner.lenient(p("The wire is on pin D9 instead of D10."))["status"] == "problem"
    assert "POLARITY IS NEVER CHECKED" in open(planner.__file__).read()


def test_led_steps_say_where_the_longer_and_shorter_legs_go():
    raw = traffic_light()
    for s in raw["steps"]:
        if s["part_ids"][0].startswith("led"):
            s["instruction"] = "Put the LED in e10 and e11."
    assert planner.check_led_legs(PlanModel.model_validate(raw)) != []  # holes only, no legs named
    for s in raw["steps"]:
        if s["part_ids"][0].startswith("led"):
            s["instruction"] = "Put the longer leg in e10 and the shorter leg in e11."
    assert planner.check_led_legs(PlanModel.model_validate(raw)) == []
    ready = json.loads((REPO / "mcp-server/physical_studio/bench/ready/traffic-light/build.json").read_text())
    assert planner.check_led_legs(PlanModel.model_validate(ready["internal"]["plan"])) == []  # the ready-made guide already does


def test_scans_list_jumper_wires():
    assert "jumper wires included" in planner.SCAN_RULES and "every plugged-in jumper wire" in planner.SCAN_RULES


def test_awkward_wires_are_repaired_not_allowed_to_sink_the_model():
    parts = [P("bb", "Breadboard", "breadboard"), P("uno", "Arduino Uno", "development_board", terms=["gnd"]), P("led0", "red LED", "led", ["e10", "e11"])]
    wires = [W("w1", "uno", "D9", "bb", "A10"),            # undeclared board pin, upper-case hole
             W("w2", "led0", "short leg", "bb", "rail_1_24.14_11"),  # leg name the builder doesn't know
             W("w3", "ghost", "1", "bb", "a20"),           # a part that isn't in the scene
             W("w4", "bb", "z99", "bb", "a12")]            # not a real hole
    scene = Spec.model_validate(dict(parts=parts, wires=wires, assumptions=[]))
    fixed = planner.fix_wires(scene)
    assert [w.id for w in fixed.wires] == ["w1", "w2"]
    assert fixed.wires[0].to_terminal == "a10" and fixed.wires[1].from_terminal == "cathode"
    assert "d9" in {t.name for t in fixed.parts[1].terminals}
    assert planner.model_of(Spec.model_validate(dict(parts=parts, wires=wires, assumptions=[])), validate, build) is not None


def test_the_scan_takes_a_second_look_for_jumper_wires(monkeypatch):
    from types import SimpleNamespace as NS
    first = {"summary": "s", "detected": [{"name": "red jumper wire", "quantity": 2, "where": "placed", "scene_id": ""}],
             "scene": dict(parts=[P("bb", "Breadboard", "breadboard"), P("led0", "red LED", "led", ["e10", "e11"])], wires=[], assumptions=[]),
             "part_guide": [], "uncertain": []}
    wires_only = dict(parts=[], wires=[W("wa", "bb", "a10", "bb", "rail_1_24.14_10"), W("wb", "bb", "a11", "bb", "rail_-1_24.14_11")], assumptions=[])
    answers = iter([json.dumps(first), json.dumps(wires_only)])
    monkeypatch.setattr(planner, "ask", lambda contents, schema: NS(text=next(answers)))
    scan = planner.scan_bench("traffic light", [b"jpeg"], "")
    assert len(scan.scene.wires) == 2 and scan.detected[0].name == "red jumper wire"


def test_anyone_can_report_a_wrong_step_and_reports_stay_private(tmp_path, monkeypatch):
    c = app(tmp_path, monkeypatch)
    bid = c.post("/api/build", json={"goal": "Traffic light with 3 LEDs"}).json()["id"]
    wait_done(c, bid)
    r = c.post(f"/api/build/{bid}/report", json={"step": 0, "text": "  The LED   is in the wrong row "})
    assert r.status_code == 201
    entry = json.loads((tmp_path / ".reports" / "reports.jsonl").read_text().splitlines()[0])
    assert entry["build"] == bid and entry["step"] == 0 and entry["text"] == "The LED is in the wrong row"
    assert c.post(f"/api/build/{bid}/report", json={"step": 99, "text": "wrong"}).status_code == 400
    assert c.post(f"/api/build/{bid}/report", json={"step": 0, "text": " "}).status_code == 400
    assert c.post("/api/build/000000000000/report", json={"step": 0, "text": "wrong"}).status_code == 404


def test_test_checkpoints_keep_only_real_steps_before_the_end(monkeypatch):
    answer = {"tests": [
        {"after_step": 3, "title": "Test the LED", "what_it_tests": "LED", "code": "void setup(){}\nvoid loop(){}", "expect": "It blinks.", "if_not": "Step 2."},
        {"after_step": 4, "title": "After the last step", "what_it_tests": "all", "code": "void setup(){}", "expect": "x", "if_not": "x"},
        {"after_step": 9, "title": "No such step", "what_it_tests": "x", "code": "void setup(){}", "expect": "x", "if_not": "x"},
        {"after_step": 3, "title": "Same step twice", "what_it_tests": "x", "code": "void setup(){}", "expect": "x", "if_not": "x"},
        {"after_step": 1, "title": "No code", "what_it_tests": "x", "code": " ", "expect": "x", "if_not": "x"}]}
    monkeypatch.setattr(planner, "ask", lambda contents, schema: types.SimpleNamespace(text=json.dumps(answer)))
    steps = [{"number": n, "title": f"Step {n}", "instruction": "Place it."} for n in range(1, 5)]
    tests = planner.write_tests({"title": "Blink", "summary": "", "steps": steps, "code": "void setup(){}"})
    assert [t["title"] for t in tests] == ["Test the LED"]
    assert planner.write_tests({"title": "No sketch", "steps": steps, "code": ""}) == []


def ready_plan(name):
    return json.loads((REPO / "mcp-server" / "physical_studio" / "bench" / "ready" / name / "build.json").read_text())["internal"]["plan"]


def test_a_module_wired_with_its_power_backwards_is_caught():
    raw = ready_plan("distance-alarm")
    assert planner.check_module_power(PlanModel.model_validate(raw)) == []
    for w in raw["scene"]["wires"]:  # swap the HC-SR04's 5V and ground wires
        if w["from_terminal"] == "5v":
            w["to_terminal"] = "a27"
        elif w["to_terminal"] == "rail_1_24.14_27":
            w["from_terminal"] = "a24"
    problems = planner.check_module_power(PlanModel.model_validate(raw))
    assert any("power pin (e24) is wired to GND" in p for p in problems)
    assert any("GND pin (e27) is wired to the board's power pin" in p for p in problems)


def test_an_unpowered_module_is_caught():
    raw = ready_plan("snake-game")
    raw["scene"]["wires"] = [w for w in raw["scene"]["wires"] if w["to_terminal"] != "f41"]  # joystick +5V wire gone
    assert any("power pin (j41) never reaches" in p for p in planner.check_module_power(PlanModel.model_validate(raw)))


def test_rails_used_on_both_halves_get_the_split_rail_note():
    for name, note in (("distance-alarm", True), ("snake-game", True), ("blink", False), ("night-light", False)):
        raw = ready_plan(name)
        assert any(planner.RAIL_GAP_NOTE in s["instruction"] for s in raw["steps"]) == note, name
        again = planner.add_rail_gap_note(copy.deepcopy(raw))
        assert sum(planner.RAIL_GAP_NOTE in s["instruction"] for s in again["steps"]) == int(note), name


def test_the_6mm_button_legs_across_the_gap_are_the_connected_pair():
    part = json.loads((REPO / "parts" / "push-button-6mm.json").read_text())
    pins = {p["id"]: p["position"] for p in part["pins"]}
    assert abs(pins["1b"][0] - pins["1a"][0]) == 6.5 and pins["1b"][1] == pins["1a"][1]  # Omron B3F: 1-2 joined, 6.5 mm apart
    assert abs(pins["2a"][1] - pins["1a"][1]) == 4.5
    assert "across the gap" in part["notes"] and "always connected" in part["notes"]
