# Physical Studio

**IKEA-style instructions for any hardware project, and an AI that checks every step from a photo of your bench.**

Say what you want to build. Physical Studio designs it from real, measured parts, writes a step-by-step guide with an animated picture and a 3D model for every step, and then checks your work: after each step you take a photo, and Gemini tells you exactly what's wrong and how to fix it, like a reversed LED, a wire on the wrong pin or a screw that isn't in.

It works for a blinking LED on a breadboard and for a double inverted pendulum on a linear rail: 30 real parts, 30 wires and 33 steps.

**Live at [physicalstudio.work](https://physicalstudio.work)** · built for Hack the Valley 11 · write-up in [`docs/devpost.md`](docs/devpost.md)

| Try it | |
|---|---|
| [Traffic light](https://physicalstudio.work/build/traffic-light) | Breadboard build: Arduino Uno, three LEDs, a crosswalk button, 18 steps with numbered holes |
| [Double inverted pendulum](https://physicalstudio.work/build/double-pendulum) | Hardware build: rack-and-pinion cart on an HGR20 rail, Teensy 4.1, DRV8874, 2× AS5600, 2× VL53L0X. 33 steps, 30 wires listed pin to pin |
| [Describe your own](https://physicalstudio.work) | Type a goal, add bench photos, links or a GitHub repo |

## What it does

**1. Describe it, or bring what you have.** Type a goal and add up to 10 photos of your bench, links to datasheets or tutorials, and connections you already know. Or paste a **GitHub repo or project page** under *Import a project*: Physical Studio reads its README, BOM, pin tables, firmware pin definitions and CAD files and turns them into a guide. Upload a **BOM** under *Parts I have* and the planner uses your parts first.

**2. It picks the right kind of build.** Circuits go to the breadboard planner. Anything with a case, a lid, motors, rails, gears or brackets goes to the CAD designer, every time (the routing comes from the prompt alone, so it's deterministic).

- **Breadboard builds** start from your bench: Gemini scans the photos into a model of what's already plugged in (commit #0, "Your bench now") and plans on top of it, never moving what's there.
- **Hardware builds** are designed by an AI driving our **MCP server**: it places real parts from a library of 118 measured parts (`parts/*.json`: dimensions, pins with their printed labels, mounting holes, STEP shapes, finishes), wires them pin to pin, checks interference and clearance, looks at rendered previews and fixes what it sees, then writes the guide.

**3. Every plan is checked by code before you see it.** We don't trust a model with a circuit unchecked:

- `check_circuit` models the breadboard as strips joined with union-find, so it can prove each LED's path reaches ground.
- `check_plan` and `check_extras` reject plans that move parts you already placed, skip a hole or add pointless steps.
- `check_interference` and `check_clearance` catch parts that collide or screws whose heads hit a component.
- `check_guide` holds every hardware guide to the bar of our hand-made pendulum guide: one part per step, a tool named for every screw, wiring grouped by part, a check line a camera can see, and no placeholder steps ("stage the motor", "drill a hole for the button").

A rejected plan goes back to the model with the reason, so it gets fixed instead of shipped.

**4. A guide you can actually follow.**

- **Animated step pictures:** each new part slides in along the direction it really goes (down into the breadboard, along a shaft's axis), screws turn as they go into their holes, and wires draw from end to end. The camera never moves, so the last frame is exactly the picture you check against. Replay and scrub through any step.
- **A 3D model after every step**, with that step's parts highlighted. Click any part or wire to see what it is, its real size, and both ends of the wire.
- **Pin-to-pin wiring:** every wiring step lists each connection with the labels printed on the boards and the wire colour, e.g. `Cart joint encoder SDA → Teensy 4.1 pin 18 / SDA (green wire)`.
- **Real looks:** boards wear their real top photos, metal parts get tiled material textures (ground steel, brushed aluminium, black anodised, PLA, plywood…) at real scale, and parts like carriage blocks and gearmotors are detailed two-material STEP shapes.
- **Check lines** on every step say what the photo should show ("Three screw heads sit flat in the Arduino's mounting holes").

**5. Build it, and get checked.** After each step, upload a photo. One Gemini call compares it with the step's reference picture and returns a verdict: done, or what's wrong and exactly what to move, turn or reconnect. Every checked step becomes a commit, so your build has a history like a git log.

**6. Bring your own AI.** *Design your own* gives you a personal key and a one-line setup for Claude Code, Claude Desktop or Cursor. Your AI designs with the same MCP tools, and the guide shows up under *Your projects*.

## How it's built

- **Gemini at the core.** Bench scans, plans and per-step photo checks run on **Gemini 3.8 Flash** (`google-genai`) with pydantic structured outputs, so every answer arrives as typed data (parts, holes, wires, verdicts). The 3D guide viewer talks to the **Gemini Live API** with short-lived tokens, so the browser never sees a key.
- **Reliability.** Calls go through a pool of team keys with round-robin and hedged requests. **OpenAI** is the fallback when the free Gemini quota runs out. Design jobs can run on Claude, Gemini, OpenAI or DeepSeek.
- **Geometry.** The MCP server (Python, FastMCP) builds real geometry with **build123d / OpenCascade**, exports GLB with photo and material textures, STL and STEP, and renders the step pictures and their motion frames itself (numpy rasteriser, one fixed camera per step).
- **Front end.** React 19 + Vite + React Three Fiber/drei.
- **Shipping.** One **Vultr** server running Docker Compose behind Caddy for HTTPS at **physicalstudio.work**.

## Guide checks

An AI writes each breadboard guide, so deterministic checks decide whether it's right. Problems go back to the AI for up to two repair rounds; a guide that still fails is shown with a red warning listing what's wrong, never as finished. A guide that passes says so on its Build page.

- **Wiring** (`bench/planner.py`): real holes, no double-booked holes, no part shorted in one strip, every LED traced from a board pin through its resistor to ground, steps and 3D model in agreement.
- **Footprints** (`bench/sketch.py`): parts sit in holes their legs can reach on a real breadboard (0.1" pitch, 0.3" between e and f). A 12 mm button straddles the gap in columns d and g, a 6 mm one in e and f; pin headers take neighbouring rows of one column; buzzer legs are about three rows apart.
- **Code vs wiring** (`bench/sketch.py`): every pin the sketch drives or reads has a wire, every wired pin is used by the sketch, and `analogWrite` is only used on PWM pins.
- **Compiles** (`bench/sketch.py`): every sketch, and every test-as-you-go sketch, is compiled with `arduino-cli` for the plan's board (Uno, Nano, Mega) before the guide is shown. Test sketches that don't compile are dropped. The server image ships the AVR core and common libraries (Servo, LedControl, LiquidCrystal I2C, DHT, NeoPixel, NewPing, Keypad).
- **Power and current** (`bench/power.py`, from the `electrical` data in [`parts/`](parts)):
  - LED current through its resistor, against the LED's and the pin's limits;
  - motors and other heavy loads wired straight to a GPIO pin;
  - modules on the wrong supply voltage (a 3.3 V-only part on 5V);
  - 5 V signals into a 3.3 V board, and 3.3 V-only inputs driven at 5 V;
  - how much the board's 5V and 3V3 pins are asked to supply. Steady draw over budget is a problem; brief peaks (a servo stalling) are a warning shown with the guide.

`tests/test_sketch.py` and `tests/test_power.py` run every check on the ready-made guides and on planted mistakes.

Not covered yet: Pico sketches aren't compiled (the guide says so), and no generated guide has been built on a real bench yet.

## Updates

- **Oct 20, 2026:** More Flatpack ideas. Each step's camera eases onto the parts it adds, which drop into place; parts hidden under others show through as a faint cyan ghost. Steps carry a one-line "why". The Drawing view inks outlines and creases with a screen-space edge shader. Hardware steps use the live 3D build as their main picture (the server render is kept as the camera check's reference). The 3D view draws on demand instead of every frame. Plywood grain is finer and straighter.
- **Oct 20, 2026:** CAD designs can't stop half-way: a text-only reply before export is answered with what's left, and export is refused (up to 3 times) while a part the request names isn't placed, a design with a board has no wires, or there are far fewer steps than parts. CAD guides with a board but no wires fail their checks.
- **Oct 20, 2026:** Studio lighting like Flatpack's: a warm key light with soft shadows fitted to each model, ambient occlusion (N8AO), neutral tone mapping and a dimmer sky light, for every guide (breadboard and CAD). Guide cards re-rendered.
- **Oct 20, 2026:** Breadboard guides' 3D models look like the real parts: an Uno with a drawn PCB (silkscreen with the real pin labels, traces, logo), headers at the real pin positions (wires land on the right pin), a DIP chip, metal USB-B, capacitors and ICSP header; bare-metal leads, glossy LEDs, resistors with colour bands for their value, real part colours. The guide cards are re-rendered from these models. Removed the contact shadow and the "checked automatically" line (failed checks and warnings still show).
- **Oct 20, 2026:** ESP32 and Teensy sketches are compiled too. Hardware/CAD guides get the power and motor-driver checks (stall current vs driver rating, supply peaks). The 3D view has Studio, Even light and Drawing looks, with a soft shadow under the model, and steps show parts and wires placed so far ([ and ] step through the guide). Ideas taken from Flatpack's interactive IKEA-style manuals. Fixed a crash on the Build page in newer Chrome.
- **Oct 20, 2026:** Power and current checks, with supply voltage, current and driver data on 55 library parts. The breadboard 3D model and step pictures use real column spacing (the e-f gap was drawn 12.7 mm wide instead of 7.62 mm).
- **Oct 20, 2026:** Guide checks for compiling, code pins vs wiring and part footprints. Guides record their check results, and the Build page shows them.
- **Oct 20, 2026:** The ready-made guide cards show renders of each finished build. The 3D builder draws a real-size Uno and recognisable modules (HC-SR04, 8×8 matrix, joystick, buzzer, button, LDR, thermistor).
- **Oct 20, 2026:** Ready-made guide fixes. The traffic light's 12 mm button moved to columns d/g so it fits, and the fire alarm no longer marks pin 13 as PWM.

## Repo layout

| Folder | What's in it |
|---|---|
| [`mcp-server/`](mcp-server) | The MCP design tools (`server.py`), design jobs (`jobs.py`), guide checks (`guide_check.py`), geometry/export/rendering, and the main site's build API (`physical_studio/bench/`: breadboard planner, CAD guides, imports, photo checks, ready-made guides). |
| [`viewer/`](viewer) | The main site: Dashboard, Your projects, the design and build pages, the 3D model, and the Gemini Live endpoints. |
| [`parts/`](parts) | The parts library: one JSON per part (dimensions, pins, mounting holes, looks), STEP shapes and `materials/`. |
| [`circuit-studio/`](circuit-studio) | The Build helper (Streamlit) at [`/studio/`](https://physicalstudio.work/studio/): the original bench-photo flow. |
| [`schemas/`](schemas) | `steps.schema.json`, the contract between the MCP server and the viewer. |
| [`deploy/`](deploy) | Docker Compose for the Vultr server: Caddy, the viewer, the MCP server and the Build helper. |
| [`firmware/`](firmware) | Arduino code for the traffic-light demo. |
| [`docs/`](docs) | Devpost write-up, steps format, wiring and the demo-video script. |

## Run it locally

```sh
# Backend (MCP tools + build API) on :8000
cd mcp-server && uv sync
MCP_TRANSPORT=http MCP_TOKEN=dev GEMINI_API_KEYS=k1,k2 uv run physical-studio-mcp

# Main site on :5173 (proxies /api to :8000)
cd viewer && npm install && npm run dev
```

Tests: `cd mcp-server && uv run pytest -q`, and `cd viewer && npx tsc -b && npx eslint src && npm run build`.
Rebuild the ready-made guides: `uv run python examples/ready_pendulum.py` (the pendulum takes a while: it renders every step and its motion frames).
Use the tools from Claude Code: `claude mcp add --transport http physical-studio https://physicalstudio.work/mcp --header "Authorization: Bearer <your key>"` (get a key from *Design your own* on the site).
