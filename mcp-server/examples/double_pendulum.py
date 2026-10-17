"""Double inverted pendulum on a rack-and-pinion cart, built through the same calls a model makes.

    uv run python examples/pendulum_parts.py    # once, writes the parts into parts/
    uv run python examples/double_pendulum.py ../viewer/public/double-pendulum

Layout (mm, +x along the rail, +z up): the rail runs along the base, the carriage block carries
the cart plate, the motor stands on the cart with its pinion underneath meshing a rack beside the
rail. The two arms swing in the x-z plane in front of the base (y < 15), so the base's front edge
goes at the edge of the table. Each joint has an AS5600 reading a magnet on the shaft end, and a
VL53L0X at each end of the rail measures the cart's position.

Wiring: Teensy 4.1 on USB. DRV8874 in IN/IN mode (PMODE high): IN1 = pin 2, IN2 = pin 3.
I2C bus Wire (SDA 18, SCL 19): cart encoder + left distance sensor. Wire1 (SDA1 17, SCL1 16):
elbow encoder + right distance sensor. AS5600 is fixed at 0x36 and VL53L0X at 0x29, so each bus
gets one of each. The 12 V adapter feeds the driver (VIN) and the 3.3 V regulator, which powers the sensors.
"""

import json
import sys
from pathlib import Path

from physical_studio.server import Studio

PROMPT = (
    "i wanna make a double inverted pendulum using a rack and pinion motor on cart motion system. "
    "Items: 12V DC motor, M1 8mm 26T gear, HGR20 400mm linear rail + HGH20CA block, 10mm ID flanged "
    "bearings, 2x VL53L0X TOF sensor, M1 10x10 400mm rack, 2x AS5600 magnetic encoder, Teensy 4.1, "
    "DRV8874 H-bridge motor driver, 12V 2A power supply, 12V to 3V3 regulator."
)
X = 90  # rotation about x that stands a flat part up: local +z -> -y (X) or +y (-X)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
studio = Studio()
studio.new_design("Double inverted pendulum", PROMPT)
place = studio.place_part

# Frame and cart. The cart sits at the middle of its travel (block 200-261.4 mm along the rail).
place("base-plate-500", (0, 15, 0), id="base-plate", name="Base plate")
place("hgr20-rail-400", (50, 50, 10), id="rail", name="Linear rail")
place("hgh20ca-block", (200, 38, 14.6), id="block", name="Carriage block")
place("rack-riser-400", (50, 112, 10), id="riser", name="Rack riser", color="grey")
place("gear-rack-m1-400", (50, 112, 29), id="rack", name="Gear rack")
place("cart-plate", (170.7, 25, 40), id="cart", name="Cart plate", color="#4a7fb5")
place("pinion-m1-26t", (216.7, 86, 29), id="pinion", name="Pinion gear")
place("dc-gearmotor-12v-37", (212.2, 81.5, 29), id="motor", name="Drive motor", color="#8a8f98")

# Cart joint: two bearings in the pivot block, the shaft through them into the lower arm.
place("pivot-block", (215.7, 25, 46), id="pivot", name="Pivot block", color="orange")
place("bearing-f6800zz", (220.2, 24, 71.5), (-X, 0, 0), id="bearing-front", name="Front cart bearing")
place("bearing-f6800zz", (220.2, 46, 50.5), (X, 0, 0), id="bearing-back", name="Back cart bearing")
place("shaft-10-48", (225.7, 1, 66), (-X, 0, 0), id="shaft-cart", name="Cart shaft")
place("arm-lower-210", (215.7, 3, 46), id="arm-lower", name="Lower arm", color="red")
place("magnet-6x2-5", (227.7, 49, 64), (-X, 0, 0), id="magnet-cart", name="Cart joint magnet")
place("encoder-mount", (215.7, 46, 46), id="mount-cart", name="Cart encoder mount", color="orange")
place("as5600-board", (219.2, 54.1, 49.5), (X, 0, 0), id="enc-cart", name="Cart joint encoder")

# Elbow joint: a bearing in the top of the lower arm, the shaft into the upper arm.
place("bearing-f6800zz", (220.2, 2, 251.5), (-X, 0, 0), id="bearing-elbow", name="Elbow bearing")
place("shaft-10-26", (225.7, -12, 246), (-X, 0, 0), id="shaft-elbow", name="Elbow shaft")
place("arm-upper-210", (215.7, -10, 226), id="arm-upper", name="Upper arm", color="yellow")
place("magnet-6x2-5", (227.7, 14, 244), (-X, 0, 0), id="magnet-elbow", name="Elbow magnet")
place("encoder-mount", (215.7, 11, 226), id="mount-elbow", name="Elbow encoder mount", color="orange")
place("as5600-board", (219.2, 19.1, 229.5), (X, 0, 0), id="enc-elbow", name="Elbow encoder")

# Distance sensors at both ends of the rail, facing the carriage.
place("tof-bracket", (30, 45, 10), id="tof-bracket-left", name="Left sensor bracket", color="orange")
place("vl53l0x-board", (40, 47.5, 38.4), (0, 90, 0), id="tof-left", name="Left distance sensor")
place("tof-bracket", (460, 45, 10), id="tof-bracket-right", name="Right sensor bracket", color="orange")
place("vl53l0x-board", (460, 47.5, 27.7), (0, -90, 0), id="tof-right", name="Right distance sensor")

# Electronics on the front strip of the base (the cart plate passes over them), adapter beside it.
place("teensy-41", (60, 17, 10), id="teensy", name="Teensy 4.1")
place("drv8874-board", (128, 17, 10), id="driver", name="Motor driver")
place("buck-12v-3v3", (155, 17, 10), id="regulator", name="3.3 V regulator", color="#2a7a4a")
place("psu-12v-2a", (-100, 40, 0), id="psu", name="12 V adapter")

wire = studio.add_wire
# Power
wire("psu", "v12", "driver", "vin", color="red", id="w-psu-vin")
wire("psu", "gnd", "driver", "gnd_p", color="black", id="w-psu-gnd")
wire("psu", "v12", "regulator", "in_p", color="red", id="w-reg-in")
wire("psu", "gnd", "regulator", "in_n", color="black", id="w-reg-gnd")
# Motor and driver control
wire("driver", "out1", "motor", "m_pos", color="orange", id="w-motor-a")
wire("driver", "out2", "motor", "m_neg", color="brown", id="w-motor-b")
wire("teensy", "d2", "driver", "in1", color="blue", id="w-in1")
wire("teensy", "d3", "driver", "in2", color="purple", id="w-in2")
wire("teensy", "3v3", "driver", "pmode", color="white", id="w-pmode")
wire("teensy", "3v3", "driver", "nsleep", color="white", id="w-nsleep")
wire("teensy", "gnd", "driver", "gnd", color="black", id="w-logic-gnd")
wire("teensy", "gnd2", "regulator", "out_n", color="black", id="w-common-gnd")
# Sensors: 3.3 V and ground from the regulator, one I2C bus per side
for sensor, vcc in (("enc-cart", "vcc"), ("enc-elbow", "vcc"), ("tof-left", "vin"), ("tof-right", "vin")):
    wire("regulator", "out_p", sensor, vcc, color="red", id=f"w-{sensor}-3v3")
    wire("regulator", "out_n", sensor, "gnd", color="black", id=f"w-{sensor}-gnd")
wire("enc-cart", "dir", "enc-cart", "gnd", color="black", id="w-enc-cart-dir")
wire("enc-elbow", "dir", "enc-elbow", "gnd", color="black", id="w-enc-elbow-dir")
for sensor, sda, scl in (("enc-cart", "d18", "d19"), ("tof-left", "d18", "d19"),
                         ("enc-elbow", "d17", "d16"), ("tof-right", "d17", "d16")):
    wire("teensy", sda, sensor, "sda", color="green", id=f"w-{sensor}-sda")
    wire("teensy", scl, sensor, "scl", color="yellow", id=f"w-{sensor}-scl")

# Assembly guide
down = lambda *ids, h=40: [{"placement": i, "from_offset": [0, 0, h]} for i in ids]  # noqa: E731
front = lambda *ids, d=40: [{"placement": i, "from_offset": [0, -d, 0]} for i in ids]  # noqa: E731
step = studio.add_step
step("Lay out the base plate", "Put the base plate on the table with its long front edge right at the table edge.",
     ["base-plate"], check="The base plate lies flat with its front edge at the edge of the table.")
step("Screw down the linear rail", "Lay the rail along the base, 35 mm in from the back of the front strip, and screw it down with M5 screws.",
     ["rail"], motion=down("rail"), tools=[{"name": "4 mm hex key", "for": "M5 rail screws"}],
     check="The rail runs straight along the base, 50 mm from each end.")
step("Slide on the carriage block", "Slide the carriage block onto the rail from one end. Keep it level so the balls stay in.",
     ["block"], motion=[{"placement": "block", "from_offset": [-260, 0, 0]}],
     callouts=[{"text": "Slide on from the end, don't lift it off again", "target": "block"}],
     check="The block sits on the rail and slides end to end smoothly.")
step("Fit the rack riser", "Screw the rack riser along the back of the base, parallel to the rail.",
     ["riser"], motion=down("riser"), check="The riser runs along the back edge, parallel to the rail.")
step("Fit the gear rack", "Screw the rack on top of the riser with its teeth facing the rail.",
     ["rack"], motion=down("rack"), callouts=[{"text": "Teeth face the rail", "target": "rack"}],
     check="The rack sits on the riser with its teeth facing the rail.")
step("Bolt on the cart plate", "Put the cart plate on the carriage block, motor hole at the back over the rack, and bolt it down with 4 M5 screws.",
     ["cart"], motion=down("cart"), tools=[{"name": "4 mm hex key", "for": "M5 cart screws"}],
     check="The cart plate sits flat on the block with its hole above the rack.")
step("Mount the drive motor", "Stand the motor on the cart plate and push its shaft down through the hole. Screw it to the plate.",
     ["motor"], motion=down("motor", h=60), check="The motor stands upright on the cart with its shaft through the plate.")
step("Fit the pinion gear", "From underneath, push the pinion onto the motor shaft so it meshes with the rack, then tighten its set screw.",
     ["pinion"], motion=[{"placement": "pinion", "from_offset": [0, 0, -25]}],
     tools=[{"name": "2 mm hex key", "for": "pinion set screw"}],
     callouts=[{"text": "Teeth mesh with the rack, no gap", "target": "pinion"}],
     check="The pinion is on the motor shaft under the cart and its teeth sit in the rack.")
step("Screw on the pivot block", "Screw the pivot block to the front of the cart plate, its big hole running front to back.",
     ["pivot"], motion=down("pivot"), check="The pivot block sits at the front of the cart with its hole running front to back.")
step("Press in the front cart bearing", "Press a flanged bearing into the front of the pivot block, flange outside.",
     ["bearing-front"], motion=front("bearing-front"), check="A bearing flange sits flat on the front face of the pivot block.")
step("Press in the back cart bearing", "Press the second bearing into the back of the pivot block, flange outside.",
     ["bearing-back"], motion=[{"placement": "bearing-back", "from_offset": [0, 40, 0]}],
     check="A bearing flange sits flat on the back face of the pivot block.")
step("Fit the lower arm", "Hold the lower arm in front of the pivot block, its small hole lined up with the bearings.",
     ["arm-lower"], motion=front("arm-lower", d=60), check="The lower arm stands in front of the cart, small hole at the bottom by the bearings.")
step("Slide in the cart shaft", "Push the 48 mm shaft from the front through the arm and both bearings, then clamp the arm to it.",
     ["shaft-cart"], motion=front("shaft-cart", d=50), tools=[{"name": "2 mm hex key", "for": "arm clamp screw"}],
     check="The shaft passes through the arm and both bearings and pokes out of the back of the pivot block.")
step("Glue on the cart magnet", "Glue the round magnet centred on the back end of the cart shaft.",
     ["magnet-cart"], callouts=[{"text": "Centred on the shaft end", "target": "magnet-cart"}],
     check="A small round magnet sits in the middle of the shaft's back end.")
step("Fit the cart encoder mount", "Screw the encoder mount to the cart behind the pivot block, its hole around the magnet.",
     ["mount-cart"], motion=[{"placement": "mount-cart", "from_offset": [0, 30, 0]}],
     check="The mount stands behind the pivot block and the magnet is inside its hole.")
step("Screw on the cart encoder", "Screw an AS5600 board to the back of the mount, chip facing the magnet.",
     ["enc-cart"], motion=[{"placement": "enc-cart", "from_offset": [0, 30, 0]}],
     callouts=[{"text": "Chip side faces the magnet", "target": "enc-cart"}],
     check="The encoder board covers the mount's hole, pins at the bottom.")
step("Press in the elbow bearing", "Press a bearing into the big hole at the top of the lower arm, flange at the front.",
     ["bearing-elbow"], motion=front("bearing-elbow"), check="A bearing flange sits on the front of the lower arm's top hole.")
step("Fit the upper arm", "Hold the upper arm in front of the lower arm, its hole lined up with the elbow bearing.",
     ["arm-upper"], motion=front("arm-upper", d=60), check="The upper arm overlaps the top of the lower arm, in front of it.")
step("Slide in the elbow shaft", "Push the 26 mm shaft from the front through the upper arm and the elbow bearing, then clamp the upper arm to it.",
     ["shaft-elbow"], motion=front("shaft-elbow", d=50), tools=[{"name": "2 mm hex key", "for": "arm clamp screw"}],
     check="The elbow shaft joins the two arms and the upper arm swings freely.")
step("Glue on the elbow magnet", "Glue the second magnet centred on the back end of the elbow shaft.",
     ["magnet-elbow"], check="A small round magnet sits in the middle of the elbow shaft's back end.")
step("Fit the elbow encoder mount", "Screw the second encoder mount to the back of the lower arm, its hole around the magnet.",
     ["mount-elbow"], motion=[{"placement": "mount-elbow", "from_offset": [0, 30, 0]}],
     check="The mount sits on the back of the lower arm's top end.")
step("Screw on the elbow encoder", "Screw the second AS5600 board to the mount, chip facing the magnet.",
     ["enc-elbow"], motion=[{"placement": "enc-elbow", "from_offset": [0, 30, 0]}],
     check="The second encoder board covers the elbow mount's hole.")
step("Fit the left distance sensor", "Screw a bracket to the left end of the base and a VL53L0X to it, sensor facing the cart.",
     ["tof-bracket-left", "tof-left"], motion=down("tof-bracket-left", "tof-left"),
     check="A distance sensor stands at the left end of the rail, facing the cart.")
step("Fit the right distance sensor", "Do the same at the right end of the rail.",
     ["tof-bracket-right", "tof-right"], motion=down("tof-bracket-right", "tof-right"),
     check="A distance sensor stands at the right end of the rail, facing the cart.")
step("Place the Teensy", "Stick the Teensy to the front strip of the base, USB port to the left.",
     ["teensy"], motion=down("teensy"), check="The Teensy lies on the front strip with its USB port on the left.")
step("Place the motor driver", "Stick the DRV8874 board next to the Teensy.",
     ["driver"], motion=down("driver"), check="The motor driver board sits to the right of the Teensy.")
step("Place the 3.3 V regulator", "Stick the regulator next to the motor driver.",
     ["regulator"], motion=down("regulator"), check="The regulator sits to the right of the motor driver.")
step("Wire the motor", "Connect the motor's two terminals to the driver's OUT1 and OUT2. Leave slack so the cart can travel.",
     ["w-motor-a", "w-motor-b"], callouts=[{"text": "Leave a loop of slack for the cart", "target": "motor"}],
     check="Orange and brown wires run from the motor to OUT1 and OUT2.")
step("Wire the driver to the Teensy", "Connect pin 2 to IN1, pin 3 to IN2, 3.3 V to PMODE and nSLEEP, and GND to GND.",
     ["w-in1", "w-in2", "w-pmode", "w-nsleep", "w-logic-gnd"],
     check="Blue and purple wires go from pins 2 and 3 to IN1 and IN2, and two white wires to PMODE and nSLEEP.")
step("Wire the cart encoder", "Connect the cart encoder: VCC and GND to the regulator, SDA to pin 18, SCL to pin 19, and DIR to GND.",
     ["w-enc-cart-3v3", "w-enc-cart-gnd", "w-enc-cart-sda", "w-enc-cart-scl", "w-enc-cart-dir"],
     check="Four wires leave the cart encoder: red, black, green to pin 18 and yellow to pin 19.")
step("Wire the elbow encoder", "Run the elbow encoder's wires down the lower arm: VCC and GND to the regulator, SDA to pin 17, SCL to pin 16, DIR to GND.",
     ["w-enc-elbow-3v3", "w-enc-elbow-gnd", "w-enc-elbow-sda", "w-enc-elbow-scl", "w-enc-elbow-dir"],
     callouts=[{"text": "Tie the wires along the arm, leave slack at the cart joint", "target": "arm-lower"}],
     check="The elbow encoder's wires run down the lower arm, green to pin 17 and yellow to pin 16.")
step("Wire the distance sensors", "Left sensor: SDA to 18, SCL to 19. Right sensor: SDA to 17, SCL to 16. Both get 3.3 V and GND from the regulator.",
     ["w-tof-left-3v3", "w-tof-left-gnd", "w-tof-left-sda", "w-tof-left-scl",
      "w-tof-right-3v3", "w-tof-right-gnd", "w-tof-right-sda", "w-tof-right-scl"],
     check="Each distance sensor has red, black, green and yellow wires.")
step("Wire the power", "Connect the 12 V adapter to the driver's VIN and GND and to the regulator's IN+ and IN-, and join the Teensy's GND to the regulator's OUT-.",
     ["psu", "w-psu-vin", "w-psu-gnd", "w-reg-in", "w-reg-gnd", "w-common-gnd"],
     callouts=[{"text": "Plug the adapter in last", "target": "psu"}],
     check="Red and black wires run from the adapter to the driver and the regulator; the adapter is still unplugged.")

report = {"interference": studio.check_interference(), "clearance": studio.check_clearance()}
print(json.dumps(report, indent=2))
previews = Path(sys.argv[2]) if len(sys.argv) > 2 else None  # optional folder for preview PNGs
for view in ("iso", "front", "top") if previews else ():
    (previews / f"{view}.png").write_bytes(studio.render_preview(view=view))
print(json.dumps(studio.export(["glb", "stl", "step"], str(out) if out else None), indent=2))
