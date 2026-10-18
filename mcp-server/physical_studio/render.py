"""Software renderer for render_preview: orthographic, z-buffered, flat shaded, outlined edges.

No OpenGL needed, so it works on headless servers. Output is a PNG with each visible
placement labelled by its id and a 10 mm scale bar, so Claude can check its own design.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .geometry import BuiltDesign

VIEWS = {
    # direction from the design towards the camera, design frame (+Z up)
    "iso": (-1.0, -1.0, 0.9),  # front-left-top: the -x wall (USB side) and the front are visible
    "iso_back": (1.0, 1.0, 0.9),
    "iso_right": (1.0, -1.0, 0.9),  # front-right-top
    "iso_left_back": (-1.0, 1.0, 0.9),
    "below": (-1.0, -1.0, -0.8),  # front-left, from underneath: parts under a plate (a pinion under a cart)
    "top": (0.0, 0.0, 1.0),
    "front": (0.0, -1.0, 0.0),
    "back": (0.0, 1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
}
BACKGROUND = (236, 233, 228)
EDGE = np.array([40, 44, 52], dtype=float)
SUPERSAMPLE = 2


def hex_rgb(color: str) -> np.ndarray:
    c = color.lstrip("#")
    return np.array([int(c[i : i + 2], 16) for i in (0, 2, 4)], dtype=float)


def camera_basis(view: str):
    if view not in VIEWS:
        raise ValueError(f"view must be one of {sorted(VIEWS)}")
    back = np.array(VIEWS[view], dtype=float)
    back /= np.linalg.norm(back)
    forward = -back
    up_hint = np.array([0.0, 1.0, 0.0]) if abs(back[2]) > 0.99 else np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def render(
    built: BuiltDesign,
    view: str = "iso",
    visible: set[str] | None = None,
    offsets: dict[str, np.ndarray] | None = None,
    highlight: set[str] | None = None,
    size: tuple[int, int] = (900, 680),
    labels: bool = True,
    stats: dict | None = None,
    textures: dict | None = None,
    focus: set[str] | None = None,
) -> bytes:
    """stats, when given, gets "highlight_px": how many pixels of the highlighted pieces are visible, and
    "wires": each visible wire's centre line in output pixels. textures: piece id -> a textured quad in the
    piece's frame (export.top_face: a board's top photo), drawn on the piece. focus: piece ids to frame in
    a close-up instead of fitting the whole build."""
    right, up, forward = camera_basis(view)
    offsets = offsets or {}
    highlight = highlight or set()
    textures = textures or {}
    ids = [pid for pid in built.pieces if visible is None or pid in visible]
    if not ids:
        raise ValueError("nothing to render")

    tris, owners, tex_of, images, uvs = [], [], [], [], []
    for k, pid in enumerate(ids):
        piece = built.pieces[pid]
        quad = textures.get(pid)
        for mesh, tex in ((piece.local_mesh(tolerance=0.1, angular=0.5), -1), (quad, len(images))):
            if mesh is None:
                continue
            v = mesh.vertices @ piece.matrix[:3, :3].T + piece.matrix[:3, 3] + offsets.get(pid, 0)
            tris.append(v[mesh.faces])
            owners.append(np.full(len(mesh.faces), k))
            tex_of.append(np.full(len(mesh.faces), tex))
            if tex >= 0:
                images.append(np.asarray(mesh.visual.material.baseColorTexture.convert("RGB"), dtype=float))
                uvs.append(np.asarray(mesh.visual.uv, dtype=float)[mesh.faces])
    tris = np.concatenate(tris)  # (T, 3, 3)
    owners = np.concatenate(owners)
    tex_of = np.concatenate(tex_of)
    tex_tri = np.cumsum(tex_of >= 0) - 1  # triangle -> its row in the uv list

    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.where(lengths == 0, 1, lengths)
    normals[(normals @ forward) > 0] *= -1  # two-sided: always face the camera

    sx, sy, depth = tris @ right, tris @ up, tris @ forward
    W, H = size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE
    margin = 0.08
    span_x, span_y = sx.max() - sx.min(), sy.max() - sy.min()
    scale = min(W * (1 - 2 * margin) / max(span_x, 1e-6), H * (1 - 2 * margin) / max(span_y, 1e-6))
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
    keep = [k for k, pid in enumerate(ids) if focus and pid in focus]
    if keep:
        # Close-up: frame these pieces with room around them (at least a third of the whole build's
        # width, so the builder can still tell where on the machine this is). The rest is cropped.
        sel = np.isin(owners, keep)
        fx, fy = sx[sel], sy[sel]
        fw = max(1.5 * (fx.max() - fx.min()), span_x / 3)
        fh = max(1.5 * (fy.max() - fy.min()), span_y / 3)
        scale = min(W * (1 - 2 * margin) / max(fw, 1e-6), H * (1 - 2 * margin) / max(fh, 1e-6))
        cx, cy = (fx.max() + fx.min()) / 2, (fy.max() + fy.min()) / 2
    px = (sx - cx) * scale + W / 2
    py = H / 2 - (sy - cy) * scale

    zbuf = np.full((H, W), np.inf)
    owner_buf = np.full((H, W), -1, dtype=np.int64)
    normal_buf = np.zeros((H, W, 3))
    tri_buf = np.full((H, W), -1, dtype=np.int64)
    bary_buf = np.zeros((H, W, 2))

    for t in range(len(tris)):
        x0, x1, x2 = px[t]
        y0, y1, y2 = py[t]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        minx, maxx = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), W - 1)
        miny, maxy = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), H - 1)
        if minx > maxx or miny > maxy:
            continue
        X, Y = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        w0 = ((x1 - X) * (y2 - Y) - (x2 - X) * (y1 - Y)) / area
        w1 = ((x2 - X) * (y0 - Y) - (x0 - X) * (y2 - Y)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * depth[t, 0] + w1 * depth[t, 1] + w2 * depth[t, 2]
        window = (slice(miny, maxy + 1), slice(minx, maxx + 1))
        closer = inside & (z < zbuf[window])
        zbuf[window][closer] = z[closer]
        owner_buf[window][closer] = owners[t]
        normal_buf[window][closer] = normals[t]
        if tex_of[t] >= 0:
            tri_buf[window][closer] = t
            bary_buf[window][closer] = np.stack([w0, w1], axis=-1)[closer]
        else:
            tri_buf[window][closer] = -1

    # Flat shading: key light from over the camera's left shoulder, plus ambient.
    light = -forward + 0.6 * up - 0.4 * right
    light /= np.linalg.norm(light)
    base = np.array([hex_rgb(built.pieces[pid].color) for pid in ids])
    hit = owner_buf >= 0
    shade = 0.45 + 0.55 * np.clip(normal_buf @ light, 0, 1)
    image = np.empty((H, W, 3))
    image[:] = BACKGROUND
    image[hit] = base[owner_buf[hit]] * shade[hit, None]
    textured = tri_buf >= 0
    if textured.any():
        t = tri_buf[textured]
        w0, w1 = bary_buf[textured, 0], bary_buf[textured, 1]
        uv_tri = np.concatenate(uvs)[tex_tri[t]]
        uv = w0[:, None] * uv_tri[:, 0] + w1[:, None] * uv_tri[:, 1] + (1 - w0 - w1)[:, None] * uv_tri[:, 2]
        colour = np.empty((len(t), 3))
        for i, img in enumerate(images):
            sel = tex_of[t] == i
            h, w = img.shape[:2]
            x = np.clip((uv[sel, 0] * w).astype(int), 0, w - 1)
            y = np.clip(((1 - uv[sel, 1]) * h).astype(int), 0, h - 1)  # uv origin bottom-left, rows top-down
            colour[sel] = img[y, x]
        image[textured] = colour * (0.75 + 0.25 * shade[textured, None])
    if stats is not None:
        lit = [k for k, pid in enumerate(ids) if pid in highlight]
        stats["highlight_px"] = int(np.isin(owner_buf, lit).sum()) if lit else 0
        stats["wires"] = {}
        for pid in ids:
            path = built.pieces[pid].path
            if path is None:
                continue
            p = path + offsets.get(pid, 0)
            x = ((p @ right - cx) * scale + W / 2) / SUPERSAMPLE
            y = (H / 2 - (p @ up - cy) * scale) / SUPERSAMPLE
            stats["wires"][pid] = np.round(np.stack([x, y], axis=1)[:: max(1, len(p) // 16)].tolist() + [[x[-1], y[-1]]], 1).tolist()
    for k, pid in enumerate(ids):
        if pid in highlight:
            mask = owner_buf == k
            image[mask] = image[mask] * 0.55 + np.array([38, 198, 218]) * 0.45

    # Outlines where the part changes or the surface turns a corner (not along wires: a tube's
    # facets would all count as corners).
    smooth = np.array([built.pieces[pid].kind == "wire" for pid in ids])
    on_smooth = hit & smooth[np.where(hit, owner_buf, 0)]
    edges = np.zeros((H, W), dtype=bool)
    # A depth jump counts as an edge when it's more than a slanted surface's change across a few pixels:
    # 0.4 mm on a small enclosure, more on a half-metre machine (else every sloped face turns to outline).
    jump = max(0.4, 3.0 / scale)
    for axis in (0, 1):
        o2 = np.roll(owner_buf, -1, axis=axis)
        n2 = np.roll(normal_buf, -1, axis=axis)
        z2 = np.roll(zbuf, -1, axis=axis)
        step_edge = np.abs(np.where(hit, zbuf, 0) - np.where(o2 >= 0, z2, 0)) > jump  # depth jump, mm
        corner = ((normal_buf * n2).sum(axis=2) < 0.85) & ~on_smooth
        crease = (owner_buf != o2) | corner | (step_edge & ~on_smooth)
        crease &= hit | (o2 >= 0)
        edges |= crease
    image[edges] = EDGE

    img = Image.fromarray(image.clip(0, 255).astype(np.uint8)).resize(size, Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=13)

    if labels:
        for k, pid in enumerate(ids):
            if smooth[k]:
                continue  # wires: colour identifies them, labels would bury the parts
            mask = owner_buf == k
            if mask.sum() < 30 * SUPERSAMPLE**2:
                continue  # hidden or tiny
            ys, xs = np.nonzero(mask)
            nearest = np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2)  # stay on this piece
            x, y = xs[nearest] / SUPERSAMPLE, ys[nearest] / SUPERSAMPLE
            box = draw.textbbox((x, y), pid, font=font, anchor="mm")
            draw.rectangle((box[0] - 4, box[1] - 2, box[2] + 4, box[3] + 2), fill=(31, 41, 51))
            draw.text((x, y), pid, font=font, fill=(255, 255, 255), anchor="mm")

    bar = 10 * scale / SUPERSAMPLE
    x0, y0 = 20, size[1] - 24
    draw.line((x0, y0, x0 + bar, y0), fill=(31, 41, 51), width=3)
    draw.text((x0 + bar + 8, y0), "10 mm", font=font, fill=(31, 41, 51), anchor="lm")
    draw.text((size[0] - 16, size[1] - 24), f"view: {view}", font=font, fill=(90, 98, 110), anchor="rm")

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
