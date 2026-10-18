"""Detailed shapes for the double pendulum's mechanical parts, so the guide's renders read as the real
thing: rail grooves and counterbored bolt holes, a carriage with black end caps and a grease nipple,
a grooved aluminium riser, rounded plates and arms with their bolt holes, a motor with a black can
over a steel gearbox.

    uv run python examples/pendulum_shapes.py

Each shape keeps its part's body size and origin (so the design's positions don't move) and is
written as parts/<id>.step. Pieces in a second material are accents (parts/<id>.accent-N.step, listed
in the part's appearance.accents) and are drawn as children of the part in the guide's GLB only; fit
checks use the main shape. Only step_file and appearance.accents in each part's JSON are touched.
"""

import json
from pathlib import Path

from build123d import Align, Axis, Box, Cylinder, Location, Rot, export_step, fillet

PARTS = Path(__file__).resolve().parents[2] / "parts"
MIN = (Align.MIN, Align.MIN, Align.MIN)
UP = (Align.CENTER, Align.CENTER, Align.MIN)


def at(shape, x, y, z):
    return shape.moved(Location((x, y, z)))


def hole_z(d, depth, x, y, top):
    """A hole drilled down from z = top."""
    return at(Cylinder(d / 2, depth + 0.5, align=UP), x, y, top - depth)


def round_z(box, r):
    """Round the vertical edges of a box."""
    return fillet(box.edges().filter_by(Axis.Z), r)


def rail():
    """HGR20: 400 x 20 x 17.5 with the side grooves the balls run in and M5 counterbores every 60 mm."""
    s = Box(400, 20, 17.5, align=MIN)
    for y in (0, 18.2):  # two grooves per side
        s -= at(Box(400, 1.8, 3.2, align=MIN), 0, y, 8.2)
        s -= at(Box(400, 1.8, 2.0, align=MIN), 0, y, 12.8)
    s = fillet(s.edges().filter_by(Axis.X).group_by(Axis.Z)[-1], 0.8)
    for x in range(20, 400, 60):
        s -= hole_z(9.5, 5.3, x, 10, 17.5) + hole_z(5.5, 17.5, x, 10, 17.5)
    return s


def carriage():
    """HGH20CA: the steel body between its end caps, with 4 tapped M5 holes on top; the caps are accents."""
    body = at(Box(47.4, 44, 25.4, align=MIN), 7, 0, 0) - at(Box(47.4, 20, 12.9, align=MIN), 7, 12, 0)
    body = fillet(body.edges().filter_by(Axis.X).group_by(Axis.Z)[-1], 1.2)
    for x in (13.9, 47.5):
        for y in (6, 38):
            body -= hole_z(4.2, 7, x, y, 25.4)
    caps = None
    for x0 in (0, 54.4):
        cap = at(Box(7, 43, 23.4, align=MIN), x0, 0.5, 1) - at(Box(7, 21, 12.9, align=MIN), x0, 11.5, 0)
        caps = cap if caps is None else caps + cap
    # Fit checks only see the main shape, so it keeps the caps' volume too, just inside the drawn caps.
    for x0 in (0.2, 54.6):
        body += at(Box(6.6, 42.6, 22.9, align=MIN), x0, 0.7, 1.2) - at(Box(6.6, 21.4, 12.9, align=MIN), x0, 11.3, 0)
    seals = at(Box(1, 43.6, 24, align=MIN), -0.6, 0.2, 0.7) - at(Box(1, 20.6, 12.9, align=MIN), -0.6, 11.7, 0)
    seals += at(Box(1, 43.6, 24, align=MIN), 61.0, 0.2, 0.7) - at(Box(1, 20.6, 12.9, align=MIN), 61.0, 11.7, 0)
    nipple = at(Cylinder(2.2, 4, rotation=(0, 90, 0), align=(Align.MIN, Align.CENTER, Align.CENTER)), 61.4, 22, 18)
    return body, [(caps, "rubber", None), (seals, "rubber", "#b3262b"), (nipple, "brass", None)]


def riser():
    """A 10 x 19 aluminium bar with a long slot on its outer face and rounded top edges."""
    s = Box(400, 10, 19, align=MIN)
    s = fillet(s.edges().filter_by(Axis.X).group_by(Axis.Z)[-1], 1.5)
    s -= at(Box(400, 1.6, 5, align=MIN), 0, 8.4, 7)
    for x in range(20, 400, 60):
        s -= hole_z(5.5, 19, x, 5, 19)
    return s


def plate(lx, ly, t, r, holes):
    s = round_z(Box(lx, ly, t, align=MIN), r)
    for x, y, d in holes:
        s -= hole_z(d, t, x, y, t)
    return s


def motor():
    """37 mm gearmotor: a steel gearbox and output shaft (the part), a black can with terminals (accents)."""
    gearbox = at(Cylinder(18.5, 22, align=UP), 18.5, 18.5, 17) + at(Cylinder(3, 17, align=UP), 18.5, 18.5, 0)
    gearbox += at(Cylinder(6, 3, align=UP), 18.5, 18.5, 14)  # the bearing boss
    for x, y in ((6, 18.5), (31, 18.5)):
        gearbox -= hole_z(3, 4, x, y, 21)  # M3 face holes
    can = at(Cylinder(17.8, 33, align=UP), 18.5, 18.5, 39) - at(Cylinder(18.6, 0.8, align=UP), 18.5, 18.5, 50)
    can -= at(Cylinder(18.6, 0.8, align=UP), 18.5, 18.5, 61)
    gearbox += at(Cylinder(17.6, 32.8, align=UP), 18.5, 18.5, 39.1)  # the can's volume, for fit checks
    tabs = at(Box(2.5, 1, 5, align=UP), 12, 18.5, 70) + at(Box(2.5, 1, 5, align=UP), 25, 18.5, 70)
    return gearbox, [(can, "black-anodised", None), (tabs, "brass", None)]


def arm(holes):
    s = fillet(Box(30, 8, 210, align=MIN).edges().filter_by(Axis.Y), 5)
    for z, d in holes:
        s -= at(Cylinder(d / 2, 9, rotation=(-90, 0, 0), align=UP), 15, -0.5, z)
    s -= at(Cylinder(1.6, 9, rotation=(-90, 0, 0), align=UP), 15, -0.5, 30)  # clamp screw
    return s


def block(lx, ly, lz, r, bore=None):
    s = fillet(Box(lx, ly, lz, align=MIN).edges().filter_by(Axis.Y), r)
    if bore:
        d, x, z = bore
        s -= at(Cylinder(d / 2, ly + 1, rotation=(-90, 0, 0), align=UP), x, -0.5, z)
    return s


SHAPES = {
    "hgr20-rail-400": lambda: (rail(), []),
    "hgh20ca-block": carriage,
    "rack-riser-400": lambda: (riser(), []),
    "base-plate-500": lambda: (plate(500, 115, 10, 6, [(x, y, 5.5) for x in (12, 488) for y in (12, 103)]), []),
    "cart-plate": lambda: (plate(120, 90, 6, 5, [(60, 75, 9)] + [(x, y, 5.5) for x in (43.2, 76.8) for y in (19, 51)]), []),
    "dc-gearmotor-12v-37": motor,
    "arm-lower-210": lambda: (arm([(15, 10), (195, 19)]), []),
    "arm-upper-210": lambda: (arm([(15, 10)]), []),
    "pivot-block": lambda: (block(30, 20, 30, 3, (19, 15, 15)), []),
    "encoder-mount": lambda: (block(30, 6.5, 30, 3, (12, 15, 15)), []),
    "tof-bracket": lambda: (block(10, 30, 35, 2), []),
}


def main():
    for pid, make in SHAPES.items():
        shape, accents = make()
        export_step(shape, str(PARTS / f"{pid}.step"))
        listed = []
        for i, (piece, material, color) in enumerate(accents):
            name = f"{pid}.accent-{i}.step"
            export_step(piece, str(PARTS / name))
            listed.append({"step_file": name, "material": material, **({"color": color} if color else {})})
        f = PARTS / f"{pid}.json"
        data = json.loads(f.read_text())
        data["step_file"] = f"{pid}.step"
        look = data.setdefault("appearance", {})
        if listed:
            look["accents"] = listed
        else:
            look.pop("accents", None)
        f.write_text(json.dumps(data, indent=2) + "\n")
        print("shaped", pid, f"(+{len(listed)} accents)" if listed else "")


if __name__ == "__main__":
    main()
