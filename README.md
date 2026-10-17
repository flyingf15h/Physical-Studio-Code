# Physical Studio Code

IKEA-style instructions for any hardware project, generated from a prompt. Built for Hack the Valley 11!

Describe a hardware project. Claude designs it out of real parts with real dimensions (through an MCP server), and the app turns the design into an animated step-by-step assembly guide. While you build, Gemini watches the workbench through the camera and tells you when a step is wrong.

## Tech stack

1. **Parts library** (JSON + STEP models): real dimensions, mounting holes, connector positions and keep-out zones, checked with calipers.
2. **MCP server** (Python, FastMCP, build123d/OpenCascade): `search_parts`, `get_part`, `create_enclosure`, `place_part`, `add_fastener`, `check_interference`, `check_clearance`, `add_step`, `render_preview`, `export`.
3. **Viewer** (React + React Three Fiber): loads the GLB and the steps JSON, with a timeline, exploded-view animations, highlights, tool callouts and dimension labels.
4. **Step tracking** (Gemini Live API): watches the build live and checks each step against the expected state.

Demo build: a traffic light around an Arduino Uno (red, yellow and green LEDs, a crosswalk button), designed live on [physicalstudio.work](https://physicalstudio.work) and built on a breadboard while Gemini watches. Pins: red D11, yellow D10, green D9 (each through 220 Ω), button D2 to GND.

## Repo layout

| Folder | What's in it |
|---|---|
| [`parts/`](parts) | Measured parts library (JSON per part, optional STEP). |
| [`mcp-server/`](mcp-server) | Python MCP server: parts lookup, placement, enclosure generation, export. Registered for Claude Code in `.mcp.json`. |
| [`schemas/`](schemas) | `steps.schema.json`, the contract between the server and the viewer, plus an example. |
| [`viewer/`](viewer) | React + R3F step-by-step assembly viewer. |
| [`circuit-studio/`](circuit-studio) | Senna's Streamlit prototype: photos + wiring instructions → Gemini → breadboard 3D model. |
| [`deploy/`](deploy) | Docker Compose for one Vultr server: Caddy (HTTPS), the viewer with the Gemini token endpoint, and the MCP server over HTTP. |
| [`firmware/`](firmware) | Arduino code for the demo (traffic light). |
| [`docs/`](docs) | Plan and the steps format. |

Quick start: `cd mcp-server && uv sync && uv run python examples/uno_box.py`, then `cd viewer && npm install && npm run dev` and open `/?design=out/arduino-uno-case`.
