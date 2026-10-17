"""What the user attaches to a design prompt: images (photos, sketches, screenshots) and links.

Images arrive as data URLs and go to the model as-is. Links are fetched here, server side, so the
model sees the page text (or the picture, for an image link). Fetching a URL the user typed is an
SSRF risk, so only public http(s) addresses are allowed, every redirect hop is checked again, and
reads are capped in size and time.
"""

from __future__ import annotations

import base64
import html
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

MAX_IMAGES = 4
MAX_IMAGE_CHARS = 3_000_000  # base64 data URL length, ~2.2 MB of image
MAX_LINKS = 5
MAX_URL_CHARS = 2000
FETCH_TIMEOUT_S = 8
MAX_FETCH_BYTES = 3_000_000
MAX_PAGE_TEXT = 6000
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=]+)$")


class AttachmentError(ValueError):
    pass


@dataclass
class Image:
    media_type: str
    data: str  # base64

    @property
    def data_url(self) -> str:
        return f"data:{self.media_type};base64,{self.data}"


@dataclass
class Link:
    url: str
    text: str | None = None  # page text, when it was a page
    image: Image | None = None  # when the link was an image
    error: str | None = None  # why it couldn't be read


def parse_images(raw) -> list[Image]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        raise AttachmentError(f"Attach at most {MAX_IMAGES} images.")
    images = []
    for item in raw:
        m = DATA_URL.match(item) if isinstance(item, str) and len(item) <= MAX_IMAGE_CHARS else None
        if not m:
            raise AttachmentError("Images must be PNG, JPEG, WebP or GIF, up to about 2 MB each.")
        images.append(Image(m.group(1), m.group(2)))
    return images


def parse_links(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_LINKS:
        raise AttachmentError(f"Add at most {MAX_LINKS} links.")
    links = []
    for url in raw:
        if not isinstance(url, str) or len(url) > MAX_URL_CHARS or urlparse(url).scheme not in ("http", "https") or not urlparse(url).hostname:
            raise AttachmentError("Links must be http:// or https:// web addresses.")
        links.append(url)
    return links


def check_public(url: str) -> None:
    """Refuses anything but http(s) to a public address (no localhost, private networks, metadata IPs)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AttachmentError("only http(s) links")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        raise AttachmentError("couldn't find that host") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise AttachmentError("that address isn't on the public internet")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirects)


def page_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", markup)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", markup))
    text = re.sub(r"\s+", " ", text).strip()
    if title:
        text = f"Title: {html.unescape(title.group(1)).strip()}\n{text}"
    return text[:MAX_PAGE_TEXT]


def fetch_link(url: str) -> Link:
    try:
        check_public(url)
        req = urllib.request.Request(url, headers={"User-Agent": "PhysicalStudio/1.0 (design assistant)"})
        with _opener.open(req, timeout=FETCH_TIMEOUT_S) as res:
            kind = res.headers.get_content_type()
            body = res.read(MAX_FETCH_BYTES + 1)
        if len(body) > MAX_FETCH_BYTES:
            return Link(url, error="too large to read")
        if kind in IMAGE_TYPES:
            return Link(url, image=Image(kind, base64.b64encode(body).decode()))
        if kind in ("text/html", "application/xhtml+xml", "text/plain"):
            charset = res.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            return Link(url, text=page_text(text) if kind != "text/plain" else text[:MAX_PAGE_TEXT])
        return Link(url, error=f"can't read {kind} files")
    except AttachmentError as e:
        return Link(url, error=str(e))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return Link(url, error=f"couldn't fetch it ({getattr(e, 'reason', e)})")
