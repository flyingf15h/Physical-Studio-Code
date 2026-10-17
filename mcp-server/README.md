# Physical Studio MCP server

Python 3.12 + [FastMCP](https://gofastmcp.com) + [build123d](https://build123d.readthedocs.io) (OpenCascade). Claude designs a project out of the measured parts in [`../parts`](../parts) and exports a GLB plus steps JSON for the viewer ([format](../docs/steps-format.md)) and STL files for printing.

## Setup

```sh
cd mcp-server
uv sync          # downloads Python 3.12 if needed; the system Python 3.14 has no OCP wheels
uv run pytest
```

## Use it from Claude Code

The repo's `.mcp.json` registers the server for anyone who opens Claude Code at the repo root (approve it when Claude Code asks). Anywhere else:

```sh
claude mcp add physical-studio -- uv run --directory /absolute/path/to/Physical-Studio-Code/mcp-server physical-studio-mcp
```

Then ask for a design, e.g. "Simon game for an Arduino Uno, 4 colored buttons with LEDs, buzzer, USB accessible on the side." Exports go to `mcp-server/out/<title>/` (ignored by git) unless `out_dir` is given.

Environment variables: `PHYSICAL_STUDIO_PARTS` (parts folder, default `../parts`), `PHYSICAL_STUDIO_OUT` (export folder).

## Tools

| Tool | What it does |
|---|---|
| `new_design(title, prompt)` | Start over. |
| `search_parts(query, category)` / `get_part(part_id)` | Look up parts; every dimension comes from here. |
| `place_part(part_id, position, rotation, id, mount)` | Put a part's origin at `position` (mm), rotation in degrees (Euler XYZ). Warns on overlapping envelopes. |
| `add_fastener(part_id, target, hole)` | Put a screw into a board's mounting hole. |
| `create_enclosure(...)` | Base + lid sized around the placed parts, standoffs under mounted boards' holes, cutouts for connectors within `cutout_reach` (12 mm) of a wall, lid holes for `+z` connectors. |
| `add_step(title, text, add, motion, tools, callouts, dimensions, check)` | Append an assembly step. Without steps, export generates base, parts, fasteners, lid. |
| `check_interference()` | Solid overlaps between every pair of pieces, and screws too long for their standoff. Intended contacts (screw in standoff) are listed separately. |
| `check_clearance(min_gap, bed)` | Pieces closer than `min_gap` (1 mm), connectors that got no cutout, case bigger than the print bed (220 x 220 x 250). |
| `render_preview(view, step, exploded, hide)` | PNG of the design with every piece labelled by id and a 10 mm scale bar, so Claude can look at its own work. Views: iso, iso_back, top, front, back, left, right. |
| `describe_design()` | Placements, enclosure size, steps. |
| `export(formats, out_dir)` | `glb` (+ `design.steps.json`), `stl` (base and lid), `step` (whole assembly). |

Geometry is rebuilt from the design state on every call, so the order of `place_part` and `create_enclosure` doesn't matter.

## Code

- `physical_studio/library.py`: loads and searches `parts/*.json`.
- `physical_studio/design.py`: design state (plain dataclasses).
- `physical_studio/geometry.py`: part proxies (or STEP files), enclosure, standoffs, cutouts.
- `physical_studio/checks.py`: interference, clearance, screw length, print-bed fit.
- `physical_studio/render.py`: software z-buffer renderer for `render_preview` (no OpenGL needed).
- `physical_studio/export.py`: GLB (written with trimesh so node names are placement ids), steps JSON, STL, STEP.
- `physical_studio/server.py`: the tools (`Studio`) and their FastMCP wrappers.

