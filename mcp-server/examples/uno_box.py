"""Builds an Arduino Uno case through the same calls Claude makes, and exports it.

    uv run python examples/uno_box.py [out_dir]

The viewer's sample (viewer/public/sample) is generated with this script.
"""

import json
import sys
from pathlib import Path

from physical_studio.server import Studio

out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
studio = Studio()
studio.new_design("Arduino Uno case", "A case for an Arduino Uno with the USB port reachable on the side.")
studio.place_part("arduino-uno", (0, 0, 0), id="uno")
enclosure = studio.create_enclosure()
cavity_min = enclosure["cavity"]["min"]

studio.add_step(
    "Lay out the case base",
    "Put the printed base on the bench with the two port openings on the left.",
    ["base"],
    check="Base is upright with the USB and barrel-jack openings on the left wall.",
)
studio.add_step(
    "Drop in the Arduino",
    "Lower the Uno onto the four standoffs, USB port first into the left opening.",
    ["uno"],
    motion=[{"placement": "uno", "from_offset": [0, 0, 40]}],
    callouts=[
        {"text": "USB-B goes into this opening", "target": "uno", "at": [-3, 38.1, 7]},
        {"text": "Barrel jack", "target": "uno", "at": [-1, 7.6, 7]},
    ],
    dimensions=[{"from": [13.97, 2.54, 1.6], "to": [15.24, 50.8, 1.6], "label": "48.3 mm hole spacing"}],
    check="All four mounting holes sit on standoffs and the USB-B port lines up with the left opening.",
)
studio.add_step(
    "Close the lid",
    "Press the lid on until the lip seats inside the walls.",
    ["lid"],
    motion=[{"placement": "lid", "from_offset": [0, 0, 50]}],
    tools=[{"name": "Hands only", "for": "press fit"}],
    check="Lid sits flush all the way round.",
)
print(json.dumps(studio.export(["glb", "stl"], str(out) if out else None), indent=2))
