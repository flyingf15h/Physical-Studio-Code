"""Builds the Simon game demo through the same calls Claude makes, checks it, and exports it.

    uv run python examples/simon.py [out_dir]

The viewer's Simon sample (viewer/public/simon) is generated with this script. After a caliper
check changes a part's numbers, rerun it with ../viewer/public/simon to re-export.
"""

import json
import sys
from pathlib import Path

from physical_studio.server import Studio

out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
studio = Studio()
studio.new_design(
    "Simon game",
    "Simon game for an Arduino Uno, 4 colored buttons with LEDs, buzzer, USB accessible on the side.",
)

# Buttons and LEDs hang under the lid: the button housings' tops (z + 3.5) and the LED flanges'
# tops (z + 1.0) sit level at the lid's underside, so the plungers and lenses poke through.
LID_UNDERSIDE = 27.5
BUTTON_Z = LID_UNDERSIDE - 3.5
LED_Z = LID_UNDERSIDE - 1.0
# (name, wire color, button xy, LED xy, button pin, LED pin)
COLORS = [
    ("red", "#d03a3a", (6.0, 30.0), (20.0, 33.1), "d2", "d8"),
    ("green", "#3a9d4f", (40.0, 30.0), (54.0, 33.1), "d3", "d9"),
    ("blue", "#3a6fd0", (6.0, 6.0), (20.0, 9.1), "d4", "d10"),
    ("yellow", "#e8c52e", (40.0, 6.0), (54.0, 9.1), "d5", "d11"),
]

studio.place_part("arduino-uno", (0, 0, 0), id="uno")
for color, _, (bx, by), (lx, ly), _, _ in COLORS:
    studio.place_part("tactile-button-12mm", (bx, by, BUTTON_Z), id=f"btn-{color}", name=f"{color.title()} button")
    studio.place_part("led-5mm", (lx, ly, LED_Z), id=f"led-{color}", name=f"{color.title()} LED")
studio.place_part("piezo-buzzer", (26.5, 19.0, 16.0), id="piezo", name="Piezo buzzer")
for hole in ("h1", "h3", "h4"):  # h2 is next to the header; a socket head won't fit there
    studio.add_fastener("m3-screw-6mm", "uno", hole, id=f"screw-{hole}")

for color, wire, _, _, btn_pin, led_pin in COLORS:
    studio.add_wire(f"btn-{color}", "a", "uno", btn_pin, color=wire, id=f"wire-btn-{color}")
    studio.add_wire(f"led-{color}", "anode", "uno", led_pin, color=wire, inline="220 ohm resistor", id=f"wire-led-{color}")
studio.add_wire("piezo", "pos", "uno", "d12", color="#e8862e", id="wire-piezo")
ground_ids = []
for (a, *_), (b, *_) in zip(COLORS, COLORS[1:]):
    for kind, pin in (("btn", "b"), ("led", "cathode")):
        gid = f"gnd-{kind}-{a}-{b}"
        studio.add_wire(f"{kind}-{a}", pin, f"{kind}-{b}", pin, color="#2b2b2b", id=gid)
        ground_ids.append(gid)
studio.add_wire("btn-yellow", "b", "uno", "gnd1", color="#2b2b2b", id="gnd-btn-uno")
studio.add_wire("led-yellow", "cathode", "uno", "gnd2", color="#2b2b2b", id="gnd-led-uno")
studio.add_wire("piezo", "neg", "uno", "gnd3", color="#2b2b2b", id="gnd-piezo-uno")
ground_ids += ["gnd-btn-uno", "gnd-led-uno", "gnd-piezo-uno"]

enclosure = studio.create_enclosure()

studio.add_step(
    "Lay out the case base",
    "Put the printed base on the bench with the USB and barrel-jack openings on the left.",
    ["base"],
    check="Base is upright with the two port openings in the left wall.",
)
studio.add_step(
    "Drop in the Arduino",
    "Lower the Uno onto the four standoffs, USB port first into the left opening.",
    ["uno"],
    motion=[{"placement": "uno", "from_offset": [0, 0, 40]}],
    callouts=[{"text": "USB-B lines up with this opening", "target": "uno", "at": [-3, 38.1, 7]}],
    check="All four mounting holes sit on standoffs and the USB-B port lines up with the left opening.",
)
screws = ["screw-h1", "screw-h3", "screw-h4"]
studio.add_step(
    "Screw down the Arduino",
    "Drive an M3 x 6 screw through the three mounting holes away from the header "
    "(leave the hole next to AREF/SCL empty). Snug, not tight.",
    screws,
    motion=[{"placement": s, "from_offset": [0, 0, 20], "from_rotation": [0, 0, 720]} for s in screws],
    tools=[{"name": "2.5 mm hex key", "for": "M3 x 6 socket screws"}],
    check="Three screw heads seated; the hole next to the digital header stays empty.",
)
for color, _, _, _, btn_pin, led_pin in COLORS:
    studio.add_step(
        f"Wire the {color} button and LED",
        f"Connect the {color} button's leg A to {btn_pin.upper()} and the {color} LED's long leg (anode) "
        f"to {led_pin.upper()} through a 220 ohm resistor.",
        [f"btn-{color}", f"led-{color}", f"wire-btn-{color}", f"wire-led-{color}"],
        motion=[
            {"placement": f"btn-{color}", "from_offset": [0, 0, 30]},
            {"placement": f"led-{color}", "from_offset": [0, 0, 30]},
        ],
        callouts=[{"text": "Long leg (anode) to the resistor", "target": f"led-{color}"}],
        check=f"{color.title()} LED's long leg goes to the resistor on {led_pin.upper()}; button leg A to {btn_pin.upper()}.",
    )
studio.add_step(
    "Wire the buzzer",
    "Connect the piezo's + leg to D12.",
    ["piezo", "wire-piezo"],
    motion=[{"placement": "piezo", "from_offset": [0, 0, 30]}],
    check="Piezo + leg goes to D12.",
)
studio.add_step(
    "Connect the grounds",
    "Daisy-chain the buttons' B legs to GND, the LEDs' short legs to the other GND, "
    "and the piezo's - leg to the GND next to D13.",
    ground_ids,
    check="Every button B leg, LED short leg and the piezo - leg is on a black wire to a GND pin.",
)
studio.add_step(
    "Close the lid",
    "Fit the lid so the LED lenses and button plungers line up with their holes, then press it on.",
    ["lid"],
    motion=[{"placement": "lid", "from_offset": [0, 0, 50]}],
    tools=[{"name": "Hands only", "for": "press fit"}],
    check="Lid sits flush, with the four LEDs and buttons showing through their holes.",
)

report = {
    "enclosure": enclosure,
    "interference": studio.check_interference(),
    "clearance": studio.check_clearance(),
}
print(json.dumps(report, indent=2))
print(json.dumps(studio.export(["glb", "stl", "step"], str(out) if out else None), indent=2))
