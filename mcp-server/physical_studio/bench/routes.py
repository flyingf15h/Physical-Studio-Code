# Senna's Build helper as HTTP routes for the main site (new for the merge; the logic is in planner.py,
# ported from circuit-studio/builder.py at 21a4f23). A build is: optional bench photos and typed
# connections -> scan (commit #0) -> checked plan with a picture and a 3D model per step -> photo commits
# on any step, each checked by the AI and given its own 3D model.
#
#   POST /api/build                {goal, have?, known?, photos?: [data URL]}  -> 202 {id}
#   GET  /api/build/<id>           status, stage, plan, commits (see snapshot())
#   POST /api/build/<id>/commit    {step, photos: [data URL], note?}           -> 200 the new commit
#
# Files go to <out_dir>/build-<id>/ and are served by the viewer at /out/build-<id>/<file>. build.json is
# rewritten after every change, so a build and its commits survive a reload or a restart.
import asyncio, base64, binascii, json, os, re, threading, time, uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse
from . import diagram, planner
from .pool import hide

BUILDS_PER_HOUR = int(os.environ.get("BUILDS_PER_HOUR", "4"))
MAX_PHOTOS = planner.MAX_PHOTOS
MAX_BYTES = 40 * 1024 * 1024
BUILD_ID = re.compile(r"[0-9a-f]{12}")
DATA_URL = re.compile(r"data:image/(jpeg|jpg|png|webp);base64,(.+)", re.S)
FAILED = "Something went wrong while planning. Wait a minute and try again."


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


class BuildStore:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.builds = {}  # id -> build dict (public fields + "internal")
        self.lock = threading.Lock()
        self.commit_locks = defaultdict(threading.Lock)
        self.recent = defaultdict(list)

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
        if not BUILD_ID.fullmatch(bid or ""):
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

    def start(self, goal, have, known, photos):
        bid = uuid.uuid4().hex[:12]
        build = {"id": bid, "status": "scanning" if photos or known.strip() else "planning", "stage": "Starting your build.",
                 "error": None, "goal": goal, "have": have, "known": known, "created": now_iso(), "plan": None, "commits": [], "internal": {}}
        with self.lock:
            self.builds[bid] = build
        self.save(build)
        threading.Thread(target=self.run, args=(build, photos), daemon=True).start()
        return bid

    def run(self, build, photos):
        bid = build["id"]
        try:
            result = planner.make_plan(build["goal"], build["have"], build["known"], photos,
                                       stage=lambda status, text: self.update(build, status=status, stage=text))
            self.update(build, plan=self.publish(bid, result), commits=[self.start_commit(bid, build, result, photos)],
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
                "code": plan["code"], "safety": plan["safety"],
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
            c = planner.commit_step(build["internal"]["plan"], step, photos, note)
            cid = planner.new_id(bid, step, note)
            commit = {"id": cid, "kind": "step", "step": step, "message": note, "time": now_iso(),
                      "images": [self.write(bid, f"img-{cid}-{k + 1}.jpg", planner.jpeg(b, 1024)) for k, b in enumerate(photos)],
                      "verdict": c["verdict"], "model": None, "guide": c["guide"],
                      "parent": build["commits"][-1]["id"] if build["commits"] else None}
            if c["model"]:
                commit["model"] = {"glb": self.write(bid, f"commit-{cid}.glb", c["model"]["glb"]), "labels": c["model"]["labels"]}
            self.update(build, commits=build["commits"] + [commit])
            return commit


def snapshot(build):
    return {k: v for k, v in build.items() if k not in ("internal", "have")}


def register_build_routes(mcp, out_dir: Path, parts_dir: Path):
    planner.configure(parts_dir)
    store = BuildStore(out_dir)

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
        return JSONResponse({"id": store.start(goal, have, known, photos)}, status_code=202)

    @mcp.custom_route("/api/build/{build_id}", methods=["GET"])
    async def status(request: Request):
        build = store.get(request.path_params["build_id"])
        if build is None:
            return JSONResponse({"error": "No such build."}, status_code=404)
        with store.lock:  # the worker thread updates this dict while it plans
            data = json.loads(json.dumps(snapshot(build)))
        return JSONResponse(data)

    @mcp.custom_route("/api/build/{build_id}/commit", methods=["POST"])
    async def commit(request: Request):
        if not code_ok(request):
            return JSONResponse({"error": "Wrong or missing demo code."}, status_code=401)
        build = store.get(request.path_params["build_id"])
        if build is None:
            return JSONResponse({"error": "No such build."}, status_code=404)
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
