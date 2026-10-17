# Steps format

The MCP server's `export` tool writes two files into one folder:

- `design.glb`: the assembled design.
- `design.steps.json`: the assembly steps, following [`schemas/steps.schema.json`](../schemas/steps.schema.json).

The viewer loads both. The step tracker (Gemini) reads the same JSON to know what each step should look like.

Example: [`schemas/examples/traffic-light.steps.json`](../schemas/examples/traffic-light.steps.json).

## Frames and units

- The **design frame** is millimetres, +Z up, the same as the parts library. Every number in the JSON is in this frame.
- The GLB has a single root node `design` that converts the design frame to glTF (scale 0.001, rotate -90° about X so +Z becomes +Y). Do not undo it; work inside it.
- Every placement is a **direct child of `design`, with the node name equal to the placement `id`**, already in its final position. Its local units are therefore mm, Z-up, so offsets from the JSON can be added straight onto `node.position`.

## Placements

`placements` lists everything in the GLB: enclosure pieces (`kind: "enclosure"`, `part: null`), library parts (`kind: "part"`), fasteners (`kind: "fastener"`) and wires (`kind: "wire"`, `part: null`). A wire also has `from` / `to` (`{placement, pin}`, pin ids from the parts library), `length_mm` and optionally `inline` (a component spliced into it, e.g. a resistor); its mesh is already routed, so the viewer treats it like any other node. A part with pins also has `pins` (`[{id, position}]`, pin tips in the part's own frame) so the viewer can draw its legs; the GLB has no leg geometry. `position`/`rotation` repeat the node's transform for anything that doesn't read the GLB (rotation is degrees, Euler order XYZ, the same as three.js `Euler` with order `'XYZ'`).

## Steps

Steps are ordered by `index`, starting at 1. Each placement is added in exactly one step (`add`).

To show step *n*, the viewer:

1. Shows every placement added in steps 1..n and hides the rest.
2. Highlights the placements in step *n*'s `add`.
3. For each entry in `motion`, starts the placement at `final position + from_offset` (and `from_rotation`) and animates it to its final transform. Placements with no motion entry just appear.
4. Shows `tools` as a callout card ("2.5 mm hex key, for the M3 x 8 screws"), `callouts` as labels pinned to the target node (`at` is in the target's local frame, defaulting to its bounding-box centre), and `dimensions` as measurement lines between two design-frame points.

For an exploded view of the whole design, offset each placement by the `from_offset` of the step that added it.

`check` is a one-line description of what a correct result looks like on camera, for example "LED long leg (anode) in the hole marked +". Gemini compares the workbench against it.

## Print info

`print` (when the design has a case) lists the printed pieces: `size_mm` of the closed case, and per piece its `file` (`design-base.stl`, `design-lid.stl`), `grams` of PLA and estimated `minutes` (a rough 12 g/h, shown as an estimate), plus totals and `step_file`. The Print screen reads it.
