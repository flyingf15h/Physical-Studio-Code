# Traffic light wiring

Pin plan for the demo build (`mcp-server/examples/traffic_light.py`, `viewer/public/traffic-light`). `firmware/traffic-light/traffic-light.ino` uses the same pins, so wire it exactly like this (or change both).

| Part | Pin | Goes to | Wire | Notes |
|---|---|---|---|---|
| Red LED | `anode` (long leg) | Uno `d11` | red, inline 220 Ω resistor | Top of the column. |
| Yellow LED | `anode` | Uno `d10` | yellow, inline 220 Ω | |
| Green LED | `anode` | Uno `d9` | green, inline 220 Ω | |
| Crosswalk button | `a` | Uno `d2` | blue | Input with internal pull-up: pressed reads LOW. |
| Crosswalk button | `b` (same side as `a`) | Uno `gnd2` | black | |
| LED grounds | red `cathode` → yellow `cathode` → green `cathode` | Uno `gnd1` | black | Daisy-chained, see below. |

## Breadboard notes

- LED long leg = anode. Put the 220 Ω resistor between the Uno pin and the anode; the short leg (cathode, flat side of the rim) goes to ground.
- Chain the three cathodes along one breadboard ground rail (or wire red → yellow → green) and run a single black wire from it to `gnd1`. With the MCP tools that is one `add_wire` per hop, e.g. `add_wire("led-red", "cathode", "led-yellow", "cathode", color="black")`.
- The 12 mm tactile button has two pairs of legs that are always connected to each other. Use two legs on the same side (`a` and `b`) so the press actually opens and closes the circuit; if the light never reacts, or walks straight away, rotate the button 90°.
- No external resistor on the button: `INPUT_PULLUP` holds D2 HIGH until the press pulls it to GND.
- D0/D1 are the USB serial lines and stay free, so uploads work with everything plugged in.

## Behaviour

On power-up the LEDs flash red, yellow, green once (lamp test), then rest on green. A button press starts the walk cycle: yellow 3 s, red 8 s while pedestrians cross, red blinking 3 s, back to green. Green always lasts at least 5 s between walks; a press during that time is served when it runs out.
