# Physical Studio Code

IKEA-style instructions for any hardware project, generated from a prompt. Built for Hack the Valley 11!

Say what you want to build and photograph your bench. Gemini works out what's already plugged in, adds the parts you still need, and writes a step-by-step build plan with a picture and a 3D model for every step. After each step you take a photo, Gemini checks it against the plan and tells you exactly what's wrong and how to fix it, like a reversed LED or a wire one hole off.

Live at [physicalstudio.work](https://physicalstudio.work) (the Build helper is at [`/studio/`](https://physicalstudio.work/studio/)).

## How it works

1. **Start from your bench.** You type a goal ("Traffic light for an Arduino Uno …"), then add up to 10 photos and the parts you have. Gemini scans the photos into a model of what's plugged in right now. That model becomes commit #0, "Your bench now".
2. **Plan.** Gemini writes a plan that builds on your bench and picks parts from a library with real dimensions (`parts/*.json`). A checker rejects any plan that drops or moves parts you already placed, skips a hole, or leaves out a required part. Every step gets a numbered-hole picture, a "check" line saying what the photo should show, and a 3D model of the bench after that step. Click a part in the model to see what it is and how to spot it.
3. **Build and commit.** After a step, upload a photo. One AI call returns a verdict (done or problem, what's wrong, how to fix it) and a 3D model built from your photo. The Commits tab shows each commit with its photos, verdict and model.

Models: Gemini 3.8 Flash on a pool of keys, taken in turn. A rate-limited key sits out, and OpenAI is the fallback when Gemini is overloaded or out of quota.

Demo build: a traffic light on an Arduino Uno with a breadboard. Pins: red D11, yellow D10, green D9 (each through 220 Ω), crosswalk button D2 to GND with `INPUT_PULLUP`. Firmware is in [`firmware/traffic-light`](firmware/traffic-light), wiring in [`docs/traffic-light-wiring.md`](docs/traffic-light-wiring.md).

## Also in the repo: the enclosure pipeline

Before the Build helper, the project designed 3D-printed enclosures from a prompt. That pipeline still works and is live at [physicalstudio.work/guide?design=traffic-light](https://physicalstudio.work/guide?design=traffic-light):

- **MCP server** (Python, FastMCP, build123d/OpenCascade): `search_parts`, `get_part`, `create_enclosure`, `place_part`, `move_part`, `add_wire`, `check_interference`, `check_clearance`, `add_step`, `render_preview`, `export`. Claude (or OpenAI/DeepSeek/Gemini through `jobs.py`) designs with them.
- **Viewer** (React + React Three Fiber): an animated assembly guide from the exported GLB + steps JSON, with exploded views, callouts and part legs, plus a Gemini Live voice and step checker.

## Repo layout

| Folder | What's in it |
|---|---|
| [`circuit-studio/`](circuit-studio) | The Build helper (Streamlit): `app_plus.py` (entry point), `builder.py` (scan, plan, step commits, model pool), `diagram.py` (step pictures), `app.py` (photos → breadboard 3D model). |
| [`parts/`](parts) | Parts library (JSON per part: dimensions, pins, mounting holes). |
| [`mcp-server/`](mcp-server) | MCP server and design-job API for the enclosure pipeline. |
| [`viewer/`](viewer) | React + R3F assembly guide and the Gemini Live endpoints. `node scripts/gemini-smoke.mjs` tests the Gemini keys, Live and the step checker against the real API. |
| [`schemas/`](schemas) | `steps.schema.json`, the contract between the MCP server and the viewer. |
| [`deploy/`](deploy) | Docker Compose for one Vultr server: Caddy (HTTPS), the Build helper, the viewer and the MCP server. |
| [`firmware/`](firmware) | Arduino code for the demo (traffic light). |
| [`docs/`](docs) | Plan, steps format and wiring. |

Quick start, Build helper: `cd circuit-studio && pip install -r requirements.txt && GEMINI_API_KEYS=k1,k2 streamlit run app_plus.py`.
Enclosure pipeline: `cd mcp-server && uv sync && uv run python examples/traffic_light.py`, then `cd viewer && npm install && npm run dev`.
