import runpy
import sys

import pytest

pytest.importorskip("physical_studio.library")

from physical_studio.design import Design, Placement, Step, Wire  # noqa: E402
from physical_studio.guide_check import check_guide  # noqa: E402
from physical_studio.server import mcp  # noqa: E402


def part(pid, name, part_id="dc-gearmotor-12v-37", kind="part", **kw):
    return Placement(pid, kind, part_id, name, (0.0, 0.0, 0.0), **kw)


def cart():
    d = Design("Cart")
    for p in (part("base", "Base plate", "base-plate-500"), part("motor", "Drive motor"), part("psu", "12 V adapter", "psu-12v-2a"),
              part("driver", "Motor driver", "drv8874-board")):
        d.placements[p.id] = p
    d.wires["w1"] = Wire("w1", ("motor", "t1"), ("driver", "out1"))
    d.wires["w2"] = Wire("w2", ("psu", "v"), ("driver", "vin"))
    return d


def good_steps(d):
    d.steps = [
        Step("Lay out the base", "Put the base plate on the table.", ["base"], check="The base plate lies flat on the table."),
        Step("Mount the motor", "Screw the motor to the base, shaft up.", ["motor"], motion=[{"placement": "motor", "from_offset": [0, 0, 40]}],
             tools=[{"name": "Phillips screwdriver", "for": "motor screws"}], callouts=[{"text": "Shaft up", "target": "motor"}],
             check="The motor stands upright at the back of the base."),
        Step("Place the driver", "Stick the driver next to the motor.", ["driver"], motion=[{"placement": "driver", "from_offset": [0, 0, 30]}],
             check="The driver board lies to the right of the motor."),
        Step("Place the adapter", "Set the adapter by the driver, unplugged.", ["psu"], motion=[{"placement": "psu", "from_offset": [0, 0, 30]}],
             check="The adapter sits by the driver and is unplugged."),
        Step("Wire the motor", "Connect the motor to OUT1.", ["w1"], check="A wire runs from the motor to OUT1."),
        Step("Wire the power", "Connect the adapter to VIN. Keep it unplugged.", ["w2"], check="A red wire runs from the adapter to VIN."),
    ]
    return d


def test_good_guide_is_clean():
    r = check_guide(good_steps(cart()))
    assert r["ok"], r["problems"]
    assert r["stats"]["steps"] == 6 and r["stats"]["steps_with_tools"] == 1


def test_no_steps():
    assert not check_guide(cart())["ok"]


def test_catches_the_usual_mistakes():
    d = cart()
    d.placements["motor"].name = "dc-gearmotor-12v-37"
    d.steps = [
        Step("Everything", "Put the base, motor and driver down.", ["base", "motor", "driver"], check="It works."),
        Step("Bolt it", "Bolt the motor down.", [], check="The motor is bolted to the base."),
        Step("Wire early", "Connect the adapter.", ["w2"], check="A wire joins the adapter and the driver."),
    ]
    problems = " | ".join(check_guide(d)["problems"])
    assert "Never added" in problems and "w1" in problems and "psu" in problems
    assert "reads like an id" in problems
    assert "adds 3 parts" in problems
    assert "can't be seen in a photo" in problems
    assert "names no tool" in problems
    assert "isn't in place yet" in problems


def test_part_with_its_own_wires_is_fine_but_others_are_not():
    d = good_steps(cart())
    d.steps[3].add.append("w2")  # the adapter and its own wire
    d.steps.pop()
    assert check_guide(d)["ok"], check_guide(d)["problems"]
    d.steps[2].add.append("w1")  # the driver with the motor's wire is still fine: it touches the driver
    d.steps.pop(3)
    d.steps[1].add.append("w2")  # but the motor step with the adapter's wire isn't
    assert any("aren't theirs" in p for p in check_guide(d)["problems"])


def test_placeholder_steps_are_problems():
    # From the live pen-plotter run: the designer laid parts out loose instead of fitting them.
    for text in ("Stand the X motor in front of the frame. It is not attached: the library has no suitable motor mount.",
                 "Put the front extrusion down. This is an incomplete layout: belts and gantry are not included.",
                 "Drill an opening for the button with the actuator as a template.", "Keep it unplugged until the missing mechanics are done."):
        d = good_steps(cart())
        d.steps[1].text = text
        assert any("placeholder" in p for p in check_guide(d)["problems"]), text
    d = good_steps(cart())
    d.steps[2].title = "Stage the driver"
    assert any("placeholder" in p for p in check_guide(d)["problems"])
    d = good_steps(cart())
    d.steps[1].text = "Screw the motor to the base so it's not loose. Do not run it until the stage is level."
    assert check_guide(d)["ok"], check_guide(d)["problems"]


def test_reference_traffic_light_passes(tmp_path):
    sys.argv = ["traffic_light.py", str(tmp_path)]
    g = runpy.run_path("examples/traffic_light.py", run_name="__main__")
    r = check_guide(g["studio"].design)
    assert r["ok"], r["problems"]


def test_check_guide_is_an_mcp_tool():
    import asyncio

    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert "check_guide" in names
