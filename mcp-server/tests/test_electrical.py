import runpy
import sys
from pathlib import Path

import pytest

pytest.importorskip("physical_studio.library")

from physical_studio import library  # noqa: E402
from physical_studio.design import Design, Placement, Wire  # noqa: E402
from physical_studio.electrical import check_wiring, volts  # noqa: E402
from physical_studio.guide_check import check_guide  # noqa: E402

LIB = library.load_library(Path(__file__).resolve().parents[2] / "parts")


def board(*parts):
    d = Design("Wiring")
    for pid, part_id in parts:
        d.placements[pid] = Placement(pid, "part", part_id, LIB[part_id]["name"] + " " + pid, (0.0, 0.0, 0.0))
    return d


def wire(d, wid, a, b, inline=None):
    d.wires[wid] = Wire(wid, a, b, inline=inline)


def test_voltages_are_read_from_printed_labels():
    assert [volts(s) for s in ("3.3V", "+12 V", "5V", "3V3", "OUT+ 3.3 V", "GND", "VIN", "18 / SDA")] == [3.3, 12, 5, 3.3, 3.3, None, None, None]


def test_a_supply_wired_to_ground_is_a_short():
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"))
    wire(d, "w1", ("psu", "v12"), ("mcu", "gnd"))
    assert any(p.startswith("Short") for p in check_wiring(d, LIB)["problems"])


def test_twelve_volts_into_a_three_volt_pin_is_a_problem():
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"))
    wire(d, "w1", ("psu", "v12"), ("mcu", "3v3"))
    assert any("12 V" in p and "3.3 V" in p for p in check_wiring(d, LIB)["problems"])


def test_supply_inputs_are_held_to_the_range_in_the_parts_notes():
    # Teensy 4.1 VIN takes 3.6 to 5.5 V: 5 V from an Uno is fine, the 12 V adapter would kill it.
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"), ("uno", "arduino-uno"), ("drv", "drv8874-board"))
    wire(d, "w1", ("psu", "v12"), ("mcu", "vin"))
    assert any("takes 3.6 to 5.5 V" in p for p in check_wiring(d, LIB)["problems"])
    d.wires["w1"] = Wire("w1", ("uno", "5v"), ("mcu", "vin"))
    wire(d, "w2", ("psu", "v12"), ("drv", "vin"))  # DRV8874: motor supply 4.5 to 37 V on VIN
    assert check_wiring(d, LIB) == {"problems": [], "tips": []}


def test_a_resistor_in_the_wire_keeps_its_ends_apart():
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"))
    wire(d, "w1", ("psu", "v12"), ("mcu", "gnd"), inline="220 ohm resistor")
    assert check_wiring(d, LIB)["problems"] == []


def test_two_fixed_address_encoders_on_one_bus_are_a_problem_and_on_two_buses_are_fine():
    d = board(("mcu", "teensy-41"), ("e1", "as5600-board"), ("e2", "as5600-board"))
    wire(d, "w1", ("e1", "sda"), ("mcu", "d18"))
    wire(d, "w2", ("e2", "sda"), ("mcu", "d18"))
    assert any("0x36 (fixed)" in p for p in check_wiring(d, LIB)["problems"])
    d.wires["w2"] = Wire("w2", ("e2", "sda"), ("mcu", "d17"))  # the second bus
    assert check_wiring(d, LIB)["problems"] == []


def test_two_sensors_with_a_second_address_are_a_tip_not_a_problem():
    d = board(("mcu", "arduino-uno"), ("b1", "bmp280-module"), ("b2", "bmp280-module"))
    wire(d, "w1", ("b1", "sda"), ("mcu", "sda"))
    wire(d, "w2", ("b2", "sda"), ("mcu", "sda"))
    r = check_wiring(d, LIB)
    assert r["problems"] == [] and any("0x76" in t for t in r["tips"])


def test_a_three_volt_only_part_on_five_volts_is_a_problem():
    d = board(("mcu", "arduino-uno"), ("b1", "bmp280-module"))
    wire(d, "w1", ("b1", "vcc"), ("mcu", "5v"))
    assert any("3.3 V only" in p for p in check_wiring(d, LIB)["problems"])
    d.wires["w1"] = Wire("w1", ("b1", "vcc"), ("mcu", "3v3"))
    assert check_wiring(d, LIB)["problems"] == []


def test_check_guide_reports_wiring_problems_when_it_has_the_library():
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"))
    wire(d, "w1", ("psu", "v12"), ("mcu", "gnd"))
    assert any(p.startswith("Short") for p in check_guide(d, LIB)["problems"])
    assert not any(p.startswith("Short") for p in check_guide(d)["problems"])  # no library: guide checks only


@pytest.mark.parametrize("example", ["traffic_light", "double_pendulum"])
def test_the_ready_made_designs_are_wired_cleanly(example, tmp_path, monkeypatch):
    from physical_studio.server import Studio

    monkeypatch.setattr(Studio, "export", lambda self, *a, **k: {})  # the design is all this test needs
    sys.argv = [f"{example}.py", str(tmp_path)]
    studio = runpy.run_path(f"examples/{example}.py", run_name="__main__")["studio"]
    r = check_wiring(studio.design, studio.library())
    assert r["problems"] == []
    # the pendulum's only notes are its gearmotor's 3 A stall current (driver 2.1 A, adapter 2 A)
    assert all("stall" in t for t in r["tips"]) and len(r["tips"]) == (2 if example == "double_pendulum" else 0)


def drive(d, driver, motor, supply):
    wire(d, driver + "-vin", supply, (driver, "vin"))
    wire(d, driver + "-a", (driver, "out1"), (motor, "m_pos"))
    wire(d, driver + "-b", (driver, "out2"), (motor, "m_neg"))


def test_a_driver_logic_pin_on_the_boards_3v3_is_not_charged_the_motor_current():
    d = board(("psu", "psu-12v-2a"), ("mcu", "teensy-41"), ("drv", "drv8874-board"), ("m", "dc-gearmotor-12v-37"))
    drive(d, "drv", "m", ("psu", "v12"))
    wire(d, "w-pmode", ("mcu", "3v3"), ("drv", "pmode"))
    wire(d, "w-in1", ("mcu", "d2"), ("drv", "in1"))
    r = check_wiring(d, LIB)
    assert r["problems"] == []
    assert any("stalls" in t and "2100 mA" in t for t in r["tips"])  # 3 A stall vs the driver's 2.1 A
    assert any("up to 3003 mA" in t for t in r["tips"])  # vs the adapter's 2 A (motor + driver)


def test_a_motor_on_a_bare_board_pin_is_a_problem():
    d = board(("mcu", "teensy-41"), ("m", "tt-gearmotor"))
    wire(d, "w1", ("mcu", "d2"), ("m", "m_pos"))
    assert any("Drive it through a motor driver" in p for p in check_wiring(d, LIB)["problems"])


def test_motors_that_draw_more_than_the_supply_gives_are_a_problem():
    d = board(("bat", "battery-9v"), ("d1", "drv8874-board"), ("d2", "drv8874-board"),
              ("m1", "dc-gearmotor-12v-37"), ("m2", "dc-gearmotor-12v-37"))
    drive(d, "d1", "m1", ("bat", "plus"))
    drive(d, "d2", "m2", ("bat", "plus"))
    assert any("can give 300 mA" in p and "about 606 mA" in p for p in check_wiring(d, LIB)["problems"])


def test_a_5v_signal_into_a_3v3_board_is_a_problem():
    d = board(("psu", "psu-12v-2a"), ("reg", "regulator-7805"), ("mcu", "teensy-41"), ("sonar", "hc-sr04"))
    wire(d, "w-in", ("psu", "v12"), ("reg", "in"))
    wire(d, "w-5v", ("reg", "out"), ("sonar", "vcc"))
    wire(d, "w-echo", ("sonar", "echo"), ("mcu", "d2"))
    assert any("level shifter" in p for p in check_wiring(d, LIB)["problems"])
