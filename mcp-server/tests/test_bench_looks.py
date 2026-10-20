import json
import struct
from pathlib import Path

from physical_studio.bench.geometry import build
from physical_studio.bench.looks import linear, uno_texture
from physical_studio.bench.spec import Spec, validate


def glb_json(glb):
    n = struct.unpack('<I', glb[12:16])[0]
    return json.loads(glb[20:20 + n])


def test_bench_glb_has_real_materials_and_the_uno_texture():
    ready = Path(__file__).resolve().parent.parent / 'physical_studio/bench/ready/traffic-light/build.json'
    scene = validate(Spec.model_validate(json.loads(ready.read_text())['internal']['plan']['scene']))
    doc = glb_json(build(scene)[0])
    names = [n['name'] for n in doc['nodes']]
    assert 'uno__top' in names and any(n.startswith('wire') or '__m' in n for n in names)
    assert doc.get('images')  # the drawn PCB
    colours = [m['pbrMetallicRoughness'].get('baseColorFactor', [0, 0, 0, 1]) for m in doc['materials']]
    red = [c / 255 for c in linear('#d23b2c')[:3]]
    assert any(all(abs(a - b) < .01 for a, b in zip(c, red)) for c in colours)  # 220 ohm: red bands
    assert any(m['pbrMetallicRoughness'].get('metallicFactor', 0) > .9 for m in doc['materials'])  # bare metal


def test_uno_texture_is_board_sized():
    w, h = uno_texture().size
    assert abs(w / h - 68.6 / 53.4) < .01
