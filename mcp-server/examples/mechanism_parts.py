"""Writes common mechanism parts into parts/: stepper motors and their drivers, aluminium extrusion and
brackets, bearings, pulleys, lead screws, couplers, rover motors and wheels, limit switches and more
screw sizes, so the design job can lay out plotters, CNC axes, robot arms and rovers from real numbers.

    uv run python examples/mechanism_parts.py

Numbers are the standard ones for each part (NEMA 17 face, 608 bearing, GT2 pulley, ISO 4762 screws,
Pololu carrier boards). None are measured yet (verified: false). Existing files with the same id are
overwritten, so edit this script, not the JSON.
"""

import json
from pathlib import Path

PARTS = Path(__file__).resolve().parents[2] / "parts"
STANDARD = "Standard numbers for this part (datasheet / ISO / NEMA); not yet measured"
PITCH = 2.54

METAL = {"color": "#b8bdc2", "metallic": 0.85, "roughness": 0.35}
ALU = {"color": "#c9cdd1", "metallic": 0.8, "roughness": 0.45}
BLACK = {"color": "#1d1f22", "metallic": 0.0, "roughness": 0.7}
STEPPER = {"color": "#2b2d30", "metallic": 0.5, "roughness": 0.45}
YELLOW = {"color": "#e8b923", "metallic": 0.0, "roughness": 0.6}
BRASS = {"color": "#c8a24a", "metallic": 0.85, "roughness": 0.35}
GREEN_PCB = {"color": "#1e6b3a", "metallic": 0.1, "roughness": 0.6}


def pin(pid, label, x, y, z, direction=(0, 0, 1)):
    return {"id": pid, "label": label, "position": [round(x, 2), round(y, 2), round(z, 2)], "direction": list(direction)}


def part(pid, name, category, size, notes, look, **extra):
    return {"id": pid, "name": name, "category": category, "source": STANDARD, "step_file": None, "body": {"size": list(size)},
            **extra, "notes": notes, "appearance": {**look, "source": "typical look of this part"},
            "verified": False, "verified_by": None, "verified_on": None}


def screw(thread, length, head_d, head_h, drive):
    return {"id": f"{thread.lower()}-screw-{length}mm", "name": f"{thread} x {length} mm socket head screw", "category": "fastener",
            "source": f"ISO 4762 {thread} socket head cap screw (head {head_d} mm, {head_h} mm tall, {drive}); not yet measured",
            "step_file": None, "body": {"size": [head_d, head_d, length + head_h]},
            "envelope": {"min": [-head_d / 2, -head_d / 2, -length], "max": [head_d / 2, head_d / 2, head_h]},
            "fastener": {"thread": thread, "length": length, "head_diameter": head_d, "head_height": head_h, "head": "socket", "drive": drive},
            "notes": f"Origin is the centre of the underside of the head; the shaft runs along -Z and the head sits from z=0 to z={head_h}. Length is measured under the head.",
            "verified": False, "verified_by": None, "verified_on": None}


def pololu_driver(pid, name, left, right, notes):
    """A Pololu-style 0.6 x 0.8 in carrier: two rows of 8 header pins, 0.5 in apart, pins pointing down."""
    pins, seen = [], {}
    for x, row in ((1.27, left), (13.97, right)):
        for i, lbl in enumerate(row):
            base = lbl.lower().replace(" ", "_")
            seen[base] = seen.get(base, 0) + 1
            pins.append(pin(base if seen[base] == 1 else f"{base}_{seen[base]}", lbl, x, 19.05 - i * PITCH, 0, (0, 0, -1)))
    return part(pid, name, "board", (15.24, 20.32, 1.6), notes, GREEN_PCB, pins=pins,
                envelope={"min": [0, 0, -8.5], "max": [15.24, 20.32, 12]})


NEMA = 42.3
NEMA_HOLE = (NEMA - 31) / 2  # M3 holes on a 31 mm square, centred on the face

PARTS_LIST = [
    part("nema17-stepper-40", "NEMA 17 stepper motor (40 mm)", "output", (NEMA, NEMA, 40),
         "42.3 mm square face, 40 mm long body. Shaft 5 mm (D-cut) sticks 24 mm out of the top face (+z) from a 22 mm x 2 mm boss "
         "at the centre. Four M3 tapped holes on a 31 mm square in the top face (centres 5.65 mm in from each edge), 4.5 mm deep. "
         "Bipolar, 4 wires: coil A = black/green, coil B = red/blue (check the datasheet; pairs read a few ohms across).",
         STEPPER, pins=[pin("a_plus", "A+ (black)", 0, 15, 10, (-1, 0, 0)), pin("a_minus", "A- (green)", 0, 18, 10, (-1, 0, 0)),
                        pin("b_plus", "B+ (red)", 0, 24, 10, (-1, 0, 0)), pin("b_minus", "B- (blue)", 0, 27, 10, (-1, 0, 0))],
         envelope={"min": [0, 0, 0], "max": [NEMA, NEMA, 66]},
         keep_out=[{"min": [NEMA / 2 - 11, NEMA / 2 - 11, 40], "max": [NEMA / 2 + 11, NEMA / 2 + 11, 66]}]),
    pololu_driver("a4988-driver", "A4988 stepper driver board",
                  ["EN", "MS1", "MS2", "MS3", "RESET", "SLEEP", "STEP", "DIR"],
                  ["VMOT", "GND", "2B", "2A", "1A", "1B", "VDD", "GND"],
                  "Pololu A4988 carrier. Joins RESET to SLEEP for normal use. VMOT 8-35 V with a 100 uF capacitor across VMOT/GND; "
                  "VDD 3-5.5 V logic. 1A/1B to one motor coil, 2A/2B to the other. Set the current limit on the trim pot before running. "
                  "Never unplug the motor while VMOT is on."),
    pololu_driver("drv8825-driver", "DRV8825 stepper driver board",
                  ["EN", "M0", "M1", "M2", "RESET", "SLEEP", "STEP", "DIR"],
                  ["VMOT", "GND", "B2", "B1", "A1", "A2", "FAULT", "GND"],
                  "Pololu DRV8825 carrier, pin-compatible with the A4988 (no VDD pin: logic comes from STEP/DIR). VMOT 8.2-45 V with a "
                  "100 uF capacitor across VMOT/GND. A1/A2 to one coil, B1/B2 to the other. Join RESET and SLEEP to logic high."),
    part("extrusion-2020-300", "2020 aluminium extrusion (300 mm)", "misc", (300, 20, 20),
         "20 x 20 mm profile, 300 mm long along x, a 6 mm T-slot centred on each of the four faces and a 4.2 mm centre hole "
         "(tap M5 at the ends). Fixes with M5 T-nuts and corner brackets.", ALU),
    part("bracket-2020-corner", "2020 corner bracket", "misc", (20, 20, 20),
         "Cast L bracket for 2020 extrusion: two 20 x 20 mm legs at 90 degrees, each with a 5.5 mm slot for an M5 x 10 screw and a T-nut.",
         ALU),
    part("bearing-608zz", "608ZZ ball bearing", "misc", (22, 22, 7),
         "8 mm bore, 22 mm outside, 7 mm wide (skateboard bearing). Axis along z; origin at the corner of its bounding box.", METAL),
    part("gt2-pulley-20t-5mm", "GT2 pulley, 20 teeth, 5 mm bore", "misc", (18, 18, 16),
         "Fits a 6 mm GT2 belt. 12.7 mm pitch diameter (40 mm of belt per turn), 16 mm flanges, 16 mm long including the hub "
         "with two M3 set screws (2 mm hex key; tighten one onto the motor shaft's flat). Axis along z.", ALU),
    part("gt2-idler-20t-5mm", "GT2 toothless idler, 5 mm bore", "misc", (18, 18, 8.5),
         "Smooth idler for 6 mm GT2 belt, 5 mm bore with a bearing inside, 18 mm flanges, 8.5 mm wide. Axis along z.", ALU),
    part("coupler-5-8mm", "Shaft coupler, 5 mm to 8 mm", "misc", (19, 19, 25),
         "Flexible aluminium coupler, 19 mm diameter, 25 mm long, 5 mm bore at the bottom for a stepper shaft and 8 mm at the top for "
         "a T8 lead screw, two M3 set screws at each end. Axis along z.", ALU),
    part("t8-leadscrew-300", "T8 lead screw (300 mm) with brass nut", "misc", (300, 22, 22),
         "8 mm trapezoidal lead screw, 8 mm lead (8 mm of travel per turn), 300 mm long along x. Brass nut: 10.2 mm body, 22 mm "
         "flange with four 3.5 mm holes on a 16 mm circle, 15 mm long.", BRASS),
    part("linear-rod-8-300", "8 mm smooth rod (300 mm)", "misc", (300, 8, 8),
         "Hardened steel rod, 8 mm diameter, 300 mm long along x, for LM8UU bearings.", METAL),
    part("lm8uu-bearing", "LM8UU linear bearing", "misc", (24, 15, 15),
         "Linear ball bearing for 8 mm rod: 15 mm outside, 24 mm long along x.", METAL),
    part("tt-gearmotor", "TT gearmotor (yellow, 1:48)", "output", (70, 22.5, 18.8),
         "The yellow hobby rover motor: 3-6 V, about 200 rpm at 6 V. 70 mm long along x including the motor can; the double-sided "
         "5.4 mm D shaft runs along y, 11 mm from the gearbox end. Two M3 holes through the gearbox for mounting. Two solder tabs.",
         YELLOW, pins=[pin("m_pos", "Motor +", 66, 6, 9.4, (1, 0, 0)), pin("m_neg", "Motor -", 66, 16.5, 9.4, (1, 0, 0))]),
    part("wheel-65mm-tt", "65 mm wheel for TT motor", "misc", (65, 65, 26),
         "Rubber tyre on a plastic hub, 65 mm diameter, 26 mm wide, pushes onto the TT motor's D shaft (an M2 screw holds it). Axis along z.",
         BLACK),
    part("caster-ball-small", "Ball caster (small)", "misc", (31, 20, 16),
         "Steel ball caster, 31 x 20 mm plate with two M3 holes 24 mm apart, 16 mm tall: the third wheel on a two-wheel rover.", METAL),
    part("limit-switch-kw12", "Limit switch (KW12 lever)", "input", (20, 6.4, 10),
         "Micro switch with a lever, 20 x 6.4 x 10 mm body, two 2.3 mm mounting holes 9.5 mm apart. Wire COM to GND and NO to an input "
         "with INPUT_PULLUP: reads LOW when pressed.", BLACK,
         pins=[pin("com", "COM", 3, 3.2, 0, (0, 0, -1)), pin("no", "NO", 10, 3.2, 0, (0, 0, -1)), pin("nc", "NC", 17, 3.2, 0, (0, 0, -1))]),
    screw("M3", 10, 5.5, 3.0, "hex 2.5mm"),
    screw("M3", 16, 5.5, 3.0, "hex 2.5mm"),
    screw("M5", 10, 8.5, 5.0, "hex 4mm"),
]


def main():
    for p in PARTS_LIST:
        (PARTS / f"{p['id']}.json").write_text(json.dumps(p, indent=2) + "\n")
    print(f"wrote {len(PARTS_LIST)} parts to {PARTS}")


if __name__ == "__main__":
    main()
