"""Writes the materials library (parts/materials/): seamless textures plus materials.json, like a
SketchUp materials palette. A part's appearance names one ("material": "ground-steel") and the
guide renders tile it at real scale (export.py).

    uv run python examples/make_materials.py

Each texture is a greyscale detail map (brushed streaks, wood grain, print layers...) that the
material's colour tints, so one map serves a family (every PLA colour, every solder mask). They're
made here from seeded noise, so they're reproducible and need no downloads. All tile seamlessly:
noise is smoothed in the frequency domain, which wraps around the edges.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[2] / "parts" / "materials"
N = 256  # pixels per side


def noise(seed: int, sx: float, sy: float | None = None) -> np.ndarray:
    """Tileable smooth noise in [-1, 1]; sx/sy are the blur widths in pixels along x and y."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((N, N))
    fy, fx = np.meshgrid(np.fft.fftfreq(N), np.fft.fftfreq(N), indexing="ij")
    sy = sx if sy is None else sy
    kernel = np.exp(-2 * (np.pi**2) * ((fx * sx) ** 2 + (fy * sy) ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * kernel))
    return out / (np.abs(out).max() + 1e-9)


def detail(a: np.ndarray, lo: float, hi: float) -> Image.Image:
    """Map [-1, 1] to brightness lo..hi (1 = the material colour itself)."""
    v = lo + (np.clip(a, -1, 1) + 1) / 2 * (hi - lo)
    return Image.fromarray((np.clip(v, 0, 1) * 255).astype(np.uint8), "L").convert("RGB")


def brushed():  # long streaks along x, the look of brushed or ground metal
    return 0.65 * noise(1, 40, 0.6) + 0.35 * noise(2, 3)


def ground():  # finer, crossed grinding marks
    return 0.5 * noise(3, 18, 0.8) + 0.3 * noise(4, 0.8, 14) + 0.2 * noise(5, 1.5)


def wood():  # growth rings bent by noise, plus fibres
    y = np.arange(N)[:, None] * np.ones((1, N))
    rings = np.sin(2 * np.pi * (y / N * 9 + 1.6 * noise(6, 30, 8)))
    return 0.7 * rings + 0.3 * noise(7, 25, 0.7)


def speckle(seed):  # MDF, rubber, anodised: fine grain
    return 0.7 * noise(seed, 0.7) + 0.3 * noise(seed + 1, 6)


def layers():  # FDM print lines along x, 32 per tile
    y = np.arange(N)[:, None] * np.ones((1, N))
    return 0.6 * np.cos(2 * np.pi * y / (N / 32)) + 0.4 * noise(9, 6, 1)


def weave():  # glass-fibre weave under a solder mask
    yy, xx = np.mgrid[0:N, 0:N]
    w = np.sin(2 * np.pi * xx / (N / 16)) * np.sin(2 * np.pi * yy / (N / 16))
    return 0.35 * w + 0.65 * noise(10, 3)


def polished():  # chrome: almost smooth, a few soft highlights
    return noise(11, 20)


# name: (maker, brightness range, colour, metallic, roughness, mm per tile, what it is)
MATERIALS = {
    "brushed-aluminium": (brushed, (0.66, 1.0), "#c3c8cd", 0.85, 0.42, 60, "Brushed aluminium plate or extrusion"),
    "ground-steel": (ground, (0.66, 1.0), "#b4b9bf", 0.9, 0.32, 40, "Ground bearing steel (linear rails, carriages)"),
    "gear-steel": (ground, (0.6, 1.0), "#9aa0a6", 0.85, 0.45, 25, "Machined carbon-steel gears and racks"),
    "chrome": (polished, (0.9, 1.0), "#dfe3e6", 1.0, 0.12, 30, "Chrome-plated shafts and bearings"),
    "black-anodised": (lambda: speckle(12), (0.62, 1.0), "#2c2e33", 0.55, 0.5, 20, "Black anodised aluminium, motor cans"),
    "plywood": (wood, (0.55, 1.0), "#cfa878", 0.0, 0.75, 120, "Birch plywood base plate"),
    "mdf": (lambda: speckle(14), (0.74, 1.0), "#b98d5f", 0.0, 0.85, 40, "MDF board"),
    "pla": (layers, (0.7, 1.0), "#f0f0ec", 0.0, 0.6, 12.8, "3D-printed PLA (tinted by the part's colour)"),
    "rubber": (lambda: speckle(16), (0.8, 1.0), "#232323", 0.0, 0.95, 15, "Rubber or matte black plastic"),
    "pcb": (weave, (0.72, 1.0), "#1d6b3a", 0.0, 0.5, 8, "PCB solder mask (tinted green, blue or purple)"),
    "brass": (brushed, (0.8, 1.0), "#c9a54f", 0.9, 0.35, 30, "Brass inserts, standoffs and terminals"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for name, (make, (lo, hi), color, metallic, roughness, tile_mm, about) in MATERIALS.items():
        detail(make(), lo, hi).save(OUT / f"{name}.jpg", quality=82)
        index[name] = {"file": f"{name}.jpg", "color": color, "metallic": metallic, "roughness": roughness,
                       "tile_mm": tile_mm, "about": about}
    (OUT / "materials.json").write_text(json.dumps(index, indent=2) + "\n")
    print("wrote", len(index), "materials to", OUT)


if __name__ == "__main__":
    main()
