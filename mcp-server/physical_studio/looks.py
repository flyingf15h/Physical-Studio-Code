"""Part looks found online: set_part_look fetches a product photo for a part's top face.

The designing AI looks a part up (manufacturer or shop page), then passes the URL of a flat top-view
photo. The server downloads it with care, since anyone with a key can ask it to: http(s) only, no
private or local addresses (checked on every redirect), at most 4 MB, and it must decode as an image.
The photo is trimmed to the part (background removed) and kept with the design, not the library.
"""

from __future__ import annotations

import io
import ipaddress
import socket
import urllib.parse
import urllib.request

from PIL import Image, ImageChops

MAX_BYTES = 4 * 1024 * 1024
MAX_SIDE = 1024
TIMEOUT_S = 10
MAX_REDIRECTS = 3


class LookError(ValueError):
    pass


def _check_host(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LookError("image_url must be an http(s) URL")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise LookError(f"can't resolve {parts.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise LookError("image_url must point at a public address")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # followed by hand in fetch_image, so each hop's host is checked


_opener = urllib.request.build_opener(_NoRedirect)


def fetch_image(url: str) -> Image.Image:
    for _ in range(MAX_REDIRECTS + 1):
        _check_host(url)
        req = urllib.request.Request(url, headers={"User-Agent": "PhysicalStudio/1.0 (part photo lookup)"})
        try:
            res = _opener.open(req, timeout=TIMEOUT_S)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise LookError(f"image download failed: HTTP {e.code}") from e
        except OSError as e:
            raise LookError(f"image download failed: {e}") from e
        data = res.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise LookError("image is larger than 4 MB")
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as e:
            raise LookError("that URL isn't an image (use the photo file itself, e.g. .jpg/.png)") from e
        return trim(img.convert("RGB"))
    raise LookError("too many redirects")


def trim(img: Image.Image, tolerance: int = 40) -> Image.Image:
    """Crop away a plain background (the colour of the top-left corner), then cap the size."""
    background = Image.new("RGB", img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, background).convert("L").point(lambda v: 255 if v > tolerance else 0)
    box = diff.getbbox()
    if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.2 * img.size[0] * img.size[1]:
        img = img.crop(box)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img
