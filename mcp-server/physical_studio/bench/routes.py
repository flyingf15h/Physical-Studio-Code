# Senna's Build helper as HTTP routes for the main site (new for the merge; the logic is in planner.py,
# ported from circuit-studio/builder.py at 21a4f23). A build is: optional bench photos and typed
# connections -> scan (commit #0) -> checked plan with a picture and a 3D model per step -> photo commits
# on any step, each checked by the AI and given its own 3D model.
#
#   POST /api/build                {goal, have?, known?, photos?: [data URL]}  -> 202 {id}
#   GET  /api/build/<id>           status, stage, plan, commits (see snapshot())
#   POST /api/build/<id>/commit    {step, photos: [data URL], note?}           -> 200 the new commit
#   POST /api/build/import         {url}  a link to an existing project        -> 202 {id} (importer.py)
#
# A build started while logged in has an owner: only they can commit to it (others get 403), GET says
# `mine` and `owner_name` (never the owner's id or email), and the planner also gets their BOM parts.
# Anonymous builds stay open to anyone with the link.
#
# Files go to <out_dir>/build-<id>/ and are served by the viewer at /out/build-<id>/<file>. build.json is
# rewritten after every change, so a build and its commits survive a reload or a restart.
import asyncio, base64, binascii, json, os, re, shutil, threading, time, uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse
from .. import users
from ..users import user_from_request
from . import cad_guide, diagram, importer, planner
from .pool import hide

BUILDS_PER_HOUR = int(os.environ.get("BUILDS_PER_HOUR", "4"))
MAX_PHOTOS = planner.MAX_PHOTOS
MAX_BYTES = 40 * 1024 * 1024
BUILD_ID = re.compile(r"[0-9a-f]{12}")
DATA_URL = re.compile(r"data:image/(jpeg|jpg|png|webp);base64,(.+)", re.S)
FAILED = "Something went wrong while planning. Wait a minute and try again."
NOT_OWNER = "Only the person who started this build can commit to it."
SUMMARY_MAX = 280  # about 3 lines under the title
REPORT_MAX = 1000  # "this step is wrong" reports
REPORTS_PER_HOUR = 20
# Ready-made guides (screen 1): finished builds kept in the repo under bench/ready/<name>/ (build.json
# with /out/build-<name>/ URLs, plus its files). They're copied into out_dir at startup, can't be
# committed to, and POST /api/build/<name>/copy gives a visitor their own copy to commit photos to.
READY_DIR = Path(__file__).with_name("ready")
READY_ID = re.compile(r"[a-z][a-z0-9-]{2,39}")
READY_NOTE = "This is a ready-made guide. Make your own copy to commit photos of your build."


# Live hardware builds: prompts that need real mechanics (motors, rails, gears, mounts, a case) run the CAD
# design pipeline (jobs.py) instead of the breadboard planner; when it finishes, cad_guide.write_build turns
# the design into the build (sections, tools, reference pictures, a 3D model per step). The route depends on
# the prompt alone: a hardware prompt never quietly becomes a breadboard build because the design slot was
# busy, the hour's designs were used up or the design failed (that's an error to try again); only a server with no CAD pipeline
# (no JobManager or no design key) plans hardware prompts on the breadboard. Imports always try CAD, and the
# same holds for them: one whose goal needs CAD errors out; one that's just a circuit falls back to the breadboard.
CAD_WORDS = ("rack and pinion", "rack-and-pinion", "pinion", "gear", "linear rail", "rail", "carriage", "cart", "pendulum", "robot arm",
             "chassis", "enclosure", "case", "box", "housing", "shell", "3d print", "3d-print", "printed", "printable", "mount", "bracket",
             "frame", "bearing", "shaft", "motor", "gearmotor", "servo", "stepper", "nema", "belt", "pulley", "wheel", "caster", "drone",
             "rover", "cnc", "plotter", "turntable", "lid", "hinge", "lead screw", "leadscrew", "extrusion", "2020", "linear rod", "slider",
             "limit switch", "propeller", "fan", "actuator", "solenoid", "screw", "standoff", "casing", "mounting")
# Whole words (plus -s/-es/-ed/-ing), so substrings like "showcase" or "fancy" can't flip the route by accident.
CAD_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(CAD_WORDS, key=len, reverse=True)) + r")(?:s|es|ed|d|ing)?\b")
NOT_CAD = re.compile(r"\b(?:just )?in case\b|\bjust in case\b")


def needs_cad(goal: str) -> bool:
    """True for builds that are mechanical as well as electronic (an enclosure, case, lid, motors, mechanical
    parts), False for breadboard circuits. Deterministic: the same prompt always takes the same route."""
    return bool(CAD_PATTERN.search(NOT_CAD.sub(" ", goal.lower())))


CAD_BUSY = "This needs a CAD design (a case, motors or mechanical parts) and the designer is busy. Try again in a minute."
CAD_FAILED = "This needs a CAD design (a case, motors or mechanical parts) and the design didn't work out."  # the page adds "try again"


def cad_available(jobs) -> bool:
    """Can this server run the CAD design pipeline at all (a JobManager with a design key)?"""
    if jobs is None:
        return False
    providers = getattr(jobs, "providers", None)
    return providers is None or bool(providers())


class BadRequest(Exception):
    pass


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_photos(items, required=False):
    """Data-URL images -> JPEG bytes (resized like the Build helper does)."""
    if items is None:
        items = []
    if not isinstance(items, list) or len(items) > MAX_PHOTOS:
        raise BadRequest(f"Send up to {MAX_PHOTOS} photos.")
    if required and not items:
        raise BadRequest("Attach at least one photo.")
    raw, total = [], 0
    for item in items:
        m = DATA_URL.fullmatch(item.strip()) if isinstance(item, str) else None
        if not m:
            raise BadRequest("Photos must be JPEG, PNG or WebP data URLs.")
        try:
            data = base64.b64decode(m[2], validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest("A photo couldn't be decoded.")
        total += len(data)
        if total > MAX_BYTES:
            raise BadRequest("Photos can be 40 MB in total at most.")
        raw.append(data)
    try:
        return [planner.jpeg(d) for d in raw]
    except Exception:
        raise BadRequest("A photo couldn't be read as an image.")


def own_part(user_id, name):
    """One of the user's BOM parts by name (None when boms.py isn't there)."""
    try:
        from ..boms import own_part as find

        return find(user_id, name)
    except Exception:
        return None


def owner_parts(user_id):
    """The owner's uploaded BOM parts for the planner ([] when anonymous or boms.py isn't there)."""
    if not user_id:
        return []
    try:
        from ..boms import user_parts
    except ImportError:
        return []
    try:
        return list(user_parts(user_id) or [])
    except Exception as e:  # a broken BOM shouldn't stop the build
        print("[bench] no BOM parts for the planner:", hide(str(e))[:300], flush=True)
        return []


class BuildStore:
    def __init__(self, out_dir: Path, jobs=None):
        self.out_dir = Path(out_dir)
        self.jobs = jobs  # jobs.JobManager for live hardware builds (None: breadboard planner only)
        self.builds = {}  # id -> build dict (public fields + "internal")
        self.lock = threading.Lock()
        self.commit_locks = defaultdict(threading.Lock)
        self.recent = defaultdict(list)
        self.reports = defaultdict(list)  # ip -> times of recent step reports
        self.ready = set()
        self.seed_ready()

    def seed_ready(self):
        for src in sorted(READY_DIR.glob("*/build.json")) if READY_DIR.is_dir() else []:
            name = src.parent.name
            if not READY_ID.fullmatch(name):
                continue
            shutil.copytree(src.parent, self.folder(name), dirs_exist_ok=True)
            build = json.loads(src.read_text())
            build.update(id=name, ready=True, owner=None, owner_name="Physical Studio")
            self.ready.add(name)
            self.builds[name] = build

    def copy(self, build, user=None):
        """A visitor's own copy of a finished build: same plan and files, a fresh commit #0, no AI call."""
        old, bid = build["id"], uuid.uuid4().hex[:12]
        src, dst = self.folder(old), self.folder(bid)
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and f.name != "build.json" and not f.name.startswith("commit-") and not (f.name.startswith("img-") and not f.name.startswith("img-start-")):
                shutil.copy2(f, dst / f.name)
        moved = lambda data: json.loads(json.dumps(data).replace(f"/out/build-{old}/", f"/out/build-{bid}/"))  # noqa: E731
        start = moved(next((c for c in build["commits"] if c["kind"] == "start"), None)) or {"kind": "start", "step": None, "images": [], "model": None, "guide": {}, "detected": []}
        start.update(id=planner.new_id(bid), time=now_iso(), message=f"Started from the ready-made guide: {build['plan']['title']}", parent=None)
        copy = {"id": bid, "status": "done", "stage": "Your build is ready.", "error": None, "goal": build["goal"], "have": "", "known": "",
                "created": now_iso(), "plan": moved(build["plan"]), "commits": [start], "internal": build["internal"],
                "owner": user["id"] if user else None, "owner_name": user["name"] if user else None, "copied_from": old}
        with self.lock:
            self.builds[bid] = copy
        self.save(copy)
        return bid

    def folder(self, bid):
        return self.out_dir / f"build-{bid}"

    def url(self, bid, name):
        return f"/out/build-{bid}/{name}"

    def write(self, bid, name, data):
        path = self.folder(bid) / name
        path.write_bytes(data)
        return self.url(bid, name)

    def save(self, build):
        folder = self.folder(build["id"])
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "build.json.tmp"
        tmp.write_text(json.dumps(build))
        tmp.replace(folder / "build.json")

    def get(self, bid):
        if not BUILD_ID.fullmatch(bid or "") and bid not in self.ready:
            return None
        with self.lock:
            if bid in self.builds:
                return self.builds[bid]
            path = self.folder(bid) / "build.json"
            if not path.exists():
                return None
            build = json.loads(path.read_text())
            if build["status"] not in ("done", "error"):  # the server restarted mid-build
                build.update(status="error", stage="", error="The server restarted while this build was planning. Start it again.")
            self.builds[bid] = build
            return build

    def allow_report(self, ip):
        now = time.time()
        with self.lock:
            self.reports[ip] = [t for t in self.reports[ip] if now - t < 3600]
            if len(self.reports[ip]) >= REPORTS_PER_HOUR:
                return False
            self.reports[ip].append(now)
            return True

    def add_report(self, entry):
        folder = self.out_dir / ".reports"
        folder.mkdir(parents=True, exist_ok=True)
        with self.lock, open(folder / "reports.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def owned(self, user_id):
        """The builds a user started (or copied), from disk: the in-memory cache only holds recent ones."""
        out = []
        for path in self.out_dir.glob("build-*/build.json"):
            try:
                build = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if build.get("owner") == user_id and not build.get("ready"):
                out.append(build)
        return out

    def export_user(self, user_id):
        return [{k: b.get(k) for k in ("id", "created", "goal", "have", "known", "status", "plan", "commits")} for b in self.owned(user_id)]

    def delete_user(self, user_id):
        for build in self.owned(user_id):
            with self.lock:
                self.builds.pop(build["id"], None)
            shutil.rmtree(self.folder(build["id"]), ignore_errors=True)

    def update(self, build, **fields):
        with self.lock:
            build.update(fields)
            self.save(build)

    def allow(self, ip):
        now = time.time()
        with self.lock:
            self.recent[ip] = [t for t in self.recent[ip] if now - t < 3600]
            if len(self.recent[ip]) >= BUILDS_PER_HOUR:
                return False
            self.recent[ip].append(now)
            return True

    def start(self, goal, have, known, photos, user=None, job=None, imported=None):
        """imported: an importer.Project, for builds made with "Import a project"."""
        bid = uuid.uuid4().hex[:12]
        build = {"id": bid, "status": "scanning" if photos or known.strip() else "planning", "stage": "Starting your build.",
                 "error": None, "goal": goal, "have": have, "known": known, "created": now_iso(), "plan": None, "commits": [], "internal": {},
                 "owner": user["id"] if user else None, "owner_name": user["name"] if user else None}
        with self.lock:
            self.builds[bid] = build
        self.save(build)
        threading.Thread(target=self.run, args=(build, photos, job, imported), daemon=True).start()
        return bid

    def cad_build(self, build, job, imported=None):
        """Wait for the CAD design job, then write its design out as this build. False if it didn't work."""
        self.update(build, status="planning", stage="Designing it in CAD from real parts: placing each part, checking the fit and planning the steps.")
        seen = 0
        while job.status in ("queued", "running"):
            if len(job.events) > seen:  # pass the design job's progress on as the stage sentence
                seen = len(job.events)
                text = str(job.events[-1].get("text") or "")
                if text:
                    self.update(build, stage="Designing it in CAD: " + text[:160])
            time.sleep(2)
        if job.status != "done" or not job.studio.design or not job.studio.design.steps:
            print("[bench] CAD job", job.id, "for build", build["id"], "ended as", job.status, hide(job.error or "")[:300], flush=True)
            return False
        self.update(build, status="modelling", stage="Turning the CAD design into your step-by-step guide.")
        done = cad_guide.write_build(job.studio, self.folder(build["id"]), build["id"], build["goal"], build["goal"].split("\n")[0][:SUMMARY_MAX], build["created"])
        plan = self.with_import(build, done["plan"], imported)
        self.update(build, plan=plan, internal=done["internal"], commits=done["commits"], status="done", stage="Your build is ready.")
        return True

    def with_import(self, build, plan, imported):
        """An imported project's own CAD files and parts list added to the finished plan."""
        if not imported:
            return plan
        self.update(build, stage="Adding the project's own CAD files and parts list.")
        return importer.attach(imported, self.folder(build["id"]), build["id"], plan)

    def run(self, build, photos, job=None, imported=None):
        bid = build["id"]
        try:
            if job:
                if self.cad_build(build, job, imported):
                    return
                if not imported or needs_cad(build["goal"]):  # hardware: a failed design is an error, never a breadboard guide for a case
                    self.update(build, status="error", stage="", error=CAD_FAILED)
                    return
                self.update(build, status="planning", stage="Planning it as a breadboard circuit instead.")
            result = planner.make_plan(build["goal"], build["have"], build["known"], photos,
                                       stage=lambda status, text: self.update(build, status=status, stage=text),
                                       own_parts=owner_parts(build.get("owner")))
            self.update(build, plan=self.with_import(build, self.publish(bid, result), imported), commits=[self.start_commit(bid, build, result, photos)],
                        internal={"plan": result["plan"], "problems": result["problems"]}, status="done", stage="Your build is ready.")
        except Exception as e:
            print("[bench] build", bid, "failed:", hide(str(e))[:900], flush=True)  # details in the log, not the page
            self.update(build, status="error", stage="", error=FAILED)

    def publish(self, bid, result):
        """The plan as the page needs it: files written to disk, URLs instead of bytes."""
        plan = result["plan"]
        steps = []
        uno = planner.LIBRARY.get("arduino-uno")
        for i, (s, m) in enumerate(zip(plan["steps"], result["steps3d"])):
            n = i + 1
            try:
                page, markers = diagram.step_svg(plan, i, uno)
                svg = re.search(r"<svg.*</svg>", page, re.S)[0]
                picture = self.write(bid, f"step-{n}.svg", svg.encode())
            except Exception as e:
                print("[bench] no picture for step", n, ":", e, flush=True)
                picture, markers = None, [(k, p["what"], p["where"], p["hole"]) for k, p in enumerate(s["placements"], 1)]
            model = None
            if m:
                model = {"glb": self.write(bid, f"step-{n}.glb", m["glb"]), "labels": m["labels"], "new": m["new"]}
            steps.append({**{k: s[k] for k in ("number", "title", "instruction", "check", "part_ids", "placements")},
                          "picture": picture, "markers": [list(x) for x in markers], "model": model})
        return {"title": plan["title"], "summary": plan["summary"], "final_result": plan["final_result"],
                "code": plan["code"], "tests": plan.get("tests", []), "safety": plan["safety"],
                "parts": [{**p, "size": planner.part_size(p["name"])} for p in plan["parts"]],
                "part_guide": planner.guide_of(plan),
                "model": {"glb": self.write(bid, "final.glb", result["model"]["glb"]), "labels": result["model"]["labels"]},
                "steps": steps}

    def start_commit(self, bid, build, result, photos):
        scan, start_model = result["scan"], result["start_model"]
        commit = {"id": planner.new_id(bid), "kind": "start", "step": None,
                  "message": "What I have: " + (scan.summary if scan else "no photos, starting from scratch"),
                  "time": now_iso(), "images": [self.write(bid, f"img-start-{k + 1}.jpg", planner.jpeg(b, 1024)) for k, b in enumerate(photos)],
                  "model": None, "guide": {}, "detected": [], "known": build["known"]}
        if start_model:
            commit["model"] = {"glb": self.write(bid, "start.glb", start_model["glb"]), "labels": start_model["labels"]}
        if scan:
            commit["guide"] = {n.id: n.what_it_is for n in scan.part_guide}
            commit["detected"] = [d.model_dump() for d in scan.detected]
            commit["uncertain"] = scan.uncertain  # kept in the JSON, not shown on the page
        return commit

    def commit(self, build, step, photos, note):
        """Photos after a step -> the AI's verdict + a 3D model of the bench as photographed."""
        bid = build["id"]
        with self.commit_locks[bid]:
            plan = build["internal"]["plan"]
            if plan.get("kind") == "cad":  # hardware builds: compared with the step's reference render
                c = cad_guide.commit_step(plan, step, photos, note, self.folder(bid))
            else:
                c = planner.commit_step(plan, step, photos, note)
            cid = planner.new_id(bid, step, note)
            commit = {"id": cid, "kind": "step", "step": step, "message": note, "time": now_iso(),
                      "images": [self.write(bid, f"img-{cid}-{k + 1}.jpg", planner.jpeg(b, 1024)) for k, b in enumerate(photos)],
                      "verdict": c["verdict"], "model": None, "guide": c["guide"],
                      "parent": build["commits"][-1]["id"] if build["commits"] else None}
            if c["model"]:
                commit["model"] = {"glb": self.write(bid, f"commit-{cid}.glb", c["model"]["glb"]), "labels": c["model"]["labels"]}
            self.update(build, commits=build["commits"] + [commit])
            return commit


def may_commit(build, user):
    """Anonymous builds are open to anyone with the link; owned ones only to their owner; ready-made
    guides to nobody (make a copy)."""
    if build.get("ready"):
        return False
    return not build.get("owner") or bool(user and user["id"] == build["owner"])


def snapshot(build, user=None):
    data = {k: v for k, v in build.items() if k not in ("internal", "have", "owner")}
    data.update(mine=may_commit(build, user), owner_name=build.get("owner_name"))
    return data


def register_build_routes(mcp, out_dir: Path, parts_dir: Path, jobs=None):
    """jobs: the server's jobs.JobManager, so hardware prompts can run the CAD design pipeline."""
    planner.configure(parts_dir)
    store = BuildStore(out_dir, jobs)
    users.EXPORT_HOOKS[:] = [store.export_user]  # a user's data download and account deletion cover their builds
    users.DELETE_HOOKS[:] = [store.delete_user]

    def code_ok(request: Request) -> bool:
        code = os.environ.get("DEMO_CODE")
        return not code or request.headers.get("x-demo-code") == code

    async def body_of(request: Request):
        try:
            body = await request.json()
            return body if isinstance(body, dict) else {}
        except Exception:
            return {}

    @mcp.custom_route("/api/build", methods=["POST"])
    async def start(request: Request):
        if not code_ok(request):
            return JSONResponse({"error": "Wrong or missing demo code."}, status_code=401)
        body = await body_of(request)
        goal = str(body.get("goal", "")).strip()
        have, known = str(body.get("have") or "").strip()[:2000], str(body.get("known") or "").strip()[:3000]
        if not 3 <= len(goal) <= 4000:
            return JSONResponse({"error": "Say what you want to build in 3 to 4000 characters."}, status_code=400)
        try:
            photos = await asyncio.to_thread(parse_photos, body.get("photos"))
        except BadRequest as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        if not store.allow(ip):
            return JSONResponse({"error": "You've started a lot of builds; try again in a while."}, status_code=429)
        job = None
        if cad_available(store.jobs) and needs_cad(goal):  # a hardware build: design it in CAD from real parts
            prompt = goal + (f"\nParts I have: {have}" if have else "") + (f"\nConnections I already know: {known}" if known else "")
            try:
                job = await store.jobs.start(prompt[:1000], ip, need_steps=True)
            except Exception as e:  # another design running, too many designs: try again, not a breadboard build
                print("[bench] no CAD job for a hardware build:", hide(str(e))[:300], flush=True)
                return JSONResponse({"error": CAD_BUSY}, status_code=503)
        return JSONResponse({"id": store.start(goal, have, known, photos, user_from_request(request), job)}, status_code=202)

    @mcp.custom_route("/api/build/match", methods=["POST"])
    async def match(request: Request):
        """The "Parts I have" chips: {items: [text]} -> each item's library part (the same lookup the planner
        uses for sizes and the parts brief), or null when the library doesn't have it."""
        items = (await body_of(request)).get("items")
        user = user_from_request(request)
        if not isinstance(items, list) or len(items) > 60:
            return JSONResponse({"error": "items must be a list of up to 60 part names."}, status_code=400)
        out = []
        for item in items:
            text = str(item).strip()[:120]
            p = planner.library_part(text) if text else None
            if not p and text and user:  # the caller's own parts, added from their BOM
                p = own_part(user["id"], text)
            out.append({"text": text, "part": p and {"id": p["id"], "name": p["name"], "category": p["category"],
                                                     "size": " × ".join(f"{v:g}" for v in p["body"]["size"]) + " mm", "verified": bool(p.get("verified")),
                                                     "mine": bool(p.get("bom"))}})
        return JSONResponse({"items": out})

    @mcp.custom_route("/api/build/import", methods=["POST"])
    async def import_project(request: Request):
        """"Import a project": {url} of a GitHub repository or a project page -> a build guide made from what
        the project already has (importer.py), opened at /build/<id> like Design it."""
        if not code_ok(request):
            return JSONResponse({"error": "Wrong or missing demo code."}, status_code=401)
        url = str((await body_of(request)).get("url") or "").strip()
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        if not store.allow(ip):
            return JSONResponse({"error": "You've started a lot of builds; try again in a while."}, status_code=429)
        try:
            project = await asyncio.to_thread(importer.gather, url)
        except importer.ProjectError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        user = user_from_request(request)
        importer.match_parts(project)
        importer.add_missing(project, user)
        # The project's wiring is what to build, not what's on the bench already (`known`), so it goes in the goal.
        wiring = "\n".join(project.wiring + project.pins)
        goal = (importer.goal(project) + (f"\nThe project's own wiring and pin assignments:\n{wiring}" if wiring else ""))[:4000]
        job = None
        if cad_available(store.jobs):
            try:
                job = await store.jobs.start(importer.prompt(project), ip, context=importer.context(project), need_steps=True)
            except Exception as e:  # busy or out of designs: an error for hardware, the breadboard planner for a circuit
                print("[bench] no CAD job for the import:", hide(str(e))[:300], flush=True)
                if needs_cad(goal):
                    return JSONResponse({"error": CAD_BUSY}, status_code=503)
        bid = store.start(goal, importer.have_text(project), "", [], user, job, project)
        return JSONResponse({"id": bid}, status_code=202)

    @mcp.custom_route("/api/build/{build_id}", methods=["GET"])
    async def status(request: Request):
        build = store.get(request.path_params["build_id"])
        if build is None:
            return JSONResponse({"error": "No such build."}, status_code=404)
        with store.lock:  # the worker thread updates this dict while it plans
            data = json.loads(json.dumps(snapshot(build, user_from_request(request))))
        return JSONResponse(data)

    @mcp.custom_route("/api/build/{build_id}/commit", methods=["POST"])
    async def commit(request: Request):
        if not code_ok(request):
            return JSONResponse({"error": "Wrong or missing demo code."}, status_code=401)
        build = store.get(request.path_params["build_id"])
        if build is None:
            return JSONResponse({"error": "No such build."}, status_code=404)
        if not may_commit(build, user_from_request(request)):
            return JSONResponse({"error": READY_NOTE if build.get("ready") else NOT_OWNER}, status_code=403)
        if build["status"] != "done":
            return JSONResponse({"error": "This build isn't ready for commits yet."}, status_code=409)
        body = await body_of(request)
        step = body.get("step")
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < len(build["internal"]["plan"]["steps"]):
            return JSONResponse({"error": "step must be a step index from this build."}, status_code=400)
        try:
            photos = await asyncio.to_thread(parse_photos, body.get("photos"), True)
        except BadRequest as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        note = str(body.get("note") or "").strip()[:1500]
        try:
            return JSONResponse(await asyncio.to_thread(store.commit, build, step, photos, note))
        except Exception as e:
            print("[bench] commit on build", build["id"], "failed:", hide(str(e))[:900], flush=True)
            return JSONResponse({"error": "Something went wrong while checking. Wait a minute and commit again."}, status_code=502)

    @mcp.custom_route("/api/build/{build_id}/summary", methods=["POST"])
    async def summary(request: Request):
        """The owner rewrites the short summary under the build's title (at most 3 lines on the page)."""
        build = store.get(request.path_params["build_id"])
        if build is None or not build.get("plan"):
            return JSONResponse({"error": "No such build."}, status_code=404)
        if not may_commit(build, user_from_request(request)):
            return JSONResponse({"error": READY_NOTE if build.get("ready") else NOT_OWNER}, status_code=403)
        text = " ".join(str((await body_of(request)).get("summary") or "").split())
        if not 3 <= len(text) <= SUMMARY_MAX:
            return JSONResponse({"error": f"Write the summary in 3 to {SUMMARY_MAX} characters."}, status_code=400)
        store.update(build, plan={**build["plan"], "summary": text})
        return JSONResponse({"summary": text})

    @mcp.custom_route("/api/build/{build_id}/report", methods=["POST"])
    async def report(request: Request):
        """Anyone viewing a guide can say a step is wrong ("the LED is in the wrong row"). Reports go to
        <out_dir>/.reports/reports.jsonl (never served: the viewer skips dot folders) for a person to review."""
        build = store.get(request.path_params["build_id"])
        if build is None or not build.get("plan"):
            return JSONResponse({"error": "No such build."}, status_code=404)
        body = await body_of(request)
        step = body.get("step")
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < len(build["plan"]["steps"]):
            return JSONResponse({"error": "step must be a step index from this build."}, status_code=400)
        text = " ".join(str(body.get("text") or "").split())[:REPORT_MAX]
        if len(text) < 3:
            return JSONResponse({"error": "Say what's wrong with this step."}, status_code=400)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        if not store.allow_report(ip):
            return JSONResponse({"error": "You've sent a lot of reports; try again in a while."}, status_code=429)
        user = user_from_request(request)
        store.add_report({"time": now_iso(), "build": build["id"], "ready": bool(build.get("ready")), "step": step,
                          "step_title": build["plan"]["steps"][step].get("title", ""), "text": text, "user": user and user["id"]})
        return JSONResponse({"ok": True}, status_code=201)

    @mcp.custom_route("/api/build/{build_id}/copy", methods=["POST"])
    async def copy(request: Request):
        build = store.get(request.path_params["build_id"])
        if build is None or build["status"] != "done" or not build.get("plan"):
            return JSONResponse({"error": "No finished build to copy."}, status_code=404)
        return JSONResponse({"id": store.copy(build, user_from_request(request))}, status_code=201)
