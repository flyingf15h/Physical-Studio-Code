"""FastMCP server exposing the design tools. One design per server process.

Run with `uv run physical-studio-mcp` (stdio). Set PHYSICAL_STUDIO_PARTS to use another
parts folder and PHYSICAL_STUDIO_OUT to change where exports go.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import numpy as np

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from . import checks, library
from .design import Design, EnclosureSpec, Placement, Step
from .export import default_steps, export_design
from .geometry import aabb, apply, build, envelope, placement_matrix
from .render import VIEWS, render

REPO_ROOT = Path(__file__).resolve().parents[2]
PARTS_DIR = Path(os.environ.get("PHYSICAL_STUDIO_PARTS", REPO_ROOT / "parts"))
OUT_DIR = Path(os.environ.get("PHYSICAL_STUDIO_OUT", REPO_ROOT / "mcp-server" / "out"))

Vec3 = tuple[float, float, float]


def r3(values) -> list[float]:
    return [round(float(v), 2) for v in values]


class Studio:
    """The tool logic, separate from FastMCP so tests can call it directly."""

    def __init__(self, parts_dir: Path = PARTS_DIR, out_dir: Path = OUT_DIR):
        self.parts_dir = parts_dir
        self.out_dir = out_dir
        self.design = Design()

    def library(self) -> dict[str, dict]:
        # Reloaded on every call so edits to parts/*.json show up without a restart.
        return library.load_library(self.parts_dir)

    def part(self, part_id: str) -> dict:
        return library.get_part(self.library(), part_id)

    def parts_used(self) -> dict[str, dict]:
        lib = self.library()
        return {p.part_id: library.get_part(lib, p.part_id) for p in self.design.placements.values()}

    def build(self):
        return build(self.design, self.parts_used(), self.parts_dir)

    # --- tools ------------------------------------------------------------------------

    def new_design(self, title: str, prompt: str = "") -> dict:
        self.design = Design(title=title, prompt=prompt)
        return {"title": title, "parts_dir": str(self.parts_dir)}

    def search_parts(self, query: str = "", category: str | None = None) -> list[dict]:
        return library.search_parts(self.library(), query, category)

    def get_part(self, part_id: str) -> dict:
        return self.part(part_id)

    def place_part(
        self,
        part_id: str,
        position: Vec3,
        rotation: Vec3 = (0.0, 0.0, 0.0),
        id: str | None = None,
        mount: bool = True,
    ) -> dict:
        part = self.part(part_id)
        if part.get("category") == "fastener":
            raise ValueError("use add_fastener for fasteners, it puts them in a mounting hole for you")
        placement_id = id or self.design.new_id(part_id)
        self.design.check_new_id(placement_id)
        placement = Placement(
            id=placement_id,
            kind="part",
            part_id=part_id,
            name=part.get("name", part_id),
            position=tuple(float(v) for v in position),
            rotation=tuple(float(v) for v in rotation),
            mount=mount,
        )
        lo, hi = aabb(placement_matrix(placement.position, placement.rotation), *envelope(part))
        warnings = []
        for other in self.design.placements.values():
            if other.kind == "fastener":
                continue
            olo, ohi = aabb(placement_matrix(other.position, other.rotation), *envelope(self.part(other.part_id)))
            if (lo < ohi).all() and (olo < hi).all():
                warnings.append(f"envelope overlaps {other.id}; run check_interference to see if the solids collide")
        self.design.placements[placement_id] = placement
        return {"id": placement_id, "envelope": {"min": r3(lo), "max": r3(hi)}, "warnings": warnings}

    def add_fastener(self, part_id: str, target: str, hole: str, id: str | None = None) -> dict:
        part = self.part(part_id)
        if part.get("category") != "fastener":
            raise ValueError(f"{part_id} is not a fastener")
        if target not in self.design.placements:
            raise ValueError(f"no placement {target!r}; placed: {list(self.design.placements)}")
        host = self.design.placements[target]
        host_part = self.part(host.part_id)
        holes = {h["id"]: h for h in host_part.get("mounting_holes", [])}
        if hole not in holes:
            raise ValueError(f"{host.part_id} has no hole {hole!r}; holes: {list(holes)}")
        m = placement_matrix(host.position, host.rotation)
        top = list(holes[hole]["position"])
        top[2] += host_part["body"]["size"][2]  # screw head sits on the top face
        position = apply(m, top)
        placement_id = id or self.design.new_id(f"{part_id}-{target}-{hole}")
        self.design.check_new_id(placement_id)
        self.design.placements[placement_id] = Placement(
            id=placement_id,
            kind="fastener",
            part_id=part_id,
            name=part.get("name", part_id),
            position=tuple(float(v) for v in position),
            rotation=host.rotation,
            attached_to=target,
            hole=hole,
        )
        return {"id": placement_id, "position": r3(position)}

    def create_enclosure(self, **settings) -> dict:
        self.design.enclosure = EnclosureSpec(**{k: v for k, v in settings.items() if v is not None})
        if not self.design.placements:
            return {"note": "enclosure settings saved; it is sized around the parts once you place them"}
        return self.describe_enclosure()

    def describe_enclosure(self) -> dict:
        built = self.build()
        if built.cavity is None:
            return {"warnings": built.warnings}
        (clo, chi), (olo, ohi) = built.cavity, built.outer
        return {
            "outer": {"min": r3(olo), "max": r3(ohi), "size": r3(ohi - olo)},
            "cavity": {"min": r3(clo), "max": r3(chi), "size": r3(chi - clo)},
            "warnings": built.warnings,
        }

    def add_step(
        self,
        title: str,
        text: str,
        add: list[str],
        motion: list[dict] | None = None,
        tools: list[dict] | None = None,
        callouts: list[dict] | None = None,
        dimensions: list[dict] | None = None,
        check: str | None = None,
    ) -> dict:
        known = set(self.design.all_ids())
        already = {pid for s in self.design.steps for pid in s.add}
        unknown = [pid for pid in add if pid not in known]
        if unknown:
            raise ValueError(f"unknown placement ids {unknown}; known: {sorted(known)}")
        repeated = [pid for pid in add if pid in already]
        if repeated:
            raise ValueError(f"{repeated} were already added in an earlier step")
        self.design.steps.append(
            Step(title, text, list(add), motion or [], tools or [], callouts or [], dimensions or [], check)
        )
        remaining = [pid for pid in self.design.all_ids() if pid not in already | set(add)]
        return {"index": len(self.design.steps), "not_yet_added": remaining}

    def describe_design(self) -> dict:
        return {
            "title": self.design.title,
            "placements": [
                {"id": p.id, "kind": p.kind, "part": p.part_id, "position": r3(p.position), "rotation": r3(p.rotation)}
                for p in self.design.placements.values()
            ],
            "enclosure": self.describe_enclosure() if self.design.enclosure and self.design.placements else None,
            "steps": [s.title for s in self.design.steps],
        }

    def check_interference(self) -> dict:
        return checks.check_interference(self.design, self.build())

    def check_clearance(self, min_gap: float = 1.0, bed: Vec3 | None = None) -> dict:
        return checks.check_clearance(self.design, self.build(), min_gap, tuple(bed) if bed else checks.DEFAULT_BED)

    def render_preview(
        self, view: str = "iso", step: int | None = None, exploded: bool = False, hide: list[str] | None = None
    ) -> bytes:
        built = self.build()
        steps = self.design.steps or default_steps(self.design, built)
        visible = set(built.pieces)
        highlight: set[str] = set()
        if step is not None:
            if not 1 <= step <= len(steps):
                raise ValueError(f"step must be between 1 and {len(steps)}")
            visible = {pid for s in steps[:step] for pid in s.add}
            highlight = set(steps[step - 1].add)
        visible -= set(hide or [])
        offsets = {}
        if exploded:
            for s in steps:
                for m in s.motion:
                    if m.get("from_offset"):
                        offsets[m["placement"]] = np.array(m["from_offset"], dtype=float)
        return render(built, view, visible, offsets, highlight)

    def export(self, formats: list[str], out_dir: str | None = None) -> dict:
        slug = re.sub(r"[^a-z0-9]+", "-", self.design.title.lower()).strip("-") or "design"
        target = Path(out_dir) if out_dir else self.out_dir / slug
        return export_design(self.design, self.build(), target, formats)


studio = Studio()
mcp = FastMCP(
    "physical-studio",
    instructions=(
        "Design hardware projects out of real, measured parts. Never invent dimensions: look parts up "
        "with search_parts/get_part and use their numbers. Units are mm, +Z up, rotations in degrees "
        "(Euler XYZ). Typical flow: new_design -> place_part (board first, at the origin) -> place the "
        "other parts -> add_fastener for each board mounting hole -> create_enclosure -> add_step for each "
        "assembly step -> check_interference + check_clearance + render_preview (look at it, fix, repeat) -> "
        "export. Connectors that face a wall (e.g. USB on -x) get a cutout if the part "
        "is within reach of that wall; parts poking up through the lid need a '+z' connector."
    ),
)


@mcp.tool
def new_design(title: str, prompt: str = "") -> dict:
    """Start a new, empty design. prompt is the user's request, kept for the assembly guide."""
    return studio.new_design(title, prompt)


@mcp.tool
def search_parts(query: str = "", category: str | None = None) -> list[dict]:
    """Search the measured parts library. category: board, input, output, fastener or misc."""
    return studio.search_parts(query, category)


@mcp.tool
def get_part(part_id: str) -> dict:
    """Full library entry for a part: body size, envelope, mounting holes, connectors, keep-outs (mm)."""
    return studio.get_part(part_id)


@mcp.tool
def place_part(
    part_id: str,
    position: Vec3,
    rotation: Vec3 = (0.0, 0.0, 0.0),
    id: str | None = None,
    mount: bool = True,
) -> dict:
    """Place a library part. position is where the part's origin (bottom-left corner of its footprint)
    goes, in mm; rotation is degrees, Euler XYZ. Boards with mount=true get standoffs under their
    mounting holes. Returns the placement id and its envelope in the design frame."""
    return studio.place_part(part_id, position, rotation, id, mount)


@mcp.tool
def add_fastener(part_id: str, target: str, hole: str, id: str | None = None) -> dict:
    """Put a fastener (e.g. an M3 screw) into mounting hole `hole` of placement `target`."""
    return studio.add_fastener(part_id, target, hole, id)


@mcp.tool
def create_enclosure(
    wall: float | None = None,
    floor: float | None = None,
    lid_thickness: float | None = None,
    margin: float | None = None,
    top_clearance: float | None = None,
    standoff_min: float | None = None,
    pilot_hole: float | None = None,
    lid: bool | None = None,
) -> dict:
    """Add a printed box around the placed parts: base with standoffs and connector cutouts, and a lid.
    It is sized automatically from the parts' envelopes plus `margin`. Defaults: wall 2, floor 2,
    lid_thickness 2, margin 3, top_clearance 2, standoff_min 5, pilot_hole 2.5 (M3 self-tapping), lid true.
    Returns the outer and inner sizes and any warnings (e.g. a connector too far from its wall)."""
    return studio.create_enclosure(
        wall=wall,
        floor=floor,
        lid_thickness=lid_thickness,
        margin=margin,
        top_clearance=top_clearance,
        standoff_min=standoff_min,
        pilot_hole=pilot_hole,
        lid=lid,
    )


@mcp.tool
def add_step(
    title: str,
    text: str,
    add: list[str],
    motion: list[dict] | None = None,
    tools: list[dict] | None = None,
    callouts: list[dict] | None = None,
    dimensions: list[dict] | None = None,
    check: str | None = None,
) -> dict:
    """Append an assembly step. add: placement ids that appear in this step ("base" and "lid" are the
    enclosure). motion: [{placement, from_offset: [x,y,z], from_rotation?: [rx,ry,rz]}].
    tools: [{name, for}]. callouts: [{text, target, at?}]. dimensions: [{from, to, label}].
    check: what a correct result looks like on camera. Format: docs/steps-format.md.
    If no steps are added, export generates a default sequence."""
    return studio.add_step(title, text, add, motion, tools, callouts, dimensions, check)


@mcp.tool
def describe_design() -> dict:
    """Current placements, enclosure size and steps."""
    return studio.describe_design()


@mcp.tool
def check_interference() -> dict:
    """Solid-vs-solid overlap check between every pair of pieces (parts, screws, base, lid), plus screws
    that are too long for their standoff. Intended contacts (board on standoffs, screw in standoff) are
    listed under `expected`, not as problems."""
    return studio.check_interference()


@mcp.tool
def check_clearance(min_gap: float = 1.0, bed: Vec3 | None = None) -> dict:
    """Pairs of pieces closer than min_gap mm (without touching), connector cutouts that couldn't be made,
    and whether the case fits the print bed (default 220 x 220 x 250 mm)."""
    return studio.check_clearance(min_gap, bed)


@mcp.tool
def render_preview(
    view: Literal["iso", "iso_back", "top", "front", "back", "left", "right"] = "iso",
    step: int | None = None,
    exploded: bool = False,
    hide: list[str] | None = None,
) -> Image:
    """Render the design to a PNG so you can check it. Each piece is labelled with its placement id and
    there is a 10 mm scale bar. step: show the assembly as of that step (1-based) with its new parts
    highlighted. hide: placement ids to leave out, e.g. ["lid"] to look inside."""
    return Image(data=studio.render_preview(view, step, exploded, hide), format="png")


@mcp.tool
def export(formats: list[Literal["glb", "stl", "step"]] = ["glb", "stl", "step"], out_dir: str | None = None) -> dict:
    """Write the design: glb + steps JSON (for the viewer), stl (base and lid, for printing), step
    (whole assembly). Returns the file paths and any build warnings."""
    return studio.export(list(formats), out_dir)


def main() -> None:
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
