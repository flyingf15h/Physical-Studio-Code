"""Builds the traffic light demo through the same calls a model makes, checks it, and exports it.

    uv run python examples/traffic_light.py [out_dir]

The viewer's demo sample (viewer/public/traffic-light) is generated with this script. After a
caliper check changes a part's numbers, rerun it with ../viewer/public/traffic-light to re-export.
Pins (the firmware must match): red LED D11, yellow D10, green D9, crosswalk button D2 (to GND,
INPUT_PULLUP), every LED through a 220 ohm resistor.
"""

import json
import sys
from pathlib import Path

from physical_studio.server import Studio

PROMPT = (
    "Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, "
    "a crosswalk button, USB accessible on the side."
)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
studio = Studio()
studio.new_design("Traffic light", PROMPT)

# The LEDs and the button hang under the lid: the LED flanges' tops (z + 1.0) and the button
# housing's top (z + 3.5) sit level at the lid's underside, so lenses and plunger poke through.
LID_UNDERSIDE = 27.5
LED_Z = LID_UNDERSIDE - 1.0
BUTTON_Z = LID_UNDERSIDE - 3.5
# (name, color, LED xy, Uno pin), top to bottom like a real traffic light
LIGHTS = [
    ("red", "red", (20.0, 33.1), "d11"),
    ("yellow", "yellow", (20.0, 21.1), "d10"),
    ("green", "green", (20.0, 9.1), "d9"),
]

studio.place_part("arduino-uno", (0, 0, 0), id="uno")
for name, color, (x, y), _ in LIGHTS:
    studio.place_part("led-5mm", (x, y, LED_Z), id=f"led-{name}", name=f"{name.title()} LED", color=color)
studio.place_part("tactile-button-12mm", (40.0, 18.0, BUTTON_Z), id="btn-walk", name="Crosswalk button", color="white")
for hole in ("h1", "h3", "h4"):  # h2 is next to the header; a socket head won't fit there
    studio.add_fastener("m3-screw-6mm", "uno", hole, id=f"screw-{hole}")

for name, color, _, pin in LIGHTS:
    studio.add_wire(f"led-{name}", "anode", "uno", pin, color=color, inline="220 ohm resistor", id=f"wire-led-{name}")
studio.add_wire("btn-walk", "a", "uno", "d2", color="blue", id="wire-btn-walk")
studio.add_wire("led-red", "cathode", "led-yellow", "cathode", color="black", id="gnd-red-yellow")
studio.add_wire("led-yellow", "cathode", "led-green", "cathode", color="black", id="gnd-yellow-green")
studio.add_wire("led-green", "cathode", "uno", "gnd1", color="black", id="gnd-leds-uno")
studio.add_wire("btn-walk", "b", "uno", "gnd2", color="black", id="gnd-btn-uno")

enclosure = studio.create_enclosure()

studio.add_step(
    "Lay out the case base",
    "Put the printed base on the bench with the USB and barrel-jack openings on the left.",
    ["base"],
    check="Base is upright with the two port openings in the left wall.",
)
studio.add_step(
    "Drop in the Arduino",
    "Lower the Uno onto the standoffs, USB port first into the left opening.",
    ["uno"],
    motion=[{"placement": "uno", "from_offset": [0, 0, 40]}],
    callouts=[{"text": "USB-B lines up with this opening", "target": "uno", "at": [-3, 38.1, 7]}],
    check="The Uno sits on its standoffs and the USB-B port lines up with the left opening.",
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
for name, _, _, pin in LIGHTS:
    studio.add_step(
        f"Wire the {name} LED",
        f"Connect the {name} LED's long leg (anode) to {pin.upper()} through a 220 ohm resistor.",
        [f"led-{name}", f"wire-led-{name}"],
        motion=[{"placement": f"led-{name}", "from_offset": [0, 0, 30]}],
        callouts=[{"text": "Long leg (anode) to the resistor", "target": f"led-{name}"}],
        check=f"The {name} LED's long leg goes through a resistor to {pin.upper()}.",
    )
studio.add_step(
    "Wire the crosswalk button",
    "Connect one leg of the button to D2 and the leg on the same side to GND.",
    ["btn-walk", "wire-btn-walk", "gnd-btn-uno"],
    motion=[{"placement": "btn-walk", "from_offset": [0, 0, 30]}],
    check="Button legs on the same side go to D2 and GND.",
)
studio.add_step(
    "Connect the LED grounds",
    "Daisy-chain the three LEDs' short legs (cathodes) together and to GND.",
    ["gnd-red-yellow", "gnd-yellow-green", "gnd-leds-uno"],
    check="All three LED short legs are on black wires that end at a GND pin.",
)
studio.add_step(
    "Close the lid",
    "Fit the lid so the three LED lenses and the button line up with their holes, red at the top, "
    "then press it on.",
    ["lid"],
    motion=[{"placement": "lid", "from_offset": [0, 0, 50]}],
    tools=[{"name": "Hands only", "for": "press fit"}],
    check="Lid sits flush, with red, yellow and green LEDs top to bottom and the button showing through.",
)

report = {
    "enclosure": enclosure,
    "interference": studio.check_interference(),
    "clearance": studio.check_clearance(),
}
print(json.dumps(report, indent=2))
print(json.dumps(studio.export(["glb", "stl", "step"], str(out) if out else None), indent=2))
