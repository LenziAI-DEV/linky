"""Medição de texto com as métricas reais da fonte, marcação de destaque e quebra de linha."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Literal

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from linky_agents.render.brand import Font

Style = Literal["plain", "accent", "soft", "strike", "break"]

# **texto** = destaque violeta · ==texto== = destaque lilás · ~~texto~~ = tachado (lilás + traço)
# |  = quebra de linha obrigatória (controle do ritmo da frase)
_MARKUP = re.compile(r"\*\*(.+?)\*\*|==(.+?)==|~~(.+?)~~|(\|)")
BREAK = "|"


class LayoutError(ValueError):
    """O conteúdo não cabe no layout, mesmo no menor tamanho permitido."""


@cache
def _metrics(path: str) -> tuple[dict[int, str], object, int]:
    font = TTFont(path)
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


@cache
def _hb_font(path: str) -> tuple[hb.Font, int]:
    face = hb.Face(hb.Blob.from_file_path(path))
    return hb.Font(face), face.upem


@cache
def _shape(text: str, path: str) -> tuple[tuple[tuple[int, int, int], ...], int, int]:
    """Glyphs posicionados como o resvg desenha: GSUB (ligaduras) e GPOS (kerning).

    Devolve ((glyph_id, x em unidades da fonte, ordem do grupo), ...), o avanço total em
    unidades e o número de grupos (clusters), sobre os quais o espaçamento entre letras vale.
    """
    font, _ = _hb_font(path)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {})
    placed, x, seen = [], 0, []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        if not seen or seen[-1] != info.cluster:
            seen.append(info.cluster)
        placed.append((info.codepoint, x + pos.x_offset, len(seen) - 1))
        x += pos.x_advance
    return tuple(placed), x, len(seen)


def measure(text: str, font: Font, size: float, tracking: float = 0.0) -> float:
    """Largura de avanço do texto como o resvg o desenha (com kerning e ligaduras)."""
    if not text:
        return 0.0
    _, advance, clusters = _shape(text, str(font.path))
    _, upm = _hb_font(str(font.path))
    return advance * size / upm + tracking * max(clusters - 1, 0)


@cache
def _glyph_y_bounds(path: str) -> tuple[dict[int, tuple[float, float]], int]:
    """yMin/yMax de cada glyph (em unidades da fonte), via tabela glyf."""
    font = TTFont(path)
    glyf = font["glyf"]
    bounds = {}
    for code, name in font.getBestCmap().items():
        g = glyf[name]
        if g.numberOfContours != 0:
            g.recalcBounds(glyf)
            bounds[code] = (g.yMin, g.yMax)
    return bounds, font["head"].unitsPerEm


def ink_extent(text: str, font: Font, size: float) -> tuple[float, float]:
    """Altura máxima acima e profundidade máxima abaixo da linha de base (px, positivos).

    Usa o desenho real dos glyphs: acentos de maiúsculas (Õ, É) sobem acima da altura de
    caixa alta e a cedilha (Ç) desce abaixo da linha de base.
    """
    bounds, upm = _glyph_y_bounds(str(font.path))
    ys = [bounds[ord(ch)] for ch in text if ord(ch) in bounds]
    if not ys:
        return 0.0, 0.0
    return max(y for _, y in ys) * size / upm, max(-min(y for y, _ in ys), 0) * size / upm


@cache
def _glyph_boxes(path: str) -> dict[int, tuple[int, int, int, int]]:
    """(xMin, yMin, xMax, yMax) de cada glyph com tinta, por ID de glyph."""
    font = TTFont(path)
    glyf = font["glyf"]
    boxes = {}
    for gid, name in enumerate(font.getGlyphOrder()):
        g = glyf[name]
        if g.numberOfContours != 0:
            g.recalcBounds(glyf)
            boxes[gid] = (g.xMin, g.yMin, g.xMax, g.yMax)
    return boxes


def glyph_ink_boxes(
    text: str, font: Font, size: float, tracking: float = 0.0, anchor: str = "start"
) -> list[tuple[float, float, float, float]]:
    """Caixa de tinta de cada glyph (x0, y0, x1, y1) em px, relativa à origem do texto.

    y cresce para baixo, como no SVG: y0 negativo fica acima da linha de base. A âncora
    segue o `text-anchor` do SVG (start, middle, end).
    """
    if not text:
        return []
    path = str(font.path)
    placed, _, _ = _shape(text, path)
    _, upm = _hb_font(path)
    boxes = _glyph_boxes(path)
    scale = size / upm
    shift = {"start": 0.0, "middle": -0.5, "end": -1.0}[anchor] * measure(
        text, font, size, tracking
    )
    out = []
    for gid, x, cluster in placed:
        if gid in boxes:
            x0, y0, x1, y1 = boxes[gid]
            ox = shift + x * scale + tracking * cluster
            out.append((ox + x0 * scale, -y1 * scale, ox + x1 * scale, -y0 * scale))
    return out


def ink_box(
    text: str, font: Font, size: float, tracking: float = 0.0, anchor: str = "start"
) -> tuple[float, float, float, float]:
    """Caixa de tinta do texto inteiro (ver glyph_ink_boxes). Texto sem tinta: caixa vazia."""
    boxes = glyph_ink_boxes(text, font, size, tracking, anchor)
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def unsupported_chars(text: str, font: Font) -> set[str]:
    cmap, _, _ = _metrics(str(font.path))
    return {ch for ch in text if not ch.isspace() and ord(ch) not in cmap}


@dataclass(frozen=True)
class Unit:
    """Uma palavra simples ou um trecho destacado (que nunca é quebrado)."""

    text: str
    style: Style


def parse_markup(markup: str) -> list[Unit]:
    units: list[Unit] = []
    pos = 0
    for m in _MARKUP.finditer(markup):
        units += [Unit(w, "plain") for w in markup[pos : m.start()].split()]
        accent, soft, strike, brk = m.groups()
        if accent is not None:
            units.append(Unit(accent.strip(), "accent"))
        elif soft is not None:
            units.append(Unit(soft.strip(), "soft"))
        elif strike is not None:
            units.append(Unit(strike.strip(), "strike"))
        elif brk is not None:
            units.append(Unit(BREAK, "break"))
        pos = m.end()
    units += [Unit(w, "plain") for w in markup[pos:].split()]
    if any(marker in u.text for u in units for marker in ("**", "==", "~~")):
        raise ValueError(f"Marcação de destaque mal formada: {markup!r}")
    return units


def plain_text(markup: str) -> str:
    return " ".join(u.text for u in parse_markup(markup) if u.style != "break")


def wrap_units(
    units: list[Unit], font: Font, size: float, max_width: float, pad: float, tracking: float
) -> list[list[Unit]] | None:
    """Quebra gulosa. Retorna None se algum trecho sozinho não couber na largura."""
    space = measure(" ", font, size)
    lines: list[list[Unit]] = [[]]
    width = 0.0
    for u in units:
        if u.style == "break":
            if lines[-1]:
                lines.append([])
                width = 0.0
            continue
        w = unit_width(u, font, size, pad, tracking)
        if w > max_width:
            return None
        extra = w if not lines[-1] else space + w
        if lines[-1] and width + extra > max_width:
            lines.append([u])
            width = w
        else:
            lines[-1].append(u)
            width += extra
    return [line for line in lines if line]


def unit_width(u: Unit, font: Font, size: float, pad: float, tracking: float) -> float:
    w = measure(u.text, font, size, tracking)
    return w + (2 * pad if u.style != "plain" else 0)


def line_width(line: list[Unit], font: Font, size: float, pad: float, tracking: float) -> float:
    space = measure(" ", font, size)
    return sum(unit_width(u, font, size, pad, tracking) for u in line) + space * (len(line) - 1)


def wrap_text(text: str, font: Font, size: float, max_width: float) -> list[str] | None:
    """Quebra de texto corrido (sem destaques). None se uma palavra não couber."""
    lines = wrap_units([Unit(w, "plain") for w in text.split()], font, size, max_width, 0, 0)
    return None if lines is None else [" ".join(u.text for u in line) for line in lines]


def fit_text(
    text: str, font: Font, sizes: list[float], max_width: float, max_lines: int
) -> tuple[float, list[str]]:
    """Maior tamanho da lista em que o texto cabe em até max_lines linhas."""
    for size in sizes:
        lines = wrap_text(text, font, size, max_width)
        if lines is not None and len(lines) <= max_lines:
            return size, lines
    raise LayoutError(f"Texto não cabe ({max_lines} linhas, {max_width:.0f}px): {text!r}")
