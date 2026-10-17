"""Personal connection keys for the hosted MCP server, and the projects each key has exported.

Anyone can get a key on screen 1 (POST /api/connect, a few per hour per address). Their own AI
(Claude Code, Claude Desktop, Cursor, ...) then connects to /mcp with it. Each key gets its own
design workspace and its own export folders, so visitors don't overwrite each other. Only a hash of
each key is stored, in <OUT_DIR>/.accounts/.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from fastmcp.server.auth import AccessToken, TokenVerifier

KEY_PREFIX = "ps_"
_lock = threading.Lock()


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class Accounts:
    def __init__(self, out_dir: Path):
        self.dir = out_dir / ".accounts"

    def _keys_file(self) -> Path:
        return self.dir / "keys.json"

    def _load_keys(self) -> dict:
        try:
            return json.loads(self._keys_file().read_text())
        except (OSError, ValueError):
            return {}

    def mint(self) -> str:
        key = KEY_PREFIX + secrets.token_urlsafe(24)
        with _lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            keys = self._load_keys()
            keys[key_hash(key)] = {"created": int(time.time())}
            self._keys_file().write_text(json.dumps(keys))
        return key

    def known(self, key: str) -> bool:
        return key.startswith(KEY_PREFIX) and key_hash(key) in self._load_keys()

    def _projects_file(self, owner: str) -> Path:
        return self.dir / f"projects-{owner}.json"

    def projects(self, owner: str) -> list[dict]:
        try:
            return json.loads(self._projects_file(owner).read_text())
        except (OSError, ValueError):
            return []

    def record(self, owner: str, project: dict) -> None:
        with _lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            mine = [p for p in self.projects(owner) if p.get("design") != project["design"]]
            self._projects_file(owner).write_text(json.dumps([{**project, "at": int(time.time())}, *mine][:100]))


def owner_of(client_id: str | None) -> str:
    """Short, filesystem-safe id for whoever is calling: a key's hash prefix, or 'team' / 'local'."""
    if not client_id:
        return "local"
    return client_id.split(":", 1)[1] if client_id.startswith("key:") else client_id


class KeyVerifier(TokenVerifier):
    """Accepts the team's MCP_TOKEN and every personal key minted by Accounts."""

    def __init__(self, team_token: str, accounts: Accounts):
        super().__init__()
        self.team_token = team_token
        self.accounts = accounts

    async def verify_token(self, token: str) -> AccessToken | None:
        if secrets.compare_digest(token, self.team_token):
            return AccessToken(token=token, client_id="team", scopes=[])
        if self.accounts.known(token):
            return AccessToken(token=token, client_id=f"key:{key_hash(token)[:12]}", scopes=[])
        return None
