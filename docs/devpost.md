# Physical Studio: Devpost draft

Draft for Hack the Valley 11. Deadline: **Oct 18, 8:00am EDT**. Edit freely; things the team still has to decide are marked **TODO**.

---

## Tagline

**IKEA-style instructions for any hardware project, and an AI that checks every step from a photo.**

Other options:
- *Say what you want to build. Physical Studio shows you how, one checked step at a time.*
- *Hardware gets git: every step is a commit, checked by Gemini from a photo of your bench.*

## Elevator pitch

Following a hardware tutorial usually means squinting at a blurry photo, guessing which breadboard hole it means, and finding the miswired ground an hour later. Physical Studio starts from **what's already on your bench**. Upload photos of it and say what you want to build. Gemini works out what's plugged in, writes a plan that builds on top of it as IKEA-style steps with numbered-hole pictures and a 3D model after every step, and then checks your work: after each step you take a photo, and one AI call tells you what's wrong, how to fix it, and gives you a 3D model of what you actually built. For bigger builds, our MCP server designs the project from a library of real, measured parts and plays it back as an animated 3D assembly guide.

**TODO (Senna):** which flow leads the demo and the pitch, the Build helper or the Assembly guides? This draft leads with the Build helper.

---

## Inspiration

<!-- TODO Kelly/Senna/Fei: swap in your own story; this is a starting point. -->
All three of us have lost evenings to hardware tutorials: the photo doesn't show which hole the wire goes in, the parts list assumes you're starting from nothing, and when the LED doesn't light you can't tell if the problem is the code, the wiring or the part. Flat-pack furniture solved this decades ago with numbered pictures and one change per step. We wanted that for electronics, plus something IKEA can't do: look at what you built and tell you whether it's right.

## What it does

Physical Studio has two parts that share one site, [physicalstudio.work](https://physicalstudio.work).

### 1. Build helper ([physicalstudio.work/studio/](https://physicalstudio.work/studio/))

1. **Show us your bench.** Say what you want to build and upload up to 10 photos of what's in front of you. Gemini scans them into a model of what's plugged in right now. That's commit #0, "Your bench now".
2. **Get a plan that builds on it.** Gemini writes IKEA-style steps: a picture with numbered breadboard holes, a 3D model of the bench after every step, and notes you get by clicking a part.
3. **Plans get checked before you see them.** `check_plan`, `check_circuit` and `check_extras` reject plans that move parts already on your bench, miswire an LED (the wire after the resistor has to reach ground; we check this with union-find over the breadboard strips) or add duplicate or USB-cable steps. A rejected plan goes back to the model to be fixed.
4. **Photo check after every step.** Upload a photo when you finish a step. One AI call returns a verdict (what's wrong and how to fix it) and a 3D model rebuilt from your photo. The **Commits** tab lists every checked step, like a git log for your build.

### 2. Assembly guides ([physicalstudio.work](https://physicalstudio.work))

- **Designed from real parts.** The Physical Studio **MCP server** lets an AI model design a project out of a parts library with real, measured dimensions, mounting holes and connector positions. Its tools are `search_parts`, `place_part`, `add_wire`, `check_interference`, `check_clearance`, `render_preview`, `add_step` and `export`. The model checks its own design for collisions and clearance and looks at rendered previews before it exports.
- **Played back as a 3D guide.** The React Three Fiber viewer plays the guide: animated steps, an exploded view, callouts, wire lengths, part legs and photo-textured boards.
- **Ready-made guides:**
  - **Traffic light:** Arduino Uno, red/yellow/green LEDs on D11/D10/D9 (each through 220 Ω) and a crosswalk button on D2.
  - **Double inverted pendulum:** a rack-and-pinion cart on an HGR20 rail with a Teensy 4.1, a DRV8874 motor driver, 2× AS5600 magnetic encoders and 2× VL53L0X distance sensors. 23 parts, 33 steps.

## How we built it

- **Gemini at the core.** Bench scans, plan writing and per-step photo checks all run on **Gemini 3.8 Flash** (`google-genai`) with **pydantic structured outputs**, so every answer arrives as typed data (parts, holes, wires, verdicts) instead of free text. The Assembly guide viewer uses the **Gemini Live API** (`gemini-3.8-live`) with ephemeral tokens, so the browser can talk to Gemini without ever seeing a key.
- **Reliability layer.** Calls go through a pool of 6 team keys with round-robin and hedged requests, and fall back to **OpenAI gpt-6.1-sol** (Responses API over `httpx`) when Gemini is rate-limited. Design jobs can run on OpenAI, DeepSeek, Gemini or Claude.
- **Deterministic checkers.** We don't trust a model with a circuit unchecked. `check_circuit` models the breadboard as strips and joins connected holes with union-find, so we can prove an LED's path reaches ground. `check_plan` and `check_extras` enforce "don't touch what's already there" and "no pointless steps".
- **3D.** The Build helper renders with Streamlit, Pillow, trimesh + numpy and a three.js (r170) scene bundled with esbuild. The MCP server (Python, FastMCP over HTTP) builds geometry with build123d/OpenCascade and exports GLB plus a steps JSON that the React 19 + Vite + React Three Fiber/drei viewer plays.
- **Shipping.** One **Vultr** server running Docker Compose behind Caddy for HTTPS, at **physicalstudio.work** (registered through Porkbun; `.work` is a GoDaddy Registry TLD).

## Challenges we ran into

- **Rate limits.** The free Gemini tier allows 20 Flash requests per day per project, and one build takes a lot of calls. We pooled keys across the team, parsed the API's retry delay so we wait exactly as long as needed, and added an OpenAI fallback so the demo never stalls.
- **AI-generated circuits that looked right but weren't.** Early plans often left the LED's ground leg on a strip that went nowhere. We fixed it twice over: a fixed wiring pattern in the prompt, plus a circuit checker that rejects any plan whose LED path doesn't reach ground.
- **The venue network blocked our brand-new domain.** Some networks block freshly registered domains, so we added an `sslip.io` fallback address on the same server.
- **Cutting scope.** We planned to 3D-print an enclosure for the demo but cut it for time, and moved the demo onto a breadboard, which turned out to suit the photo checks better.

## Accomplishments that we're proud of

- The photo-check loop works on a real bench: build a step, take a photo, get a specific fix (which wire, which hole), not just "looks wrong". <!-- TODO: paste a real verdict from the demo here -->

- Plans start from the bench you already have instead of assuming an empty table.
- A circuit checker that catches miswired grounds before a beginner ever sees the plan.
- A 23-part, 33-step double inverted pendulum guide built from real part dimensions, not just a blinky demo.
- Two working products, deployed on our own domain with HTTPS, built by three people in one weekend.

## What we learned

- Structured outputs plus a deterministic checker beat a bigger prompt. Once we could reject bad plans with code and send the reason back, the quality jumped.
- Multimodal models are much better at checking against a known expected state than at describing a photo from scratch, so every step carries its expected bench model.
- Plan for rate limits and flaky networks on day one, especially at a hackathon.
- Real dimensions matter: designing against measured parts caught problems a picture never would.

## What's next

- Merge the two flows: start from a photo of your bench and end with a full 3D assembly guide and enclosure.
- Live checking with the Gemini Live API and a camera, so you don't have to stop and take a photo.
- A bigger measured parts library, with community contributions.
- Bring back the 3D-printed enclosure: export print-ready STL files sized to the parts.
- Firmware generation and upload checks to go with each wiring plan.

## Built with

`gemini-api` · `google-genai` · `gemini-3.8-flash` · `gemini-live-api` · `openai` · `python` · `streamlit` · `pydantic` · `pillow` · `trimesh` · `numpy` · `three.js` · `esbuild` · `fastmcp` · `mcp` · `build123d` · `opencascade` · `react` · `vite` · `react-three-fiber` · `drei` · `typescript` · `node.js` · `httpx` · `docker` · `docker-compose` · `caddy` · `vultr` · `porkbun` · `godaddy-registry` · `arduino` · `teensy`

## Prize tracks to tick

- **Best Use of Gemini API:** multimodal photo checks are the core loop (bench scan → plan → per-step verdict + 3D model), plus the Live API in the viewer.
- **Best Use of Vultr:** the whole stack runs on one Vultr server.
- **Best Domain Name (GoDaddy Registry):** physicalstudio.work.

## Links

- Live site: https://physicalstudio.work
- Build helper: https://physicalstudio.work/studio/
- Code: https://github.com/notkelly1/Physical-Studio-Code
- Demo video: **TODO (Kelly):** link once uploaded (board task d0962092)

## Open questions before submitting

- [ ] **Senna:** which flow is the main demo? Reorder "What it does" to match.
- [ ] **Kelly/Senna/Fei:** personalize Inspiration.
- [ ] **Kelly:** demo video link.
- [ ] Check the model names (Gemini 3.8 Flash, gemini-3.8-live, gpt-6.1-sol) against the deployed config.
- [ ] Add screenshots: bench scan, a step with numbered holes, a photo verdict, the Commits tab, the pendulum guide.
