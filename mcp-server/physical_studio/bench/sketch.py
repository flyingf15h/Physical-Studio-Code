# Deterministic checks on a breadboard plan that the AI can't be trusted to get right on its own:
# the sketch compiles for the board, the pins in the code are the pins the wires go to, and parts
# with a fixed leg spacing (buttons, pin headers, buzzers) sit in holes they can physically reach.
# Problems are plain sentences, fed back to the planner's repair rounds like check_plan's.
import hashlib, os, re, shutil, subprocess, tempfile

# Boards we can compile for with the cores installed in the image (deploy/mcp.Dockerfile).
FQBN = [(re.compile(r'\buno\b', re.I), 'arduino:avr:uno'), (re.compile(r'\bnano\b', re.I), 'arduino:avr:nano'),
        (re.compile(r'\bmega\b', re.I), 'arduino:avr:mega')]
PWM = {'arduino:avr:uno': {3, 5, 6, 9, 10, 11}, 'arduino:avr:nano': {3, 5, 6, 9, 10, 11},
       'arduino:avr:mega': set(range(2, 14)) | {44, 45, 46}}
ANALOG_BASE = {'arduino:avr:uno': 14, 'arduino:avr:nano': 14, 'arduino:avr:mega': 54}
POWER = re.compile(r'^(gnd\d*|5v|3v3|3\.3v|vin|ioref|aref|reset|rst|v5|vcc)$')


def board_of(scene):
    """(board part, fqbn) for the plan's development board, fqbn None when we can't compile for it."""
    for p in scene.parts:
        if p.kind == 'development_board':
            return p, next((f for rx, f in FQBN if rx.search(p.name)), None)
    return None, None


# --- 1. compile --------------------------------------------------------------------------------
CLI = os.environ.get('ARDUINO_CLI') or shutil.which('arduino-cli')
_compiled = {}


def compile_sketch(code, fqbn):
    """None when it compiles (or arduino-cli isn't installed: then it's logged, not blocked), else the
    compiler's first errors as one short paragraph. Cached by code, so repair rounds don't recompile."""
    if not CLI or not fqbn or not (code or '').strip():
        if not CLI: print('[bench] arduino-cli not installed: sketches are not compiled', flush=True)
        return None
    key = hashlib.sha1((fqbn + code).encode()).hexdigest()
    if key in _compiled: return _compiled[key]
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'sketch'))
        with open(os.path.join(d, 'sketch', 'sketch.ino'), 'w') as f: f.write(code)
        try:
            r = subprocess.run([CLI, 'compile', '--fqbn', fqbn, '--no-color', os.path.join(d, 'sketch')],
                               capture_output=True, text=True, timeout=120)
            out = None if r.returncode == 0 else errors_of(r.stdout + r.stderr, d)
        except subprocess.TimeoutExpired:
            out = None  # a slow machine is not the sketch's fault
            print('[bench] arduino-cli compile timed out', flush=True)
    _compiled[key] = out
    return out


def errors_of(text, tmp):
    text = text.replace(tmp + '/sketch/', '')
    lines = [l.strip() for l in text.splitlines() if re.search(r'error|No such file', l)]
    return ' '.join(lines[:4])[:600] or text.strip()[-600:]


# --- 2. code pins vs wiring --------------------------------------------------------------------
NUM = r'(A\d{1,2}|\d{1,2}|LED_BUILTIN)'
CONST = re.compile(r'(?:#define\s+(\w+)\s+' + NUM + r'\b)|(?:\b(?:const\s+)?(?:static\s+)?(?:unsigned\s+)?(?:byte|int|uint8_t|short|long|char)\s+(\w+)\s*=\s*' + NUM + r'\s*;)')
ARRAY = re.compile(r'\b(?:const\s+)?(?:byte|int|uint8_t)\s+(\w+)\s*\[\s*\d*\s*\]\s*=\s*\{([^}]*)\}')
CALL = re.compile(r'\b(pinMode|digitalWrite|digitalRead|analogRead|analogWrite|tone|noTone|pulseIn|attach)\s*\(\s*([A-Za-z_]\w*|\d+)(?:\s*\[[^\]]*\])?')
INPUTS = re.compile(r'\b(?:digitalRead|analogRead|pulseIn)\s*\(\s*([A-Za-z_]\w*|\d+)|\bpinMode\s*\(\s*([A-Za-z_]\w*|\d+)\s*,\s*INPUT')


def strip_comments(code):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', code, flags=re.S)


def pin_number(token, fqbn):
    token = token.strip()
    if token == 'LED_BUILTIN': return 13
    if re.fullmatch(r'A\d{1,2}', token): return ANALOG_BASE[fqbn] + int(token[1:])
    return int(token) if token.isdigit() else None


def pin_label(n, fqbn):
    base = ANALOG_BASE[fqbn]
    return f'A{n - base}' if n >= base else f'D{n}'


def code_pins(code, fqbn):
    """{pin number: how the code uses it} for the pins the sketch drives or reads by name or number.
    Pins it can't resolve (a loop variable, a computed pin) are left out rather than guessed."""
    code = re.sub(r'randomSeed\s*\([^;]*;', '', strip_comments(code))  # analogRead of a floating pin for a seed is fine
    names = {}
    for m in CONST.finditer(code):
        name, val = (m[1], m[2]) if m[1] else (m[3], m[4])
        n = pin_number(val, fqbn)
        if n is not None: names[name] = [n]
    for m in ARRAY.finditer(code):
        vals = [pin_number(v, fqbn) for v in m[2].split(',') if v.strip()]
        if vals and all(v is not None for v in vals): names[m[1]] = vals
    def resolve(tok):
        return names.get(tok) or ([pin_number(tok, fqbn)] if pin_number(tok, fqbn) is not None else [])
    used, inputs = {}, set()
    for m in CALL.finditer(code):
        for n in resolve(m[2]): used.setdefault(n, m[1])
    for m in INPUTS.finditer(code):
        for n in resolve(m[1] or m[2]): inputs.add(n)
    return used, inputs, names


def wired_pins(scene, board, fqbn):
    """{pin number: wire name} for the board's signal pins that a wire goes to (power and ground left out)."""
    out = {}
    for w in scene.wires:
        for part, term in ((w.from_part, w.from_terminal), (w.to_part, w.to_terminal)):
            if part != board.id: continue
            t = term.lower().replace(' ', '').replace('pin:', '').lstrip('~')
            if POWER.match(t): continue
            m = re.fullmatch(r'(?:d|gpio|io)?(\d{1,2})', t) or re.fullmatch(r'a(\d{1,2})', t)
            if not m: continue
            n = ANALOG_BASE[fqbn] + int(m[1]) if t.startswith('a') else int(m[1])
            out[n] = w.name
    return out


def mentions(code, n, fqbn, names):
    """Does the code refer to pin n anywhere (a constant, a literal, a library constructor's argument)?"""
    code = strip_comments(code)
    if any(n in v for v in names.values()): return True
    tokens = [str(n)] + ([f'A{n - ANALOG_BASE[fqbn]}'] if n >= ANALOG_BASE[fqbn] else [])
    return any(re.search(r'(?<![\w.])' + re.escape(t) + r'(?![\w.])', code) for t in tokens)


def check_pins(code, scene):
    board, fqbn = board_of(scene)
    if not board or not fqbn or not (code or '').strip(): return []
    used, inputs, names = code_pins(code, fqbn)
    wired = wired_pins(scene, board, fqbn)
    problems = []
    for n, how in sorted(used.items()):
        if n in wired: continue
        if n == 13 and n not in inputs: continue  # the Uno's own L LED on D13 is a fine output
        problems.append(f'The sketch uses pin {pin_label(n, fqbn)} ({how}), but no wire goes to that pin. '
                        'Wire the part that pin is for, or change the code to the pin that is wired.')
    for n, wire in sorted(wired.items()):
        if not mentions(code, n, fqbn, names):
            problems.append(f'Wire "{wire}" goes to pin {pin_label(n, fqbn)}, but the sketch never uses that pin. '
                            'Make the code and the wiring use the same pin.')
    for m in re.finditer(r'\banalogWrite\s*\(\s*([A-Za-z_]\w*|\d+)', strip_comments(code)):
        for n in names.get(m[1]) or ([pin_number(m[1], fqbn)] if pin_number(m[1], fqbn) is not None else []):
            if n not in PWM[fqbn]:
                problems.append(f'The sketch calls analogWrite on pin {pin_label(n, fqbn)}, which has no PWM on this board '
                                f'(PWM pins: {", ".join(map(str, sorted(PWM[fqbn])))}). Move it to a PWM pin.')
    return problems


# --- 3. footprints -----------------------------------------------------------------------------
# A real breadboard's columns, 0.1" apart with the 0.3" DIP gap between e and f (the 3D template draws it wider).
COLS = dict(zip('abcdefghij', [13.97, 11.43, 8.89, 6.35, 3.81, -3.81, -6.35, -8.89, -11.43, -13.97]))
HOLE = re.compile(r'([a-j])(\d{1,2})$')
HEADER = re.compile(r'module|hc-?sr04|ultrasonic|max7219|matrix|joystick|ky-?\d|oled|lcd|display|dht\d*|bmp\d*|mpu-?\d*|rfid|rc522|relay|driver|header|breakout', re.I)


def xy(hole):
    m = HOLE.match(hole.lower())
    return ((int(m[2]) - 1) * 2.54, COLS[m[1]]) if m else None


def check_footprints(scene):
    problems = []
    for p in scene.parts:
        if p.kind != 'generic': continue
        pts = [xy(h) for h in p.mount_holes]
        if not pts or None in pts: continue
        name = p.name
        if re.search(r'button|push.?button|tactile|switch', name, re.I) and len(pts) == 4:
            big = not re.search(r'\b6\s?(x\s?6\s?)?mm', name, re.I)
            across = sorted({round(y, 2) for _, y in pts}); rows = sorted({round(x, 2) for x, _ in pts})
            want_across, label = ((12.5, 'columns d and g') if big else (6.5, 'columns e and f'))
            ok = (len(across) == 2 and len(rows) == 2 and abs(across[1] - across[0] - want_across) <= 1.3
                  and abs(rows[1] - rows[0] - 5.0) <= 1.3)
            if not ok:
                size = '12 mm' if big else '6 mm'
                problems.append(f'{name}: a {size} button\'s legs are {want_across} x 5 mm apart, so it must straddle the centre gap in '
                                f'{label}, two rows apart (e.g. {"d20, g20, d22, g22" if big else "e20, f20, e22, f22"}); '
                                f'{", ".join(p.mount_holes)} doesn\'t fit it.')
        elif re.search(r'buzzer|piezo', name, re.I) and len(pts) == 2:
            dist = ((pts[0][0] - pts[1][0]) ** 2 + (pts[0][1] - pts[1][1]) ** 2) ** .5
            if not 4.5 <= dist <= 10.5:
                problems.append(f'{name}: a 12 mm buzzer\'s legs are about 6.5-7.6 mm apart (three rows); '
                                f'{", ".join(p.mount_holes)} are {dist:.1f} mm apart. Put its legs three rows apart in one column.')
        elif HEADER.search(name) and len(pts) >= 3:
            cols = {h.lower()[0] for h in p.mount_holes}; rows = sorted(int(HOLE.match(h.lower())[2]) for h in p.mount_holes)
            if len(cols) != 1 or rows != list(range(rows[0], rows[0] + len(rows))):
                problems.append(f'{name}: its pin header is a straight row of pins 2.54 mm apart, so its {len(pts)} pins go in '
                                f'{len(pts)} neighbouring rows of one column (e.g. e{rows[0]} to e{rows[0] + len(pts) - 1}); '
                                f'{", ".join(p.mount_holes)} doesn\'t fit it.')
    return problems


def check_sketch(plan):
    """Pins and compile problems for a plan object (pydantic Plan). Footprints are in check_plan."""
    code = getattr(plan, 'code', '') or ''
    board, fqbn = board_of(plan.scene)
    problems = check_pins(code, plan.scene)
    err = compile_sketch(code, fqbn)
    if err: problems.append(f'The sketch does not compile for the {board.name}: {err} Fix the code.')
    return problems
