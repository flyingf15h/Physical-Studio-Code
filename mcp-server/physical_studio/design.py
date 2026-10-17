"""In-memory design state: enclosure settings, placed parts, fasteners and assembly steps.

Everything here is plain data. Geometry is derived from it in geometry.py, so tools can be
called in any order (place parts first, then create the enclosure, or the other way round).
All lengths are mm in the design frame (+Z up), rotations are degrees, Euler order XYZ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RESERVED_IDS = {"base", "lid", "design"}


@dataclass
class EnclosureSpec:
    wall: float = 2.0
    floor: float = 2.0
    lid_thickness: float = 2.0
    margin: float = 2.0  # gap between the parts' envelopes and the inner walls
    top_clearance: float = 2.0  # gap between the tallest part and the lid
    standoff_min: float = 4.0  # shortest standoff under a mounted board
    standoff_diameter: float = 6.0
    pilot_hole: float = 2.5  # M3 self-tapping into PLA; 4.0 for heat-set inserts
    cutout_clearance: float = 0.5  # added on every side of a connector opening
    cutout_reach: float = 12.0  # max distance from a connector to its wall for a cutout
    lid: bool = True


@dataclass
class Placement:
    id: str
    kind: str  # "part" or "fastener"; enclosure pieces are added at build time
    part_id: str
    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mount: bool = True  # boards: put standoffs under the mounting holes
    attached_to: str | None = None  # fasteners: placement id and hole id they go into
    hole: str | None = None


@dataclass
class Step:
    title: str
    text: str
    add: list[str]
    motion: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    callouts: list[dict] = field(default_factory=list)
    dimensions: list[dict] = field(default_factory=list)
    check: str | None = None


@dataclass
class Design:
    title: str = "Untitled design"
    prompt: str = ""
    enclosure: EnclosureSpec | None = None
    placements: dict[str, Placement] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)

    def new_id(self, base: str) -> str:
        base = re.sub(r"[^a-z0-9_-]+", "-", base.lower()).strip("-") or "part"
        if base not in self.placements and base not in RESERVED_IDS:
            return base
        n = 2
        while f"{base}-{n}" in self.placements:
            n += 1
        return f"{base}-{n}"

    def check_new_id(self, placement_id: str) -> None:
        if not ID_PATTERN.match(placement_id):
            raise ValueError(f"id {placement_id!r} must be lowercase letters, digits, '-' or '_'")
        if placement_id in RESERVED_IDS:
            raise ValueError(f"id {placement_id!r} is reserved for the enclosure")
        if placement_id in self.placements:
            raise ValueError(f"id {placement_id!r} is already placed")

    def all_ids(self) -> list[str]:
        ids = list(self.placements)
        if self.enclosure:
            ids = ["base", *ids] + (["lid"] if self.enclosure.lid else [])
        return ids
