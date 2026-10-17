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
