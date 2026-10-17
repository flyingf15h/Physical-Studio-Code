# Physical Studio

IKEA-style instructions for any hardware project, generated from a prompt. Built for Hack the Valley 11.

Describe a hardware project. Claude designs it out of real parts with real dimensions (through an MCP server), and the app turns the design into an animated step-by-step assembly guide. While you build, Gemini watches the workbench through the camera and tells you when a step is wrong.

## How it fits together

1. **Parts library** (JSON + STEP models): real dimensions, mounting holes, connector positions and keep-out zones, checked with calipers.
2. **MCP server** (Python, FastMCP, build123d/OpenCascade): `search_parts`, `get_part`, `create_enclosure`, `place_part`, `add_fastener`, `check_interference`, `check_clearance`, `add_step`, `render_preview`, `export`.
3. **Viewer** (React + React Three Fiber): loads the GLB and the steps JSON, with a timeline, exploded-view animations, highlights, tool callouts and dimension labels.
4. **Step tracking** (Gemini Live API): watches the build live and checks each step against the expected state.

Demo build: a Simon memory game in a printed case around an Arduino Uno (4 buttons with LEDs and a buzzer, USB reachable on the side).

## Hackathon

- Devpost due **Oct 18, 2026, 8:00am EDT**. The GitHub link is required, the pitch is 4 minutes and Q&A is 1 minute.
- Tracks: Top 3, MLH Best Use of Gemini API, MLH Best Use of Vultr (host the MCP server/backend), MLH Best Domain Name (GoDaddy Registry). Maybe Climate/Sustainability (repair-guide angle) and the DEV Writing Challenge after the event.

The full planning conversation (parts lists, timeline, risks, track reasoning) is in [docs/hack-the-valley-plan.md](docs/hack-the-valley-plan.md).
