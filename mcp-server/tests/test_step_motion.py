"""The step animation's motion frames (export.motion_frames): rendered with the step picture's own camera,
new parts easing in along the way they go, screws turning down their axis, wires left out until the end."""
import runpy
import sys

import numpy as np
import pytest

pytest.importorskip("physical_studio.library")

from PIL import Image  # noqa: E402

from physical_studio import export  # noqa: E402
from physical_studio.render import render  # noqa: E402

SIZE = (640, 480)


@pytest.fixture(scope="module")
def light(tmp_path_factory):
    out = tmp_path_factory.mktemp("motion")
    sys.argv = ["traffic_light.py", str(out)]
    studio = runpy.run_path("examples/traffic_light.py", run_name="__main__")["studio"]
    built = studio.build()
    doc = export.steps_document(studio.design, built, "design.glb")
    export.step_pictures(built, doc, out, motion=True)
    return built, doc, out


def frames_of(built, entry, shown):
    new = set(entry["add"]) & set(built.pieces)
    visible = (shown | new) - ({"lid"} if "lid" not in new else set())
    stats = {}
    render(built, entry["picture_view"], visible, None, new, size=(160, 120), labels=False, stats=stats)
    return new, visible, export.motion_frames(built, entry, visible, new, entry["picture_view"], stats["camera"], (160, 120))


def test_a_fixed_camera_keeps_the_framing_however_far_a_part_is_moved(light):
    built, doc, _ = light
    ids = set(built.pieces)
    some = next(iter(ids))
    stats, moved, fixed = {}, {}, {}
    render(built, "iso", ids, None, None, size=(160, 120), labels=False, stats=stats)
    render(built, "iso", ids, {some: np.array([0, 0, 300.0])}, None, size=(160, 120), labels=False, stats=moved)
    render(built, "iso", ids, {some: np.array([0, 0, 300.0])}, None, size=(160, 120), labels=False, stats=fixed, camera=stats["camera"])
    assert moved["camera"] != stats["camera"]  # fitting the moved part would zoom out
    assert fixed["camera"] == stats["camera"]


def test_new_parts_start_offset_and_ease_into_place_screws_turning_down_their_axis(light):
    built, doc, _ = light
    shown, seen_screw, seen_part = set(), False, False
    for entry in doc["steps"]:
        new, visible, frames = frames_of(built, entry, shown)
        shown |= new
        moving = {pid for pid in new if built.pieces[pid].kind != "wire"}
        wires = new - moving
        assert len(frames) == (export.MOTION_FRAMES if moving else 0) + (1 if wires else 0)
        for f in frames:
            assert not (f["visible"] & wires) and visible - wires <= f["visible"]  # earlier parts stay, new wires wait
            assert set(f["offsets"]) <= moving  # nothing earlier moves
        motion = frames[: export.MOTION_FRAMES] if moving else []
        for pid in moving:
            lengths = [float(np.linalg.norm(f["offsets"][pid])) for f in motion]
            assert lengths[0] > 0 and all(a > b for a, b in zip(lengths, lengths[1:]))  # sliding in, slowing down
            assert lengths[-1] < 0.1 * lengths[0]
            piece = built.pieces[pid]
            if piece.kind == "fastener":
                seen_screw = True
                assert motion[0]["offsets"][pid] @ piece.matrix[:3, 2] > 0  # above its hole, along its axis
                turns = [f["turns"][pid] for f in motion]
                assert all(a > b for a, b in zip(turns, turns[1:])) and turns[-1] > 0 and turns[0] % 90
            elif not (entry.get("motion") or export.AXIAL.search(f"{piece.part_id} {piece.name}")):
                seen_part = True
                off = motion[0]["offsets"][pid]
                assert off[2] > 0 and abs(off[0]) < 1e-9 and abs(off[1]) < 1e-9  # straight down from above
        if wires and frames:
            assert frames[-1]["offsets"] == {}  # the seated frame: parts in, wires still to draw
    assert seen_screw and seen_part


def test_round_parts_slide_along_their_own_axis():
    assert export.round_axis(np.array([22.0, 22.0, 7.0])) == 2  # a 608 bearing: the bore runs along z
    assert export.round_axis(np.array([10.0, 48.0, 10.0])) == 1  # a shaft lying along y
    assert export.AXIAL.search("bearing-608zz") and export.AXIAL.search("shaft-10-48") and not export.AXIAL.search("arduino-uno")


def test_step_pictures_write_a_small_sprite_of_frames_beside_each_picture(light):
    built, doc, out = light
    with_frames = [s for s in doc["steps"] if s.get("picture_frames")]
    assert with_frames
    for s in with_frames:
        f = s["picture_frames"]
        sprite = Image.open(out / f["file"])
        assert f["file"] == s["picture"].replace(".png", "-motion.png")
        assert sprite.size == (SIZE[0] * f["count"], SIZE[1]) and Image.open(out / s["picture"]).size == SIZE
        assert (out / f["file"]).stat().st_size < 90_000 * f["count"]
        assert f["seated"] == any(built.pieces[p].kind == "wire" for p in s["add"] if p in built.pieces)
