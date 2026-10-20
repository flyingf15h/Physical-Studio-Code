# Real-looking materials for the breadboard bench GLBs (geometry.py): each colour gets a finish (bare metal,
# glossy LED epoxy, plastic, solder mask), and the Uno's top face gets a drawn PCB texture (solder mask,
# copper traces, white silkscreen with the real pin labels from parts/arduino-uno.json).
import functools
import json
import random
from pathlib import Path

import trimesh
from PIL import Image, ImageDraw, ImageFont
from trimesh.visual.material import PBRMaterial

PARTS = Path(__file__).resolve().parents[3] / 'parts'
METAL = {'#bbc1c5', '#bdc5cc', '#b3bbc1', '#aab1b7', '#c9cdd2', '#d6d9dc'}
GOLD = {'#c2b888', '#c8a85a'}
BLACK = {'#1b2228', '#30383d', '#151c22', '#293139', '#20282c', '#333b41', '#323a40', '#111316'}


def linear(hex_color):
    """glTF wants linear colour factors; trimesh writes what it's given."""
    def ch(c):
        c /= 255
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    rgb = bytes.fromhex(hex_color.lstrip('#')[:6])
    return [round(ch(c) * 255) for c in rgb] + [255]


def finish(hex_color, kind=''):
    """(metallic, roughness) for a part colour."""
    c = hex_color.lower()
    if c in METAL: return .95, .32
    if c in GOLD: return .9, .3
    if c in BLACK: return 0, .5
    if kind == 'led': return 0, .18
    if kind == 'wire': return 0, .45
    return 0, .6


def material(hex_color, kind=''):
    metal, rough = finish(hex_color, kind)
    return PBRMaterial(baseColorFactor=linear(hex_color), metallicFactor=metal, roughnessFactor=rough, doubleSided=True)


@functools.lru_cache(maxsize=1)
def uno_pins():
    return json.loads((PARTS / 'arduino-uno.json').read_text())['pins']


@functools.lru_cache(maxsize=1)
def uno_texture():
    """The Uno's top as a picture, 16 px per mm, board origin at the bottom left (the USB side is -x)."""
    s = 16
    W, H = round(68.6 * s), round(53.4 * s)
    img = Image.new('RGB', (W, H), '#00737a')
    d = ImageDraw.Draw(img)
    px = lambda x, y: (x * s, H - y * s)
    rnd = random.Random(7)
    for _ in range(26000):  # solder mask isn't flat: a fine grain
        x, y = rnd.randrange(W), rnd.randrange(H)
        v = rnd.randrange(-9, 9)
        d.point((x, y), (0, max(0, 0x73 + v), max(0, 0x7a + v)))
    trace = '#0b858c'
    for _ in range(46):  # copper traces under the mask, routed at 0/45/90 degrees
        x, y = rnd.uniform(14, 62), rnd.uniform(9, 46)
        pts = [px(x, y)]
        for _ in range(rnd.randint(2, 4)):
            dx, dy = rnd.choice([(1, 0), (0, 1), (1, 1), (1, -1), (-1, 0), (0, -1)])
            k = rnd.uniform(2, 9)
            x, y = min(66, max(3, x + dx * k)), min(50, max(4, y + dy * k))
            pts.append(px(x, y))
        d.line(pts, fill=trace, width=int(.35 * s), joint='curve')
    for _ in range(60):  # vias
        x, y = px(rnd.uniform(12, 64), rnd.uniform(8, 46))
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill='#c9b071'); d.ellipse([x - 3, y - 3, x + 3, y + 3], fill='#203033')
    for hx, hy in [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)]:  # mounting holes: tinned ring
        x, y = px(hx, hy)
        d.ellipse([x - 3.2 * s, y - 3.2 * s, x + 3.2 * s, y + 3.2 * s], fill='#d4c08a')
        d.ellipse([x - 1.6 * s, y - 1.6 * s, x + 1.6 * s, y + 1.6 * s], fill='#1a1f22')
    font = lambda mm: ImageFont.load_default(size=int(mm * s))
    ink = '#f2f4f2'
    for pin in uno_pins():  # pin labels just inside each header
        x, y, _ = pin['position']
        top = y > 26
        label = pin['label'].replace('~', '')
        tx, ty = px(x, y - 3.6 if top else y + 3.6)
        img_t = Image.new('RGBA', (int(5 * s), int(1.7 * s)), (0, 0, 0, 0))
        ImageDraw.Draw(img_t).text((0, 0), label, font=font(1.35), fill=ink)
        img_t = img_t.rotate(90, expand=True)
        img.paste(img_t, (int(tx - img_t.width / 2), int(ty - (img_t.height if not top else 0))), img_t)
    d.text(px(47, 41.5), 'DIGITAL (PWM~)', font=font(1.9), fill=ink, anchor='mm')
    d.text(px(37, 11.5), 'POWER', font=font(1.9), fill=ink, anchor='mm')
    d.text(px(57, 11.5), 'ANALOG IN', font=font(1.9), fill=ink, anchor='mm')
    d.text(px(30, 31), 'UNO', font=font(7.5), fill=ink, anchor='mm')
    d.text(px(30, 24.5), 'ARDUINO', font=font(2.6), fill=ink, anchor='mm')
    cx, cy = px(48, 31)  # the infinity logo
    for dx in (-2.3, 2.3):
        d.ellipse([cx + (dx - 2.2) * s, cy - 2.2 * s, cx + (dx + 2.2) * s, cy + 2.2 * s], outline=ink, width=int(.55 * s))
    d.text((cx - 2.3 * s, cy), '-', font=font(3), fill=ink, anchor='mm'); d.text((cx + 2.3 * s, cy), '+', font=font(3), fill=ink, anchor='mm')
    d.text(px(10, 45), 'L', font=font(1.6), fill=ink, anchor='mm'); d.text(px(10, 42.5), 'TX', font=font(1.4), fill=ink, anchor='mm')
    d.text(px(10, 40.5), 'RX', font=font(1.4), fill=ink, anchor='mm'); d.text(px(62, 28), 'ON', font=font(1.6), fill=ink, anchor='mm')
    d.text(px(60, 47), 'ICSP', font=font(1.3), fill=ink, anchor='mm'); d.text(px(8, 24), 'RESET', font=font(1.3), fill=ink, anchor='mm')
    return img


def uno_top(x0, y0, z):
    """A quad over the Uno's top face (board origin at x0, y0), textured with uno_texture()."""
    w, h = 68.6, 53.4
    verts = [[x0, y0, z], [x0 + w, y0, z], [x0 + w, y0 + h, z], [x0, y0 + h, z]]
    m = trimesh.Trimesh(vertices=verts, faces=[[0, 1, 2], [0, 2, 3]], process=False)
    m.visual = trimesh.visual.TextureVisuals(uv=[[0, 0], [1, 0], [1, 1], [0, 1]], material=PBRMaterial(
        baseColorTexture=uno_texture(), metallicFactor=0, roughnessFactor=.45, doubleSided=True))
    return m
