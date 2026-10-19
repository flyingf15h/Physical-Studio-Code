# 2-minute demo: the traffic light, end to end

Hard cap 2:00. Record at 1080p (Win+Alt+R / Xbox Game Bar, or OBS). Chrome at 1920×1080, zoom 100%,
bookmarks bar hidden, notifications off. Keep raw files outside git. Upload to YouTube as Unlisted.

The venue network blocks physicalstudio.work; use https://155-138-154-8.sslip.io if it does.

**Before you hit record:** log in (only the person who started a build can photo-check it), and take
one phone photo of a finished traffic light step (the breadboard or case with the LEDs in) to drag
in at shot 5.

| # | Time | On screen | Voice-over (roughly) |
|---|------|-----------|----------------------|
| 1 | 0:00–0:15 | Dashboard. Click the **Traffic light** demo card (the prompt fills in). In **Parts I have** type `uno` ⏎, `3 le` ⏎ (it suggests LED 5 mm first and keeps the 3), `but` ⏎. Three green ✓ chips. Click **Design it**. | "Physical Studio is IKEA instructions for any hardware project. Say what you want and what you have, and the parts come from a library of real, measured parts." |
| 2 | 0:15–0:40 | The live design, **sped up about 8× in the edit**. Slow to 1× for 2–3 s on the "found a problem, fixed it, checked again" note and the checks going green. | "An AI designs the case from those parts through our MCP server. It never invents a dimension, and it checks its own work: here it found a screw hitting the Uno's header and fixed it." |
| 3 | 0:40–1:05 | The guide opens. Point at the sidebar sections, open a step: the picture with the new part in cyan, tools, camera check. Rotate the 3D model once. | "Then it writes the guide: one part per step, a picture and a 3D model of exactly what your build should look like." |
| 4 | 1:05–1:30 | Open a wiring step. **Click a wire in the picture**: it lights up with A/B tags, e.g. *Uno D11 → Red LED +*. Then click the same wire in the 3D model to show the end markers. | "Every wire is clickable: it tells you exactly which pin each end goes to, in the picture and in 3D." |
| 5 | 1:30–1:50 | Drag your phone photo onto the step's photo check. Hold on the verdict card (done, or the fix it suggests). | "Snap a photo after each step and Gemini checks it against the reference picture, then tells you what to fix or what to do next." |
| 6 | 1:50–2:00 | The finished model rotating, then a title card: physicalstudio.work · github.com/notkelly1/Physical-Studio-Code. | "Real parts, real dimensions, a guide anyone can follow. Physical Studio, live on Vultr." |

## Cut without the photo check (1:50)

Same shots minus 5; shot 3 and 4 get the extra time. Read at a relaxed pace (~140 words/min).

| # | Time | On screen | Voice-over |
|---|------|-----------|------------|
| 1 | 0:00–0:15 | Traffic light card, `uno` ⏎ `3 le` ⏎ `but` ⏎, Design it | "This is Physical Studio: IKEA-style instructions for any hardware project. Tell it what you want to build and what parts you have. Every part comes from a library of real, measured components." |
| 2 | 0:15–0:40 | Live design at 8×, 1× on the fix note and green checks | "Gemini designs the case through our MCP server, using the real dimensions of each part. Nothing is guessed. It checks its own work: here it caught a screw hitting the Uno's header, moved it, and checked again. Fit, clearance and printer size all pass." |
| 3 | 0:40–1:10 | Guide: sidebar sections, a step picture (new part in cyan), tools, rotate the 3D model | "Then it writes the build guide. Steps are grouped by section, one part at a time, each with the tools you need, a picture from the best angle, and a 3D model of exactly what your build should look like at that step." |
| 4 | 1:10–1:40 | Wiring step: click a wire in the picture (A/B tags), then the same wire in 3D | "Wiring is where beginners get stuck, so every wire is clickable. Click one and it tells you exactly which pin each end goes to, say the Uno's pin 11 to the red LED. It works in the picture and in the 3D model." |
| 5 | 1:40–1:50 | Finished model rotating, title card | "Real parts, real dimensions, a guide anyone can follow. Physical Studio, powered by Gemini and live on Vultr." |

## If something goes wrong live
- Design slow or failing: cut to the ready-made guide at `/?design=traffic-light` for shots 3–4
  (no clickable wires there yet), or record shots 3–5 on the double pendulum
  (`/build/double-pendulum`, Wiring section) and say "here's a bigger one".
- Skip **Print**: that screen still says "coming soon".
- Editing: Clipchamp (built into Windows) speeds up shot 2 and adds the title card.
