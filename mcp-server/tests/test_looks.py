import asyncio
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from physical_studio import looks
from physical_studio.accounts import Accounts, KeyVerifier, key_hash
from physical_studio.server import Studio

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def studio(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    shutil.copy(REPO / "parts" / "arduino-uno.json", parts)
    s = Studio(parts, tmp_path / "out")
    s.new_design("Look test")
    s.place_part("arduino-uno", (0, 0, 0), id="uno")
    return s


def test_set_part_look_colours_the_part_and_textures_its_top(studio, monkeypatch, tmp_path):
    photo = Image.new("RGB", (686, 534), "#0a5a8a")  # same aspect as the Uno's 68.6 x 53.4 top
    monkeypatch.setattr("physical_studio.server.fetch_image", lambda url: photo)
    out = studio.set_part_look("arduino-uno", color="#0a5a8a", roughness=0.5, top_image_url="https://example.com/uno.jpg")
    assert out["appearance"]["color"] == "#0a5a8a" and "warning" not in out
    assert studio.build().pieces["uno"].color == "#0a5a8a"
    studio.export(["glb"], str(tmp_path / "x"))
    glb = (tmp_path / "x" / "design.glb").read_bytes()
    assert b"uno-top" in glb  # the textured top face is its own child node
    assert (tmp_path / "x" / "design.png").exists()


def test_set_part_look_warns_about_a_stretched_photo(studio, monkeypatch):
    monkeypatch.setattr("physical_studio.server.fetch_image", lambda url: Image.new("RGB", (100, 400)))
    assert "stretched" in studio.set_part_look("arduino-uno", top_image_url="https://example.com/a.jpg")["warning"]


def test_new_design_forgets_looks(studio):
    studio.set_part_look("arduino-uno", color="red")
    studio.new_design("Next")
    assert studio.looks == {}


def test_trim_removes_a_plain_background():
    img = Image.new("RGB", (200, 100), "white")
    img.paste(Image.new("RGB", (120, 60), "green"), (40, 20))
    assert looks.trim(img).size == (120, 60)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/a.png", "http://169.254.169.254/latest"])
def test_fetch_refuses_local_addresses(url):
    with pytest.raises(looks.LookError):
        looks.fetch_image(url)


def test_keys_are_stored_hashed_and_verified(tmp_path):
    accounts = Accounts(tmp_path)
    key = accounts.mint()
    assert key.startswith("ps_") and accounts.known(key) and not accounts.known("ps_nope")
    assert key not in (tmp_path / ".accounts" / "keys.json").read_text()
    verifier = KeyVerifier("team-secret", accounts)
    assert asyncio.run(verifier.verify_token(key)).client_id == f"key:{key_hash(key)[:12]}"
    assert asyncio.run(verifier.verify_token("team-secret")).client_id == "team"
    assert asyncio.run(verifier.verify_token("wrong")) is None


def test_projects_are_recorded_per_owner(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.record("abc", {"design": "out/a", "title": "A"})
    accounts.record("abc", {"design": "out/b", "title": "B"})
    accounts.record("abc", {"design": "out/a", "title": "A again"})
    assert [p["title"] for p in accounts.projects("abc")] == ["A again", "B"]
    assert accounts.projects("other") == []
    json.loads((tmp_path / ".accounts" / "projects-abc.json").read_text())
