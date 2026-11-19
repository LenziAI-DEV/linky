"""Os 3 layouts da identidade visual (ver docs/brand/guia-visual.md).

Cada layout recebe um spec validado e devolve SVG determinístico. Tamanhos de fonte se ajustam
dentro de limites. Se o conteúdo não couber, levanta LayoutError (nunca corta texto em silêncio).
"""

from __future__ import annotations

import base64
import itertools
from dataclasses import dataclass, field
from typing import Literal
from xml.sax.saxutils import escape

import resvg_py

from linky_agents.render.brand import Brand, Font, assets_dir, load_brand
from linky_agents.render.spec import ContrasteSpec, EscadaSpec, TeseSpec
from linky_agents.render.text import (
    LayoutError,
    Unit,
    fit_text,
    glyph_ink_boxes,
    ink_box,
    line_width,
    measure,
    parse_markup,
    unit_width,
    unsupported_chars,
    wrap_units,
)

Spec = EscadaSpec | ContrasteSpec | TeseSpec


# ---------------------------------------------------------------------------- primitivas
def _attr(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def text(x, y, s, font: Font, size, fill, anchor="start", tracking=0.0) -> str:
    return (
        f'<text x="{_attr(x)}" y="{_attr(y)}" font-family="{font.family}" '
        f'font-weight="{font.weight}" font-size="{_attr(size)}" fill="{fill}" '
        f'text-anchor="{anchor}" letter-spacing="{_attr(tracking)}">{escape(s)}</text>'
    )


def rect(x, y, w, h, fill, rx=0, stroke=None, sw=0) -> str:
    s = f' stroke="{stroke}" stroke-width="{_attr(sw)}"' if stroke else ""
    return (
        f'<rect x="{_attr(x)}" y="{_attr(y)}" width="{_attr(w)}" height="{_attr(h)}" '
        f'rx="{_attr(rx)}" fill="{fill}"{s}/>'
    )


def halftone(x0, y0, cols, rows, step, color, direction, rmax) -> str:
    """Retícula ancorada: pontos maiores do lado da estrutura indicada por `direction`."""
    dots = []
    for i in range(cols):
        for j in range(rows):
            k = {
                "right": i / max(cols - 1, 1),
                "down": j / max(rows - 1, 1),
                "up": 1 - j / max(rows - 1, 1),
            }[direction]
            r = rmax * k**1.4
            if r > 0.6:
                dots.append(
                    f'<circle cx="{_attr(x0 + i * step)}" cy="{_attr(y0 + j * step)}" r="{r:.2f}"/>'
                )
    return f'<g fill="{color}">{"".join(dots)}</g>'


def check_icon(x, y, s, box, mark) -> str:
    return rect(x, y, s, s, box, rx=4) + (
        f'<path d="M{_attr(x + s * 0.22)},{_attr(y + s * 0.52)} L{_attr(x + s * 0.43)},'
        f'{_attr(y + s * 0.72)} L{_attr(x + s * 0.80)},{_attr(y + s * 0.30)}" fill="none" '
        f'stroke="{mark}" stroke-width="{_attr(s * 0.14)}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )


def _check_glyphs(spec: Spec, b: Brand) -> None:
    fields = [spec.headline, spec.source]
    fields += [spec.company.name] if spec.company else []
    if isinstance(spec, EscadaSpec):
        fields += [spec.context or "", spec.milestone or ""]
        fields += [s.title for s in spec.steps] + [s.text for s in spec.steps]
    elif isinstance(spec, ContrasteSpec):
        fields += spec.items
    else:
        fields += [t.title for t in spec.equation] + [t.subtitle for t in spec.equation]
    missing = set()
    for f in fields:
        missing |= unsupported_chars(f.upper(), b.f("headline")) | unsupported_chars(f, b.f("body"))
    missing -= {"*", "=", "~"}
    if missing:
        raise LayoutError(f"Caracteres sem suporte na fonte: {sorted(missing)}")


# ---------------------------------------------------------------------------- manchete
# Folga mínima entre a tinta de uma linha (acento, cedilha) e o bloco de destaque vizinho
_BOX_CLEARANCE = 0.04
# O bloco de destaque se estende 0,10 × tamanho acima da caixa alta e abaixo da linha de base
_BOX_BLEED = 0.10


@dataclass
class Headline:
    size: float
    lines: list[list[Unit]]
    pad: float
    gaps: list[float] = field(default_factory=list)  # distância entre linhas de base, por par
    # por linha: quanto os blocos de destaque sobem acima e descem abaixo da linha de base
    boxes: list[tuple[float, float]] = field(default_factory=list)
    align: str = "start"

    @property
    def cap(self) -> float:
        return self.size * 0.70

    def lh(self, b: Brand) -> float:
        return self.size * b.line_height

    def height(self, b: Brand) -> float:
        return self.cap + sum(self.gaps)


@dataclass(frozen=True)
class _Ink:
    """Algo desenhado numa linha da manchete: um glyph solto ou um bloco de destaque."""

    x0: float
    x1: float
    above: float  # px acima da linha de base
    below: float  # px abaixo da linha de base
    boxed: bool


def _box_extents(line: list[Unit], font: Font, size: float, tracking: float) -> tuple[float, float]:
    """Altura dos blocos da linha: o padrão da marca, crescendo para cobrir a tinta da própria
    palavra (acento de Ê ou Á em cima, cedilha ou rabo do Q embaixo) com folga."""
    cap, bleed, clear = size * 0.70, size * _BOX_BLEED, size * _BOX_CLEARANCE
    above, below = cap + bleed, bleed
    for u in line:
        if u.style != "plain":
            x0, y0, x1, y1 = ink_box(u.text, font, size, tracking)
            above, below = max(above, -y0 + clear), max(below, y1 + clear)
    return above, below


def _line_inks(
    line: list[Unit],
    font: Font,
    size: float,
    pad: float,
    tracking: float,
    align: str,
    box: tuple[float, float],
) -> list[_Ink]:
    lw = line_width(line, font, size, pad, tracking)
    cx = -lw / 2 if align == "center" else 0.0
    space = measure(" ", font, size)
    out = []
    for u in line:
        w = unit_width(u, font, size, pad, tracking)
        if u.style == "plain":
            for gx0, gy0, gx1, gy1 in glyph_ink_boxes(u.text, font, size, tracking):
                out.append(_Ink(cx + gx0, cx + gx1, -gy0, gy1, False))
        else:
            out.append(_Ink(cx, cx + w, box[0], box[1], True))
        cx += w + space
    return out


def _line_gaps(
    lines: list[list[Unit]],
    font: Font,
    size: float,
    lh: float,
    pad: float,
    tracking: float,
    align: str,
    boxes: list[tuple[float, float]],
) -> list[float]:
    """Entrelinha de cada par: a da marca, aumentada só onde a tinta encostaria.

    A entrelinha da marca (0,92) é apertada de propósito. Medimos a tinta real, glyph a
    glyph, e só onde as duas linhas se sobrepõem na horizontal: o til de "FUNÇÕES" contra o
    bloco de cima, a cedilha ou o rabo do Q contra o bloco de baixo, e também tinta contra
    tinta entre linhas sem bloco. Blocos contra blocos seguem a entrelinha da marca.
    """
    clear = size * _BOX_CLEARANCE
    std_above, std_below = size * (0.70 + _BOX_BLEED), size * _BOX_BLEED
    inks = [
        _line_inks(line, font, size, pad, tracking, align, box)
        for line, box in zip(lines, boxes, strict=True)
    ]
    gaps = []
    for upper, lower in itertools.pairwise(inks):
        need = lh
        for u in upper:
            for low in lower:
                if u.x0 < low.x1 + clear and low.x0 < u.x1 + clear:
                    # um bloco que cresceu (para cobrir acento ou cedilha) afasta a linha
                    # vizinha na mesma medida, preservando o respiro natural da marca
                    if u.boxed:
                        need = max(need, lh + u.below - std_below)
                    if low.boxed:
                        need = max(need, lh + low.above - std_above)
                    pad = 0.0 if u.boxed and low.boxed else clear
                    need = max(need, u.below + low.above + pad)
        gaps.append(need)
    return gaps


def fit_headline(
    markup: str,
    b: Brand,
    max_width: float,
    max_height: float,
    max_lines: int,
    max_size: float | None = None,
    align: str = "start",
) -> Headline:
    units = [Unit(u.text.upper(), u.style) for u in parse_markup(markup)]
    font = b.f("headline")
    size = float(min(max_size or b.headline_max, b.headline_max))
    while size >= b.headline_min:
        pad = size * 0.11
        lines = wrap_units(units, font, size, max_width, pad, b.tracking)
        if lines is not None and len(lines) <= max_lines:
            boxes = [_box_extents(line, font, size, b.tracking) for line in lines]
            gaps = _line_gaps(
                lines, font, size, size * b.line_height, pad, b.tracking, align, boxes
            )
            h = Headline(size, lines, pad, gaps, boxes, align)
            if h.height(b) <= max_height:
                return h
        size -= 4
    raise LayoutError(f"Manchete não cabe no layout: {markup!r}")


@dataclass(frozen=True)
class HeadlinePart:
    """Uma peça desenhada da manchete, com o papel de cor (plain, accent_box, strike...)."""

    kind: Literal["box", "text", "strike"]
    role: str
    x: float
    y: float  # topo da caixa ou linha de base do texto
    w: float = 0.0
    h: float = 0.0
    text: str = ""


def headline_parts(h: Headline, b: Brand, x: float, top: float, align: str) -> list[HeadlinePart]:
    """Geometria da manchete: blocos primeiro, texto por cima, tachados por último."""
    font = b.f("headline")
    boxes, glyphs, strikes = [], [], []
    space = measure(" ", font, h.size)
    baseline = top + h.cap
    for i, line in enumerate(h.lines):
        lw = line_width(line, font, h.size, h.pad, b.tracking)
        cx = x - lw / 2 if align == "center" else x
        for u in line:
            w = unit_width(u, font, h.size, h.pad, b.tracking)
            tx = cx + (h.pad if u.style != "plain" else 0)
            if u.style == "plain":
                glyphs.append(HeadlinePart("text", "plain", tx, baseline, text=u.text))
            else:
                box = "accent_box" if u.style == "accent" else "soft_box"
                color = "accent_text" if u.style == "accent" else "soft_text"
                above, below = h.boxes[i]
                boxes.append(HeadlinePart("box", box, cx, baseline - above, w, above + below))
                glyphs.append(HeadlinePart("text", color, tx, baseline, text=u.text))
                if u.style == "strike":
                    tw = w - 2 * h.pad
                    strikes.append(
                        HeadlinePart(
                            "strike",
                            "strike",
                            tx - 4,
                            baseline - h.cap * 0.47,
                            tw + 8,
                            h.size * 0.07,
                        )
                    )
            cx += w + space
        if i < len(h.gaps):
            baseline += h.gaps[i]
    return boxes + glyphs + strikes


def draw_headline(
    h: Headline, b: Brand, x: float, top: float, align: str, colors: dict[str, str]
) -> str:
    """Desenha blocos primeiro e texto por cima (blocos nunca cobrem acentos)."""
    font = b.f("headline")
    out = []
    for part in headline_parts(h, b, x, top, align):
        if part.kind == "text":
            out.append(
                text(
                    part.x, part.y, part.text, font, h.size, colors[part.role], tracking=b.tracking
                )
            )
        else:
            out.append(rect(part.x, part.y, part.w, part.h, colors[part.role]))
    return "".join(out)


# ---------------------------------------------------------------------------- blocos comuns
def company_mark(spec: Spec, b: Brand, x: float, y: float, color: str, anchor="start") -> str:
    if not spec.company:
        return ""
    if spec.company.logo_svg:
        path = assets_dir() / "logos" / spec.company.logo_svg
        if not path.exists():
            raise LayoutError(f"Logo não encontrado: {path}")
        data = base64.b64encode(path.read_bytes()).decode()
        w, hgt = 240, 54
        lx = x - w / 2 if anchor == "middle" else x
        align = "xMidYMid" if anchor == "middle" else "xMinYMid"
        return (
            f'<image x="{_attr(lx)}" y="{_attr(y - hgt + 8)}" width="{w}" height="{hgt}" '
            f'preserveAspectRatio="{align} meet" href="data:image/svg+xml;base64,{data}"/>'
        )
    return text(x, y, spec.company.name, b.f("body_bold"), 46, color, anchor=anchor, tracking=-1)


def fit_source(source: str, b: Brand, max_width: float) -> float:
    size, _ = fit_text(source, b.f("body"), [19, 18, 17, 16], max_width, 1)
    return size


def _svg(b: Brand, parts: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{b.width}" height="{b.height}" '
        f'viewBox="0 0 {b.width} {b.height}">' + "".join(parts) + "</svg>"
    )


# ---------------------------------------------------------------------------- layout 1
def escada(spec: EscadaSpec, b: Brand) -> str:
    W, H, M, c = b.width, b.height, b.margin, b.c
    parts = [
        rect(0, 0, W, H, c("paper")),
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        f'fill="{c("violet")}"/></marker></defs>',
        # retícula ancorada na faixa do rodapé (cresce para baixo, sangra pela esquerda)
        halftone(14, 1044, 16, 8, 24, c("violet"), "down", 8),
    ]
    top = 120
    if spec.company:
        parts.append(company_mark(spec, b, M, 140, c("ink")))
        top = 186
    if spec.context:
        _, ctx = fit_text(spec.context, b.f("body_medium"), [28], W - 2 * M, 1)
        parts.append(text(M, 186, ctx[0], b.f("body_medium"), 28, c("muted_on_paper")))
        top = 232
    h = fit_headline(spec.headline, b, max_width=830, max_height=640 - top, max_lines=4)
    parts.append(
        draw_headline(
            h,
            b,
            M,
            top,
            "start",
            {
                "plain": c("ink"),
                "accent_box": c("violet"),
                "accent_text": c("white"),
                "soft_box": c("lavender"),
                "soft_text": c("ink"),
                "strike": c("ink"),
            },
        )
    )

    bw, bh, depth = 250, 140, 24
    pos = [(410, 1040), (570, 880), (730, 720)]
    anchors = [(x - 4, y - 4) for x, y in pos]
    (x1, y1), (x2, y2), (x3, y3) = anchors
    end = (x3 + 178, y3 - 60)
    parts.append(
        f'<path d="M{x1},{y1} C{x1 - 70},{y1 - 90} {x2 - 90},{y2 + 40} {x2},{y2} '
        f"M{x2},{y2} C{x2 - 70},{y2 - 90} {x3 - 90},{y3 + 40} {x3},{y3} "
        f'M{x3},{y3} C{x3 - 30},{y3 - 80} {x3 + 120},{y3 - 110} {end[0]},{end[1]}" fill="none" '
        f'stroke="{c("violet")}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow)"/>'
    )
    inner = bw - 48
    for (bx, by), step in reversed(list(zip(pos, spec.steps, strict=True))):
        tsize, tlines = fit_text(step.title.upper(), b.f("headline_alt"), [33, 30, 28], inner, 1)
        bsize, blines = fit_text(step.text, b.f("body"), [22, 21, 20], inner, 2)
        parts.append(
            f'<path d="M{bx + bw},{by} l{depth},{depth} v{bh} l-{depth},-{depth} z" fill="{c("charcoal")}"/>'
            f'<path d="M{bx},{by + bh} l{depth},{depth} h{bw} l-{depth},-{depth} z" fill="{c("ink")}"/>'
            + rect(bx, by, bw, bh, c("white"), stroke=c("ink"), sw=3)
            + text(bx + 24, by + 52, tlines[0], b.f("headline_alt"), tsize, c("ink"))
        )
        for i, ln in enumerate(blines):
            parts.append(
                text(bx + 24, by + 90 + i * 27, ln, b.f("body"), bsize, c("muted_on_paper"))
            )
    for i, (cx, cy) in enumerate(anchors, start=1):
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="25" fill="{c("violet")}" stroke="{c("paper")}" stroke-width="4"/>'
        )
        parts.append(text(cx, cy + 10, str(i), b.f("headline"), 30, c("white"), anchor="middle"))
    if spec.milestone:
        fx, fy = 935, 560
        # Área útil da bandeira: do mastro (+6) até antes do entalhe (+60); centro em +33
        msize, _ = fit_text(spec.milestone.upper(), b.f("headline"), [28, 26, 24, 22, 20], 52, 1)
        parts.append(
            f'<line x1="{fx}" y1="{fy}" x2="{fx}" y2="{y3 - 10}" stroke="{c("ink")}" stroke-width="4"/>'
            f'<path d="M{fx},{fy} h84 l-20,24 l20,24 h-84 z" fill="{c("lime")}" stroke="{c("ink")}" stroke-width="3"/>'
            + text(
                fx + 33,
                fy + 34,
                spec.milestone.upper(),
                b.f("headline"),
                msize,
                c("ink"),
                anchor="middle",
            )
        )
    else:
        parts.append(
            f'<circle cx="{end[0] + 14}" cy="{end[1] + 10}" r="12" fill="{c("lime")}" stroke="{c("ink")}" stroke-width="3"/>'
        )

    parts.append(rect(0, 1230, W, H - 1230, c("violet")))
    sig_w = max(measure(b.name, b.f("body_bold"), 30), measure(b.tagline, b.f("body_medium"), 22))
    ssize = fit_source(spec.source, b, W - 2 * M - sig_w - 40)
    parts.append(text(M, 1300, spec.source, b.f("body"), ssize, c("text_on_violet")))
    parts.append(text(W - M, 1272, b.name, b.f("body_bold"), 30, c("white"), anchor="end"))
    parts.append(text(W - M, 1302, b.tagline, b.f("body_medium"), 22, c("lime"), anchor="end"))
    return _svg(b, parts)


# ---------------------------------------------------------------------------- layout 2
def contraste(spec: ContrasteSpec, b: Brand) -> str:
    W, H, M, c = b.width, b.height, b.margin, b.c
    parts = [
        rect(0, 0, W, H, c("charcoal")),
        # retícula ancorada na borda direita (cresce para a borda e sangra)
        halftone(860, 120, 10, 46, 24, c("halftone_on_charcoal"), "right", 8),
    ]
    top = 150
    if spec.company:
        parts.append(company_mark(spec, b, M, 150, c("white")))
        top = 220
    n = len(spec.items)
    lowest_first = 1130 - 64 * (n - 1)  # checklist encostado no limite inferior
    min_gap = 130
    h = fit_headline(
        spec.headline, b, max_width=780, max_height=lowest_first - 34 - min_gap - top, max_lines=5
    )
    # o checklist acompanha a manchete: folga mínima + 40% do espaço que sobrar
    head_bottom = top + h.height(b) + h.size * 0.10
    spare = lowest_first - 34 - head_bottom - min_gap
    first_item = round(head_bottom + min_gap + 34 + max(spare, 0) * 0.4)
    parts.append(
        draw_headline(
            h,
            b,
            M,
            top,
            "start",
            {
                "plain": c("white"),
                "accent_box": c("violet"),
                "accent_text": c("white"),
                "soft_box": c("lavender"),
                "soft_text": c("charcoal"),
                "strike": c("white"),
            },
        )
    )
    item_width = 860 - (M + 56) - 10
    for i, item in enumerate(spec.items):
        size, lines = fit_text(item, b.f("body_medium"), [34, 32, 30], item_width, 1)
        y = first_item + i * 64
        parts.append(check_icon(M, y - 30, 36, c("lavender"), c("charcoal")))
        parts.append(text(M + 56, y, lines[0], b.f("body_medium"), size, c("text_on_charcoal")))
    parts.append(
        f'<line x1="{M}" y1="1210" x2="{W - M}" y2="1210" stroke="{c("rule_on_charcoal")}" stroke-width="2"/>'
    )
    sig_w = max(measure(b.name, b.f("body_bold"), 30), measure(b.tagline, b.f("body_medium"), 22))
    ssize = fit_source(spec.source, b, W - 2 * M - sig_w - 40)
    parts.append(text(M, 1290, spec.source, b.f("body"), ssize, c("muted_on_charcoal")))
    parts.append(text(W - M, 1262, b.name, b.f("body_bold"), 30, c("white"), anchor="end"))
    parts.append(text(W - M, 1292, b.tagline, b.f("body_medium"), 22, c("lavender"), anchor="end"))
    return _svg(b, parts)


# ---------------------------------------------------------------------------- layout 3
def tese(spec: TeseSpec, b: Brand) -> str:
    W, H, c = b.width, b.height, b.c
    cx = W / 2
    parts = [
        rect(0, 0, W, H, c("lavender")),
        # retícula como textura da moldura (o painel cobre o centro)
        halftone(10, 10, 46, 57, 24, c("violet"), "up", 5),
        rect(56, 56, W - 112, H - 112, c("paper")),
    ]
    top = 200
    if spec.company:
        parts.append(company_mark(spec, b, cx, 170, c("ink"), anchor="middle"))
        top = 250
    bottom = 800
    h = fit_headline(
        spec.headline,
        b,
        max_width=840,
        max_height=bottom - top,
        max_lines=5,
        max_size=116,
        align="center",
    )
    offset = (bottom - top - h.height(b)) / 2
    parts.append(
        draw_headline(
            h,
            b,
            cx,
            top + offset,
            "center",
            {
                "plain": c("ink"),
                "accent_box": c("violet"),
                "accent_text": c("white"),
                "soft_box": c("lavender"),
                "soft_text": c("ink"),
                "strike": c("ink"),
            },
        )
    )
    by = 880
    styles = [(c("white"), c("ink")), (c("lavender_soft"), c("ink")), (c("violet"), c("white"))]
    for (bx, term), (fill, color) in zip(
        zip((140, 430, 720), spec.equation, strict=True), styles, strict=True
    ):
        tsize, tl = fit_text(term.title.upper(), b.f("headline"), [40, 36, 32], 190, 1)
        ssize, sl = fit_text(term.subtitle, b.f("body_medium"), [24, 22, 20], 196, 1)
        parts.append(rect(bx, by, 220, 150, fill, rx=18, stroke=c("ink"), sw=3))
        parts.append(text(bx + 110, by + 70, tl[0], b.f("headline"), tsize, color, anchor="middle"))
        parts.append(
            text(bx + 110, by + 108, sl[0], b.f("body_medium"), ssize, color, anchor="middle")
        )
    for ox, op in ((395, "+"), (685, "=")):
        parts.append(
            f'<circle cx="{ox}" cy="{by + 75}" r="27" fill="{c("lime")}" stroke="{c("ink")}" stroke-width="3"/>'
        )
        parts.append(text(ox, by + 92, op, b.f("headline"), 48, c("ink"), anchor="middle"))
    parts.append(
        f'<line x1="102" y1="1150" x2="{W - 102}" y2="1150" stroke="{c("rule_on_paper")}" stroke-width="2"/>'
    )
    ssize = fit_source(spec.source, b, 860)
    parts.append(
        text(
            cx, 1200, spec.source, b.f("body"), min(ssize, 18), c("muted_on_paper"), anchor="middle"
        )
    )
    parts.append(
        text(
            cx,
            1250,
            f"{b.name}  ·  {b.tagline}",
            b.f("body_semibold"),
            24,
            c("ink"),
            anchor="middle",
        )
    )
    return _svg(b, parts)


# ---------------------------------------------------------------------------- API
_LAYOUTS = {"escada": escada, "contraste": contraste, "tese": tese}


def render_svg(spec: Spec, brand: Brand | None = None) -> str:
    b = brand or load_brand()
    _check_glyphs(spec, b)
    return _LAYOUTS[spec.layout](spec, b)


def render_png(spec: Spec, brand: Brand | None = None) -> bytes:
    b = brand or load_brand()
    svg = render_svg(spec, b)
    png = resvg_py.svg_to_bytes(
        svg_string=svg, font_dirs=[str(assets_dir() / "fonts")], skip_system_fonts=True
    )
    return bytes(png)
