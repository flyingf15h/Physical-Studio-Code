"""Writes the common hobby-electronics parts into parts/: boards, sensors, displays, motors, passives and
power, so the Build helper can look up whatever a beginner says they have.

    uv run python examples/common_parts.py

Numbers are typical datasheet / standard values for the usual breakout or package (2.54 mm header pitch,
TO-92/TO-220 outlines, 1/4 W axial resistors, common module board sizes). None are measured yet
(verified: false). Existing files with the same id are overwritten, so edit this script, not the JSON.
"""

import json
from pathlib import Path

PARTS = Path(__file__).resolve().parents[2] / "parts"
TYPICAL = "Typical datasheet/standard numbers for this part or its most common breakout; not yet measured"
PITCH = 2.54

# Looks for the guide's 3D view (appearance in parts/README.md).
BLUE_PCB = {"color": "#1f5fa8", "metallic": 0.1, "roughness": 0.6}
GREEN_PCB = {"color": "#1e6b3a", "metallic": 0.1, "roughness": 0.6}
BLACK_PCB = {"color": "#24262a", "metallic": 0.1, "roughness": 0.6}
PURPLE_PCB = {"color": "#5b3c8c", "metallic": 0.1, "roughness": 0.6}
BLACK = {"color": "#1d1f22", "metallic": 0.0, "roughness": 0.7}
WHITE = {"color": "#ece9e2", "metallic": 0.0, "roughness": 0.8}
BEIGE = {"color": "#d8c7a0", "metallic": 0.0, "roughness": 0.7}
METAL = {"color": "#b8bdc2", "metallic": 0.85, "roughness": 0.35}


def header(labels, x0, y, axis="x", z=0.0, direction=(0, 0, -1)):
    """One row of header pins, 2.54 mm apart, starting at (x0, y)."""
    pins = []
    for i, label in enumerate(labels):
        pid = label.lower().replace(" ", "_").replace("/", "_").replace("+", "plus").replace("-", "minus")
        x, yy = (x0 + i * PITCH, y) if axis == "x" else (x0, y + i * PITCH)
        pins.append({"id": pid, "label": label, "position": [round(x, 2), round(yy, 2), z], "direction": list(direction)})
    return pins


def legs(labels, x0, y, pitch=PITCH, length=10.0):
    """Through-hole legs pointing down, e.g. an LED or a TO-92 package."""
    return [{"id": label.lower().replace(" ", "_"), "label": label, "position": [round(x0 + i * pitch, 2), y, -length], "direction": [0, 0, -1]}
            for i, label in enumerate(labels)]


def holes(points, diameter):
    return [{"id": f"h{i + 1}", "position": [x, y, 0.0], "diameter": diameter} for i, (x, y) in enumerate(points)]


def part(id, name, category, size, pins=(), notes="", look=None, mounting=(), connectors=(), below=0.0, above=0.0, source=TYPICAL):
    x, y, z = size
    data = {"id": id, "name": name, "category": category, "source": source, "step_file": None,
            "body": {"size": [x, y, z]},
            "envelope": {"min": [0.0, 0.0, -below], "max": [x, y, z + above]},
            "mounting_holes": list(mounting), "connectors": list(connectors), "pins": list(pins),
            "notes": notes, "verified": False, "verified_by": None, "verified_on": None}
    if look:
        data["appearance"] = {**look, "source": "Typical colour of the common part"}
    return data


def board(id, name, size, rows, notes, look=BLUE_PCB, mounting=(), connectors=(), category="board", above=8.0):
    """A breakout or dev board: PCB of thickness size[2], header rows given as (labels, x0, y, axis)."""
    pins = [p for labels, x0, y, axis in rows for p in header(labels, x0, y, axis, z=-8.5)]
    return part(id, name, category, size, pins, notes, look, mounting, connectors, below=8.5, above=above)


def usb(face, center, w=8.0, h=3.0, kind="usb-micro"):
    return {"id": "usb", "type": kind, "face": face, "center": center, "size": [w, h], "protrusion": 1.0}


GPIO_NANO_L = ["D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "GND", "RST", "RX0", "TX1"]
GPIO_NANO_R = ["D13", "3V3", "REF", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "RST", "GND", "VIN"]
ESP32_L = ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27", "D14", "D12", "D13", "GND", "VIN"]
ESP32_R = ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "D17", "D16", "D4", "D2", "D15", "GND", "3V3"]
PICO_L = ["GP0", "GP1", "GND", "GP2", "GP3", "GP4", "GP5", "GND", "GP6", "GP7", "GP8", "GP9", "GND", "GP10", "GP11", "GP12", "GP13", "GND", "GP14", "GP15"]
PICO_R = ["VBUS", "VSYS", "GND", "3V3_EN", "3V3", "ADC_VREF", "GP28", "GND", "GP27", "GP26", "RUN", "GP22", "GND", "GP21", "GP20", "GP19", "GP18", "GND", "GP17", "GP16"]
NODEMCU_L = ["A0", "RSV", "RSV", "SD3", "SD2", "SD1", "CMD", "SD0", "CLK", "GND", "3V3", "EN", "RST", "GND", "VIN"]
NODEMCU_R = ["D0", "D1", "D2", "D3", "D4", "3V3", "GND", "D5", "D6", "D7", "D8", "RX", "TX", "GND", "3V3"]

PARTS_LIST = [
    # ---- boards ----
    board("arduino-nano", "Arduino Nano (ATmega328P)", [43.2, 18.5, 1.6],
          [(GPIO_NANO_L, 3.81, 1.65, "x"), (GPIO_NANO_R, 3.81, 16.89, "x")],
          "Breadboard-friendly: plug it across the centre gap so each pin has its own row. Pins D2-D13 are digital, A0-A7 analog (A6/A7 analog only), PWM on D3, D5, D6, D9, D10, D11. Runs at 5 V.",
          look=BLUE_PCB, connectors=[usb("-x", [0.0, 9.25, 3.6], 8.0, 4.0, "usb-mini")]),
    board("esp32-devkit-v1", "ESP32 DevKit V1 (30-pin)", [51.4, 28.3, 1.6],
          [(ESP32_L, 7.32, 1.45, "x"), (ESP32_R, 7.32, 26.85, "x")],
          "3.3 V logic: never feed 5 V into a GPIO. Wi-Fi + Bluetooth. Too wide for one breadboard: it straddles the gap with only one free row of holes on each side, or use two breadboards. D34, D35, VP and VN are input only.",
          look=BLACK_PCB, connectors=[usb("-x", [0.0, 14.15, 3.2])]),
    board("esp8266-nodemcu", "ESP8266 NodeMCU (v2, Amica)", [48.3, 25.4, 1.6],
          [(NODEMCU_L, 6.35, 1.27, "x"), (NODEMCU_R, 6.35, 24.13, "x")],
          "3.3 V logic. Wi-Fi. Label D0-D8 is not the GPIO number (D4 = GPIO2, the onboard LED). Only one analog input, A0 (0-3.3 V).",
          look=BLACK_PCB, connectors=[usb("-x", [0.0, 12.7, 3.2])]),
    board("raspberry-pi-pico", "Raspberry Pi Pico", [51.0, 21.0, 1.0],
          [(PICO_L, 1.61, 1.61, "x"), (PICO_R, 1.61, 19.39, "x")],
          "3.3 V logic, RP2040. Straddles the breadboard gap. 26 usable GPIO; GP26-GP28 are also analog inputs. The onboard LED is GP25.",
          look=GREEN_PCB, mounting=holes([(2.0, 4.8), (2.0, 16.2), (49.0, 4.8), (49.0, 16.2)], 2.1),
          connectors=[usb("-x", [0.0, 10.5, 2.4])]),
    part("raspberry-pi-4", "Raspberry Pi 4 Model B", "board", [85.0, 56.0, 1.4],
         header([f"GPIO header pin {i}" for i in range(1, 21)], 7.1, 52.5, z=10.0, direction=(0, 0, 1))
         + header([f"GPIO header pin {i}" for i in range(21, 41)], 7.1, 49.96, z=10.0, direction=(0, 0, 1)),
         "A small Linux computer. 3.3 V GPIO on the 40-pin header; never connect 5 V to a GPIO. Needs a 5 V 3 A USB-C supply.",
         GREEN_PCB, holes([(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)], 2.75),
         [{"id": "usb_c", "type": "usb-c", "face": "-y", "center": [11.2, 0.0, 3.2], "size": [9.0, 3.2], "protrusion": 1.0},
          {"id": "usb_a", "type": "usb-a", "face": "+x", "center": [85.0, 9.0, 8.0], "size": [14.0, 16.0], "protrusion": 2.0},
          {"id": "ethernet", "type": "rj45", "face": "+x", "center": [85.0, 45.75, 7.0], "size": [16.0, 13.5], "protrusion": 2.0}],
         above=16.0),
    part("breadboard-full", "Breadboard, full size (830 tie points)", "misc", [165.1, 54.6, 8.5], (),
         "Rows 1-63; holes a-e in one row are connected, f-j likewise; the centre gap separates them. Two power rails run along each long edge.",
         WHITE),
    part("breadboard-half", "Breadboard, half size (400 tie points)", "misc", [82.6, 54.6, 8.5], (),
         "Rows 1-30; holes a-e in one row are connected, f-j likewise. Two power rails along each long edge.", WHITE),
    # ---- inputs ----
    part("push-button-6mm", "Tactile push button 6x6 mm", "input", [6.0, 6.0, 5.0],
         [{"id": "1a", "label": "1", "position": [0.75, 0.0, -3.5], "direction": [0, 0, -1]}, {"id": "1b", "label": "1", "position": [5.25, 0.0, -3.5], "direction": [0, 0, -1]},
          {"id": "2a", "label": "2", "position": [0.75, 6.0, -3.5], "direction": [0, 0, -1]}, {"id": "2b", "label": "2", "position": [5.25, 6.0, -3.5], "direction": [0, 0, -1]}],
         "Straddle the breadboard's centre gap. The two legs on the same side are always connected; pressing joins the two sides. Read it with INPUT_PULLUP and wire the other side to GND.",
         BLACK, below=3.5),
    part("potentiometer-10k", "Potentiometer 10 kΩ (rotary, 16 mm)", "input", [16.0, 18.0, 10.0], legs(["1", "wiper", "3"], 3.0, 9.0, 5.0, 5.0),
         "Outer legs to 5 V (or 3.3 V) and GND, the middle leg (wiper) to an analog pin. Turning it changes the voltage on the wiper.",
         BLUE_PCB, below=5.0, above=15.0),
    part("trimpot-10k", "Trim potentiometer 10 kΩ (3386)", "input", [9.5, 10.0, 4.8], legs(["1", "wiper", "3"], 2.21, 5.0),
         "Small screwdriver-adjusted pot that fits a breadboard. Outer legs to power and GND, middle leg to an analog pin.", BLUE_PCB, below=5.0),
    part("slide-switch-spdt", "Slide switch SPDT (SS12D00)", "input", [8.6, 3.6, 3.7], legs(["1", "common", "3"], 1.76, 1.8, 2.54, 4.0),
         "The middle leg connects to one outer leg or the other depending on the slider.", BLACK, below=4.0, above=4.0),
    part("photoresistor-ldr", "Photoresistor (LDR, 5 mm)", "input", [5.1, 4.3, 2.0], legs(["1", "2"], 0.85, 2.15, 3.4, 20.0),
         "Resistance drops in light. Use it in a voltage divider with a 10 kΩ resistor and read the middle point on an analog pin.", BEIGE, below=20.0),
    part("thermistor-ntc-10k", "Thermistor NTC 10 kΩ", "input", [5.0, 3.0, 3.0], legs(["1", "2"], 1.25, 1.5, 2.5, 20.0),
         "Resistance drops as it warms. Voltage divider with a 10 kΩ resistor into an analog pin.", BLACK, below=20.0),
    part("hc-sr04", "Ultrasonic distance sensor HC-SR04", "input", [45.0, 20.0, 1.6], header(["VCC", "Trig", "Echo", "GND"], 18.69, 1.5, z=-8.5),
         "5 V sensor: Trig to an output pin, Echo to an input pin (on 3.3 V boards, put a voltage divider on Echo). Measures 2-400 cm.",
         BLUE_PCB, holes([(2.0, 2.0), (43.0, 2.0), (2.0, 18.0), (43.0, 18.0)], 1.8),
         [{"id": "transducers", "type": "ultrasonic", "face": "+z", "center": [22.5, 10.0, 13.6], "size": [42.0, 16.0], "protrusion": 12.0}],
         below=8.5, above=12.0),
    part("pir-hc-sr501", "PIR motion sensor HC-SR501", "input", [32.0, 24.0, 1.6], header(["VCC", "OUT", "GND"], 13.46, 2.0, z=-8.5),
         "Powered from 5 V; OUT goes high (3.3 V) for a few seconds when it sees movement. Two pots set sensitivity and on-time.",
         GREEN_PCB, holes([(2.0, 12.0), (30.0, 12.0)], 2.0),
         [{"id": "dome", "type": "pir-lens", "face": "+z", "center": [16.0, 12.0, 14.0], "size": [23.0, 23.0], "protrusion": 12.4}],
         below=8.5, above=12.4),
    part("dht11", "Temperature + humidity sensor DHT11", "input", [15.5, 12.0, 5.5], legs(["VCC", "DATA", "NC", "GND"], 3.94, 6.0, 2.54, 8.0),
         "One-wire style data pin: add a 10 kΩ pull-up from DATA to VCC (modules on a small board already have it).", {"color": "#4a8fd4", "metallic": 0.0, "roughness": 0.7}, below=8.0),
    part("dht22", "Temperature + humidity sensor DHT22 (AM2302)", "input", [25.1, 15.1, 7.7], legs(["VCC", "DATA", "NC", "GND"], 8.74, 7.55, 2.54, 8.0),
         "Like the DHT11 but more accurate. 10 kΩ pull-up from DATA to VCC.", WHITE, below=8.0),
    part("ds18b20", "Temperature sensor DS18B20 (TO-92)", "input", [4.8, 3.8, 4.8], legs(["GND", "DQ", "VDD"], 1.13, 1.9, 1.27, 12.0),
         "1-Wire: 4.7 kΩ pull-up from DQ to VDD. Flat side facing you: GND, DQ, VDD left to right.", BLACK, below=12.0),
    board("mpu6050-gy521", "Accelerometer + gyro MPU-6050 (GY-521)", [21.0, 16.0, 1.6], [(["VCC", "GND", "SCL", "SDA", "XDA", "XCL", "AD0", "INT"], 1.61, 1.5, "x")],
          "I2C at address 0x68 (0x69 with AD0 high). VCC 3.3-5 V; SDA/SCL to the board's I2C pins.", BLUE_PCB, holes([(2.5, 13.5), (18.5, 13.5)], 3.0), category="input", above=3.0),
    part("ir-receiver-vs1838b", "IR receiver VS1838B", "input", [6.0, 5.0, 9.0], legs(["OUT", "GND", "VCC"], 0.46, 2.5, 2.54, 12.0),
         "Receives TV-remote signals (38 kHz). OUT to a digital pin; works at 3.3 or 5 V.", BLACK, below=12.0),
    board("joystick-ky023", "Joystick module (KY-023)", [34.0, 26.0, 1.6], [(["GND", "+5V", "VRx", "VRy", "SW"], 1.0, 7.92, "y")],
          "Two pots: VRx and VRy to analog pins; SW is a push button (use INPUT_PULLUP).", BLACK_PCB, holes([(3.0, 3.0), (31.0, 3.0), (3.0, 23.0), (31.0, 23.0)], 3.0), category="input", above=32.0),
    board("rotary-encoder-ky040", "Rotary encoder (KY-040)", [32.0, 19.0, 1.6], [(["GND", "+", "SW", "DT", "CLK"], 1.0, 4.42, "y")],
          "CLK and DT to two digital pins (read the order to get direction); SW is the push button.", BLACK_PCB, holes([(14.5, 2.5), (14.5, 16.5)], 3.0), category="input", above=28.0),
    board("sound-sensor-ky038", "Sound sensor (KY-038)", [35.0, 15.0, 1.6], [(["AO", "GND", "+", "DO"], 30.5, 3.69, "y")],
          "AO is the microphone level (analog pin); DO goes high above the threshold set by the blue pot.", BLUE_PCB, holes([(9.0, 7.5)], 3.0), category="input", above=10.0),
    board("soil-moisture-sensor", "Soil moisture sensor (capacitive v1.2)", [98.0, 23.0, 1.6], [(["GND", "VCC", "AOUT"], 1.5, 8.96, "y")],
          "AOUT to an analog pin; lower reading = wetter soil. Only the probe end goes in the soil.", BLACK_PCB, category="input", above=3.0),
    board("water-level-sensor", "Water level sensor", [62.0, 20.0, 1.6], [(["S", "+", "-"], 58.0, 7.46, "y")],
          "S to an analog pin; the reading rises as more of the traces are under water.", {"color": "#c0392b", "metallic": 0.1, "roughness": 0.6}, category="input", above=1.0),
    board("touch-sensor-ttp223", "Capacitive touch sensor (TTP223)", [24.0, 15.0, 1.6], [(["GND", "VCC", "SIG"], 21.0, 4.96, "y")],
          "SIG goes high while the pad is touched. 2-5.5 V.", {"color": "#c0392b", "metallic": 0.1, "roughness": 0.6}, category="input", above=1.0),
    board("rfid-rc522", "RFID reader RC522 (13.56 MHz)", [60.0, 39.0, 1.6], [(["SDA", "SCK", "MOSI", "MISO", "IRQ", "GND", "RST", "3.3V"], 1.5, 10.61, "y")],
          "SPI at 3.3 V only. Reads MIFARE cards and key fobs.", BLUE_PCB, holes([(3.0, 3.0), (57.0, 3.0), (3.0, 36.0), (57.0, 36.0)], 3.0), category="input", above=3.0),
    part("keypad-4x4", "Membrane keypad 4x4", "input", [69.0, 76.0, 1.0], header(["R1", "R2", "R3", "R4", "C1", "C2", "C3", "C4"], 25.61, 76.0, z=0.5, direction=(0, 1, 0)),
         "Eight wires: four rows and four columns to eight digital pins; the Keypad library scans them.", BLACK, above=1.0),
    # ---- outputs ----
    part("led-3mm", "LED 3 mm", "output", [3.8, 3.8, 5.3], legs(["anode", "cathode"], 3.17, 1.9, -2.54, 10.0),
         "Long leg is the anode (+). Needs a series resistor (220-330 Ω at 5 V).", {"color": "#d94b4b", "metallic": 0.0, "roughness": 0.3}, below=10.0),
    part("led-rgb-5mm", "RGB LED 5 mm (common cathode)", "output", [5.8, 5.8, 8.6], legs(["red", "cathode", "green", "blue"], 0.0, 2.9, 1.9, 10.0),
         "The longest leg is the common cathode (to GND). Each colour leg needs its own 220 Ω resistor to a PWM pin.", WHITE, below=10.0),
    part("buzzer-active-12mm", "Active buzzer 12 mm (5 V)", "output", [12.0, 12.0, 9.5], legs(["plus", "minus"], 2.2, 6.0, 7.6, 8.0),
         "Beeps by itself when powered: + (longer leg, marked) to a digital pin, - to GND. A passive buzzer needs tone() instead.", BLACK, below=8.0),
    part("servo-sg90", "Micro servo SG90 (9 g)", "output", [22.8, 12.2, 22.7],
         [{"id": "signal", "label": "Signal (orange)", "position": [0.0, 6.1, 10.0], "direction": [-1, 0, 0]},
          {"id": "vcc", "label": "V+ (red)", "position": [0.0, 6.1, 9.0], "direction": [-1, 0, 0]},
          {"id": "gnd", "label": "GND (brown)", "position": [0.0, 6.1, 8.0], "direction": [-1, 0, 0]}],
         "Orange = signal to a PWM pin, red = 5 V, brown = GND. 0-180°. Power several servos from a separate 5 V supply with a shared GND.",
         {"color": "#2f6fc7", "metallic": 0.0, "roughness": 0.5}, holes([(-2.35, 6.1), (25.15, 6.1)], 2.0), above=6.0),
    part("servo-mg996r", "Servo MG996R (metal gear)", "output", [40.7, 19.7, 42.9],
         [{"id": "signal", "label": "Signal (orange)", "position": [0.0, 9.85, 20.0], "direction": [-1, 0, 0]},
          {"id": "vcc", "label": "V+ (red)", "position": [0.0, 9.85, 19.0], "direction": [-1, 0, 0]},
          {"id": "gnd", "label": "GND (brown)", "position": [0.0, 9.85, 18.0], "direction": [-1, 0, 0]}],
         "Needs its own 5-6 V supply (up to 2.5 A when stalled); share GND with the board.", BLACK,
         holes([(-4.0, 4.9), (-4.0, 14.8), (44.7, 4.9), (44.7, 14.8)], 4.5), above=6.0),
    part("stepper-28byj48", "Stepper motor 28BYJ-48 (5 V)", "output", [28.0, 28.0, 19.0],
         [{"id": "cable", "label": "5-wire cable to ULN2003 board", "position": [14.0, 0.0, 9.0], "direction": [0, -1, 0]}],
         "Plug its cable into a ULN2003 driver board; never drive it straight from GPIO pins. 2048 steps per turn.", METAL,
         holes([(-3.5, 14.0), (31.5, 14.0)], 4.2), above=10.0),
    board("uln2003-driver", "Stepper driver board ULN2003", [35.0, 32.0, 1.6], [(["IN1", "IN2", "IN3", "IN4"], 1.5, 12.19, "y"), (["-", "+"], 30.0, 14.73, "y")],
          "IN1-IN4 to four digital pins; + to 5 V, - to GND. The white socket takes the 28BYJ-48's plug.", GREEN_PCB,
          holes([(2.5, 2.5), (32.5, 2.5), (2.5, 29.5), (32.5, 29.5)], 3.0), above=12.0),
    board("l298n-driver", "Motor driver L298N (dual H-bridge)", [43.0, 43.0, 1.6], [(["ENA", "IN1", "IN2", "IN3", "IN4", "ENB"], 14.15, 2.0, "x")],
          "Drives two DC motors (or one stepper) from 5-35 V. ENA/ENB to PWM pins, IN1-IN4 to digital pins; share GND with the board.",
          {"color": "#c0392b", "metallic": 0.1, "roughness": 0.6}, holes([(3.0, 3.0), (40.0, 3.0), (3.0, 40.0), (40.0, 40.0)], 3.0), above=27.0),
    part("dc-motor-130", "DC hobby motor (130 size, 3-6 V)", "output", [27.5, 20.0, 15.0],
         [{"id": "plus", "label": "+", "position": [0.0, 5.0, 7.5], "direction": [-1, 0, 0]}, {"id": "minus", "label": "-", "position": [0.0, 15.0, 7.5], "direction": [-1, 0, 0]}],
         "Never run it straight from a GPIO pin: use a transistor/MOSFET with a flyback diode, or a motor driver.", METAL, above=0.0),
    board("relay-module-1ch", "Relay module, 1 channel (5 V)", [50.0, 26.0, 1.6], [(["VCC", "GND", "IN"], 1.5, 10.46, "y")],
          "IN from a digital pin switches the relay. Only switch low voltages unless you know mains wiring.", BLUE_PCB,
          holes([(3.0, 3.0), (47.0, 3.0), (3.0, 23.0), (47.0, 23.0)], 3.0), above=17.0),
    board("oled-ssd1306-128x64", "OLED display 0.96\" 128x64 (SSD1306, I2C)", [27.3, 27.8, 1.6], [(["GND", "VCC", "SCL", "SDA"], 9.84, 25.5, "x")],
          "I2C at 0x3C. VCC 3.3-5 V. Use the Adafruit SSD1306 or U8g2 library.", BLUE_PCB, holes([(2.0, 2.0), (25.3, 2.0), (2.0, 25.8), (25.3, 25.8)], 2.0),
          category="output", above=2.1),
    board("lcd-1602-i2c", "LCD 16x2 with I2C backpack", [80.0, 36.0, 1.6], [(["GND", "VCC", "SDA", "SCL"], -2.0, 13.19, "y")],
          "Only four wires thanks to the I2C backpack (address 0x27 or 0x3F). Turn the backpack's pot if the text is invisible.", {"color": "#2e7d32", "metallic": 0.1, "roughness": 0.6},
          holes([(2.5, 2.5), (77.5, 2.5), (2.5, 33.5), (77.5, 33.5)], 3.0), category="output", above=9.7),
    part("seven-segment-1digit", "7-segment display, 1 digit 0.56\" (common cathode)", "output", [12.6, 19.0, 8.0],
         legs(["E", "D", "COM", "C", "DP"], 1.22, 0.0, 2.54, 6.0) + legs(["G", "F", "COM2", "A", "B"], 1.22, 15.24, 2.54, 6.0),
         "Each segment needs its own 220 Ω resistor; the two COM pins go to GND.", BLACK, below=6.0),
    board("tm1637-4digit", "4-digit display module TM1637", [42.0, 24.0, 1.6], [(["CLK", "DIO", "VCC", "GND"], 40.0, 8.19, "y")],
          "Two data wires (CLK, DIO) to any digital pins; TM1637Display library.", BLUE_PCB, holes([(2.0, 2.0), (40.0, 2.0), (2.0, 22.0), (40.0, 22.0)], 2.2),
          category="output", above=8.0),
    part("neopixel-ring-12", "NeoPixel ring, 12 LEDs (WS2812B)", "output", [37.0, 37.0, 3.2], header(["DIN", "5V", "GND", "DOUT"], 14.69, 3.0, z=0.0),
         "Data into DIN through a 330 Ω resistor; 5 V supply with a 1000 µF capacitor across it for more than a few LEDs.", BLACK_PCB),
    # ---- passives, power, communication ----
    part("resistor-220", "Resistor 220 Ω (1/4 W)", "misc", [6.3, 2.5, 2.5], legs(["1", "2"], -1.93, 1.25, 10.16, 3.0),
         "Bands red, red, brown (gold). Either way round. The usual LED resistor at 5 V.", BEIGE, below=3.0),
    part("resistor-1k", "Resistor 1 kΩ (1/4 W)", "misc", [6.3, 2.5, 2.5], legs(["1", "2"], -1.93, 1.25, 10.16, 3.0),
         "Bands brown, black, red (gold). Common base resistor for a transistor.", BEIGE, below=3.0),
    part("resistor-10k", "Resistor 10 kΩ (1/4 W)", "misc", [6.3, 2.5, 2.5], legs(["1", "2"], -1.93, 1.25, 10.16, 3.0),
         "Bands brown, black, orange (gold). Common pull-up/pull-down and voltage-divider value.", BEIGE, below=3.0),
    part("capacitor-ceramic-100nf", "Ceramic capacitor 100 nF", "misc", [5.0, 2.5, 5.0], legs(["1", "2"], 1.23, 1.25, 2.54, 5.0),
         "Marked 104. Either way round. Put one across the power pins of a chip or module to smooth noise.", {"color": "#d9a441", "metallic": 0.0, "roughness": 0.6}, below=5.0),
    part("capacitor-electrolytic-100uf", "Electrolytic capacitor 100 µF 25 V", "misc", [6.3, 6.3, 11.0], legs(["plus", "minus"], 1.9, 3.15, 2.5, 5.0),
         "Polarised: the stripe marks the minus leg (also the shorter one). Wrong way round can make it pop.", {"color": "#1c2f6b", "metallic": 0.2, "roughness": 0.4}, below=5.0),
    part("diode-1n4007", "Diode 1N4007", "misc", [5.2, 2.7, 2.7], legs(["anode", "cathode"], -2.44, 1.35, 10.16, 3.0),
         "The silver band is the cathode. Use as a flyback diode across motors and relay coils (band towards +).", BLACK, below=3.0),
    part("transistor-2n2222", "NPN transistor 2N2222A (TO-92)", "misc", [4.8, 3.8, 4.8], legs(["E", "B", "C"], 1.13, 1.9, 1.27, 12.0),
         "Flat side facing you: E, B, C. 1 kΩ from a GPIO pin to the base; the load goes between + and the collector.", BLACK, below=12.0),
    part("mosfet-irlz44n", "N-channel MOSFET IRLZ44N (TO-220, logic level)", "misc", [10.0, 4.5, 15.0], legs(["G", "D", "S"], 2.46, 2.25, 2.54, 13.0),
         "Logic-level: switches a motor or LED strip from a 5 V pin. Gate through 220 Ω, 10 kΩ gate-to-source pull-down; add a flyback diode for motors.",
         BLACK, holes([(5.0, 2.25)], 3.6), below=13.0, above=6.0),
    part("regulator-7805", "Voltage regulator 7805 (5 V, TO-220)", "misc", [10.0, 4.5, 15.0], legs(["IN", "GND", "OUT"], 2.46, 2.25, 2.54, 13.0),
         "7-35 V in, 5 V out (up to 1 A, gets hot). 0.33 µF on the input and 0.1 µF on the output.", BLACK, holes([(5.0, 2.25)], 3.6), below=13.0, above=6.0),
    part("battery-9v", "9 V battery", "misc", [48.5, 26.5, 17.5],
         [{"id": "plus", "label": "+", "position": [6.5, 13.25, 17.5], "direction": [0, 0, 1]}, {"id": "minus", "label": "-", "position": [19.2, 13.25, 17.5], "direction": [0, 0, 1]}],
         "Use a snap connector. Fine for a board's VIN, too weak for motors.", {"color": "#202326", "metallic": 0.1, "roughness": 0.5}),
    part("battery-holder-4xaa", "Battery holder, 4x AA (6 V)", "misc", [62.0, 57.0, 15.0],
         [{"id": "plus", "label": "+ (red wire)", "position": [0.0, 10.0, 7.5], "direction": [-1, 0, 0]}, {"id": "minus", "label": "- (black wire)", "position": [0.0, 47.0, 7.5], "direction": [-1, 0, 0]}],
         "6 V with alkaline cells: good for servos and small motors. Share GND with the board.", BLACK),
    board("hc-05-bluetooth", "Bluetooth module HC-05", [37.0, 16.0, 1.6], [(["STATE", "RXD", "TXD", "GND", "VCC", "EN"], 1.5, 1.65, "y")],
          "Serial Bluetooth: TXD to the board's RX, RXD to TX through a voltage divider (3.3 V input). Default PIN 1234.", BLUE_PCB, category="misc", above=3.0),
    board("microsd-module", "MicroSD card module (SPI)", [42.0, 24.0, 1.6], [(["GND", "VCC", "MISO", "MOSI", "SCK", "CS"], 1.5, 5.65, "y")],
          "SPI: MISO, MOSI and SCK to the board's SPI pins, CS to any digital pin. FAT32 cards.", BLUE_PCB, holes([(3.0, 3.0), (39.0, 3.0), (3.0, 21.0), (39.0, 21.0)], 3.0),
          category="misc", above=3.0),
]


def main():
    PARTS.mkdir(exist_ok=True)
    for data in PARTS_LIST:
        (PARTS / f"{data['id']}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(PARTS_LIST)} parts to {PARTS}")


if __name__ == "__main__":
    main()
