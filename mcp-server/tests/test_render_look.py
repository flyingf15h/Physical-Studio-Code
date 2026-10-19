import numpy as np
import pytest

pytest.importorskip("physical_studio.library")

from physical_studio.geometry import part_finish  # noqa: E402
from physical_studio.render import ambient_occlusion  # noqa: E402


def test_a_flat_surface_is_never_darkened_however_it_slopes():
    y, x = np.mgrid[0:200, 0:200].astype(float)
    hit = np.ones((200, 200), dtype=bool)
    for slope in (0.0, 0.3, 2.0):
        assert ambient_occlusion(100 + slope * x + 0.5 * slope * y, hit, scale=1.0).min() > 0.999


def test_the_floor_next_to_a_standing_part_darkens_but_its_far_side_does_not():
    z = np.full((200, 200), 100.0)
    z[:, 100:] = 98.0  # a block standing nearer the camera on the right half (within the 3 mm reach here)
    occ = ambient_occlusion(z, np.ones_like(z, dtype=bool), scale=1.0)
    assert occ[100, 99] < 0.9 and occ[100, 98] < occ[100, 96]  # floor at the block's foot, fading away from it
    assert occ[100, 20] > 0.999 and occ[100, 150] > 0.999  # open floor, and the block's own face


def test_something_far_in_front_casts_no_halo():
    z = np.full((200, 200), 100.0)
    z[:, 100:] = 0.0  # an arm 100 mm in front of the plate
    occ = ambient_occlusion(z, np.ones_like(z, dtype=bool), scale=1.0)
    assert occ[100, 97] > 0.999


def test_the_background_does_not_darken_silhouettes():
    z = np.full((200, 200), 100.0)
    hit = np.zeros_like(z, dtype=bool)
    hit[50:150, 50:150] = True
    assert ambient_occlusion(z, hit, scale=1.0)[hit].min() > 0.999


def test_finishes_come_from_the_look_then_the_material_then_the_kind_of_part():
    assert part_finish({"appearance": {"metallic": 0.9, "roughness": 0.3}}) == (0.9, 0.3)
    assert part_finish({"appearance": {"material": "chrome"}}) == (0.8, 0.2)
    assert part_finish({"category": "fastener"}) == (0.6, 0.6)
    assert part_finish({"category": "board"}) == (0.0, 0.6)
