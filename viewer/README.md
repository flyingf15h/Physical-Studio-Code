# Viewer

React + React Three Fiber assembly guide. It loads a `design.glb` plus `design.steps.json` written by the MCP server's `export` tool ([format](../docs/steps-format.md)).

```sh
cd viewer
npm install
npm run dev
```

- `http://localhost:5173/` opens the bundled sample (`public/sample`, made by `mcp-server/examples/uno_box.py`).
- `http://localhost:5173/?design=out/<title>` opens the MCP server's export in `mcp-server/out/<title>/`, served live by the dev server. Reload after Claude exports again.
- Drop a `.glb` and `.steps.json` onto the page to open any other design.

Controls: ← / → step, space play, `e` exploded view, drag to orbit, scroll to zoom.

What it does per step: shows the placements added so far, flies the new ones in from their `from_offset` / `from_rotation`, pulses them cyan, pins `callouts` to their target and draws `dimensions`. The card shows the step text, the `tools`, and the `check` line that the camera step tracker uses.

Code: `src/steps.ts` (types matching `schemas/steps.schema.json`), `src/Assembly.tsx` (the 3D scene: animation, highlight, callouts, dimensions), `src/App.tsx` (loading, step list, timeline).

## Gemini step tracking

"Watch my bench" (top right) streams the webcam (1 frame/s) and microphone to the Gemini Live API. On every step change Gemini gets the step text, its `check` line and a capture of the 3D view as the expected result. Gemini then:

- calls `step_done` when the step is visibly complete, and the guide moves on by itself;
- calls `flag_problem` when something is wrong ("the base is rotated, the openings face right"), shown in red on the step card;
- talks: you hear it and can ask it questions out loud (transcripts show in the panel).

Setup: put `GEMINI_API_KEY=...` in `viewer/.env.local` (gitignored) and restart `npm run dev`. The key stays on the dev server: `/api/gemini-token` (in `vite.config.ts`) mints a single-use token that expires in 30 minutes, and only that reaches the browser. `GEMINI_LIVE_MODEL` overrides the model (default `gemini-3.8-live`).

Code: `src/tracker/session.ts` (Live session, prompts, function calls, frame and auto-check timers), `src/tracker/audio.ts` (16 kHz mic capture, 24 kHz playback), `src/tracker/TrackerPanel.tsx` (UI, captures the expected render).
