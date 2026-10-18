"""Physical Studio accounts: email + password sign-up and login, sessions, and saved projects.

Passwords are stored as scrypt hashes with a per-user salt; sessions are random tokens of which
only a hash is stored. Everything lives in <OUT_DIR>/.accounts/ (never served: the viewer refuses
dot paths). The browser keeps its session token and sends it as `Authorization: Bearer sess_...`.

Guest mode: POST /api/auth/guest makes a guest (no email or password) with its own session, so a
visitor can save projects and upload a BOM without signing up. Signing up while in guest mode turns
that guest into the new account, keeping its id, so its projects, parts and builds come along.

Other modules use user_from_request(request) to find who is calling (None when signed out).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

SESSION_PREFIX = "sess_"
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")
MIN_PASSWORD = 8
SESSION_DAYS = 30
_lock = threading.Lock()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _scrypt(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


class Users:
    def __init__(self, out_dir: Path):
        self.dir = out_dir / ".accounts"

    # --- storage ---------------------------------------------------------------------------------

    def _read(self, name: str, default):
        try:
            return json.loads((self.dir / name).read_text())
        except (OSError, ValueError):
            return default

    def _write(self, name: str, data) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{name}.tmp"
        tmp.write_text(json.dumps(data))
        tmp.replace(self.dir / name)  # atomic, so a crash never leaves half a file

    # --- accounts --------------------------------------------------------------------------------

    def guest(self) -> tuple[str, dict]:
        user = {"id": secrets.token_hex(8), "email": "", "name": "Guest", "guest": True, "created": int(time.time())}
        with _lock:
            users = self._read("users.json", {})
            users[f"guest:{user['id']}"] = user
            self._write("users.json", users)
        return self._new_session(user), self.public(user)

    def signup(self, email: str, password: str, name: str = "", guest: dict | None = None) -> tuple[str, dict]:
        """guest: the signed-in guest, if any; the account takes over its id (and so its projects)."""
        email = email.strip().lower()
        if not EMAIL.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
        with _lock:
            users = self._read("users.json", {})
            if email in users:
                raise ValueError("There's already an account with that email. Log in instead.")
            salt = secrets.token_bytes(16)
            if guest and guest.get("guest"):
                users.pop(f"guest:{guest['id']}", None)
            user = {
                "id": guest["id"] if guest and guest.get("guest") else secrets.token_hex(8),
                "email": email,
                "name": (name.strip() or email.split("@")[0])[:60],
                "salt": salt.hex(),
                "password": _scrypt(password, salt),
                "created": int(time.time()),
            }
            users[email] = user
            self._write("users.json", users)
        return self._new_session(user), self.public(user)

    def login(self, email: str, password: str) -> tuple[str, dict]:
        user = self._read("users.json", {}).get(email.strip().lower())
        if not user or not hmac.compare_digest(_scrypt(password, bytes.fromhex(user["salt"])), user["password"]):
            raise ValueError("That email and password don't match.")
        return self._new_session(user), self.public(user)

    def _new_session(self, user: dict) -> str:
        token = SESSION_PREFIX + secrets.token_urlsafe(32)
        with _lock:
            sessions = self._read("sessions.json", {})
            now = time.time()
            sessions = {k: v for k, v in sessions.items() if v["expires"] > now}  # drop expired ones
            key = f"guest:{user['id']}" if user.get("guest") else user["email"]
            sessions[_hash(token)] = {"user": key, "expires": now + SESSION_DAYS * 86400}
            self._write("sessions.json", sessions)
        return token

    def logout(self, token: str) -> None:
        with _lock:
            sessions = self._read("sessions.json", {})
            if sessions.pop(_hash(token), None) is not None:
                self._write("sessions.json", sessions)

    def user_for(self, token: str) -> dict | None:
        if not token.startswith(SESSION_PREFIX):
            return None
        session = self._read("sessions.json", {}).get(_hash(token))
        if not session or session["expires"] < time.time():
            return None
        user = self._read("users.json", {}).get(session["user"])
        return self.public(user) if user else None

    @staticmethod
    def public(user: dict) -> dict:
        return {"id": user["id"], "email": user["email"], "name": user["name"], "guest": bool(user.get("guest"))}

    # --- saved projects --------------------------------------------------------------------------

    def projects(self, user_id: str) -> list[dict]:
        return self._read(f"saved-{user_id}.json", [])

    def save_project(self, user_id: str, project: dict) -> dict:
        design = str(project.get("design", ""))
        if not re.fullmatch(r"(build/[\w-]{1,40}|out/[\w-]{1,80}|[\w-]{1,80})", design):
            raise ValueError("Unknown project.")
        entry = {
            "design": design,
            "title": str(project.get("title", ""))[:120] or "Untitled project",
            "prompt": str(project.get("prompt", ""))[:500],
            "steps": int(project.get("steps") or 0),
            "updated": int(time.time()),
        }
        with _lock:
            mine = [p for p in self.projects(user_id) if p["design"] != design]
            self._write(f"saved-{user_id}.json", [entry, *mine][:200])
        return entry

    def forget_project(self, user_id: str, design: str) -> None:
        with _lock:
            self._write(f"saved-{user_id}.json", [p for p in self.projects(user_id) if p["design"] != design])


def bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


_users: Users | None = None


def user_from_request(request: Request) -> dict | None:
    """The signed-in user making this request ({id, email, name}), or None."""
    return _users.user_for(bearer(request)) if _users else None


LOGINS_PER_MINUTE = 10
_attempts: dict[str, list[float]] = {}


def _too_many(request: Request) -> bool:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < 60]
    _attempts[ip] = [*recent, now]
    return len(recent) >= LOGINS_PER_MINUTE


def register_user_routes(mcp, out_dir: Path) -> Users:
    global _users
    users = _users = Users(out_dir)

    async def body(request: Request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def fail(message: str, status: int = 400):
        return JSONResponse({"error": message}, status_code=status)

    @mcp.custom_route("/api/auth/signup", methods=["POST"])
    async def signup(request: Request):
        if _too_many(request):
            return fail("Too many attempts. Wait a minute and try again.", 429)
        b = await body(request)
        try:
            token, user = users.signup(
                str(b.get("email", "")), str(b.get("password", "")), str(b.get("name", "")), user_from_request(request)
            )
        except ValueError as e:
            return fail(str(e))
        return JSONResponse({"token": token, "user": user})

    @mcp.custom_route("/api/auth/login", methods=["POST"])
    async def login(request: Request):
        if _too_many(request):
            return fail("Too many attempts. Wait a minute and try again.", 429)
        b = await body(request)
        try:
            token, user = users.login(str(b.get("email", "")), str(b.get("password", "")))
        except ValueError as e:
            return fail(str(e), 401)
        return JSONResponse({"token": token, "user": user})

    @mcp.custom_route("/api/auth/guest", methods=["POST"])
    async def guest(request: Request):
        if _too_many(request):
            return fail("Too many attempts. Wait a minute and try again.", 429)
        token, user = users.guest()
        return JSONResponse({"token": token, "user": user})

    @mcp.custom_route("/api/auth/logout", methods=["POST"])
    async def logout(request: Request):
        users.logout(bearer(request))
        return JSONResponse({})

    @mcp.custom_route("/api/auth/me", methods=["GET"])
    async def me(request: Request):
        user = user_from_request(request)
        return JSONResponse({"user": user}) if user else fail("Not logged in.", 401)

    @mcp.custom_route("/api/projects", methods=["GET", "POST"])
    async def projects(request: Request):
        user = user_from_request(request)
        if not user:
            return fail("Log in to save projects.", 401)
        if request.method == "GET":
            return JSONResponse(users.projects(user["id"]))
        try:
            return JSONResponse(users.save_project(user["id"], await body(request)))
        except ValueError as e:
            return fail(str(e))

    @mcp.custom_route("/api/projects/forget", methods=["POST"])
    async def forget(request: Request):
        user = user_from_request(request)
        if not user:
            return fail("Log in first.", 401)
        users.forget_project(user["id"], str((await body(request)).get("design", "")))
        return JSONResponse({})

    return users
