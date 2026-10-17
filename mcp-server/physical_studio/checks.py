"""Fit checks on a built design: solid overlaps, small gaps, screw lengths, print size.

Some contacts are intended and reported as expected rather than as problems: a screw threading
into the base's standoff, the lid sitting on the base, a screw head on its board. Mounted boards
are checked against the base without its standoffs, since resting on them is the point.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from build123d import Part

from .design import Design
from .geometry import BuiltDesign, BuiltPiece, to_location

OVERLAP_TOLERANCE = 0.01  # mm^3; below this it's tessellation/boolean noise
DEFAULT_BED = (220.0, 220.0, 250.0)  # Prusa MK4 / Bambu A1-sized printer


def placed(piece: BuiltPiece) -> Part:
    return piece.shape.moved(to_location(piece.matrix))


def overlap_volume(a: Part, b: Part) -> float:
    result = a.intersect(b)
    if result is None:
        return 0.0
    shapes = result if isinstance(result, (list, tuple)) else [result]
    return float(sum(getattr(s, "volume", 0.0) for s in shapes))


def bbox_gap(a: Part, b: Part) -> float:
    """Lower bound on the distance between two shapes, from their bounding boxes."""
    ba, bb = a.bounding_box(), b.bounding_box()
    lo_a, hi_a = np.array(tuple(ba.min)), np.array(tuple(ba.max))
    lo_b, hi_b = np.array(tuple(bb.min)), np.array(tuple(bb.max))
    gaps = np.maximum(0, np.maximum(lo_a - hi_b, lo_b - hi_a))
    return float(np.linalg.norm(gaps))


def expected_contact(design: Design, a: str, b: str, touching_only: bool = False) -> str | None:
    """Why a contact between a and b is intended, or None. touching_only: contacts that are fine as
    surface contact but a problem if the solids actually overlap (lid on base, screw head on board)."""
    if touching_only and {a, b} == {"base", "lid"}:
        return "lid sits on the base"
    for x, y in ((a, b), (b, a)):
        p = design.placements.get(x)
        if p is None:
            continue
        if p.kind == "fastener" and y == "base":
            return "screw threads into its standoff"
        if touching_only and p.kind == "fastener" and y == p.attached_to:
            return "screw head clamps the board"
    return None


def shapes_for(design: Design, built: BuiltDesign, a: str, b: str, shapes: dict[str, Part]) -> tuple[Part, Part]:
    """A mounted board is checked against the base without its standoffs (it sits on them by
    design), so walls and floor still count."""
    def pick(x: str, other: str) -> Part:
        if x == "base" and built.shell is not None:
            p = design.placements.get(other)
            if p is not None and p.kind == "part" and p.mount:
                return built.shell
        return shapes[x]

    return pick(a, b), pick(b, a)


def solids(built: BuiltDesign) -> dict[str, Part]:
    """Placed solids; wires are flexible and left out of fit checks."""
    return {pid: placed(piece) for pid, piece in built.pieces.items() if piece.shape is not None}


def check_interference(design: Design, built: BuiltDesign) -> dict:
    shapes = solids(built)
    problems, expected = [], []
    for a, b in combinations(shapes, 2):
        sa, sb = shapes_for(design, built, a, b, shapes)
        if bbox_gap(sa, sb) > 0:
            continue
        volume = overlap_volume(sa, sb)
        if volume <= OVERLAP_TOLERANCE:
            continue
        entry = {"a": a, "b": b, "overlap_mm3": round(volume, 2)}
        reason = expected_contact(design, a, b)
        if reason:
            expected.append({**entry, "why": reason})
        else:
            problems.append(entry)
    problems += screw_length_problems(design, built)
    return {"ok": not problems, "problems": problems, "expected": expected}


def screw_length_problems(design: Design, built: BuiltDesign) -> list[dict]:
    """A screw longer than board + standoff bottoms out on the floor and won't tighten."""
    if built.cavity is None:
        return []
    floor_top = float(built.cavity[0][2])
    problems = []
    for p in design.placements.values():
        if p.kind != "fastener":
            continue
        piece = built.pieces[p.id]
        tip = float(placed(piece).bounding_box().min.Z)
        if tip < floor_top - 1e-6:
            problems.append(
                {
                    "a": p.id,
                    "b": "base",
                    "issue": f"screw tip at z={tip:.2f} is {floor_top - tip:.2f} mm below the floor top "
                    f"(z={floor_top:.2f}); it bottoms out. Use a shorter screw or raise standoff_min.",
                }
            )
    return problems


def check_clearance(design: Design, built: BuiltDesign, min_gap: float = 1.0, bed=DEFAULT_BED) -> dict:
    shapes = solids(built)
    tight = []
    for a, b in combinations(shapes, 2):
        sa, sb = shapes_for(design, built, a, b, shapes)
        if bbox_gap(sa, sb) >= min_gap or expected_contact(design, a, b, touching_only=True):
            continue
        if overlap_volume(sa, sb) > OVERLAP_TOLERANCE:
            continue  # an overlap, reported by check_interference
        gap = float(sa.distance_to(sb))
        if gap < min_gap:
            tight.append({"a": a, "b": b, "gap_mm": round(gap, 2)})

    notes = [w for w in built.warnings]
    if built.outer is not None:
        size = built.outer[1] - built.outer[0]
        fits = all(s <= b for s, b in zip(sorted(size[:2]), sorted(bed[:2]))) and size[2] <= bed[2]
        if not fits:
            notes.append(f"case is {size.round(1).tolist()} mm, bigger than the {list(bed)} mm print bed")
    return {"ok": not tight and not notes, "min_gap_mm": min_gap, "too_close": tight, "notes": notes}
