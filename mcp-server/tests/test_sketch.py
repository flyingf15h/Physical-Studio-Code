import copy
import json
from pathlib import Path

import pytest

from physical_studio.bench import sketch
from physical_studio.bench.spec import Spec

READY = Path(__file__).parents[1] / "physical_studio" / "bench" / "ready"
BREADBOARD_GUIDES = ["traffic-light", "blink", "night-light", "distance-alarm", "snake-game", "fire-alarm"]


def ready(name):
    return json.loads((READY / name / "build.json").read_text())["internal"]["plan"]


@pytest.mark.parametrize("name", BREADBOARD_GUIDES)
def test_the_ready_made_guides_pass_the_pin_and_footprint_checks(name):
    plan = ready(name)
    scene = Spec.model_validate(plan["scene"])
    assert sketch.check_pins(plan["code"], scene) == []
    assert sketch.check_footprints(scene) == []


def test_a_12mm_button_in_e_and_f_is_caught():
    plan = ready("traffic-light")
    for p in plan["scene"]["parts"]:
        if p["id"] == "button":
            p["mount_holes"] = ["e44", "f44", "e46", "f46"]
    problems = sketch.check_footprints(Spec.model_validate(plan["scene"]))
    assert len(problems) == 1 and "columns d and g" in problems[0]


def test_a_module_header_that_skips_a_row_is_caught():
    plan = ready("distance-alarm")
    for p in plan["scene"]["parts"]:
        if p["id"] == "sensor":
            p["mount_holes"] = ["e24", "e25", "e26", "e28"]
    problems = sketch.check_footprints(Spec.model_validate(plan["scene"]))
    assert len(problems) == 1 and "neighbouring rows" in problems[0]


def test_code_on_a_different_pin_than_the_wire_is_caught():
    plan = ready("traffic-light")
    code = plan["code"].replace("RED_PIN = 11", "RED_PIN = 12")
    problems = sketch.check_pins(code, Spec.model_validate(plan["scene"]))
    assert any("pin D12" in p and "no wire" in p for p in problems)
    assert any("pin D11" in p and "never uses" in p for p in problems)


def test_analog_write_on_a_pin_without_pwm_is_caught():
    plan = ready("traffic-light")
    code = plan["code"].replace("digitalWrite(GREEN_PIN", "analogWrite(GREEN_PIN").replace("GREEN_PIN = 9", "GREEN_PIN = 8")
    scene = copy.deepcopy(plan["scene"])
    for w in scene["wires"]:
        for end in ("from_terminal", "to_terminal"):
            if w[end].lower() == "d9":
                w[end] = "d8"
    for p in scene["parts"]:
        for t in p.get("terminals", []):
            if t["name"].lower() == "d9":
                t["name"] = "d8"
    problems = sketch.check_pins(code, Spec.model_validate(scene))
    assert any("no PWM" in p for p in problems)


def test_library_pins_and_random_seeds_are_not_flagged():
    plan = ready("snake-game")  # LedControl(11, 13, 10, 1) and randomSeed(analogRead(A2))
    assert sketch.check_pins(plan["code"], Spec.model_validate(plan["scene"])) == []


needs_cli = pytest.mark.skipif(not sketch.CLI, reason="arduino-cli not installed")


@needs_cli
@pytest.mark.parametrize("name", BREADBOARD_GUIDES)
def test_the_ready_made_sketches_compile(name):
    plan = ready(name)
    assert sketch.compile_sketch(plan["code"], "arduino:avr:uno") is None
    for t in json.loads((READY / name / "build.json").read_text())["plan"].get("tests", []):
        assert sketch.compile_sketch(t["code"], "arduino:avr:uno") is None, t["title"]


@needs_cli
def test_a_sketch_that_does_not_compile_is_caught():
    err = sketch.compile_sketch("void setup() { pinMode(13, OUTPUT) }\nvoid loop() {}\n", "arduino:avr:uno")
    assert err and "error" in err


BLINK = "void setup() { pinMode(LED_BUILTIN, OUTPUT); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); delay(500); digitalWrite(LED_BUILTIN, LOW); delay(500); }\n"


@needs_cli
@pytest.mark.parametrize("fqbn", ["teensy:avr:teensy41", "esp32:esp32:esp32doit-devkit-v1"])
def test_teensy_and_esp32_sketches_compile_and_errors_are_caught(fqbn):
    status, msg = sketch.compile_result(BLINK, fqbn)
    if status == "skipped":
        pytest.skip(msg)  # that core isn't installed here
    assert status == "ok", msg
    assert sketch.compile_result(BLINK.replace("HIGH);", "HIGH)"), fqbn)[0] == "error"


def test_boards_get_their_own_compiler_and_pin_names():
    from types import SimpleNamespace as NS
    def fq(name):
        return sketch.board_of(NS(parts=[NS(kind="development_board", name=name)]))[1]
    assert fq("Teensy 4.1") == "teensy:avr:teensy41"
    assert fq("ESP32 DevKit V1") == "esp32:esp32:esp32doit-devkit-v1"
    assert fq("Seeed XIAO ESP32-C3") == "esp32:esp32:XIAO_ESP32C3"
    assert fq("Arduino Nano") == "arduino:avr:nano"
    assert sketch.pin_number("A0", "esp32:esp32:esp32doit-devkit-v1") == 36 and sketch.pin_number("A14", "teensy:avr:teensy41") == 38
    assert sketch.pin_label(25, "esp32:esp32:esp32doit-devkit-v1") == "GPIO25" and sketch.pin_label(15, "arduino:avr:uno") == "A1"
