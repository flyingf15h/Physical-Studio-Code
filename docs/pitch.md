# Physical Studio: 4-minute pitch

4 min pitch + 1 min Q&A. Slides: [`slides.md`](slides.md). Devpost text: [`devpost.md`](devpost.md).

**One sentence to land:** Physical Studio is assembly visualization with correct dimensions: an animated 3D guide built from real, measured parts, so what you see is what fits. Gemini checks your build against it.
**Don't say:** "git for hardware" or "version control". If the Commits tab comes up, call it "your build history".

## Roles

- **Speaker:** one person talks the whole way through (fewer handoffs, fewer lost seconds). <!-- TODO: pick who. -->
- **Driver:** a second person runs the laptop: slides, then the live guide, then the clip.
- **Prop:** the third holds the printed case and the breadboard build.

## Script

Timed at about 140 words a minute. Spoken words: ~430, plus a 40 s video clip and ~20 s of silent demo.

**0:00–0:15 · Title**
> Hi, we're Physical Studio. You tell it what you want to build, it shows you every step in 3D at real size, and then Gemini checks your work.

**0:15–0:40 · Problem**
> If you've followed an electronics tutorial, you know the feeling. The photo is blurry, so you guess which hole the wire goes in. You print a case and it's two millimetres too small. You go to screw the board down and the screw hits a header. Every one of those is the same problem: the picture you're following isn't true to the real parts.

**0:40–0:55 · Thesis**
> IKEA solved this decades ago. Their instructions work because IKEA knows the exact size of every part. We built that for electronics.

**0:55–1:55 · Live demo: the guide** *(driver switches to physicalstudio.work/guide?design=traffic-light)*
> Here's a traffic light for an Arduino Uno. One sentence of prompt: three LEDs in a column on the lid, a crosswalk button, USB on the side.
> An AI model designed this, but it's not drawing pictures. It builds with our MCP server, from a library of real parts. Watch: the Uno drops onto its standoffs. *(pause)* The screws spin down into the real mounting holes. *(pause)* The LEDs slide up into the lid, and the wires draw pin to pin: red to D11, yellow to D10, green to D9.
> *(exploded view)* Every part comes apart so you can see what goes where. Every step has a callout, the tool you need, and a line telling you what you should see when you're done.

**1:55–2:30 · Correct dimensions** *(back to slides; prop holds up the case)*
> The reason you can trust this picture is the numbers behind it. Over a hundred parts, from datasheets, checked with calipers. The model can only place parts from that library, so it can't make up a size. Before you see a design, it has to pass collision and clearance checks. Those checks caught something we didn't: on the Uno, a screw head in the hole next to AREF hits the header. So the guide tells you to leave that hole empty. And because everything's real size, it exports a case. This one. We printed it.

**2:30–3:15 · Gemini checks your work** *(play the 40 s clip)*
> Then you build it, and Gemini watches. *(clip plays: LED in backwards, photo, verdict, flip, pass)* It compares your photo with the expected render for that step, so it doesn't just say "looks wrong". It says the red LED is in backwards and which leg goes where.

*(Talk over the clip only at the start and the verdict; let the verdict sit on screen for a second.)*

**3:15–3:35 · Past breadboards**
> It's not just blinky LEDs. This is a double inverted pendulum: a cart on a linear rail, a motor driver, a Teensy, magnetic encoders. Twenty-three parts, thirty-three steps, a 3D model for every one, from its real CAD.

**3:35–3:50 · How it's built**
> Any model can drive it: Claude, Gemini, OpenAI. The MCP server does the geometry in OpenCascade, the guide plays in React Three Fiber, and Gemini does the checking. It's all live on Vultr at physicalstudio.work.

**3:50–4:00 · Close**
> Physical Studio. What you see is what fits. Thanks!

## Q&A prep (1 min, so answer in two sentences)

- **"How do you know the dimensions are right?"** Each part is a JSON file from the datasheet, and we checked the demo parts with calipers. Photos only change how a part looks, never its size.
- **"What if my part isn't in the library?"** You can upload a BOM and missing parts get added to your library; the next step is community parts checked against a caliper measurement.
- **"Isn't this just an LLM drawing pictures?"** No. The model calls tools that place real geometry, and code checks for collisions, clearance and miswired circuits before anyone sees it.
- **"Why Gemini?"** Multimodal checking against an expected render is where it shines, and the Live API lets the browser stream to it without exposing a key. Gemini can also drive the design tools.
- **"How accurate is the photo check?"** It caught the reversed LED in our tests and returns "unclear" instead of guessing on a bad photo. Glare is the main failure, so the guide tells you what to put in frame.
- **"What about rate limits?"** Key pool, retry delays from the API, and a fallback model.

## Rehearsal checklist

- [ ] Two full timed run-throughs with a stopwatch; cut the "How it's built" slide first if you're over 4:00.
- [ ] The demo clip is downloaded on the laptop (not streamed) and starts from the slide with one click.
- [ ] The live guide is already loaded in a tab; the venue network may block physicalstudio.work, so also open the `sslip.io` fallback and have a phone hotspot ready.
- [ ] If the live site won't load, play the backup demo video instead and narrate the same lines.
- [ ] Printed case and breadboard build on the table, within reach of the prop person.
- [ ] Fill the three image TODOs in `slides.md` with screenshots from the live site.
