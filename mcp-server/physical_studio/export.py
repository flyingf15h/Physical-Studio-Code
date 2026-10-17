"""Writes a built design to disk: GLB + steps JSON for the viewer, STL/STEP for printing and CAD.

The GLB is written with trimesh rather than build123d's export_gltf, which splits each shape
into one node per face and renames it. Here every placement is one node named by its id,
under a root node "design" that maps the design frame (mm, Z up) to glTF (m, Y up).
See docs/steps-format.md.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh
from build123d import export_step, export_stl

from .design import Design, Step
from .geometry import BuiltDesign, assembly

DESIGN_TO_GLTF = np.array(
    [
        [0.001, 0, 0, 0],
        [0, 0, 0.001, 0],
        [0, -0.001, 0, 0],
        [0, 0, 0, 1],
    ]
)  # scale mm -> m, rotate -90 degrees about X (+Z up becomes +Y up)


def hex_to_rgba(color: str) -> list[int]:
    c = color.lstrip("#")
    return [int(c[i : i + 2], 16) for i in (0, 2, 4)] + [255]


def write_glb(built: BuiltDesign, path: Path) -> None:
    scene = trimesh.Scene(base_frame="world")
    scene.graph.update(frame_from="world", frame_to="design", matrix=DESIGN_TO_GLTF)
    for piece in built.pieces.values():
        mesh = piece.local_mesh().copy()
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=piece.id,
                baseColorFactor=hex_to_rgba(piece.color),
                metallicFactor=0.6 if piece.kind == "fastener" else 0.0,
                roughnessFactor=0.6,
            )
        )
        scene.add_geometry(
            mesh,
            node_name=piece.id,
            geom_name=piece.id,
            parent_node_name="design",
            transform=piece.matrix,
        )
    path.write_bytes(scene.export(file_type="glb"))


def default_steps(design: Design, built: BuiltDesign) -> list[Step]:
    """Base, then each part dropping in, then fasteners screwing in, then the lid."""
    steps: list[Step] = []
    if "base" in built.pieces:
        steps.append(Step("Lay out the case base", "Put the printed case base on the bench.", ["base"]))
    lift = 40.0
    for p in design.placements.values():
        if p.kind == "fastener":
            continue
        steps.append(
            Step(
                f"Add the {p.name}",
                f"Place the {p.name} as shown.",
                [p.id],
                motion=[{"placement": p.id, "from_offset": [0, 0, lift]}],
            )
        )
    by_part: dict[str, list[str]] = {}
    for p in design.placements.values():
        if p.kind == "fastener":
            by_part.setdefault(p.name, []).append(p.id)
    for name, ids in by_part.items():
        steps.append(
            Step(
                f"Fasten with {len(ids)} x {name}",
                f"Screw in the {name}s. Snug, not tight.",
                ids,
                motion=[{"placement": i, "from_offset": [0, 0, 20], "from_rotation": [0, 0, 720]} for i in ids],
            )
        )
    wires_by_part: dict[str, list[str]] = {}  # non-board end's placement id -> wire ids
    for wire in design.wires.values():
        ends = [wire.a[0], wire.b[0]]
        other = next((pid for pid in ends if parts_category(built, pid) != "board"), ends[1])
        wires_by_part.setdefault(other, []).append(wire.id)
    for pid, ids in wires_by_part.items():
        name = design.placements[pid].name
        steps.append(
            Step(
                f"Wire the {name}",
                f"Connect {len(ids)} wire{'s' if len(ids) > 1 else ''} to the {name} as shown.",
                ids,
                tools=[{"name": "Jumper wires", "for": name}],
            )
        )
    if "lid" in built.pieces:
        steps.append(
            Step(
                "Close the lid",
                "Press the lid onto the base.",
                ["lid"],
                motion=[{"placement": "lid", "from_offset": [0, 0, 50]}],
            )
        )
    return steps


PLA_DENSITY = 1.24  # g/cm3
GRAMS_PER_HOUR = 12.0  # rough rate for a 0.4 mm nozzle at default speeds; shown as an estimate


def print_info(built: BuiltDesign, name: str, formats: list[str]) -> dict | None:
    """Size, filament and time estimates for the printed pieces, for the Print screen."""
    if built.outer is None:
        return None
    pieces = []
    for pid in ("base", "lid"):
        piece = built.pieces.get(pid)
        if piece is None:
            continue
        volume = float(piece.shape.volume)  # mm3; thin walls print close to solid
        grams = volume / 1000 * PLA_DENSITY
        pieces.append(
            {
                "id": pid,
                "name": piece.name,
                "file": f"{name}-{pid}.stl" if "stl" in formats else None,
                "volume_mm3": round(volume),
                "grams": round(grams, 1),
                "minutes": round(grams / GRAMS_PER_HOUR * 60),
            }
        )
    size = (built.outer[1] - built.outer[0]).round(1).tolist()
    return {
        "size_mm": size,
        "material": "PLA",
        "pieces": pieces,
        "total_grams": round(sum(p["grams"] for p in pieces), 1),
        "total_minutes": sum(p["minutes"] for p in pieces),
        "step_file": f"{name}.step" if "step" in formats else None,
    }


def parts_category(built: BuiltDesign, pid: str) -> str | None:
    piece = built.pieces.get(pid)
    return piece.category if piece else None


def steps_document(design: Design, built: BuiltDesign, model_name: str, printing: dict | None = None) -> dict:
    steps = design.steps or default_steps(design, built)
    added = [pid for s in steps for pid in s.add]
    missing = [pid for pid in built.pieces if pid not in added]
    if missing:
        steps = [*steps, Step("Remaining parts", "Add the remaining parts.", missing)]
    lo, hi = built.bounds()
    placements = []
    for piece in built.pieces.values():
        position = [round(float(v), 3) for v in piece.matrix[:3, 3]]
        placements.append(
            {
                "id": piece.id,
                "kind": piece.kind,
                "part": piece.part_id,
                "name": piece.name,
                "position": position,
                "rotation": [round(float(v), 3) for v in piece.rotation],
                "color": piece.color,
                **piece.extra,
            }
        )
    doc_steps = []
    for i, s in enumerate(steps, start=1):
        entry = {"index": i, "title": s.title, "text": s.text, "add": list(s.add)}
        for key in ("motion", "tools", "callouts", "dimensions"):
            if getattr(s, key):
                entry[key] = getattr(s, key)
        if s.check:
            entry["check"] = s.check
        doc_steps.append(entry)
    doc = {
        "format": "physical-studio-steps",
        "version": 1,
        "title": design.title,
        "model": model_name,
        "units": "mm",
        "bounds": {"min": lo, "max": hi},
        "placements": placements,
        "steps": doc_steps,
    }
    if design.prompt:
        doc["prompt"] = design.prompt
    if printing:
        doc["print"] = printing
    return doc


def export_design(design: Design, built: BuiltDesign, out_dir: Path, formats: list[str], name: str = "design") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    if "glb" in formats:
        glb = out_dir / f"{name}.glb"
        write_glb(built, glb)
        steps_path = out_dir / f"{name}.steps.json"
        printing = print_info(built, name, formats)
        steps_path.write_text(json.dumps(steps_document(design, built, glb.name, printing), indent=2) + "\n")
        written += [str(glb), str(steps_path)]
    if "stl" in formats:
        # Only the printed pieces; library parts are bought, not printed.
        for pid in ("base", "lid"):
            if pid in built.pieces:
                stl = out_dir / f"{name}-{pid}.stl"
                export_stl(built.pieces[pid].shape, str(stl), tolerance=0.01, angular_tolerance=math.radians(5))
                written.append(str(stl))
    if "step" in formats:
        step = out_dir / f"{name}.step"
        export_step(assembly(built), str(step))
        written.append(str(step))
    return {"files": written, "warnings": built.warnings}
