"""Top-face pictures for parts, from the library's optional "appearance.top" field.

    "top": {"image": "teensy-41.top.jpg"}             a photo of the top face next to the part's JSON
    "top": {"pcb": {"mask": "#f4f4f0", "chips": [...]}}  drawn: solder mask, holes, pads, chips, labels

The picture covers the body's top face: its left edge is the part's x = 0, its top edge y = size[1].
A drawn PCB puts a pad on every pin and a hole on every mounting hole, so it matches the part's data.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PX_PER_MM = 24
MAX_SIDE = 1024


def top_image(part: dict, parts_dir: Path) -> Image.Image | None:
    top = (part.get("appearance") or {}).get("top")
    if not top:
        return None
    if top.get("image"):
        path = parts_dir / top["image"]
        return Image.open(path).convert("RGB") if path.exists() else None
    if top.get("pcb") is not None:
        return pcb_image(part, top["pcb"])
    return None


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _light(hex_color: str) -> bool:
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i : i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


def pcb_image(part: dict, pcb: dict) -> Image.Image:
    sx, sy = part["body"]["size"][:2]
    scale = min(PX_PER_MM, MAX_SIDE / max(sx, sy))
    w, h = max(1, round(sx * scale)), max(1, round(sy * scale))
    mask = pcb.get("mask", "#1e6b3a")
    silk = pcb.get("silk", "#222222" if _light(mask) else "#f2f2f2")
    img = Image.new("RGB", (w, h), mask)
    d = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        return x * scale, (sy - y) * scale  # image y runs down, part y runs up

    for hole in part.get("mounting_holes", []):
        x, y = px(*hole["position"][:2])
        r = hole["diameter"] / 2 * scale
        d.ellipse([x - r - 0.6 * scale, y - r - 0.6 * scale, x + r + 0.6 * scale, y + r + 0.6 * scale], fill="#c9c9c4")
        d.ellipse([x - r, y - r, x + r, y + r], fill="#3a3a3a")
    label_font = _font(max(8, round(1.1 * scale)))
    for pin in part.get("pins", []):
        x, y = px(*pin["position"][:2])
        r = 0.8 * scale
        d.ellipse([x - r, y - r, x + r, y + r], fill="#d8d8d2", outline="#9a9a94")
        d.ellipse([x - 0.4 * scale, y - 0.4 * scale, x + 0.4 * scale, y + 0.4 * scale], fill="#2a2a2a")
        label = pin.get("label", pin["id"]).split(" ")[0]
        d.text((x, y - 1.2 * scale), label, fill=silk, font=label_font, anchor="md")
    for chip in pcb.get("chips", []):
        (cx, cy), (cw, ch) = chip["at"], chip["size"]
        x0, y0 = px(cx - cw / 2, cy + ch / 2)
        x1, y1 = px(cx + cw / 2, cy - ch / 2)
        d.rectangle([x0, y0, x1, y1], fill=chip.get("color", "#1b1b1b"))
        if chip.get("label"):
            f = _font(max(8, round(min(ch, cw / max(1, len(chip["label"])) * 1.6) * 0.5 * scale)))
            d.text(((x0 + x1) / 2, (y0 + y1) / 2), chip["label"], fill="#9a9a9a", font=f, anchor="mm")
    if pcb.get("title"):
        x, y = px(*pcb.get("title_at", [sx / 2, 2.5]))
        d.text((x, y), pcb["title"], fill=silk, font=_font(max(8, round(1.4 * scale))), anchor="mm")
    return img
