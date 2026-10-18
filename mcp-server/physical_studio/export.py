"""Writes a built design to disk: GLB + steps JSON for the viewer, STL/STEP for printing and CAD.

The GLB is written with trimesh rather than build123d's export_gltf, which splits each shape
into one node per face and renames it. Here every placement is one node named by its id,
under a root node "design" that maps the design frame (mm, Z up) to glTF (m, Y up).
See docs/steps-format.md.
"""

from __future__ import annotations

import json
import functools
import math
from pathlib import Path

import numpy as np
import trimesh
from build123d import export_step, export_stl

from .design import Design, Step
from .geometry import BuiltDesign, assembly
from .render import render
from .textures import top_image

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


# --- materials (parts/materials/, made by examples/make_materials.py) -----------------------------
# A part's appearance may name a material, SketchUp style: a seamless greyscale detail texture that
# the part's colour tints, a finish (metallic, roughness) and its real size per tile in mm.


@functools.lru_cache(maxsize=8)
def material_library(materials_dir: Path) -> dict[str, dict]:
    try:
        return json.loads((materials_dir / "materials.json").read_text())
    except (OSError, ValueError):
        return {}


@functools.lru_cache(maxsize=32)
def material_texture(materials_dir: Path, name: str):
    from PIL import Image

    spec = material_library(materials_dir).get(name)
    return Image.open(materials_dir / spec["file"]).convert("RGB") if spec else None


def box_uv(mesh: trimesh.Trimesh, tile_mm: float) -> trimesh.Trimesh:
    """Each face gets its own corners and UVs from the two axes it faces least (a box projection),
    in millimetres / tile_mm, so a 400 mm rail repeats the texture instead of stretching one tile."""
    corners = mesh.vertices[mesh.faces].reshape(-1, 3)
    axis = np.repeat(np.abs(mesh.face_normals).argmax(axis=1), 3)
    u = np.where(axis == 0, corners[:, 1], corners[:, 0])
    v = np.where(axis == 2, corners[:, 1], corners[:, 2])
    out = trimesh.Trimesh(vertices=corners, faces=np.arange(len(corners)).reshape(-1, 3), process=False)
    out.visual = trimesh.visual.TextureVisuals(uv=np.column_stack([u, v]) / max(tile_mm, 0.1))
    return out


def textured(mesh: trimesh.Trimesh, name: str, color: str, look: dict, parts_dir: Path | None, kind: str = "part"):
    """A mesh with its material: a tiled texture when look names one, else a plain colour and finish."""
    spec = material_library(parts_dir / "materials").get(look.get("material", "")) if parts_dir else None
    texture = material_texture(parts_dir / "materials", look["material"]) if spec else None
    if texture is not None:
        mesh = box_uv(mesh, float(spec.get("tile_mm", 50)))
        mesh.visual.material = trimesh.visual.material.PBRMaterial(
            name=name,
            baseColorTexture=texture,
            baseColorFactor=hex_to_rgba(color),  # the texture is greyscale detail; the colour tints it
            metallicFactor=float(look.get("metallic", spec.get("metallic", 0.0))),
            roughnessFactor=float(look.get("roughness", spec.get("roughness", 0.6))),
        )
        return mesh
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            name=name,
            baseColorFactor=hex_to_rgba(color),
            metallicFactor=float(look.get("metallic", 0.6 if kind == "fastener" else 0.0)),
            roughnessFactor=float(look.get("roughness", 0.6)),
        )
    )
    return mesh


def accent_meshes(part: dict, parts_dir: Path | None) -> list[tuple[trimesh.Trimesh, str, dict]]:
    """A part's accents: extra pieces in another material (a carriage's black end caps, a motor's can),
    each a STEP file next to the part's JSON: appearance.accents = [{step_file, material, color?}]."""
    out = []
    for i, accent in enumerate((part.get("appearance") or {}).get("accents") or []):
        path = parts_dir / accent.get("step_file", "") if parts_dir else None
        if not path or not path.is_file():
            continue
        spec = material_library(parts_dir / "materials").get(accent.get("material", ""), {})
        out.append((accent_mesh(path), accent.get("color") or spec.get("color", "#888888"), accent))
    return out


@functools.lru_cache(maxsize=64)
def accent_mesh(path: Path) -> trimesh.Trimesh:
    from build123d import import_step

    from .geometry import mesh_of

    return mesh_of(import_step(path))


def top_face(piece, part: dict, parts_dir: Path) -> trimesh.Trimesh | None:
    """A quad just above the body's top face, textured with the part's top picture (textures.py)."""
    image = top_image(part, parts_dir)
    if image is None:
        return None
    sx, sy, sz = (float(v) for v in part["body"]["size"])
    z = sz + 0.03  # just above the body so it never z-fights
    quad = trimesh.Trimesh(
        vertices=[[0, 0, z], [sx, 0, z], [sx, sy, z], [0, sy, z]], faces=[[0, 1, 2], [0, 2, 3]], process=False
    )
    quad.visual = trimesh.visual.TextureVisuals(
        uv=[[0, 0], [1, 0], [1, 1], [0, 1]],
        material=trimesh.visual.material.PBRMaterial(
            name=f"{piece.id}-top", baseColorTexture=image, metallicFactor=0.0, roughnessFactor=0.55
        ),
    )
    return quad


def write_glb(built: BuiltDesign, path: Path, parts: dict[str, dict] | None = None, parts_dir: Path | None = None,
              only: set[str] | None = None, suffix: str = "") -> None:
    """parts (library entries by id) adds each part's appearance: metal finish and top picture. only: just
    these piece ids (a build page step model); suffix: added to node names (the build page looks for
    "<id>__mesh")."""
    scene = trimesh.Scene(base_frame="world")
    scene.graph.update(frame_from="world", frame_to="design", matrix=DESIGN_TO_GLTF)
    for piece in built.pieces.values():
        if only is not None and piece.id not in only:
            continue
        part = (parts or {}).get(piece.part_id) or {}
        look = part.get("appearance") or {}
        mesh = textured(piece.local_mesh().copy(), piece.id, piece.color, look, parts_dir, piece.kind)
        scene.add_geometry(
            mesh,
            node_name=piece.id + suffix,
            geom_name=piece.id + suffix,
            parent_node_name="design",
            transform=piece.matrix,
        )
        for i, (accent, color, accent_look) in enumerate(accent_meshes(part, parts_dir) if piece.kind == "part" else []):
            name = f"{piece.id}{suffix}-accent-{i}"  # a child, so clicking it still picks the part
            scene.add_geometry(textured(accent.copy(), name, color, accent_look, parts_dir), node_name=name, geom_name=name,
                               parent_node_name=piece.id + suffix)
        quad = top_face(piece, part, parts_dir) if parts_dir and piece.kind == "part" else None
        if quad is not None:
            scene.add_geometry(quad, node_name=f"{piece.id}{suffix}-top", geom_name=f"{piece.id}{suffix}-top", parent_node_name=piece.id + suffix)
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
        if s.section:
            entry["section"] = s.section
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


# Angles a step picture may use. iso unless another one shows the new part clearly better (a pinion under
# the cart, a sensor on the back of an arm).
PICTURE_VIEWS = ("iso", "iso_right", "iso_back", "iso_left_back", "below")


def best_view(built: BuiltDesign, visible: set[str], new: set[str]) -> str:
    seen = {}
    for view in PICTURE_VIEWS:
        stats: dict = {}
        render(built, view, visible, None, new, size=(200, 150), labels=False, stats=stats)
        seen[view] = stats["highlight_px"]
    best = max(seen, key=seen.get)
    return best if seen[best] > 1.5 * seen["iso"] + 20 else "iso"


def top_textures(built: BuiltDesign, parts: dict[str, dict], parts_dir: Path) -> dict:
    """Piece id -> its textured top quad (top_face), for render's textures."""
    out = {}
    for piece in built.pieces.values():
        part = parts.get(piece.part_id) or {}
        quad = top_face(piece, part, parts_dir) if piece.kind == "part" and part.get("body") else None
        if quad is not None:
            out[piece.id] = quad
    return out


def extent(built: BuiltDesign, ids: set[str]) -> float:
    """The largest side of the box around these pieces, mm."""
    pts = []
    for pid in ids:
        piece = built.pieces[pid]
        b = piece.local_mesh(tolerance=0.5, angular=1.0).bounds
        corners = np.array([[x, y, z] for x in b[:, 0] for y in b[:, 1] for z in b[:, 2]])
        pts.append(corners @ piece.matrix[:3, :3].T + piece.matrix[:3, 3])
    pts = np.concatenate(pts)
    return float((pts.max(axis=0) - pts.min(axis=0)).max())


def close_up(built: BuiltDesign, visible: set[str], new: set[str]) -> set[str] | None:
    """What a step picture should zoom in on, or None to show the whole build: when the new parts are
    small next to the build (wires on a half-metre machine, a sensor, a pinion), frame them together
    with the parts their wires plug into."""
    if not new or len(visible) <= len(new):
        return None
    focus = set(new)
    for pid in new:
        piece = built.pieces[pid]
        if piece.kind == "wire":
            focus |= {piece.extra["from"]["placement"], piece.extra["to"]["placement"]} & visible
    return focus if extent(built, focus) < 0.45 * extent(built, visible) else None


def step_pictures(built: BuiltDesign, doc: dict, out_dir: Path, textures: dict | None = None) -> list[str]:
    """step-01.png, step-02.png, ...: what the build looks like after each step, its new parts highlighted
    (the lid left off until the step that adds it), from the angle that shows the new parts best. Photo
    checks show the AI this as the correct result. Each entry also gets picture_wires: every wire in the
    picture as a line in fractions of the picture's width and height, so the page can make wires clickable."""
    written, shown = [], set()
    size = (640, 480)
    for i, entry in enumerate(doc["steps"], start=1):
        new = set(entry.get("add", []))
        shown |= new
        visible = (shown if "lid" in new else shown - {"lid"}) & set(built.pieces)
        lit = new & visible
        view = best_view(built, visible, lit) if lit and len(visible) > 1 else "iso"
        path = out_dir / f"step-{i:02d}.png"
        stats: dict = {}
        focus = close_up(built, visible, lit)
        path.write_bytes(render(built, view, visible, None, lit, size=size, labels=False, stats=stats, textures=textures, focus=focus))
        entry["picture"] = path.name
        entry["picture_view"] = view
        entry["picture_close_up"] = focus is not None
        entry["picture_wires"] = [{"id": wid, "points": [[round(x / size[0], 4), round(y / size[1], 4)] for x, y in pts]}
                                  for wid, pts in stats["wires"].items()]
        written.append(str(path))
    return written


def export_design(
    design: Design,
    built: BuiltDesign,
    out_dir: Path,
    formats: list[str],
    name: str = "design",
    parts: dict[str, dict] | None = None,
    parts_dir: Path | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    if "glb" in formats:
        glb = out_dir / f"{name}.glb"
        write_glb(built, glb, parts, parts_dir)
        # Thumbnail for the projects list on screen 1: the finished design, no labels.
        thumb = out_dir / f"{name}.png"
        textures = top_textures(built, parts, parts_dir) if parts and parts_dir else None
        thumb.write_bytes(render(built, "iso", size=(480, 360), labels=False, textures=textures))
        written.append(str(thumb))
        steps_path = out_dir / f"{name}.steps.json"
        printing = print_info(built, name, formats)
        doc = steps_document(design, built, glb.name, printing)
        written += step_pictures(built, doc, out_dir, textures)
        steps_path.write_text(json.dumps(doc, indent=2) + "\n")
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
