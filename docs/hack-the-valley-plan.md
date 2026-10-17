# Hack the Valley 11: Project Plan Conversation

---

## User

figure out a project plan with a list of materials for hack the valley based on this idea

*[Screenshot of Discord messages from darsh:]*
> it's still a cool idea for like the step by step hardware tracking thing
> i wouldn't say it's a new vcs for hardware
> cause you can make like animations of assembly
> for custom projects and that would be cool
> and if you could connect that to an mcp with proper dimensioning given
> that would be really goated cause then you could prompt to an actual visualization of a hardware project
> with opus 5.5 being good enough for cad

## Claude

Here's a plan built around what darsh described: you describe a hardware project, Claude designs it from real part dimensions through an MCP server, and the app turns the result into an animated step-by-step assembly guide. To show it working, you'd build one real project at the hackathon by following your own app's instructions.

### The pitch

**"IKEA instructions for any hardware project, generated from a prompt."** Like darsh said, don't call it a VCS for hardware. Pitch it as assembly visualization.

The main technical claim is **correct dimensions**. Claude doesn't make up measurements. Every part comes from a library with measured or manufacturer dimensions, and the MCP tools force Claude to place real parts, then check that they fit.

### Architecture

1. **Parts library** (JSON files plus STEP models). Each part records its size, mounting holes, connector positions and keep-out zones. You can get STEP files from KiCad's 3D library, SnapEDA or manufacturer pages. Check them with calipers on the parts you actually bring.
2. **MCP server** (Python with FastMCP and build123d, which uses the OpenCascade CAD engine). Tools:
   - `search_parts`, `get_part`: look up parts and their real dimensions
   - `create_enclosure(params)`: parametric box/shell with wall thickness, lid style, screw bosses
   - `place_part(id, position, rotation)`, `add_fastener(type, at)`
   - `check_interference()`, `check_clearance()`: catch collisions before export
   - `add_step(text, parts, motion, tool)`: defines one assembly step and its animation
   - `render_preview()`: returns a PNG so Claude can look at its own design and fix it
   - `export(stl | step | glb)`
3. **Viewer** (React with Three Fiber). It loads the GLB plus the steps JSON and shows a timeline scrubber. Each step animates parts flying in from an exploded view, highlights the new parts, shows tool callouts ("M3 screw, 2.5mm hex") and labels key dimensions.
4. **Step tracking** (stretch goal, but it's the "tracking" part darsh liked). A phone or webcam points at the bench. When you say "done," Claude's vision compares the photo to the rendered expected state for that step, then either moves on or flags what's wrong ("OLED is upside down").

### Demo project: a small macropad

It's simple, prints in about 1.5 hours and is easy to show off. The live demo: type "4-key macropad with an OLED and a knob, Pico inside, USB-C on the back." The app generates the CAD and the guide, you print the case and assemble it on stage following the animation, then plug it in and it works.

### Materials list (2 sets, so one can be a spare)

| Item | Qty | ~Cost (CAD) |
|---|---|---|
| Raspberry Pi Pico / Pico 2 (with headers) | 2 | $20 |
| MX-style switches | 10 | $10 |
| Keycaps (blank 1u) | 10 | $8 |
| Hot-swap sockets (Kailh), so no soldering on stage | 10 | $6 |
| SSD1306 0.96" I2C OLED | 2 | $12 |
| EC11 rotary encoder + knob | 2 | $8 |
| M3 + M2 screw assortment + heat-set inserts | 1 kit | $20 |
| Dupont/silicone hookup wire | 1 | $8 |
| USB-C to micro-USB cable (or USB-C Pico clone) | 2 | $10 |
| PLA filament (1 spool) | 1 | $25 |
| Digital calipers (for measuring parts, and a nice prop for judges) | 1 | $20 |
| Phone tripod / webcam (for step tracking) | 1 | $15 |
| Soldering iron, solder, flush cutters, hex drivers | — | bring own |
| 3D printer (Bambu A1 mini or similar) | 1 | bring/borrow |
| **Total** | | **~$160 + printer** |

**Software:** Claude API key (Opus 5.5), build123d, FastMCP, trimesh (to export GLB), three.js / React Three Fiber, CircuitPython or KMK for the macropad firmware.

### 36-hour timeline (4 people)

| Hours | CAD/MCP (2 people) | Viewer (1 person) | Hardware/tracking (1 person) |
|---|---|---|---|
| 0–4 | Parts library JSON for ~10 parts, build123d env working | Viewer skeleton, loads a GLB | Measure parts, check them against the STEP files |
| 4–12 | MCP tools: place, enclosure, export | Steps JSON format, exploded animation | Test print the base enclosure early |
| 12–20 | Interference check, `render_preview` loop | Timeline, highlights, callouts | Firmware, wiring |
| 20–28 | Prompt → full macropad design works end to end | Polish, dimension labels | Step tracking with vision |
| 28–32 | Print the generated case | Record a backup demo video | Assemble from the app's guide |
| 32–36 | Devpost, slides, rehearse | | |

### Risks

- **Claude producing broken geometry:** keep the tools high-level (templates plus placing parts) rather than raw CAD code, and use the `render_preview` loop so it can check its own work.
- **OpenCascade install problems:** set up the Python environment before the event on every laptop. Setting up an environment isn't writing project code, but read HTV's rules on pre-written work.
- **Print time or printer failure:** pre-print a case from a hand-made design as a fallback, and have the backup video ready.
- **Scope creep:** step tracking is the first thing to cut. The demo works without it.

### Before you buy

My search didn't find the dates for this year's main 36-hour event. The 2024 edition was October 4–6, and today is October 14, so check that it hasn't already happened. Also ask the organizers whether they lend out hardware or provide printer access.

Sources:
- [Hack the Valley Hack Day (MLH)](https://events.mlh.com/events/14400-hack-the-valley-hack-day)
- [Hack the Valley on U of T SOP](https://sop.utoronto.ca/group/hack-the-valley)
- [SDGs@UofT x Hack the Valley](https://sdg.utoronto.ca/sdgsuoft-x-hack-the-valley/)

---

## User

we dont have a lot of these parts i have an arduino uno not a raspberry pi i dont have hot swap sockets or an oled or a rotary encoder

## Claude

The Uno can't act as a USB keyboard without reflashing its USB chip, so I'd drop the macropad. A **Simon memory game** in a printed case works better. It's playable at the judging table and only needs the Uno plus cheap parts from a typical starter kit.

The Uno is also a good test of the dimensioning claim. Its 4 mounting holes are unevenly spaced, and the USB-B and barrel jack sit at fixed spots on one edge. If the generated case gets the standoffs and the cutouts for those two ports right on the first print, judges can see the dimensions are real.

### Revised demo build

Prompt: "Simon game for an Arduino Uno, 4 colored buttons with LEDs, buzzer, USB accessible on the side."

| Item | Qty | Have it? | ~Cost if not (CAD) |
|---|---|---|---|
| Arduino Uno | 1 | ✅ | — |
| 12mm tactile buttons + caps (or 24mm arcade buttons, nicer) | 4 | ? | $5 / $12 |
| 5mm LEDs, 4 colors | 4 | ? | $3 |
| 220Ω resistors | 4 | ? | $2 |
| Piezo buzzer | 1 | ? | $2 |
| Jumper wires (M-F) | ~20 | ? | $5 |
| Small perfboard or mini breadboard | 1 | ? | $4 |
| M3 screws + nuts (Uno mounting) | 4–8 | ? | $5 |
| PLA + printer access | — | ? | — |
| Calipers | 1 | ? | $20 |
| Phone + tripod (step tracking) | 1 | ? | $15 |

If you have to buy everything except the Uno, it comes to about **$50–60**, or under $10 if you have a starter kit.

### What changes in the plan

- **Parts library** gets smaller: Uno, tactile button, 5mm LED, piezo, M3 screw. That's 5 parts to measure and model instead of 10.
- **Firmware** is about 50 lines of Arduino code instead of KMK, so the hardware person has more time for step tracking.
- **The assembly guide gets more interesting:** screw the Uno onto standoffs, press the LEDs into the lid, mount the buttons, wire them, close the lid. Each step clearly shows something new being added.

Everything else in the plan stays the same: the MCP tools, the viewer, the timeline and the risks.

What other parts do you have? If you've got a servo, an ultrasonic sensor, or a 16x2 LCD from a starter kit, a project with a moving part (like a servo-driven desk radar) would make an even better assembly animation.

---

## User

dont include the parts used for the demo only include sutff we need for the actual project

## Claude

Without the demo parts, the project is almost all software. The only hardware it needs is for the step-tracking feature.

### Hardware

| Item | Qty | Why | ~Cost (CAD) |
|---|---|---|---|
| Laptops | 1 per person | Development | — |
| Phone or USB webcam | 1 | Camera for step tracking | have it |
| Phone tripod / clamp mount | 1 | Holds the camera over the workbench | $15 |
| Digital calipers | 1 | Checking the dimensions of the parts in the library | $20 |

### Software and accounts

| Item | Why | Cost |
|---|---|---|
| Claude API key (Opus 5.5) | Designs the parts, step tracking (vision) | pay per use, ask about sponsor credits |
| Python 3.11+, FastMCP | MCP server | free |
| build123d (OpenCascade) | CAD engine, STEP/STL export | free |
| trimesh | Converts models to GLB for the viewer | free |
| React + Three Fiber (three.js) | Assembly viewer and animation | free |
| KiCad 3D library / SnapEDA account | STEP models of real parts | free |
| Vercel or similar | Hosting the viewer for judges | free tier |
| GitHub repo | Collaboration | free |

That's about **$35** of hardware, and you may already have both items. The API usage will likely be the biggest cost, so check whether HTV has a sponsor offering Claude credits.

If you skip step tracking, you don't need the tripod or webcam. The calipers are only needed if you want to check the part dimensions yourself. You could rely on the manufacturer specs instead, but then you can't say the dimensions are verified.

---

## User

can we also use gemini for the gemini prize track

## Claude

Yes. The natural split is to give Gemini the camera work, since step tracking is the vision-heavy part:

- **Claude (Opus 5.5):** generates the CAD through the MCP server, same as before.
- **Gemini:** watches the workbench through the Live API (real-time video streaming). It checks each step as you build, tells you aloud when something's wrong ("the LED is in backwards"), and moves to the next step automatically. Before, tracking was a photo check when you said "done." Now it watches the build live.

That makes step tracking a core feature instead of a stretch goal, so move it out of the "cut first" spot in the risks. It also gives the Gemini track a clear story: "Claude designs it, Gemini watches you build it."

Prize tracks sometimes require Gemini to be the main model, or ban mixing providers. Check the HTV track rules before committing. If Gemini has to do everything, swap it in for the CAD agent too. The MCP tools are plain function calls, so Gemini can use them without changes.

### Updated software list additions

| Item | Why | Cost |
|---|---|---|
| Gemini API key (Google AI Studio) | Step tracking (Live API, video + voice) | free tier, may have hackathon credits |
| `google-genai` Python SDK | Calling the Live API | free |

The hardware list doesn't change. The phone or webcam on the tripod that you already planned for step tracking is the camera Gemini watches.

---

## User

out of these prize tracks what shuld we go for

*[Pasted the Hack the Valley 11 Devpost page: deadline Oct 18, 2026 @ 8:00am EDT; 4-minute pitch + 1-minute Q&A; GitHub link required. Prize tracks: Top 3, Best Solo, Best Beginner, School of Cities (Toronto civic tech), Project KAZE (personal safety), PointClickCare (early health risk detection), FDM (healthier working life), MLH Gemini, MLH Solana, MLH Tiger Data, MLH Vultr, MLH DEV Writing Challenge, MLH GoDaddy Registry domain, Papiers Autoresearch, Fintech, Healthcare, AI for Social Impact, Climate/Sustainability. Judging: technicality, design, impact, presentation, inspiration, authenticity.]*

## Claude

Go for these four. They fit the project with little or no extra work:

| Track | Prize | Why it fits | Extra work |
|---|---|---|---|
| **Top 3** (automatic) | Pixel 10a / keyboards / AirPods | The main target. The idea scores well on the "Authenticity" and "Inspiration" criteria because AI-generated assembly guides aren't a common hackathon project. | none |
| **[MLH] Best Use of Gemini API** | MLH swag kits | Already planned for step tracking with the Live API | none |
| **[MLH] Best Use of Vultr** | M5Stack Tab5 | Host the MCP server and backend on a Vultr instance with the free credits. The prize is hardware, which suits a hardware team. | ~30 min |
| **[MLH] Best Domain Name (GoDaddy Registry)** | gift card | Register a fun domain for the viewer | ~10 min |

**Maybe:**
- **Best Climate Action or Sustainability Hack:** only if you work repair into the pitch. The same pipeline could generate disassembly and repair guides for existing devices, which ties into right-to-repair and e-waste. It's a decent second angle, but don't change the build for it.
- **[MLH] DEV Writing Challenge ($100):** write a blog post after the event. It costs nothing during the hackathon.

**Skip:**
- **Tiger Data:** you could log step-tracking events as time series, but it would feel bolted on.
- **Solana, School of Cities, Project KAZE, PointClickCare, FDM, Papiers, Fintech, Healthcare:** none of these fit the project.
- **Best Solo / Best Beginner:** you have a team, and these probably don't apply to you.

The Gemini prize is only swag, so don't let it drive design decisions. It's still worth entering since you're using Gemini anyway.

The Devpost submission is due **Oct 18 at 8:00am** and must include the GitHub link, or the project won't be judged. The pitch is 4 minutes plus 1 minute of Q&A. That's tight, so plan the demo around the generated assembly animation, then a short clip of Gemini catching a mistake while you build.
