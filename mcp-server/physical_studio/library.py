"""Loads and searches the parts library (parts/*.json, format in parts/README.md)."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

DEFAULT_PARTS_DIR = Path(__file__).resolve().parents[2] / "parts"
CATEGORIES = {"board", "input", "output", "fastener", "misc"}
REQUIRED = ("id", "name", "category", "body")


class PartError(ValueError):
    pass


def validate_part(part: dict, path: Path) -> None:
    missing = [k for k in REQUIRED if k not in part]
    if missing:
        raise PartError(f"{path.name}: missing {', '.join(missing)}")
    if part["id"] != path.stem:
        raise PartError(f"{path.name}: id {part['id']!r} must match the file name {path.stem!r}")
    if part["category"] not in CATEGORIES:
        raise PartError(f"{path.name}: category {part['category']!r} is not one of {sorted(CATEGORIES)}")
    size = part["body"].get("size")
    if not (isinstance(size, list) and len(size) == 3 and all(isinstance(v, (int, float)) and v > 0 for v in size)):
        raise PartError(f"{path.name}: body.size must be three positive numbers (mm)")
    for hole in part.get("mounting_holes", []):
        if not {"id", "position", "diameter"} <= hole.keys() or len(hole["position"]) != 3:
            raise PartError(f"{path.name}: mounting hole {hole.get('id')!r} needs id, position [x,y,z] and diameter")
    for conn in part.get("connectors", []):
        if not {"id", "face", "center", "size"} <= conn.keys():
            raise PartError(f"{path.name}: connector {conn.get('id')!r} needs id, face, center and size")
        if conn["face"] not in {"-x", "+x", "-y", "+y", "-z", "+z"}:
            raise PartError(f"{path.name}: connector {conn['id']!r} has unknown face {conn['face']!r}")


def load_library(parts_dir: Path = DEFAULT_PARTS_DIR) -> dict[str, dict]:
    parts_dir = Path(parts_dir)
    if not parts_dir.is_dir():
        raise PartError(f"parts folder {parts_dir} does not exist")
    library: dict[str, dict] = {}
    for path in sorted(parts_dir.glob("*.json")):
        try:
            part = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise PartError(f"{path.name}: invalid JSON ({e})") from e
        validate_part(part, path)
        library[part["id"]] = part
    return library


def summary(part: dict) -> dict:
    return {
        "id": part["id"],
        "name": part["name"],
        "category": part["category"],
        "body_size": part["body"]["size"],
        "verified": bool(part.get("verified", False)),
    }


def search_parts(library: dict[str, dict], query: str = "", category: str | None = None) -> list[dict]:
    """Every word of the query must appear in the part's id, name, category or notes. Parts whose id or name
    has the words come before ones that only mention them in their notes."""
    if category is not None and category not in CATEGORIES:
        raise PartError(f"category {category!r} is not one of {sorted(CATEGORIES)}")
    words = query.lower().split()
    results = []
    for part in library.values():
        if category and part["category"] != category:
            continue
        haystack = " ".join(str(part.get(k, "")) for k in ("id", "name", "category", "notes")).lower()
        if all(w in haystack for w in words):
            title = f"{part['id']} {part['name']}".lower()
            results.append((-sum(w in title for w in words), len(results), summary(part)))
    return [r[2] for r in sorted(results, key=lambda r: r[:2])]


def get_part(library: dict[str, dict], part_id: str) -> dict:
    if part_id in library:
        return library[part_id]
    close = difflib.get_close_matches(part_id, list(library), n=3, cutoff=0.4)
    hint = f"; did you mean {', '.join(close)}?" if close else f"; available: {', '.join(sorted(library))}"
    raise KeyError(f"no part {part_id!r}{hint}")
