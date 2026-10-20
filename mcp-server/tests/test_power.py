import copy
import json
from pathlib import Path

import pytest

from physical_studio.bench import planner, power
from physical_studio.bench.spec import Spec

READY = Path(__file__).parents[1] / "physical_studio" / "bench" / "ready"
PlanModel = planner.plan_model(Spec)


@pytest.fixture(autouse=True)
def library():
    planner.configure(Path(__file__).parents[2] / "parts")


def ready(name):
    return json.loads((READY / name / "build.json").read_text())["internal"]["plan"]


def check(plan):
    return power.check_power(PlanModel.model_validate(plan))


def part(plan, pid):
    return next(p for p in plan["scene"]["parts"] if p["id"] == pid)


def rename_pin(plan, old, new):
    for w in plan["scene"]["wires"]:
        for end in ("from_terminal", "to_terminal"):
            if w[end].lower() == old:
                w[end] = new
    for p in plan["scene"]["parts"]:
        for t in p.get("terminals", []):
            if t["name"].lower() == old:
                t["name"] = new


@pytest.mark.parametrize("name", ["traffic-light", "blink", "night-light", "distance-alarm", "snake-game", "fire-alarm"])
def test_the_ready_made_guides_pass_the_power_checks(name):
    assert check(ready(name)) == ([], [])


def test_an_led_resistor_that_is_too_small_is_caught():
    plan = ready("blink")
    part(plan, "led_resistor")["name"] = "47 ohm resistor"
    problems, _ = check(plan)
    assert len(problems) == 1 and "64 mA" in problems[0] and "at least 150 ohm" in problems[0]


def test_a_huge_led_resistor_is_only_a_warning():
    plan = ready("blink")
    part(plan, "led_resistor")["name"] = "1 Mohm resistor"
    problems, warnings = check(plan)
    assert problems == [] and "dim" in warnings[0]


def test_a_5v_sensor_on_the_3v3_pin_is_caught():
    plan = ready("distance-alarm")
    rename_pin(plan, "5v", "3v3")
    problems, _ = check(plan)
    assert any("4.5-5.5 V" in p and "3V3" in p for p in problems)


def test_a_motor_on_a_bare_gpio_pin_is_caught():
    plan = ready("distance-alarm")
    part(plan, "buzzer")["name"] = "130 DC motor"
    problems, _ = check(plan)
    assert any("130 DC motor draws" in p and "transistor" in p for p in problems)


def test_a_5v_sensor_output_into_a_3v3_board_is_caught():
    plan = ready("distance-alarm")
    part(plan, "uno")["name"] = "ESP32 DevKit V1"
    problems, _ = check(plan)
    assert any("level shifter" in p for p in problems)


def test_the_5v_pin_budget_warns_on_peaks_and_fails_on_steady_draw():
    plan = ready("snake-game")
    part(plan, "joystick")["name"] = "SG90 servo"  # the matrix's 330 mA peak + a servo stalling
    problems, warnings = check(plan)
    assert problems == [] and any("up to 980 mA" in w for w in warnings)
    part(plan, "matrix")["name"] = "MG996R servo"
    problems, _ = check(plan)
    assert any("about 750 mA" in p for p in problems)
