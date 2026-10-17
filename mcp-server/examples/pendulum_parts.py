"""Writes the parts the double inverted pendulum (examples/double_pendulum.py) uses into parts/.

    uv run python examples/pendulum_parts.py

Numbers are typical datasheet / standard values (HIWIN HGR20/HGH20CA, module-1 gear and rack,
F6800ZZ bearing, 37 mm gearmotor, Teensy 4.1, common AS5600 / VL53L0X / DRV8874 breakouts) and
our own sizes for the printed parts. None are measured yet (verified: false). Round and U-shaped
parts get a generated STEP file so they look right and fit-check properly.
"""

import json
from pathlib import Path

from build123d import Align, Box, Cylinder, Location, Rot, export_step

PARTS = Path(__file__).resolve().parents[2] / "parts"
TYPICAL = "Typical datasheet/standard numbers for this part; the shop listing wasn't checked and it is not yet measured"
PRINTED = "Our own size for a 3D-printed (or cut) part of the double inverted pendulum; change freely"
MIN = (Align.MIN, Align.MIN, Align.MIN)


def pins(*rows):
    """rows of (id, label, [x, y, z], direction)"""
    return [{"id": i, "label": label, "position": list(p), "direction": list(d)} for i, label, p, d in rows]


def part(pid, name, category, size, source=TYPICAL, notes="", step=None, **extra):
    data = {
        "id": pid,
        "name": name,
        "category": category,
        "source": source,
        "step_file": f"{pid}.step" if step is not None else None,
        "body": {"size": list(size)},
        **extra,
        "notes": notes,
        "verified": False,
        "verified_by": None,
        "verified_on": None,
    }
    (PARTS / f"{pid}.json").write_text(json.dumps(data, indent=2) + "\n")
    if step is not None:
        export_step(step, str(PARTS / f"{pid}.step"))
    print("wrote", pid)


def tube_z(od, idia, h, x, y, z0=0.0):
    """Cylinder along +z with a bore, its axis at (x, y), from z0 to z0 + h."""
    outer = Cylinder(od / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if idia:
        outer = outer - Cylinder(idia / 2, h + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((0, 0, -1)))
    return outer.moved(Location((x, y, z0)))


def bore_y(shape, d, x, z, depth):
    """Drill a hole of diameter d along y through a block, axis at (x, z)."""
    drill = Cylinder(d / 2, depth + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((x, -1, z)) * Rot(-90, 0, 0))
    return shape - drill


# --- mechanics -----------------------------------------------------------------------------------

part("base-plate-500", "Base plate 500 x 115 mm", "misc", [500, 115, 10], PRINTED,
     "10 mm plywood or aluminium plate. Its front edge goes at the edge of the table (or on legs) so the pendulum can hang down.")
part("hgr20-rail-400", "HGR20 linear rail, 400 mm", "misc", [400, 20, 17.5],
     notes="HIWIN-style HGR20 profile: 20 mm wide, 17.5 mm tall. M5 screws every 60 mm into the base plate.")
carriage = Box(61.4, 44, 25.4, align=MIN) - Box(61.4, 20, 12.9, align=MIN).moved(Location((0, 12, 0)))
part("hgh20ca-block", "HGH20CA carriage block", "misc", [61.4, 44, 25.4],
     notes="Rides on the HGR20 rail; the 20 mm channel wraps the rail. 30 mm from the rail's bottom to the block's top. 4x M5 on top for the cart plate.",
     step=carriage)
part("rack-riser-400", "Rack riser, 400 mm", "misc", [400, 10, 19], PRINTED,
     "Printed or aluminium spacer that lifts the rack so the pinion meshes just under the cart plate.")
part("gear-rack-m1-400", "Gear rack M1 10 x 10, 400 mm", "misc", [400, 10, 10],
     notes="Module 1 rack, 10 x 10 mm section. The teeth face the rail (-y); pitch line 1 mm in from the toothed face.")
cart = Box(120, 90, 6, align=MIN)
cart = cart - Cylinder(4.5, 8, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((60, 75, -1)))
part("cart-plate", "Cart plate 120 x 90 mm", "misc", [120, 90, 6], PRINTED,
     "Bolts onto the carriage block. The motor shaft drops through the 9 mm hole to the pinion underneath.", step=cart)
motor = tube_z(37, 0, 55, 18.5, 18.5, 17) + tube_z(6, 0, 17, 18.5, 18.5, 0)
part("dc-gearmotor-12v-37", "12 V DC gearmotor (37 mm)", "output", [37, 37, 72],
     notes="37 mm gearmotor: 55 mm body, 6 mm output shaft 17 mm long, pointing down (-z). If the pinion's bore is 8 mm, use a 6-to-8 mm sleeve or a 6 mm-bore pinion.",
     step=motor,
     pins=pins(("m_pos", "Motor +", [12, 18.5, 72], [0, 0, 1]), ("m_neg", "Motor -", [25, 18.5, 72], [0, 0, 1])))
part("pinion-m1-26t", "Pinion gear M1 26T (8 mm bore)", "misc", [28, 28, 10],
     notes="Module 1, 26 teeth: 26 mm pitch diameter, 28 mm outside, 10 mm face. 81.7 mm of cart travel per motor turn.",
     step=tube_z(28, 8, 10, 14, 14))
bearing = tube_z(21, 10, 1, 10.5, 10.5) + tube_z(19, 10, 5, 10.5, 10.5, 1)
part("bearing-f6800zz", "Flanged bearing 10 mm ID (F6800ZZ)", "misc", [21, 21, 6],
     notes="10 mm bore, 19 mm outside, 5 mm wide, 21 mm flange 1 mm thick. Presses into a 19 mm pocket with the flange on the outside.",
     step=bearing)
pivot = bore_y(Box(30, 20, 30, align=MIN), 19, 15, 15, 20)
part("pivot-block", "Pivot block", "misc", [30, 20, 30], PRINTED,
     "Holds the cart joint's two bearings (19 mm bore through). Screws to the cart plate.", step=pivot)
part("shaft-10-48", "Steel shaft 10 mm x 48 mm", "misc", [10, 10, 48], PRINTED,
     "Cut from 10 mm rod (h7, modelled 9.9 mm so it slides in the bearings). Cart joint: through both pivot-block bearings into the lower arm.", step=tube_z(9.9, 0, 48, 5, 5))
part("shaft-10-26", "Steel shaft 10 mm x 26 mm", "misc", [10, 10, 26], PRINTED,
     "Cut from 10 mm rod. Elbow joint: through the lower arm's bearing into the upper arm.", step=tube_z(9.9, 0, 26, 5, 5))
lower = bore_y(bore_y(Box(30, 8, 210, align=MIN), 10, 15, 15, 8), 19, 15, 195, 8)
part("arm-lower-210", "Lower pendulum arm", "misc", [30, 8, 210], PRINTED,
     "Clamped to the cart shaft at the bottom (10 mm hole); a flanged bearing in the 19 mm hole at the top.", step=lower)
upper = bore_y(Box(30, 8, 210, align=MIN), 10, 15, 15, 8)
part("arm-upper-210", "Upper pendulum arm", "misc", [30, 8, 210], PRINTED,
     "Clamped to the elbow shaft at the bottom (10 mm hole). Free at the top.", step=upper)
part("encoder-mount", "Encoder mount", "misc", [30, 6.5, 30], PRINTED,
     "Holds an AS5600 board 1 mm from the magnet on the shaft end (12 mm hole for the magnet).",
     step=bore_y(Box(30, 6.5, 30, align=MIN), 12, 15, 15, 6.5))
part("magnet-6x2-5", "Diametric magnet 6 x 2.5 mm", "misc", [6, 6, 2.5],
     notes="Comes with the AS5600 board. Glue it centred on the shaft end.", step=tube_z(6, 0, 2.5, 3, 3))
part("tof-bracket", "Distance sensor bracket", "misc", [10, 30, 35], PRINTED,
     "Holds a VL53L0X board at the end of the rail, facing the carriage.")

# --- electronics ---------------------------------------------------------------------------------

top = [("vin", "VIN", 0), ("gnd2", "GND", 1), ("3v3", "3.3V", 2), ("d19", "19 / SCL", 7), ("d18", "18 / SDA", 8),
       ("d17", "17 / SDA1", 9), ("d16", "16 / SCL1", 10)]
bottom = [("gnd", "GND", 0), ("d2", "2 (PWM)", 3), ("d3", "3 (PWM)", 4)]
part("teensy-41", "Teensy 4.1", "board", [61, 18, 1.6],
     notes="600 MHz Cortex-M7, 3 I2C buses (Wire 18/19, Wire1 17/16). Powered over USB here; its pins are 3.3 V only.",
     envelope={"min": [0, 0, 0], "max": [61, 18, 4]},
     connectors=[{"id": "usb", "type": "micro-usb", "face": "-x", "center": [0, 9, 2.6], "size": [8, 3], "protrusion": 1}],
     pins=pins(*[(i, label, [3.17 + 2.54 * n, 16.62, 1.6], [0, 0, 1]) for i, label, n in top],
               *[(i, label, [3.17 + 2.54 * n, 1.38, 1.6], [0, 0, 1]) for i, label, n in bottom]))
logic = [("in1", "IN1/EN"), ("in2", "IN2/PH"), ("pmode", "PMODE"), ("nsleep", "nSLEEP"), ("gnd", "GND")]
power = [("vm", "VM (12 V)"), ("gnd_p", "GND"), ("out1", "OUT1"), ("out2", "OUT2")]
part("drv8874-board", "DRV8874 motor driver board", "board", [20.3, 12.7, 1.6],
     notes="H-bridge, up to 37 V / 2.1 A. PMODE high = IN/IN (PWM) mode; nSLEEP high to run.",
     envelope={"min": [0, 0, 0], "max": [20.3, 12.7, 3]},
     pins=pins(*[(i, label, [1.27 + 2.54 * n, 1.27, 1.6], [0, 0, 1]) for n, (i, label) in enumerate(logic)],
               *[(i, label, [1.27 + 2.54 * n, 11.43, 1.6], [0, 0, 1]) for n, (i, label) in enumerate(power)]))
part("buck-12v-3v3", "12 V to 3.3 V regulator", "board", [22, 17, 5],
     notes="Small step-down module. Powers the four sensors from the 12 V supply.",
     pins=pins(("in_p", "IN+", [2, 2, 5], [0, 0, 1]), ("in_n", "IN-", [2, 15, 5], [0, 0, 1]),
               ("out_p", "OUT+ 3.3 V", [20, 2, 5], [0, 0, 1]), ("out_n", "OUT-", [20, 15, 5], [0, 0, 1])))
sensor_pins = [("vcc", "VCC"), ("gnd", "GND"), ("dir", "DIR"), ("scl", "SCL"), ("sda", "SDA")]
part("as5600-board", "AS5600 magnetic encoder board", "input", [23, 23, 1.6],
     notes="12-bit angle sensor, I2C address 0x36 (fixed), so each one needs its own I2C bus. Chip side faces the magnet, 0.5 to 3 mm away.",
     pins=pins(*[(i, label, [3 + 2.54 * n, 1.27, 0], [0, 0, -1]) for n, (i, label) in enumerate(sensor_pins)]))
tof_pins = [("vin", "VIN"), ("gnd", "GND"), ("scl", "SCL"), ("sda", "SDA"), ("xshut", "XSHUT")]
part("vl53l0x-board", "VL53L0X distance sensor board", "input", [10.7, 25, 2.5],
     notes="Time-of-flight distance sensor, up to about 1.2 m, I2C address 0x29. Faces the carriage to measure where the cart is.",
     pins=pins(*[(i, label, [1.27, 2.5 + 2.54 * n, 0], [0, 0, -1]) for n, (i, label) in enumerate(tof_pins)]))
part("psu-12v-2a", "12 V 2 A power adapter", "misc", [85, 50, 32],
     notes="Wall adapter. Feeds the motor driver (VM) and the 3.3 V regulator.",
     pins=pins(("v12", "+12 V", [85, 20, 16], [1, 0, 0]), ("gnd", "GND", [85, 30, 16], [1, 0, 0])))
