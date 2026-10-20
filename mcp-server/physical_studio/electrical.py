"""check_wiring: electrical mistakes in a design's wires, found from the boards' printed pin labels.

The parts library has no electrical model, but the labels printed on the boards say most of what
matters (GND, 3.3V, +12 V, VCC, SDA), and each part's notes give its I2C address and whether it's
3.3 V only. Wires join pins into nets (a wire with an inline part, e.g. a resistor, doesn't join its
ends); then a net may not:
- join a ground pin to a supply pin (a short),
- join two different supply voltages (12 V into a 3.3 V pin),
- carry 5 V or more to the supply pin of a 3.3 V only part,
- put two devices with the same fixed I2C address on one SDA line.
check_power adds current, from the parts' `electrical` data (parts/README.md): what each supply,
regulator and motor driver is asked to deliver against its rating, motors on a bare board pin, and
5 V signals into a board whose pins take 3.3 V.
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
    power = check_power(design, library)
    return {"problems": problems + power["problems"], "tips": tips + power["tips"]}


def check_power(design: Design, library: dict[str, dict]) -> dict:
    """Supply budgets and drive limits. Steady draw over a rating is a problem; brief peaks (a motor
    stalling) are tips, since a driver's current limit or a bigger supply handles them."""
    problems: list[str] = []
    tips: list[str] = []
    groups = nets(design)
    net_of = {pin: n for n, g in enumerate(groups) for pin in g}

    def part(pid):
        p = design.placements.get(pid)
        return p, (library.get(p.part_id, {}) if p else {})

    def elec(pid):
        return part(pid)[1].get("electrical") or {}

    def label(pin):
        q = next((q for q in part(pin[0])[1].get("pins", []) if q.get("id") == pin[1]), {})
        return q.get("label") or pin[1]

    def pname(pid):
        p, lib = part(pid)
        return p.name if p else pid

    def sources():
        """(pin, volts, mA it can give) for every supply output: adapters, batteries, regulators, board 5V/3V3 pins."""
        out = []
        for pid in design.placements:
            e = elec(pid)
            if e.get("output_pin") and e.get("output_ma"):
                out.append(((pid, e["output_pin"]), e.get("output_v"), e["output_ma"]))
            for rail, ma in (e.get("rails_ma") or {}).items():
                for q in part(pid)[1].get("pins", []):
                    if re.fullmatch(r"\+?" + {"5v": r"5\s*V", "3v3": r"3(\.3\s*V|V3)"}[rail], q.get("label", "").strip(), re.I):
                        out.append(((pid, q["id"]), 5.0 if rail == "5v" else 3.3, ma))
        return out

    def on_net(n, skip):
        return {pin[0] for pin in groups[n] if pin[0] != skip and not GROUND.search(label(pin))} if n is not None else set()

    def motors_of(pid):
        """Parts that need a driver and share a net with this driver's (non-supply) pins."""
        found = set()
        for pin in (q for q in net_of if q[0] == pid):
            for other in on_net(net_of[pin], pid):
                if elec(other).get("needs_driver"):
                    found.add(other)
        return found

    MOTOR_SUPPLY = re.compile(r"^\+?\s*(VIN|VM|VMOT|VS|V\+|\+|\d+(\.\d+)?\s*V)\b", re.I)

    def load(pid, volts, seen, via=None):
        """(typical, peak) mA this part takes from a supply at `volts` through its pin `via`, including what
        it passes on."""
        if pid in seen:
            return 0.0, 0.0
        e = elec(pid)
        if e.get("drive_ma") and via is not None and not MOTOR_SUPPLY.search(label(via)):
            return 1.0, 1.0  # a driver's logic pin (SLEEP, PMODE, VCC): the motor current isn't on this supply
        seen.add(pid)
        if e.get("input_pin") and e.get("output_pin"):  # a regulator: its outputs' load, converted to its input
            out_v = e.get("output_v") or volts
            typ = peak = 0.0
            out_net = net_of.get((pid, e["output_pin"]))
            for other in on_net(out_net, pid):
                t, pk = load(other, out_v, seen, next((q for q in groups[out_net] if q[0] == other), None))
                typ, peak = typ + t, peak + pk
            if e.get("output_ma") and typ > e["output_ma"]:
                problems.append(f"{pname(pid)} gives at most {e['output_ma']} mA, but its loads draw about {typ:.0f} mA. Use a bigger regulator.")
            if e.get("linear") or not volts:
                return typ, peak
            k = out_v / (volts * e.get("efficiency", 0.85))
            return typ * k, peak * k
        if e.get("drive_ma"):  # a motor driver: its motors' current flows through it
            typ = peak = 0.0
            for m in motors_of(pid):
                me = elec(m)
                typ, peak = typ + me.get("current_ma", 0), peak + me.get("peak_ma", me.get("current_ma", 0))
                if me.get("current_ma", 0) > e["drive_ma"]:
                    problems.append(f"{pname(m)} draws about {me['current_ma']} mA running, more than {pname(pid)}'s {e['drive_ma']} mA. Use a bigger driver.")
                elif me.get("peak_ma", 0) > e["drive_ma"]:
                    tips.append(f"{pname(m)} can draw {me['peak_ma']} mA when it stalls, more than {pname(pid)}'s {e['drive_ma']} mA. "
                                f"Set the driver's current limit (or rely on its overcurrent shutdown) and say so in the wiring step.")
                seen.add(m)
            return typ + e.get("current_ma", 0), peak + e.get("peak_ma", e.get("current_ma", 0))
        if e.get("needs_driver"):
            return 0.0, 0.0  # counted through its driver, or flagged below when it has none
        return float(e.get("current_ma", 0)), float(e.get("peak_ma", e.get("current_ma", 0)))

    for pin, volts, rating in sources():
        n = net_of.get(pin)
        if n is None:
            continue
        typ = peak = 0.0
        seen: set = {pin[0]}
        users = []
        for other in sorted(on_net(n, pin[0])):
            t, pk = load(other, volts, seen, next((q for q in groups[n] if q[0] == other), None))
            if t or pk:
                users.append(pname(other))
            typ, peak = typ + t, peak + pk
        what = f"{pname(pin[0])}'s {label(pin)} output"
        who = " and ".join(filter(None, [", ".join(users[:-1]), users[-1] if users else ""]))
        if typ > rating:
            problems.append(f"{what} can give {rating} mA, but {who} {'draws' if len(users) == 1 else 'draw'} about {typ:.0f} mA. Use a bigger supply or split the load.")
        elif peak > rating:
            tips.append(f"{what} can give {rating} mA, but {who} can briefly draw up to {peak:.0f} mA together (a motor starting or stalling). "
                        "If the board resets when the motor starts, use a bigger supply.")

    boards = {pid: elec(pid) for pid in design.placements if elec(pid).get("logic_v")}
    supply_v = {}
    for pin, volts, _ in sources():
        if net_of.get(pin) is not None:
            for other in on_net(net_of[pin], pin[0]):
                supply_v[other] = max(supply_v.get(other, 0), volts or 0)
    for g in groups:
        board_pins = [p for p in g if p[0] in boards and not GROUND.search(label(p)) and not is_supply(label(p))]
        if not board_pins:
            continue
        for pid in {p[0] for p in g if p[0] not in boards}:
            e = elec(pid)
            if e.get("needs_driver"):
                problems.append(f"{pname(pid)} is wired straight to {pname(board_pins[0][0])} {label(board_pins[0])}, but it draws about "
                                f"{e.get('current_ma')} mA and a board pin gives {boards[board_pins[0][0]].get('pin_ma', 20)} mA. Drive it through a motor driver or transistor.")
            sv = e.get("signal_v")
            out_v = supply_v.get(pid) if sv == "supply" else sv
            board = boards[board_pins[0][0]]
            if out_v and out_v > 3.6 and not board.get("five_v_tolerant", True):
                problems.append(f"{pname(pid)} is powered from {out_v:g} V, so its signal on {pname(board_pins[0][0])} {label(board_pins[0])} is {out_v:g} V, "
                                "but that pin takes 3.3 V. Power it from 3.3 V, or add a level shifter or divider.")
    return {"problems": list(dict.fromkeys(problems)), "tips": list(dict.fromkeys(tips))}
