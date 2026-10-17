# Simon game wiring

Pin plan for the demo build. `firmware/simon/simon.ino` uses the same pins, so wire it exactly like this (or change both).

| Part | Pin | Goes to | Wire | Notes |
|---|---|---|---|---|
| Red button | `a` | Uno `d2` | red | Input with internal pull-up: pressed reads LOW. |
| Green button | `a` | Uno `d3` | green | |
| Blue button | `a` | Uno `d4` | blue | |
| Yellow button | `a` | Uno `d5` | yellow | |
| Red LED | `anode` (long leg) | Uno `d8` | red, inline 220 Ω resistor | |
| Green LED | `anode` | Uno `d9` | green, inline 220 Ω | |
| Blue LED | `anode` | Uno `d10` | blue, inline 220 Ω | |
| Yellow LED | `anode` | Uno `d11` | yellow, inline 220 Ω | |
| Piezo | `pos` | Uno `d12` | orange | Driven with `tone()`. |
| Grounds | button `b`, LED `cathode`, piezo `neg` | Uno GND | black | See below. |

## Grounds

Nine parts need ground, but the Uno has only three GND sockets (`gnd1` and `gnd2` on the power header, `gnd3` next to D13). Daisy-chain each group and run one wire per group to the Uno:

- Buttons: red `b` → green `b` → blue `b` → yellow `b` → Uno `gnd1`
- LEDs: red `cathode` → green → blue → yellow `cathode` → Uno `gnd2`
- Piezo: `neg` → Uno `gnd3`

With the MCP tools that is one `add_wire` per hop, all black, e.g. `add_wire("btn-red", "b", "btn-green", "b", color="black")`.

## Why these pins

- D0/D1 are the USB serial lines; leaving them free keeps uploads working with everything plugged in.
- D2–D5 and D8–D11 are plain digital pins grouped by role, so the firmware loops over them.
- D12 is free of any timer conflict with `tone()` on the Uno (D3 and D11 PWM stop while a tone plays, which doesn't matter here because the LEDs only switch on and off).
