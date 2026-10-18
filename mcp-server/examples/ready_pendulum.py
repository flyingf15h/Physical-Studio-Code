"""Rebuilds the build page's ready-made double inverted pendulum guide (physicalstudio.work/build/double-pendulum)
from the real CAD design in examples/double_pendulum.py: real parts, mechanical steps grouped into sections, a
reference picture and a 3D model after every step, and photo checks against those pictures.

    uv run python examples/ready_pendulum.py
"""

import runpy
import shutil
import sys
import tempfile
from pathlib import Path

from physical_studio.bench.cad_guide import write_build

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "physical_studio" / "bench" / "ready" / "double-pendulum"
SUMMARY = ("A cart on a linear rail balances two hinged arms upright. A 12 V gearmotor drives the cart through a rack and "
           "pinion, two AS5600 encoders read the joint angles, two VL53L0X sensors track the cart, and a Teensy 4.1 runs the loop.")
# (first step, section) in step order; each runs until the next one starts.
SECTIONS = [(1, "Base and rail"), (6, "Cart and drive motor"), (9, "Cart joint and encoder"), (17, "Elbow joint and encoder"),
            (23, "Distance sensors"), (25, "Electronics"), (28, "Wiring")]


def main():
    sys.argv = ["double_pendulum.py", tempfile.mkdtemp()]
    ns = runpy.run_path(str(HERE / "double_pendulum.py"), run_name="__main__")
    studio = ns["studio"]
    for n, step in enumerate(studio.design.steps, 1):
        step.section = next(name for first, name in reversed(SECTIONS) if n >= first)
    if OUT.exists():
        shutil.rmtree(OUT)
    build = write_build(studio, OUT, "double-pendulum", ns["PROMPT"], SUMMARY, "2026-10-18T00:00:00+00:00")
    print(f"wrote {len(build['plan']['steps'])} steps to {OUT}")


if __name__ == "__main__":
    main()
