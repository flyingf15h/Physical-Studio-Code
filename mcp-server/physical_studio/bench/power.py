# Power and current checks on a breadboard plan, from the library parts' `electrical` data
# (parts/README.md): LED current through its resistor, motors and other heavy loads on a bare
# GPIO pin, modules on the wrong supply voltage, 5 V signals into a 3.3 V board, and how much the
# board's 5V and 3V3 pins are asked to supply. Problems must be fixed (they go to the repair
# rounds); warnings are true but not fatal (a servo's stall current), and are shown with the guide.
import re

from . import planner  # planner imports this module too; its functions are looked up when called

SUPPLY = {'5v': 5.0, '3v3': 3.3, '3.3v': 3.3}
COLOURS = ('red', 'orange', 'yellow', 'green', 'blue', 'white', 'pink', 'purple')


def electrical(name):
    p = planner.library_part(name)
    return (p or {}).get('electrical') or {}, p


def ohms(name):
    """220 for "220 ohm resistor (red LED)", 10000 for "10 kΩ resistor"; None when the name has no value."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*(k|m)?\s*(?:ohms?|Ω|r\b)', name, re.I) or re.search(r'(\d+(?:\.\d+)?)\s*(k|m)\b', name, re.I)
    if not m: return None
    return float(m[1]) * {'k': 1e3, 'm': 1e6}.get((m[2] or '').lower(), 1)


class Nets:
    """Which breadboard strips, rails and board pins are joined by wires (union-find)."""
    def __init__(self, scene):
        self.parts = {p.id: p for p in scene.parts}
        self.boards = {p.id for p in scene.parts if p.kind == 'development_board'}
        self.parent = {}
        for w in scene.wires:
            a, b = self.node(w.from_part, w.from_terminal), self.node(w.to_part, w.to_terminal)
            if a and b: self.parent[self.find(a)] = self.find(b)

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]; x = self.parent[x]
        return x

    def node(self, part, term):
        term = term.lower().replace(' ', '').replace('pin:', '')
        if part in self.boards: return ('pin', term)
        p = self.parts.get(part)
        if p and p.kind == 'breadboard': return planner.group(term)
        if p and p.mount_holes:
            return planner.group(p.mount_holes[{'anode': 0, 'cathode': 1, '1': 0, '2': 1}.get(term, 0)].lower())
        return None

    def of_hole(self, hole):
        g = planner.group(hole.lower())
        return self.find(g) if g else None

    def pins_on(self, net):
        """Board pin names on this net."""
        return {n[1] for n in list(self.parent) if n[0] == 'pin' and self.find(n) == net} if net else set()


def is_ground(pin): return pin.startswith('gnd')
def is_power(pin): return pin in SUPPLY or pin in ('vin', 'ioref', 'aref', 'reset', 'rst')
def is_signal(pin): return not is_ground(pin) and not is_power(pin)


def check_power(plan):
    """(problems, warnings) for a plan object (pydantic Plan with .scene and .steps)."""
    scene = plan.scene
    problems, warnings = [], []
    board = next((p for p in scene.parts if p.kind == 'development_board'), None)
    if not board: return problems, warnings
    be, _ = electrical(board.name)
    if not be: return problems, warnings
    logic = be['logic_v']; nets = Nets(scene)
    draw = {'5v': [0, 0], '3v3': [0, 0]}  # typical, peak mA asked of each supply pin
    users = {'5v': [], '3v3': []}
    pin_total = 0.0
    resistors = [(p, [nets.of_hole(h) for h in p.mount_holes[:2]]) for p in scene.parts
                 if p.kind == 'resistor' and len(p.mount_holes) >= 2]

    # LEDs: current through the series resistor from a pin (or a supply rail)
    for led in (p for p in scene.parts if p.kind == 'led' and len(p.mount_holes) == 2):
        le, _ = electrical(led.name)
        colour = next((c for c in COLOURS if c in led.name.lower()), 'red')
        vf = (le.get('vf') or {}).get(colour, 2.0); limit = le.get('max_ma', 20)
        a, k = nets.of_hole(led.mount_holes[0]), nets.of_hole(led.mount_holes[1])
        for r, (x, y) in resistors:
            if a in (x, y): source_net = y if x == a else x  # resistor on the anode side: its far end is the source
            elif k in (x, y): source_net = a                   # resistor on the cathode side: the anode row is
            else: continue
            pins = nets.pins_on(source_net)
            src = next((q for q in sorted(pins) if is_signal(q)), None) or next((q for q in pins if q in SUPPLY), None)
            if not src or not ohms(r.name): break
            volts = SUPPLY.get(src, logic)
            ma = max(0.0, (volts - vf) / ohms(r.name) * 1000)
            if is_signal(src): pin_total += ma
            if ma > limit:
                problems.append(f'{led.name}: with the {r.name} on {src.upper()} about {ma:.0f} mA flows, more than the LED\'s {limit} mA. '
                                f'Use a bigger resistor (at least {-(-(volts - vf) / limit * 1000 // 10) * 10:.0f} ohm).')
            elif is_signal(src) and ma > be['pin_ma']:
                problems.append(f'{led.name}: about {ma:.0f} mA from pin {src.upper()}, more than the {be["pin_ma"]} mA a pin of the '
                                f'{board.name} can safely give. Use a bigger resistor.')
            elif ma < 1:
                warnings.append(f'{led.name}: only about {ma:.1f} mA flows through the {r.name}, so it will be very dim.')
            break

    # modules: supply voltage, logic levels, heavy loads on GPIO, supply budget
    for p in scene.parts:
        if p.kind not in ('generic',) or not p.mount_holes: continue
        e, lib = electrical(p.name)
        if not e: continue
        hole_nets = [nets.of_hole(h) for h in p.mount_holes]
        pins = set().union(*(nets.pins_on(n) for n in hole_nets))
        supply = next((s for s in ('5v', '3v3', '3.3v') if s in pins), None)
        rail = '3v3' if supply == '3.3v' else supply
        volts = SUPPLY.get(supply)
        signal = sorted(pin for pin in pins if is_signal(pin))
        lo, hi = (e.get('supply_v') or [None, None])
        if volts and lo is not None and not (lo - .05 <= volts <= hi + .05):
            problems.append(f'{p.name} runs on {lo:g}-{hi:g} V, but it is powered from the board\'s {supply.upper()} pin ({volts:g} V). '
                            f'{"Power it from 3V3 instead." if hi < 4 else "Power it from 5V instead." if lo > 3.4 else ""}'.strip())
        if e.get('needs_driver') and signal:
            problems.append(f'{p.name} draws about {e["current_ma"]} mA (up to {e["peak_ma"]} mA), but a {board.name} pin can only give '
                            f'{be["pin_ma"]} mA, and {", ".join(s.upper() for s in signal)} is wired straight to it. Drive it through a '
                            'transistor, MOSFET or motor driver, with its own supply and a shared ground.')
        sv = e.get('signal_v'); out_v = volts if sv == 'supply' else sv
        if signal and not be.get('five_v_tolerant') and out_v and out_v > 3.6:
            problems.append(f'{p.name} is powered from {volts:g} V, so its outputs are {volts:g} V, but the {board.name}\'s pins only take 3.3 V '
                            f'({", ".join(s.upper() for s in signal)}). Add a level shifter or a voltage divider, or power it from 3.3 V if it allows.')
        for pin_id, vmax in (e.get('pin_max_v') or {}).items():
            hole = pin_hole(plan, p, lib, pin_id)
            if hole and logic > vmax + .1 and any(is_signal(x) for x in nets.pins_on(nets.of_hole(hole))):
                problems.append(f'{p.name}\'s {pin_id.upper()} pin takes {vmax:g} V, but a {logic:g} V board pin drives it. '
                                'Put a voltage divider (e.g. 1 k and 2 k) in that wire.')
        if rail:
            draw[rail][0] += e.get('current_ma', 0); draw[rail][1] += e.get('peak_ma', e.get('current_ma', 0))
            users[rail].append(p.name)

    for rail, (typ, peak) in draw.items():
        budget = (be.get('rails_ma') or {}).get(rail)
        if not budget or not users[rail]: continue
        who = ', '.join(users[rail])
        if typ > budget:
            problems.append(f'The parts on the board\'s {rail.upper()} pin ({who}) draw about {typ} mA, more than the {budget} mA it can supply. '
                            'Give them their own power supply (shared ground with the board).')
        elif peak > budget:
            warnings.append(f'The parts on the board\'s {rail.upper()} pin ({who}) can briefly draw up to {peak} mA (e.g. a servo stalling or every LED '
                            f'at full brightness), more than the {budget} mA it supplies, which can reset the board. If it resets, power them separately.')
    if pin_total > be.get('total_pin_ma', 1e9):
        problems.append(f'The LEDs together draw about {pin_total:.0f} mA from the board\'s pins, more than the {be["total_pin_ma"]} mA '
                        'all pins together can give. Use bigger resistors or a driver.')
    return problems, warnings


def pin_hole(plan, part, lib, pin_id):
    """The hole a module's pin (by library id/label) goes in, read from the step that places it."""
    labels = {pin_id.lower()} | {q.get('label', '').lower() for q in (lib or {}).get('pins', []) if q['id'].lower() == pin_id.lower()}
    for s in plan.steps:
        if part.id not in s.part_ids: continue
        for pl in s.placements:
            what = pl.what.lower()
            if any(re.search(r'(?<![a-z0-9])' + re.escape(l) + r'(?![a-z0-9])', what) for l in labels if l):
                return pl.hole.strip().lower()
    return None
