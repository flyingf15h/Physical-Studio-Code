# Physical Studio: Devpost writeup

For Hack the Valley 11. Deadline: **Oct 18, 8:00am EDT**. Pitch: 4 min + 1 min Q&A (script and slides in [`pitch.md`](pitch.md) and [`slides.md`](slides.md)).

**Framing:** Physical Studio is **assembly visualization with correct dimensions**: an animated, IKEA-style 3D guide built from real, measured parts, so what you see on screen is what fits on your bench. Lead with that. The Commits tab is a feature, not the pitch; don't call it "git for hardware".

Paste each section below into the matching Devpost field. Items still to fill in are marked **TODO**.

---

## Tagline

**Say what you want to build. See every step in 3D, at real size, and let Gemini check your work.**

## Elevator pitch (Devpost "short description")

Hardware tutorials show a blurry photo and hope you guess right. Physical Studio turns a one-line prompt into an animated, IKEA-style 3D assembly guide built from real, measured parts: every board, LED, screw and mounting hole is at its true size, so the case it designs fits, the screws clear the headers, and the picture on each step matches what's on your bench. Then Gemini watches your build and tells you exactly what's wrong, like an LED in backwards.

---

## Inspiration

<!-- TODO Kelly/Senna/Fei: swap in a real moment from one of you if you have one. -->
Every one of us has lost an evening to a hardware tutorial: a photo that doesn't show which hole the wire goes in, a case that's 2 mm too small for the board, a screw that hits a header. Flat-pack furniture solved the first problem decades ago with numbered pictures and one change per step. But IKEA instructions work because IKEA knows the exact size of every part. We wanted that for electronics: a guide where every part on screen is the real part at its real size, so you can trust the picture.

## What it does

**1. Prompt to design, from real parts.** Type what you want, e.g. *"Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, a crosswalk button, USB accessible on the side."* An AI model designs it with our **MCP server**, using a library of 100+ parts whose dimensions, pin positions, mounting holes and connector positions come from datasheets and were checked with calipers. It never invents a number.

**2. Checked before you see it.** The model has to pass the same checks an engineer would: `check_interference` (do any parts collide?), `check_clearance` (is there room for fingers, screw heads and cables?) and `render_preview` (it looks at its own render and fixes what's off). One real catch: on the Arduino Uno, an M3 socket head at the mounting hole next to AREF/SCL overlaps the digital header, so the design leaves that hole empty and the guide says so.

**3. Played back as an animated 3D assembly guide.** Our React Three Fiber viewer plays one step per part: the board drops onto its standoffs, screws spin down into their holes, LEDs slide into the lid, wires draw from pin to pin. Exploded view, callouts ("USB-B lines up with this opening"), the tools for each step, wire lengths and photo-textured boards with real finishes. Every step has a reference picture and a "check" line saying what you should see.

**4. A case that fits.** Because the design uses true dimensions, the export includes a print-ready enclosure (base and lid STL) with cutouts where the USB and barrel jack meet the wall and holes where the LEDs and button poke through the lid. We printed it. <!-- TODO Kelly: confirm the printed case fit the real Uno first try; if yes, say "It fit first try." -->

**5. Gemini watches your bench.** Point a camera at your build or take a photo after a step. Gemini compares it with that step's expected 3D render and gives a verdict with a specific fix, e.g. *"The red LED is in backwards: the long leg should go toward the resistor."* <!-- TODO: paste the real verdict text from the recorded demo. --> A deterministic circuit checker (union-find over breadboard strips) rejects plans whose LED path doesn't reach ground before a beginner ever sees them.

**It goes past breadboards.** The ready-made **double inverted pendulum** guide is a rack-and-pinion cart on an HGR20 linear rail with a Teensy 4.1, a DRV8874 motor driver, two AS5600 magnetic encoders and two VL53L0X distance sensors: 30 parts, 33 steps, generated from its real CAD design with a 3D model per step.

Try it at [physicalstudio.work](https://physicalstudio.work). The traffic-light guide: [physicalstudio.work/guide?design=traffic-light](https://physicalstudio.work/guide?design=traffic-light).

## How we built it

- **Real-parts design engine.** A Python **MCP server** (FastMCP over HTTP) exposes `search_parts`, `get_part`, `place_part`, `add_fastener`, `add_wire`, `create_enclosure`, `check_interference`, `check_clearance`, `render_preview`, `add_step`, `check_guide` and `export`. Geometry is built with **build123d / OpenCascade**; each part is a JSON file of measured dimensions, pins and holes (`parts/*.json`). Units are millimetres throughout.
- **Any model can drive it.** Design jobs run on Claude, Gemini, OpenAI or DeepSeek through the same tools, with one shared design guide (part colours, lid-mounted parts, one step per part, camera-checkable steps). `check_guide` sends weak guides back to the model before export.
- **Export.** We tessellate each placement ourselves and write the GLB with **trimesh**, one node per part, plus a steps JSON (validated by `schemas/steps.schema.json`), a STEP file and print-ready STLs. (build123d's own glTF export split every shape into one node per face, so the viewer couldn't find parts by name.)
- **Viewer.** **React 19 + Vite + React Three Fiber/drei** plays the steps JSON: motion paths, exploded view, callouts, part legs, material textures (PCB, brushed aluminium, PLA…).
- **Gemini.** **Gemini 3.8 Flash** (`google-genai`) with **pydantic structured outputs** checks each step photo against the expected render and returns a typed verdict. The viewer uses the **Gemini Live API** (`gemini-3.8-live`) with ephemeral tokens, so the browser talks to Gemini without ever seeing a key.
- **Reliability.** A pool of team keys taken in turn, hedged requests, retry delays parsed from the API, and an OpenAI fallback when Gemini is rate-limited.
- **Shipping.** Docker Compose behind Caddy (HTTPS) on a **Vultr** server, at **physicalstudio.work**, a `.work` domain run by **GoDaddy Registry**. <!-- TODO tszfei: if the site has moved to Oracle Cloud, update this line and the Vultr prize line below. -->

## Challenges we ran into

- **Dimensions that looked right but weren't.** Datasheet drawings and KiCad footprints disagree with each other, and with the board on the desk. We caliper-checked every part in the demo builds and modelled header *housings* as keep-outs, not just pin rows. That's how the checker caught the screw that hits the Uno's header.
- **Models making things up.** Left alone, a model will guess a part's size from memory. The MCP tools only accept parts from the library, and the design guide forbids taking a size from an image or web page; photos can change a part's *look*, never its numbers.
- **Getting the animation to show the action.** Our first step animations zoomed and crossfaded, which hid what actually moved. We rebuilt them with a fixed camera: parts slide in along their insertion direction, screws turn as they go down, wires draw after the parts are in.
- **Rate limits.** The free Gemini tier allows 5 requests a minute and 20 a day per project, and a camera checking every few seconds burns through that fast. We pooled keys, parsed retry delays and added a fallback so the demo doesn't stall.
- **The venue network blocked our brand-new domain.** Some networks block freshly registered hostnames, so we kept an `sslip.io` address on the same server as a fallback.

## Accomplishments that we're proud of

- A guide where the 3D model is trustworthy: real parts at real sizes, checked for collisions and clearance before anyone sees it.
- A generated case we could actually print.
- Gemini catching a backwards LED from a phone photo and saying how to fix it.
- Going past blinky: a 30-part, 33-step inverted-pendulum build from real CAD.
- The same MCP tools work for Claude, Gemini, OpenAI and DeepSeek.
- Deployed on our own domain with HTTPS by three people in one weekend.

## What we learned

- Correct dimensions are the feature. Once every part was real, collisions, clearances, cutouts and the printed case all fell out of the same data.
- Tools plus deterministic checks beat a bigger prompt: rejecting a bad design with code and sending back the reason improved quality more than any prompt change.
- Multimodal models are far better at comparing a photo with a known expected picture than at describing a photo from scratch, so every step carries its expected render.
- Plan for rate limits and flaky networks on day one.

## What's next

- Grow the measured parts library, with community submissions checked against calipers.
- Start from a photo of what's already on your bench and build the guide on top of it.
- Continuous checking with the Gemini Live API, so you never stop to take a photo.
- Firmware generated alongside each guide, with an upload check.

## Built with

`gemini-api` · `google-genai` · `gemini-live-api` · `mcp` · `fastmcp` · `python` · `build123d` · `opencascade` · `trimesh` · `pydantic` · `react` · `vite` · `react-three-fiber` · `drei` · `three.js` · `typescript` · `node.js` · `streamlit` · `openai` · `claude` · `docker` · `caddy` · `vultr` · `godaddy-registry` · `arduino` · `teensy`

## Prize tracks to tick

- **Best Use of Gemini API:** Gemini checks every step against the expected 3D render (structured verdicts), Live API in the viewer, and Gemini can drive the MCP design tools.
- **Best Use of Vultr:** the whole stack runs on one Vultr server. <!-- TODO tszfei: drop if the live site is now on Oracle Cloud. -->
- **Best Domain Name (GoDaddy Registry):** physicalstudio.work.

## Links

- Live site: https://physicalstudio.work
- Traffic-light guide: https://physicalstudio.work/guide?design=traffic-light
- Code: https://github.com/flyingf15h/Physical-Studio-Code
- Demo video: **TODO:** link once uploaded

## Before you hit submit

- [ ] Demo video link (and paste the real Gemini verdict above).
- [ ] Screenshots, in this order: the traffic-light guide mid-animation, the exploded view, the printed case next to the 3D model, a Gemini verdict, the pendulum guide.
- [ ] Confirm hosting (Vultr or Oracle) and fix the two Vultr lines.
- [ ] Repo is public and the link works logged out.
- [ ] All three teammates added on Devpost; the three prize tracks ticked.
