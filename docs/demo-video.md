# Devpost demo video: recording script

Target 2:30–3:00 (hard cap 4:00). Record at 1080p (OBS, or Win+Alt+R / Xbox Game Bar on Windows).
Keep the raw files **outside git** (e.g. `~/Videos/physical-studio-demo/`). Upload to YouTube as
**Unlisted**, then put the link in PROJECT.md and docs/devpost.md (line "Demo video") and tell tszfei.

Before you start: Chrome at 1920×1080, zoom 100%, bookmarks bar hidden, notifications off.
Open https://physicalstudio.work in a fresh tab.

## Shots

| # | Time | What's on screen | Voice-over (roughly) |
|---|------|------------------|----------------------|
| 1 | 0:00–0:15 | Screen 1 (Describe). Click the **Traffic light** demo card; the prompt fills in: "Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, a crosswalk button, USB accessible on the side." Pick **OpenAI**, click **Design it**. | "Physical Studio is IKEA instructions for any hardware project. You describe it..." |
| 2 | 0:15–1:05 | Screen 2, live. Record the whole 3–5 min wait, then **speed it up 4–6×** in the edit. Slow back to 1× on: the checklist ticking, a preview image, the **"found a problem, fixed it, checked again"** note (usually the Uno h2 screw clash), the three checks going green. | "...and an AI designs it out of real, measured parts through our MCP server. It never invents a dimension. It checks its own work: here it found a screw that hits the Uno's header, removed it, and checked again." |
| 3 | 1:05–1:15 | The finished 3D model on screen 2: drag to rotate once. | "Every standoff and cutout comes from the real board's numbers." |
| 4 | 1:15–2:05 | The guide (`/guide?design=traffic-light` for a clean take if the live one has hiccups). Press play through the first steps (base, board, screws), rotate and zoom, toggle **Exploded** on and off, jump to a wiring step and hold on the resistor callouts. | "Then it turns the design into an animated step-by-step guide: one part per step, the tool you need, and every wire, resistors included." |
| 5 | 2:05–2:45 | **Gemini slot (real camera).** "Watch my bench" on the breadboard build: put an LED in backwards, show the card flagging it and Gemini saying so, flip the LED, the step goes green and the guide moves on. If this clip isn't recorded yet, leave a title card "Gemini bench clip" here and drop it in later. | "While you build, Gemini watches your bench. It knows what this step should look like, so when the LED goes in backwards it tells you, and when it's right it moves you on." |
| 6 | 2:45–3:00 | Back to the rotating model or the printed case; title card with physicalstudio.work and the GitHub link (github.com/notkelly1/Physical-Studio-Code). | "Real parts, real dimensions, a guide anyone can follow. Physical Studio, live on Vultr at physicalstudio.work." |

## Notes
- Use OpenAI, not Gemini, for the design: Gemini on the free-tier key is too slow.
- The bench clip needs a real camera, so the screen capture can't cover shot 5. Film it on a phone
  clamped over the breadboard, or capture the browser tab with the webcam view showing.
- Editing: Clipchamp (built into Windows) can speed up a section, cut and add title cards.

## Backup recording (in case the live demo fails)

`~/Videos/physical-studio-backup-demo.mp4` on tszfei's machine (`~/Videos/physical-studio-demo/`, raw
clips in `raw-clips/`). It's 3:17, 1080p, silent, with captions. Recorded Oct 18 from the live site
with headless Chromium:
1. Typing a traffic-light prompt (with a buzzer) and clicking **Design it**. The live design took about 75 s and is shown at 3× speed.
2. Stepping through the guide that came out of it, with step pictures and the rotating 3D bench.
3. The ready-made enclosure guide (`/guide?design=traffic-light`): steps, rotate, zoom, Exploded.
4. **Watch my bench**: Gemini Live sees the camera and speaks the step. The camera feed is
   *simulated* (a still render of step 1) because the recording machine has no webcam, and the caption says so.
   In this take Gemini gave the instruction but didn't call the step done. In an earlier take the checker hit a Gemini 503 ("high demand").
5. Photo check on the fresh build: Gemini answered "Looks right".

To re-record: `pip install playwright`, then from an empty folder run `mkdir shots clips`, then
`python3 <repo>/docs/backup-demo/rec_design.py`, then `rec_guide.py`, then `rec_track.py`, then
`bash <repo>/docs/backup-demo/edit.sh`. Chromium comes from snap (`/snap/chromium/current/...`).
Playwright's video recording needs its own ffmpeg build, so symlink the system one:
`ln -s /usr/bin/ffmpeg ~/.cache/ms-playwright/ffmpeg-1011/ffmpeg-linux`.
