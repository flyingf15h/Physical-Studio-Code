import json
import runpy
import sys

import pytest

pytest.importorskip("physical_studio.library")

from physical_studio.bench.reference import reference_images  # noqa: E402


def test_export_writes_a_picture_per_step_and_the_check_can_load_it(tmp_path):
    sys.argv = ["traffic_light.py", str(tmp_path)]
    runpy.run_path("examples/traffic_light.py", run_name="__main__")
    doc = json.loads((tmp_path / "design.steps.json").read_text())
    pictures = [s["picture"] for s in doc["steps"]]
    assert pictures == [f"step-{i:02d}.png" for i in range(1, len(doc["steps"]) + 1)]
    assert all((tmp_path / p).stat().st_size > 1000 for p in pictures)
    first, last = reference_images(tmp_path, 0), reference_images(tmp_path, len(pictures) - 1)
    assert len(first) == 1 and first[0].size == (640, 480) and len(last) == 1
    assert reference_images(tmp_path, 99) == [] and reference_images(tmp_path / "nope", 0) == []
