"""check_wiring: electrical mistakes in a design's wires, found from the boards' printed pin labels.

The parts library has no electrical model, but the labels printed on the boards say most of what
matters (GND, 3.3V, +12 V, VCC, SDA), and each part's notes give its I2C address and whether it's
3.3 V only. Wires join pins into nets (a wire with an inline part, e.g. a resistor, doesn't join its
ends); then a net may not:
- join a ground pin to a supply pin (a short),
- join two different supply voltages (12 V into a 3.3 V pin),
- carry 5 V or more to the supply pin of a 3.3 V only part,
- put two devices with the same fixed I2C address on one SDA line.
`problems` are mistakes that break or burn parts; `tips` are ones the builder can fix with a jumper or a
setting (a second I2C address).
"""

from __future__ import annotations

import re

from .design import Design

GROUND = re.compile(r"\bGND\b", re.I)
VOLTS = re.compile(r"\b(\d)V(\d)\b|(\d+(?:\.\d+)?)\s*V\b", re.I)  # "3V3", "3.3V", "+12 V", "5V"
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*V\b", re.I)  # "4.5 to 37 V", "8-35 V"
REGULATED_INPUT = re.compile(r"^(VIN|VBUS|VSYS)\b", re.I)  # take a range through a regulator, not 3.3 V only
SUPPLY = re.compile(r"^\+?\s*(VCC|VIN|VDD|VMOT|VM|V\+|VBUS|VSYS|IN\+|OUT\+)\b", re.I)
ADDRESS = re.compile(r"0x[0-9a-f]{2}", re.I)
LOW_VOLTAGE_ONLY = re.compile(r"3\.3\s*V only", re.I)


def volts(label: str) -> float | None:
    m = VOLTS.search(label)
    if not m:
        return None
    return float(f"{m.group(1)}.{m.group(2)}") if m.group(1) else float(m.group(3))


def rated(notes: str, label: str) -> tuple[float, float] | None:
    """The input range the part's notes give for a supply pin, e.g. "VMOT 8-35 V" -> (8, 35) for VMOT:
    the first range in a sentence that names the pin."""
    word = re.match(r"[+\s]*([A-Za-z]+\+?)", label)
    if not word:
        return None
    for sentence in re.split(r"(?<=[.;])\s+", notes):
        if re.search(rf"(?<!\w){re.escape(word.group(1))}(?!\w)", sentence):
            m = RANGE.search(sentence)
            if m:
                return float(m.group(1)), float(m.group(2))
    return None


def is_supply(label: str) -> bool:
    return bool(SUPPLY.search(label.strip())) or (volts(label) is not None and not GROUND.search(label))


def nets(design: Design) -> list[set[tuple[str, str]]]:
    """Pins joined by plain wires, as sets of (placement id, pin id)."""
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for w in design.wires.values():
        a, b = find(tuple(w.a)), find(tuple(w.b))
        if not w.inline:
            parent[a] = b
    groups: dict = {}
    for pin in parent:
        groups.setdefault(find(pin), set()).add(pin)
    return [g for g in groups.values() if len(g) > 1]


def check_wiring(design: Design, library: dict[str, dict]) -> dict:
    problems: list[str] = []
    tips: list[str] = []

    def part_of(pid):
        p = design.placements.get(pid)
        return p, (library.get(p.part_id, {}) if p else {})

    def label(pin):
        p, part = part_of(pin[0])
        q = next((q for q in part.get("pins", []) if q.get("id") == pin[1]), {})
        return q.get("label") or pin[1]

    def name(pin):
        p, _ = part_of(pin[0])
        return f"{p.name if p else pin[0]} {label(pin)}"

    for net in nets(design):
        pins = sorted(net)
        grounds = [p for p in pins if GROUND.search(label(p))]
        supplies = [p for p in pins if is_supply(label(p)) and not GROUND.search(label(p))]
        if grounds and supplies:
            problems.append(f"Short: {name(supplies[0])} is wired to {name(grounds[0])}. A supply pin and a ground pin "
                            "must never share a wire; check which pin each end of that wire goes to.")
            continue
        levels = {p: volts(label(p)) for p in supplies if volts(label(p)) is not None}
        if levels and max(levels.values()) - min(levels.values()) > 0.3:
            hi = max(levels, key=levels.get)
            lo = min(levels, key=levels.get)
            problems.append(f"{name(hi)} ({levels[hi]:g} V) is wired to {name(lo)} ({levels[lo]:g} V). Feed the "
                            f"{levels[lo]:g} V pin from a {levels[lo]:g} V supply or a regulator instead.")
        level = max(levels.values(), default=None)
        for p in supplies if level is not None else []:
            if volts(label(p)) is not None:
                continue  # a source itself (the 3.3V pin), not an input
            _, part = part_of(p[0])
            notes, what = part.get("notes", ""), part.get("name", "that part")
            limits = rated(notes, label(p))
            if limits and not limits[0] - 0.05 <= level <= limits[1] + 0.05:
                problems.append(f"{name(p)} gets {level:g} V, but {what} takes {limits[0]:g} to {limits[1]:g} V there. "
                                "Feed it from a supply in that range.")
            elif not limits and level >= 4.5 and LOW_VOLTAGE_ONLY.search(notes) and not REGULATED_INPUT.match(label(p)):
                problems.append(f"{name(p)} gets {level:g} V, but {what} is 3.3 V only. Power it from a 3.3 V pin.")

        sda = [p for p in pins if re.search(r"\bSDA\d*\b", label(p), re.I)]  # "SDA", "18 / SDA", "17 / SDA1"
        seen: dict[str, tuple[str, bool]] = {}
        for p in sda:
            _, part = part_of(p[0])
            notes = part.get("notes", "")
            addresses = [a.lower() for a in ADDRESS.findall(notes)]
            if not addresses:
                continue
            first, fixed = addresses[0], len(set(addresses)) == 1
            if first in seen:
                other, other_fixed = seen[first]
                if fixed and other_fixed:
                    problems.append(f"{name(p)} and {other} share one I2C line, and both answer at {first} (fixed). Put one "
                                    "on the board's second I2C bus (e.g. Teensy 4.1 pins 17/16).")
                else:
                    tips.append(f"{name(p)} and {other} both default to I2C address {first} on one line. Set one to its other "
                                "address (its address pin or jumper) and say so in the wiring step.")
            else:
                seen[first] = (name(p), fixed)
    return {"problems": problems, "tips": tips}
