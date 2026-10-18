"""Turns a Design into build123d solids, one per placement, plus the generated enclosure.

Part geometry comes from the part's STEP file when it has one, otherwise from a proxy built
out of its library boxes (body, connectors, keep-outs). The enclosure is sized around the
placed parts' envelopes, gets standoffs under mounted boards and openings for connectors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from build123d import Align, Box, Compound, Cylinder, Location, Part, import_step
from OCP.gp import gp_Trsf

from .design import Design, EnclosureSpec, Placement, Wire

MIN = (Align.MIN, Align.MIN, Align.MIN)
FACE_NORMALS = {
    "-x": (-1, 0, 0),
    "+x": (1, 0, 0),
    "-y": (0, -1, 0),
    "+y": (0, 1, 0),
    "-z": (0, 0, -1),
    "+z": (0, 0, 1),
}
# Which local axes a connector's [width, height] opening spans on each face.
FACE_PLANE_AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}
MATERIALS_DIR = Path(__file__).resolve().parents[2] / "parts" / "materials"
CATEGORY_COLORS = {
    "board": "#1f6fb2",
    "input": "#e0b020",
    "output": "#d04040",
    "fastener": "#8a8f98",
    "misc": "#6a9955",
}
ENCLOSURE_COLORS = {"base": "#d9d9d9", "lid": "#f2f2f2"}
WIRE_RADIUS = 0.75  # 22 AWG jumper with insulation
INLINE_RADIUS = 1.3  # a 1/4 W resistor body spliced into the wire


@dataclass
class BuiltPiece:
    id: str
    kind: str
    part_id: str | None
    name: str
    shape: Part | None  # in the piece's local frame; None for mesh-only pieces (wires)
    matrix: np.ndarray  # local frame -> design frame
    color: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mesh: trimesh.Trimesh | None = None  # ready-made geometry, used instead of tessellating shape
    extra: dict = field(default_factory=dict)  # kind-specific fields for the steps JSON
    category: str | None = None  # library category for parts
    path: np.ndarray | None = None  # wires: the centre line, pin to pin (design frame, mm)

    def local_mesh(self, tolerance: float = 0.05, angular: float = 0.3) -> trimesh.Trimesh:
        return self.mesh if self.mesh is not None else mesh_of(self.shape, tolerance, angular)


@dataclass
class BuiltDesign:
    pieces: dict[str, BuiltPiece]
    cavity: tuple[np.ndarray, np.ndarray] | None = None  # inner min/max corners
    shell: Part | None = None  # the base without standoffs, for checking boards against walls and floor
    outer: tuple[np.ndarray, np.ndarray] | None = None
    warnings: list[str] = field(default_factory=list)

    def bounds(self) -> tuple[list[float], list[float]]:
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for piece in self.pieces.values():
            if piece.shape is None:
                bmin, bmax = piece.mesh.bounds
            else:
                bb = piece.shape.bounding_box()
                bmin, bmax = np.array(tuple(bb.min)), np.array(tuple(bb.max))
            a, b = aabb(piece.matrix, bmin, bmax)
            lo, hi = np.minimum(lo, a), np.maximum(hi, b)
        return [round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]


def mesh_of(shape, tolerance: float = 0.05, angular: float = 0.3) -> trimesh.Trimesh:
    vertices, triangles = shape.tessellate(tolerance, angular)
    return trimesh.Trimesh(
        vertices=np.array([tuple(v) for v in vertices], dtype=float),
        faces=np.array(triangles, dtype=np.int64),
        process=False,
    )


# --- transforms -------------------------------------------------------------------------


def placement_matrix(position, rotation) -> np.ndarray:
    """4x4 matrix for a translation plus Euler XYZ rotation (degrees), as in three.js."""
    rx, ry, rz = (math.radians(a) for a in rotation)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = mx @ my @ mz
    m[:3, 3] = position
    m[np.abs(m) < 1e-12] = 0.0
    return m


def to_location(m: np.ndarray) -> Location:
    t = gp_Trsf()
    t.SetValues(*(float(v) for v in m[:3, :].flatten()))
    return Location(t)


def apply(m: np.ndarray, point) -> np.ndarray:
    return m[:3, :3] @ np.asarray(point, dtype=float) + m[:3, 3]


def aabb(m: np.ndarray, lo, hi) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned box (design frame) around a local box moved by m."""
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    moved = corners @ m[:3, :3].T + m[:3, 3]
    return moved.min(axis=0), moved.max(axis=0)


def is_axis_aligned(m: np.ndarray) -> bool:
    r = np.abs(m[:3, :3])
    return bool(np.all((r < 1e-6) | (np.abs(r - 1) < 1e-6)))


def box_between(lo, hi) -> Part:
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    size = hi - lo
    return Box(*size, align=MIN).moved(Location(tuple(lo)))


# --- parts ------------------------------------------------------------------------------


def material_color(part: dict) -> str | None:
    """The colour of the material a part's appearance names (parts/materials/materials.json)."""
    name = (part.get("appearance") or {}).get("material")
    if not name:
        return None
    from .export import material_library  # here to avoid a circular import at load time

    return (material_library(MATERIALS_DIR).get(name) or {}).get("color")


def part_shape(part: dict, parts_dir: Path) -> Part:
    step_file = part.get("step_file")
    if step_file and (parts_dir / step_file).exists():
        return import_step(parts_dir / step_file)
    if part.get("category") == "fastener" and part.get("fastener"):
        return fastener_shape(part)
    return proxy_shape(part)


def lid_mount_z(part: dict) -> float | None:
    """Height (part frame) where the lid's underside sits on a lid-mounted part, e.g. the top of a
    tactile switch's square housing or an LED's flange. Above it only the +z openings continue."""
    mount = part.get("lid_mount")
    return float(mount["z"]) if mount else None


def proxy_shape(part: dict) -> Part:
    """Body box plus connector blocks and above-board keep-outs, good enough to see and fit."""
    size = np.array(part["body"]["size"], dtype=float)
    mz = lid_mount_z(part)
    if mz is not None and 0 < mz < size[2]:
        shape = box_between((0, 0, 0), (size[0], size[1], mz))
        for conn in part.get("connectors", []):
            if conn.get("face") == "+z":
                w, h = conn["size"]
                cx, cy, cz = conn["center"]
                top = cz + float(conn.get("protrusion", 0.0))
                shape = shape + box_between((cx - w / 2, cy - h / 2, mz), (cx + w / 2, cy + h / 2, top))
        return shape
    shape = box_between((0, 0, 0), size)
    for conn in part.get("connectors", []):
        block = connector_block(conn, size)
        if block is not None:
            shape = shape + block
    for zone in part.get("keep_out", []):
        if zone["min"][2] >= 0:  # skip underside pin zones, they're mostly empty space
            shape = shape + box_between(zone["min"], zone["max"])
    for hole in part.get("mounting_holes", []):
        x, y, _ = hole["position"]
        drill = Cylinder(hole["diameter"] / 2, size[2] + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
        shape = shape - drill.moved(Location((x, y, -1)))
    return shape


def connector_block(conn: dict, body_size: np.ndarray) -> Part | None:
    face = conn.get("face")
    if face not in FACE_NORMALS:
        return None
    normal = np.array(FACE_NORMALS[face], dtype=float)
    axis = int(np.argmax(np.abs(normal)))
    u, v = FACE_PLANE_AXES[face[1]]
    center = np.array(conn["center"], dtype=float)
    w, h = conn["size"]
    protrusion = float(conn.get("protrusion", 0.0))
    depth = min(8.0, float(body_size[axis]))  # how far it runs back into the part
    lo, hi = center.copy(), center.copy()
    lo[u], hi[u] = center[u] - w / 2, center[u] + w / 2
    lo[v], hi[v] = center[v] - h / 2, center[v] + h / 2
    outer, inner = center[axis] + normal[axis] * protrusion, center[axis] - normal[axis] * depth
    lo[axis], hi[axis] = min(outer, inner), max(outer, inner)
    if np.any(hi - lo <= 0):
        return None
    return box_between(lo, hi)


def fastener_shape(part: dict) -> Part:
    f = part["fastener"]
    thread = float(str(f.get("thread", "M3")).lstrip("Mm") or 3)
    length = float(f.get("length", part["body"]["size"][2]))
    head_d = float(f.get("head_diameter", thread * 1.8))
    head_h = float(f.get("head_height", thread))
    head = Cylinder(head_d / 2, head_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shaft = Cylinder(thread / 2, length, align=(Align.CENTER, Align.CENTER, Align.MAX))
    return head + shaft


def envelope(part: dict) -> tuple[np.ndarray, np.ndarray]:
    if part.get("envelope"):
        return np.array(part["envelope"]["min"], dtype=float), np.array(part["envelope"]["max"], dtype=float)
    return np.zeros(3), np.array(part["body"]["size"], dtype=float)


# --- enclosure --------------------------------------------------------------------------


def enclosure_frame(design: Design, parts: dict[str, dict], spec: EnclosureSpec, warnings: list[str]):
    """Inner cavity (min, max) and the floor-top height, from the placed parts."""
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    top = -np.inf  # highest top among parts that sit inside the case
    lid_parts: list[tuple[str, float]] = []  # (placement id, design z of its lid mount)
    mounted_bottoms = []
    for p in design.placements.values():
        if p.kind == "fastener":
            continue
        part = parts[p.part_id]
        m = placement_matrix(p.position, p.rotation)
        a, b = aabb(m, *envelope(part))
        lo, hi = np.minimum(lo, a), np.maximum(hi, b)
        mz = lid_mount_z(part)
        if mz is not None and np.allclose(m[:3, 2], (0, 0, 1)):
            lid_parts.append((p.id, float(apply(m, (0, 0, mz))[2])))
        else:
            top = max(top, float(b[2]))
        if p.mount and part.get("mounting_holes"):
            mounted_bottoms.append(float(p.position[2]))
    if not np.isfinite(lo).all():
        raise ValueError("place at least one part before building the enclosure")
    floor_top = lo[2] - spec.margin
    if mounted_bottoms:
        floor_top = min(floor_top, min(mounted_bottoms) - spec.standoff_min)
    lid_underside = max([top + spec.top_clearance] + [z for _, z in lid_parts])
    for pid, z in lid_parts:
        if lid_underside - z > 0.01:
            warnings.append(
                f"{pid}: its lid mount is {lid_underside - z:.2f} mm below the lid; raise it by that much "
                f"(z + {lid_underside - z:.2f}) so it seats against the lid and pokes through"
            )
    cavity_lo = np.array([lo[0] - spec.margin, lo[1] - spec.margin, floor_top])
    cavity_hi = np.array([hi[0] + spec.margin, hi[1] + spec.margin, lid_underside])
    return cavity_lo, cavity_hi


def build(design: Design, parts: dict[str, dict], parts_dir: Path) -> BuiltDesign:
    """parts maps every part id used by the design to its library entry."""
    pieces: dict[str, BuiltPiece] = {}
    warnings: list[str] = []
    shape_cache: dict[str, Part] = {}

    for p in design.placements.values():
        part = parts[p.part_id]
        if p.part_id not in shape_cache:
            shape_cache[p.part_id] = part_shape(part, parts_dir)
        pieces[p.id] = BuiltPiece(
            id=p.id,
            kind=p.kind,
            part_id=p.part_id,
            name=p.name,
            shape=shape_cache[p.part_id],
            matrix=placement_matrix(p.position, p.rotation),
            color=p.color
            or (part.get("appearance") or {}).get("color")
            or material_color(part)
            or CATEGORY_COLORS.get(part.get("category", "misc"), "#999999"),
            position=tuple(p.position),
            rotation=tuple(p.rotation),
            category=part.get("category"),
            # Pin tips in the part frame, so the viewer can draw legs (display only).
            extra={"pins": [{"id": q["id"], "position": [float(v) for v in q["position"]]} for q in part["pins"]]}
            if part.get("pins")
            else {},
        )

    built = BuiltDesign(pieces={}, warnings=warnings)
    spec = design.enclosure
    if spec is None or not design.placements:
        built.pieces = pieces
        add_wires(built, design, parts)
        return built

    cavity_lo, cavity_hi = enclosure_frame(design, parts, spec, warnings)
    outer_lo = cavity_lo - np.array([spec.wall, spec.wall, spec.floor])
    outer_hi = cavity_hi + np.array([spec.wall, spec.wall, spec.lid_thickness if spec.lid else 0.0])
    built.cavity, built.outer = (cavity_lo, cavity_hi), (outer_lo, outer_hi)

    base = box_between(outer_lo, [outer_hi[0], outer_hi[1], cavity_hi[2]]) - box_between(
        cavity_lo, [cavity_hi[0], cavity_hi[1], cavity_hi[2] + 1]
    )
    shell = base
    lid = box_between([outer_lo[0], outer_lo[1], cavity_hi[2]], outer_hi) if spec.lid else None
    if lid is not None:
        # Locating lip that drops inside the walls.
        gap, lip_w, lip_h = 0.2, 1.2, 2.0
        lip_outer_lo = cavity_lo[:2] + gap
        lip_outer_hi = cavity_hi[:2] - gap
        lip = box_between([*lip_outer_lo, cavity_hi[2] - lip_h], [*lip_outer_hi, cavity_hi[2]]) - box_between(
            [*(lip_outer_lo + lip_w), cavity_hi[2] - lip_h - 1], [*(lip_outer_hi - lip_w), cavity_hi[2]]
        )
        lid = lid + lip

    for p in design.placements.values():
        part = parts[p.part_id]
        m = pieces[p.id].matrix
        if p.kind != "fastener" and p.mount and part.get("mounting_holes"):
            base = add_standoffs(base, p, part, m, spec, cavity_lo[2], warnings)
        for conn in part.get("connectors", []):
            target, cut = connector_cutout(p, conn, m, spec, cavity_lo, cavity_hi, outer_lo, outer_hi, warnings)
            if target == "base":
                base = base - cut
                shell = shell - cut
            elif target == "lid" and lid is not None:
                lid = lid - cut

    identity = np.eye(4)
    built.shell = shell
    built.pieces["base"] = BuiltPiece("base", "enclosure", None, "Case base", base, identity, ENCLOSURE_COLORS["base"])
    built.pieces.update(pieces)
    if lid is not None:
        built.pieces["lid"] = BuiltPiece("lid", "enclosure", None, "Case lid", lid, identity, ENCLOSURE_COLORS["lid"])
    add_wires(built, design, parts)
    return built


# --- wires ------------------------------------------------------------------------------


def pin_frame(design: Design, parts: dict[str, dict], placement_id: str, pin_id: str):
    """Design-frame position and outward direction of a part's pin."""
    p = design.placements[placement_id]
    pin = next(q for q in parts[p.part_id].get("pins", []) if q["id"] == pin_id)
    m = placement_matrix(p.position, p.rotation)
    direction = m[:3, :3] @ np.array(pin.get("direction", [0, 0, 1]), dtype=float)
    return apply(m, pin["position"]), direction / (np.linalg.norm(direction) or 1)


def wire_path(a, da, b, db, samples: int = 48) -> np.ndarray:
    """Cubic Bezier that leaves each pin along its direction, like a jumper bent by hand."""
    reach = float(np.clip(0.35 * np.linalg.norm(b - a), 8.0, 40.0))
    c1, c2 = a + da * reach, b + db * reach
    t = np.linspace(0, 1, samples)[:, None]
    return (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t**2 * c2 + t**3 * b


def tube(path: np.ndarray, radii: np.ndarray, sides: int = 10) -> trimesh.Trimesh:
    """Tube mesh along a polyline, with parallel-transported rings so it doesn't twist."""
    tangents = np.gradient(path, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1, keepdims=True)
    helper = np.array([0.0, 0.0, 1.0]) if abs(tangents[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    normal = np.cross(tangents[0], helper)
    normal /= np.linalg.norm(normal)
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    rings = []
    for i, (point, tangent) in enumerate(zip(path, tangents)):
        if i:
            normal = normal - tangent * (normal @ tangent)
            normal /= np.linalg.norm(normal)
        binormal = np.cross(tangent, normal)
        rings.append(point + radii[i] * (np.outer(np.cos(angles), normal) + np.outer(np.sin(angles), binormal)))
    vertices = np.concatenate(rings + [path[:1], path[-1:]])
    faces = []
    n = len(path)
    for i in range(n - 1):
        for j in range(sides):
            a, b = i * sides + j, i * sides + (j + 1) % sides
            c, d = a + sides, b + sides
            faces += [[a, b, d], [a, d, c]]
    start, end = n * sides, n * sides + 1
    for j in range(sides):
        faces.append([start, (j + 1) % sides, j])
        faces.append([end, (n - 1) * sides + j, (n - 1) * sides + (j + 1) % sides])
    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)


def wire_piece(design: Design, parts: dict[str, dict], wire: Wire) -> BuiltPiece:
    a, da = pin_frame(design, parts, *wire.a)
    b, db = pin_frame(design, parts, *wire.b)
    path = wire_path(a, da, b, db)
    radii = np.full(len(path), WIRE_RADIUS)
    if wire.inline:
        middle = len(path) // 2
        radii[middle - 3 : middle + 3] = INLINE_RADIUS
    length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
    names = [design.placements[x].name for x, _ in (wire.a, wire.b)]
    return BuiltPiece(
        id=wire.id,
        kind="wire",
        part_id=None,
        name=wire.label or f"Wire {names[0]} {wire.a[1]} to {names[1]} {wire.b[1]}",
        shape=None,
        matrix=np.eye(4),
        color=wire.color,
        mesh=tube(path, radii),
        path=path,
        extra={
            "from": {"placement": wire.a[0], "pin": wire.a[1]},
            "to": {"placement": wire.b[0], "pin": wire.b[1]},
            "length_mm": round(length, 1),
            **({"inline": wire.inline} if wire.inline else {}),
        },
    )


def add_wires(built: BuiltDesign, design: Design, parts: dict[str, dict]) -> None:
    for wire in design.wires.values():
        built.pieces[wire.id] = wire_piece(design, parts, wire)


def add_standoffs(base: Part, p: Placement, part: dict, m: np.ndarray, spec: EnclosureSpec, floor_top: float, warnings):
    if not np.allclose(m[:3, 2], (0, 0, 1)):
        warnings.append(f"{p.id}: board is not flat (Z up), so no standoffs were added")
        return base
    for hole in part["mounting_holes"]:
        x, y, z = apply(m, hole["position"])
        height = z - floor_top
        if height <= 0.5:
            warnings.append(f"{p.id}/{hole['id']}: hole is at or below the floor, no standoff")
            continue
        post = Cylinder(spec.standoff_diameter / 2, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        pilot = Cylinder(spec.pilot_hole / 2, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        base = base + (post - pilot).moved(Location((x, y, floor_top)))
    return base


def connector_cutout(p, conn, m, spec, cavity_lo, cavity_hi, outer_lo, outer_hi, warnings):
    """Returns ("base" | "lid" | None, cutting solid in the design frame)."""
    face = conn.get("face")
    if face not in FACE_NORMALS:
        warnings.append(f"{p.id}/{conn.get('id')}: unknown face {face!r}")
        return None, None
    if not is_axis_aligned(m):
        warnings.append(f"{p.id}/{conn.get('id')}: part is not rotated by a multiple of 90 degrees, no cutout")
        return None, None
    normal = m[:3, :3] @ np.array(FACE_NORMALS[face], dtype=float)
    axis = int(np.argmax(np.abs(normal)))
    sign = 1 if normal[axis] > 0 else -1
    center = apply(m, conn["center"])

    wall_inner = cavity_hi[axis] if sign > 0 else cavity_lo[axis]
    wall_outer = outer_hi[axis] if sign > 0 else outer_lo[axis]
    distance = (wall_inner - center[axis]) * sign
    if distance > spec.cutout_reach:
        warnings.append(
            f"{p.id}/{conn['id']}: faces {face} but the wall is {distance:.1f} mm away "
            f"(more than {spec.cutout_reach} mm), no cutout. Move the part closer to that wall."
        )
        return None, None
    target = "lid" if (axis == 2 and sign > 0) else "base"

    # Opening size in local axes, then mapped to design axes through the rotation.
    u, v = FACE_PLANE_AXES[face[1]]
    half_local = np.zeros(3)
    clearance = float(conn.get("clearance", spec.cutout_clearance))
    half_local[u] = conn["size"][0] / 2 + clearance
    half_local[v] = conn["size"][1] / 2 + clearance
    half = np.abs(m[:3, :3]) @ half_local
    lo, hi = center - half, center + half
    # A little inside the connector face, or inside the wall if the face is already past it
    # (lid-mounted parts poke through the lid).
    start = (min(center[axis], wall_inner) if sign > 0 else max(center[axis], wall_inner)) - sign * 1.0
    end = wall_outer + sign * 1.0
    lo[axis], hi[axis] = min(start, end), max(start, end)
    return target, box_between(lo, hi)


def assembly(built: BuiltDesign) -> Compound:
    children = []
    for piece in built.pieces.values():
        if piece.shape is None:
            continue  # wires are flexible; they don't belong in the CAD assembly
        shape = piece.shape.moved(to_location(piece.matrix))
        shape.label = piece.id
        children.append(shape)
    return Compound(children=children)
