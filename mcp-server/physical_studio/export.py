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


def mesh_of(shape, tolerance: float = 0.05, angular: float = 0.3) -> trimesh.Trimesh:
    vertices, triangles = shape.tessellate(tolerance, angular)
    return trimesh.Trimesh(
        vertices=np.array([tuple(v) for v in vertices], dtype=float),
        faces=np.array(triangles, dtype=np.int64),
        process=False,
    )


def hex_to_rgba(color: str) -> list[int]:
    c = color.lstrip("#")
    return [int(c[i : i + 2], 16) for i in (0, 2, 4)] + [255]


def write_glb(built: BuiltDesign, path: Path) -> None:
    scene = trimesh.Scene(base_frame="world")
    scene.graph.update(frame_from="world", frame_to="design", matrix=DESIGN_TO_GLTF)
    for piece in built.pieces.values():
        mesh = mesh_of(piece.shape)
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


def steps_document(design: Design, built: BuiltDesign, model_name: str) -> dict:
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
    return doc


def export_design(design: Design, built: BuiltDesign, out_dir: Path, formats: list[str], name: str = "design") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    if "glb" in formats:
        glb = out_dir / f"{name}.glb"
        write_glb(built, glb)
        steps_path = out_dir / f"{name}.steps.json"
        steps_path.write_text(json.dumps(steps_document(design, built, glb.name), indent=2) + "\n")
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
