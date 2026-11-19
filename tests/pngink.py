"""Tinta real de um SVG renderizado pelo resvg: decodifica o PNG (RGBA 8 bits) sem dependências."""

from __future__ import annotations

import struct
import zlib

import resvg_py

from linky_agents.render.brand import assets_dir


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def decode(png: bytes) -> tuple[int, int, list[bytes]]:
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(png):
        (n,) = struct.unpack(">I", png[pos : pos + 4])
        kind, data = png[pos + 4 : pos + 8], png[pos + 8 : pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", data[:10])
            assert (depth, ctype) == (8, 6), "esperado RGBA 8 bits"
        elif kind == b"IDAT":
            idat += data
        pos += 12 + n
    raw, stride, rows, prev, i = zlib.decompress(idat), w * 4, [], bytearray(w * 4), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1 : i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            c = prev[x - 4] if x >= 4 else 0
            line[x] = (
                line[x] + (0, a, prev[x], (a + prev[x]) // 2, _paeth(a, prev[x], c))[f]
            ) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, rows


def render(body: str, width: int = 1080, height: int = 400) -> tuple[int, int, list[bytes]]:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">{body}</svg>'
    png = resvg_py.svg_to_bytes(
        svg_string=svg, font_dirs=[str(assets_dir() / "fonts")], skip_system_fonts=True
    )
    return decode(bytes(png))


def ink_bbox(body: str, width: int = 1080, height: int = 400) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) da tinta (alfa > 0), com x1 e y1 exclusivos."""
    w, _, rows = render(body, width, height)
    xs, ys = [], []
    for y, r in enumerate(rows):
        row = [x for x in range(w) if r[4 * x + 3]]
        if row:
            xs += (row[0], row[-1])
            ys.append(y)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def ink_pixels(body: str, width: int = 1080, height: int = 400) -> set[tuple[int, int]]:
    w, _, rows = render(body, width, height)
    return {(x, y) for y, r in enumerate(rows) for x in range(w) if r[4 * x + 3] > 64}
