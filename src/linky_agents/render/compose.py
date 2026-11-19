"""Motor de composição: a imagem como JSON de peças, validada pelas regras da marca.

O agente de direção de arte (e, no T2, os scripts de `tools/t2_art/`) descreve a imagem como
uma `Composition`: o fundo e uma lista de **peças** (manchete com destaque, pilhas, linha do
tempo...), cada uma feita de elementos primitivos. O motor é o guardião da identidade
(ADR 0002 e ADR 0006): antes de desenhar, `check` aplica as regras e devolve cada violação
com um motivo legível, para o agente corrigir. `to_svg` e `to_png` recusam a composição
inválida com `CompositionRejected`.

A biblioteca de componentes (fim do T2) entra aqui como funções que devolvem uma `Piece`:
o nome da peça é o ID do componente, e é ele que forma a assinatura da composição usada
contra a repetição (ver `linky_agents.render.registry`).
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Literal

import resvg_py
from pydantic import BaseModel, ConfigDict, Field, model_validator

from linky_agents.render.brand import Brand, assets_dir, load_brand
from linky_agents.render.layouts import Headline, fit_headline, headline_parts, rect, text
from linky_agents.render.text import LayoutError, glyph_ink_boxes, unsupported_chars

Point = tuple[float, float]
BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 (y para baixo, como no SVG)


# ============================================================================ contrato (JSON)
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Element(_Strict):
    id: str | None = Field(default=None, description="Nome curto, usado nos motivos de recusa")


class RectEl(_Element):
    kind: Literal["rect"]
    x: float
    y: float
    w: Annotated[float, Field(gt=0)]
    h: Annotated[float, Field(gt=0)]
    fill: str | None = None
    stroke: str | None = None
    stroke_width: Annotated[float, Field(ge=0)] = 0
    radius: Annotated[float, Field(ge=0)] = 0
    dash: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _paint(self) -> RectEl:
        if self.fill is None and (self.stroke is None or not self.stroke_width):
            raise ValueError("retângulo sem preenchimento nem contorno")
        return self


class CircleEl(_Element):
    kind: Literal["circle"]
    cx: float
    cy: float
    r: Annotated[float, Field(gt=0)]
    fill: str | None = None
    stroke: str | None = None
    stroke_width: Annotated[float, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _paint(self) -> CircleEl:
        if self.fill is None and (self.stroke is None or not self.stroke_width):
            raise ValueError("círculo sem preenchimento nem contorno")
        return self


class LineEl(_Element):
    """Linha ou polilinha (fio, conector, trilho)."""

    kind: Literal["line"]
    points: Annotated[list[Point], Field(min_length=2)]
    stroke: str
    width: Annotated[float, Field(gt=0)]
    cap: Literal["butt", "round"] = "butt"


class PolygonEl(_Element):
    kind: Literal["polygon"]
    points: Annotated[list[Point], Field(min_length=3)]
    fill: str


class TextEl(_Element):
    """Uma linha de texto. `y` é a linha de base; `strike` desenha um tachado nessa cor."""

    kind: Literal["text"]
    x: float
    y: float
    text: Annotated[str, Field(min_length=1)]
    font: str
    size: Annotated[float, Field(gt=0)]
    fill: str
    anchor: Literal["start", "middle", "end"] = "start"
    tracking: float = 0.0
    strike: str | None = None


class HeadlineEl(_Element):
    """Manchete com destaques (**violeta**, ==lilás==, ~~tachado~~, | quebra), ajustada à caixa."""

    kind: Literal["headline"]
    markup: Annotated[str, Field(min_length=3)]
    x: float
    top: float
    max_width: Annotated[float, Field(gt=0)]
    max_height: Annotated[float, Field(gt=0)]
    max_lines: Annotated[int, Field(ge=1, le=6)]
    align: Literal["start", "center"] = "start"
    max_size: float | None = None
    plain: str = "@texto"
    accent_box: str = "violet"
    accent_text: str = "white"
    soft_box: str = "lavender"
    soft_text: str = "ink"
    strike: str = "@texto"


Edge = Literal["left", "right", "top", "bottom"]


class HalftoneEl(_Element):
    """Retícula: grade regular de pontos que nasce de uma borda ou estrutura (`anchor`).

    Os pontos são maiores no lado `grow_from` (colado à estrutura) e diminuem para fora.
    `anchor` é "canvas" (a borda da imagem) ou o `id` de outro elemento.
    """

    kind: Literal["halftone"]
    x: float
    y: float
    w: Annotated[float, Field(gt=0)]
    h: Annotated[float, Field(gt=0)]
    color: str
    grow_from: Edge
    anchor: str
    step: Annotated[float, Field(ge=12, le=48)] = 24
    rmax: Annotated[float, Field(gt=0)] = 7.0
    gamma: Annotated[float, Field(gt=0)] = 1.3
    min_dot: Annotated[float, Field(ge=0)] = 0.8
    fade_steps: Annotated[int, Field(ge=1)] | None = Field(
        default=None,
        description="Passos da âncora até o ponto sumir (padrão: a profundidade da retícula)",
    )
    profile: Literal["flat", "peak"] = "flat"


Element = Annotated[
    RectEl | CircleEl | LineEl | PolygonEl | TextEl | HeadlineEl | HalftoneEl,
    Field(discriminator="kind"),
]


class Piece(_Strict):
    """Uma peça da composição. `name` é o ID do componente (base da assinatura)."""

    name: Annotated[str, Field(min_length=2, max_length=60)]
    elements: Annotated[list[Element], Field(min_length=1)]


class Composition(_Strict):
    """A imagem: tema, fundo e peças.

    `theme` ("claro", papel, ou "escuro", grafite) define o fundo padrão e os papéis de cor que
    os elementos podem usar no lugar do token: `@fundo`, `@texto`, `@apoio`, `@fio`,
    `@superficie` e `@reticula` (tabela em `tokens.json`, "themes").
    """

    theme: Literal["claro", "escuro"] = "claro"
    background: str | None = None
    pieces: Annotated[list[Piece], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_ids(self) -> Composition:
        ids = [e.id for p in self.pieces for e in p.elements if e.id]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"IDs de elemento repetidos: {dup}")
        return self


_COLOR_FIELDS = (
    "fill",
    "stroke",
    "color",
    "strike",
    "plain",
    "accent_box",
    "accent_text",
    "soft_box",
    "soft_text",
)


def _resolve_theme(c: Composition, b: Brand) -> Composition:
    """Troca os papéis do tema (`@texto`...) pelos tokens e fixa o fundo."""
    roles = b.themes[c.theme]

    def token(v):
        return roles.get(v[1:], v) if isinstance(v, str) and v.startswith("@") else v

    data = c.model_dump()
    data["background"] = token(data["background"] or "@fundo")
    for piece in data["pieces"]:
        for el in piece["elements"]:
            for f in _COLOR_FIELDS:
                if f in el:
                    el[f] = token(el[f])
    return Composition.model_validate(data)


# ============================================================================ violações
@dataclass(frozen=True)
class Violation:
    """Uma regra quebrada, com o lugar (peça/elemento) e o motivo em português."""

    rule: str  # marca, margem, colisão, contraste, lima, retícula, repetição
    where: str  # "peça/elemento"
    message: str

    @property
    def key(self) -> str:
        return f"{self.rule}:{self.where}"

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.message}"


class CompositionRejected(ValueError):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(f"- {v}" for v in violations)
        super().__init__(f"Composição recusada ({len(violations)} motivo(s)):\n{lines}")


# ============================================================================ desenho plano
@dataclass
class _Drawn:
    """Um item desenhado (depois de expandir a manchete), com geometria para as regras."""

    where: str
    kind: Literal["shape", "outline", "line", "text", "halftone", "strike"]
    box: BBox
    svg: str
    paint: str | None = None  # token da cor de preenchimento (ou do traço, em linhas)
    eid: str | None = None
    glyphs: list[BBox] = field(default_factory=list)
    size: float = 0.0
    weight: int = 400
    segments: list[tuple[Point, Point]] = field(default_factory=list)
    width: float = 0.0
    circle: tuple[float, float, float] | None = None
    owner: int | None = None  # tachado: índice do texto que ele risca
    element: object = None
    stroke: str | None = None  # token do contorno de formas preenchidas
    points: list[Point] = field(default_factory=list)  # polígono
    radius: float = 0.0  # canto arredondado do retângulo


def _a(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _where(piece: Piece, i: int, el) -> str:
    return f"{piece.name}/{el.id or f'{el.kind}{i + 1}'}"


def _union(boxes: Iterable[BBox]) -> BBox:
    boxes = list(boxes)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _text_drawn(where, x, y, s, font_key, size, fill, anchor, tracking, b: Brand, eid=None):
    font = b.f(font_key)
    glyphs = [
        (x + g[0], y + g[1], x + g[2], y + g[3])
        for g in glyph_ink_boxes(s, font, size, tracking, anchor)
    ]
    box = _union(glyphs) if glyphs else (x, y, x, y)
    return _Drawn(
        where,
        "text",
        box,
        text(x, y, s, font, size, b.c(fill), anchor=anchor, tracking=tracking),
        paint=fill,
        eid=eid,
        glyphs=glyphs,
        size=size,
        weight=font.weight,
    )


def _halftone_dots(el: HalftoneEl) -> list[tuple[float, float, float]]:
    cols, rows = max(int(el.w // el.step), 1), max(int(el.h // el.step), 1)
    across = cols if el.grow_from in ("left", "right") else rows
    dots = []
    for i in range(cols):
        for j in range(rows):
            depth = {"left": i, "right": cols - 1 - i, "top": j, "bottom": rows - 1 - j}[
                el.grow_from
            ]
            fade = el.fade_steps or max(across - 1, 1)
            k = max(1 - depth / fade, 0) ** el.gamma
            if el.profile == "peak":
                side, n = (j, rows) if el.grow_from in ("left", "right") else (i, cols)
                mid = (n - 1) / 2
                k *= 1 - 0.25 * abs(side - mid) / max(mid, 1)
            r = el.rmax * k
            if r >= el.min_dot:
                dots.append((el.x + (i + 0.5) * el.step, el.y + (j + 0.5) * el.step, r))
    return dots


def _expand(c: Composition, b: Brand) -> list[_Drawn]:
    out: list[_Drawn] = []
    for piece in c.pieces:
        for i, el in enumerate(piece.elements):
            where = _where(piece, i, el)
            out += _expand_one(el, where, b, len(out))
    return out


def _expand_one(el, where: str, b: Brand, base: int) -> list[_Drawn]:
    c = b.c
    if isinstance(el, RectEl):
        stroke = (
            f' stroke="{c(el.stroke)}" stroke-width="{_a(el.stroke_width)}"' if el.stroke else ""
        )
        dash = f' stroke-dasharray="{_a(el.dash[0])} {_a(el.dash[1])}"' if el.dash else ""
        fill = c(el.fill) if el.fill else "none"
        svg = (
            f'<rect x="{_a(el.x)}" y="{_a(el.y)}" width="{_a(el.w)}" height="{_a(el.h)}" '
            f'rx="{_a(el.radius)}" fill="{fill}"{stroke}{dash}/>'
        )
        half = el.stroke_width / 2 if el.stroke else 0
        box = (el.x - half, el.y - half, el.x + el.w + half, el.y + el.h + half)
        kind = "shape" if el.fill else "outline"
        d = _Drawn(where, kind, box, svg, el.fill or el.stroke, el.id, width=el.stroke_width)
        d.stroke = el.stroke if el.fill else None
        d.radius = min(el.radius, el.w / 2, el.h / 2)
        return [d]
    if isinstance(el, CircleEl):
        stroke = (
            f' stroke="{c(el.stroke)}" stroke-width="{_a(el.stroke_width)}"' if el.stroke else ""
        )
        fill = c(el.fill) if el.fill else "none"
        svg = f'<circle cx="{_a(el.cx)}" cy="{_a(el.cy)}" r="{_a(el.r)}" fill="{fill}"{stroke}/>'
        r = el.r + (el.stroke_width / 2 if el.stroke else 0)
        box = (el.cx - r, el.cy - r, el.cx + r, el.cy + r)
        kind = "shape" if el.fill else "outline"
        return [
            _Drawn(
                where,
                kind,
                box,
                svg,
                el.fill or el.stroke,
                el.id,
                width=el.stroke_width if el.stroke else 0.0,
                circle=(el.cx, el.cy, r),
                stroke=el.stroke if el.fill else None,
            )
        ]
    if isinstance(el, LineEl):
        pts = " ".join(f"{_a(x)},{_a(y)}" for x, y in el.points)
        cap = ' stroke-linecap="round"' if el.cap == "round" else ""
        svg = (
            f'<polyline points="{pts}" fill="none" stroke="{c(el.stroke)}" '
            f'stroke-width="{_a(el.width)}"{cap}/>'
        )
        segs = list(zip(el.points, el.points[1:], strict=False))
        box = _union(_segment_box(p, q, el.width / 2, el.cap) for p, q in segs)
        return [_Drawn(where, "line", box, svg, el.stroke, el.id, segments=segs, width=el.width)]
    if isinstance(el, PolygonEl):
        pts = " ".join(f"{_a(x)},{_a(y)}" for x, y in el.points)
        svg = f'<polygon points="{pts}" fill="{c(el.fill)}"/>'
        xs, ys = [p[0] for p in el.points], [p[1] for p in el.points]
        box = (min(xs), min(ys), max(xs), max(ys))
        return [_Drawn(where, "shape", box, svg, el.fill, el.id, points=list(el.points))]
    if isinstance(el, TextEl):
        t = _text_drawn(
            where, el.x, el.y, el.text, el.font, el.size, el.fill, el.anchor, el.tracking, b, el.id
        )
        t.element = el
        if not el.strike:
            return [t]
        x0, _, x1, _ = t.box
        cap = el.size * 0.70
        sy, sh = el.y - cap * 0.47 - 1, max(el.size * 0.07, 3)
        strike = _Drawn(
            where,
            "strike",
            (x0 - 2, sy, x1 + 2, sy + sh),
            rect(x0 - 2, sy, x1 - x0 + 4, sh, c(el.strike)),
            el.strike,
            el.id,
            owner=base,
        )
        return [t, strike]
    if isinstance(el, HeadlineEl):
        h: Headline = fit_headline(
            el.markup, b, el.max_width, el.max_height, el.max_lines, el.max_size, el.align
        )
        parts = headline_parts(h, b, el.x, el.top, el.align)
        out: list[_Drawn] = []
        for k, part in enumerate(parts):
            token = getattr(el, part.role)
            w = f"{where}#{k + 1}"
            if part.kind == "text":
                d = _text_drawn(
                    w,
                    part.x,
                    part.y,
                    part.text,
                    "headline",
                    h.size,
                    token,
                    "start",
                    b.tracking,
                    b,
                    el.id,
                )
                out.append(d)
            else:
                box = (part.x, part.y, part.x + part.w, part.y + part.h)
                svg = rect(part.x, part.y, part.w, part.h, c(token))
                kind = "strike" if part.kind == "strike" else "shape"
                d = _Drawn(w, kind, box, svg, token, el.id)
                if kind == "strike":
                    d.owner = _struck_text(out, box, base)
                out.append(d)
        return out
    if isinstance(el, HalftoneEl):
        dots = _halftone_dots(el)
        svg = (
            f'<g fill="{c(el.color)}">'
            + "".join(f'<circle cx="{_a(x)}" cy="{_a(y)}" r="{r:.2f}"/>' for x, y, r in dots)
            + "</g>"
        )
        box = (el.x, el.y, el.x + el.w, el.y + el.h)
        d = _Drawn(where, "halftone", box, svg, el.color, el.id)
        d.element = el
        return [d]
    raise TypeError(el)  # pragma: no cover


def _segment_box(p: Point, q: Point, half: float, cap: str) -> BBox:
    """Caixa do traço: a ponta reta (butt) não avança na direção do segmento."""
    (x0, y0), (x1, y1) = p, q
    if cap == "round" or (x0 != x1 and y0 != y1):
        hx = hy = half
    elif y0 == y1:  # horizontal
        hx, hy = 0.0, half
    else:  # vertical
        hx, hy = half, 0.0
    return (min(x0, x1) - hx, min(y0, y1) - hy, max(x0, x1) + hx, max(y0, y1) + hy)


def _struck_text(out: list[_Drawn], box: BBox, base: int) -> int | None:
    for k, d in enumerate(out):
        if d.kind == "text" and _overlap(d.box, box):
            return base + k
    return None


# ============================================================================ geometria
def _overlap(a: BBox, b: BBox, pad: float = 0.0) -> bool:
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


def _contains(outer: BBox, inner: BBox) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _seg_rect_dist(p: Point, q: Point, r: BBox) -> float:
    """Distância entre um segmento e um retângulo (0 se cruzam)."""
    (x0, y0), (x1, y1) = p, q
    if _overlap((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), r) and (x0 == x1 or y0 == y1):
        return 0.0
    best = math.inf
    steps = max(int(math.hypot(x1 - x0, y1 - y0) // 2), 1)
    for s in range(steps + 1):
        t = s / steps
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        dx = max(r[0] - x, 0, x - r[2])
        dy = max(r[1] - y, 0, y - r[3])
        best = min(best, math.hypot(dx, dy))
    return best


def _in_polygon(x: float, y: float, pts: list[Point]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _rounded_parts(d: _Drawn) -> tuple[list[BBox], list[tuple[float, float, float]]]:
    """Retângulo de canto arredondado = dois retângulos em cruz + quatro círculos."""
    x0, y0, x1, y1 = d.box
    r = d.radius
    cross = [(x0 + r, y0, x1 - r, y1), (x0, y0 + r, x1, y1 - r)]
    corners = [(cx, cy, r) for cx in (x0 + r, x1 - r) for cy in (y0 + r, y1 - r)]
    return cross, corners


def _point_in(d: _Drawn, x: float, y: float) -> bool:
    """O ponto está dentro da forma preenchida (polígono, círculo ou retângulo)?"""
    if d.points:
        return _in_polygon(x, y, d.points)
    if d.circle:
        cx, cy, r = d.circle
        return math.hypot(x - cx, y - cy) <= r
    if d.radius:
        cross, corners = _rounded_parts(d)
        return any(_contains(c, (x, y, x, y)) for c in cross) or any(
            math.hypot(x - cx, y - cy) <= r for cx, cy, r in corners
        )
    return _contains(d.box, (x, y, x, y))


def _circle_near(cx: float, cy: float, r: float, box: BBox, pad: float) -> bool:
    dx = max(box[0] - cx, 0, cx - box[2])
    dy = max(box[1] - cy, 0, cy - box[3])
    return math.hypot(dx, dy) < r + pad


def _touches(d: _Drawn, glyph: BBox, pad: float) -> bool:
    """O item `d` encosta na caixa de tinta de um glyph (com folga `pad`)?"""
    if not _overlap(d.box, glyph, pad):
        return False
    if d.kind == "line":
        return any(_seg_rect_dist(p, q, glyph) < d.width / 2 + pad for p, q in d.segments)
    if d.circle:
        cx, cy, r = d.circle
        dx = max(glyph[0] - cx, 0, cx - glyph[2])
        dy = max(glyph[1] - cy, 0, cy - glyph[3])
        nearest = math.hypot(dx, dy)
        if d.kind == "shape":
            return nearest < r + pad
        # anel (só contorno): toca se a caixa do glyph alcança a faixa do traço
        farthest = max(math.hypot(x - cx, y - cy) for x in glyph[0::2] for y in glyph[1::2])
        return nearest < r + pad and farthest > r - d.width - pad
    if d.kind == "shape" and d.points:
        g = (glyph[0] - pad, glyph[1] - pad, glyph[2] + pad, glyph[3] + pad)
        pts = d.points
        edges = zip(pts, pts[1:] + pts[:1], strict=True)
        return (
            any(_in_polygon(x, y, pts) for x in g[0::2] for y in g[1::2])
            or any(_contains(g, (x, y, x, y)) for x, y in pts)
            or any(_seg_rect_dist(p, q, g) < 0.5 for p, q in edges)
        )
    if d.kind == "shape" and d.radius:
        cross, corners = _rounded_parts(d)
        return any(_overlap(c, glyph, pad) for c in cross) or any(
            _circle_near(cx, cy, r, glyph, pad) for cx, cy, r in corners
        )
    if d.kind == "outline":  # só o traço conta
        inner = (d.box[0] + d.width, d.box[1] + d.width, d.box[2] - d.width, d.box[3] - d.width)
        return not _contains(
            inner, (glyph[0] - pad, glyph[1] - pad, glyph[2] + pad, glyph[3] + pad)
        )
    return True


def _stroke_area(d: _Drawn) -> float:
    if d.circle:
        return 2 * math.pi * d.circle[2] * d.width
    return 2 * ((d.box[2] - d.box[0]) + (d.box[3] - d.box[1])) * d.width


def _area(d: _Drawn) -> float:
    if d.kind == "text":
        return sum((g[2] - g[0]) * (g[3] - g[1]) for g in d.glyphs)
    if d.kind == "line":
        return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in d.segments) * d.width
    if d.circle and d.kind == "shape":
        return math.pi * d.circle[2] ** 2
    if d.kind == "outline":
        return _stroke_area(d)
    if d.kind == "halftone":
        return sum(math.pi * r * r for _, _, r in _halftone_dots(d.element))
    return (d.box[2] - d.box[0]) * (d.box[3] - d.box[1])


# ============================================================================ cores
def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    """Razão de contraste do WCAG 2 entre duas cores #RRGGBB."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ============================================================================ regras
def _check_brand(c: Composition, b: Brand) -> list[Violation]:
    out = []
    color_fields = _COLOR_FIELDS
    if c.background not in b.colors:
        out.append(Violation("marca", "fundo", f"cor {c.background!r} não é token da marca"))
    for piece in c.pieces:
        for i, el in enumerate(piece.elements):
            where = _where(piece, i, el)
            for f in color_fields:
                v = getattr(el, f, None)
                if v is not None and v not in b.colors:
                    out.append(
                        Violation(
                            "marca",
                            where,
                            f"cor {v!r} não é token da marca (use {sorted(b.colors)})",
                        )
                    )
            if isinstance(el, TextEl):
                if el.font not in b.fonts:
                    out.append(
                        Violation(
                            "marca", where, f"fonte {el.font!r} não é da marca ({sorted(b.fonts)})"
                        )
                    )
                else:
                    missing = unsupported_chars(el.text, b.f(el.font))
                    if missing:
                        out.append(
                            Violation(
                                "marca",
                                where,
                                f"caracteres sem suporte na fonte: {sorted(missing)}",
                            )
                        )
            if isinstance(el, HeadlineEl):
                missing = unsupported_chars(el.markup.upper(), b.f("headline")) - {
                    "*",
                    "=",
                    "~",
                    "|",
                }
                if missing:
                    out.append(
                        Violation(
                            "marca", where, f"caracteres sem suporte na fonte: {sorted(missing)}"
                        )
                    )
    return out


def _check_margins(drawn: list[_Drawn], b: Brand) -> list[Violation]:
    W, H, M = b.width, b.height, b.margin
    footer = b.rules["footer"]
    out = []
    for d in drawn:
        x0, y0, x1, y1 = d.box
        if d.kind == "strike":  # faz parte do texto que risca
            continue
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            out.append(Violation("margem", d.where, "fica inteiro fora da imagem"))
            continue
        if d.kind == "text":
            top, bottom = M, H - M
            if _norm(d.where).startswith("rodape"):  # faixa do rodapé: fonte e assinatura
                top, bottom = footer["top"], H - footer["bottom_margin"]
            if x0 < M or y0 < top or x1 > W - M or y1 > bottom:
                out.append(
                    Violation(
                        "margem",
                        d.where,
                        f"texto fora da área útil (tinta em x {x0:.0f}..{x1:.0f}, "
                        f"y {y0:.0f}..{y1:.0f}; a margem é de {M} px)",
                    )
                )
            continue
        sides = [
            ("esquerda", x0 < M, x0 <= 0),
            ("topo", y0 < M, y0 <= 0),
            ("direita", x1 > W - M, x1 >= W),
            ("base", y1 > H - M, y1 >= H),
        ]
        bad = [name for name, inside_margin, bleeds in sides if inside_margin and not bleeds]
        if bad:
            out.append(
                Violation(
                    "margem",
                    d.where,
                    f"entra na margem de {M} px ({', '.join(bad)}) sem sangrar: ou respeita a "
                    "margem ou vai até a borda da imagem",
                )
            )
    return out


def _backdrops(drawn: list[_Drawn], b: Brand) -> tuple[dict[int, str | None], list[Violation]]:
    """Para cada texto, a cor que fica logo abaixo dele (ou None se não há fundo único)."""
    pad = b.rules["clearance"]
    under: dict[int, str | None] = {}
    out: list[Violation] = []
    for i, t in enumerate(drawn):
        if t.kind != "text":
            continue
        # o que está por cima do texto
        for d in drawn[i + 1 :]:
            if d.kind == "strike" and d.owner == i:
                continue
            if d.kind == "text":
                if any(_overlap(g, h, pad) for g in t.glyphs for h in d.glyphs):
                    out.append(
                        Violation("colisão", t.where, f"o texto encosta no texto de {d.where}")
                    )
            elif any(_touches(d, g, pad) for g in t.glyphs):
                out.append(
                    Violation("colisão", t.where, f"{d.where} é desenhado por cima do texto")
                )
        # o que está por baixo: o primeiro item que ele toca, de cima para baixo
        backdrop: str | None = "__bg__"
        for d in reversed(drawn[:i]):
            if d.kind == "strike":
                continue
            if d.kind == "text":
                if any(_overlap(g, h, pad) for g in t.glyphs for h in d.glyphs):
                    out.append(
                        Violation("colisão", t.where, f"o texto encosta no texto de {d.where}")
                    )
                    backdrop = None
                    break
                continue
            touching = [g for g in t.glyphs if _touches(d, g, pad)]
            if not touching:
                continue
            if d.kind == "shape" and _contains(d.box, t.box) and _inside_shape(d, t):
                backdrop = d.paint
            elif d.kind == "halftone":
                out.append(
                    Violation(
                        "colisão",
                        t.where,
                        f"texto sobre a retícula de {d.where} (ela só pode ser textura)",
                    )
                )
                backdrop = None
            elif d.kind == "line":
                out.append(Violation("colisão", t.where, f"a linha {d.where} atravessa o texto"))
                backdrop = None
            else:
                out.append(
                    Violation(
                        "colisão",
                        t.where,
                        f"o texto invade a borda de {d.where} (fica metade dentro, metade fora)",
                    )
                )
                backdrop = None
            break
        under[i] = None if backdrop is None else (backdrop if backdrop != "__bg__" else "")
    return under, out


def _inside_shape(d: _Drawn, t: _Drawn) -> bool:
    """A caixa de tinta do texto inteira dentro da forma (os 4 cantos)."""
    return all(_point_in(d, x, y) for x in t.box[0::2] for y in t.box[1::2])


def _check_contrast(drawn, under, background: str, b: Brand) -> list[Violation]:
    rules = b.rules["contrast"]
    small_min, large_min = rules["text_min"], rules["large_text_min"]
    large, large_bold = rules["large_size"], rules["large_bold_size"]
    out = []
    for i, token in under.items():
        if token is None:
            continue
        t = drawn[i]
        bg = token or background
        ratio = contrast_ratio(b.c(t.paint), b.c(bg))
        is_large = t.size >= large or (t.size >= large_bold and t.weight >= 700)
        need = large_min if is_large else small_min
        if ratio < need - 1e-9:
            kind = "grande" if is_large else "pequeno"
            out.append(
                Violation(
                    "contraste",
                    t.where,
                    f"{t.paint} sobre {bg}: {ratio:.2f}:1, abaixo de {need}:1 para texto {kind} "
                    f"({t.size:g} px)",
                )
            )
    return out


def _check_lime(drawn: list[_Drawn], b: Brand) -> list[Violation]:
    rules = b.rules["lime"]
    max_el, max_total = rules["max_element_area"], rules["max_total_area"]
    max_side = rules["max_shape_side"]
    out, total = [], 0.0
    for d in drawn:
        if d.paint != "lime" and d.stroke != "lime":
            continue
        area = _area(d) if d.paint == "lime" else _stroke_area(d)
        total += area
        w, h = d.box[2] - d.box[0], d.box[3] - d.box[1]
        if area > max_el:
            out.append(
                Violation(
                    "lima",
                    d.where,
                    f"área de lima {area:.0f} px² passa de {max_el} px² "
                    "(lima só em detalhes pequenos)",
                )
            )
        elif d.kind in ("shape", "outline", "line") and max(w, h) > max_side:
            out.append(
                Violation(
                    "lima",
                    d.where,
                    f"peça de lima com {max(w, h):.0f} px de lado "
                    f"(máximo {max_side} px: lima só em detalhes pequenos)",
                )
            )
    if total > max_total and not out:  # um excesso por peça já explica o total
        out.append(
            Violation("lima", "composição", f"lima soma {total:.0f} px², acima de {max_total} px²")
        )
    return out


def _check_halftones(drawn: list[_Drawn], background: str, b: Brand) -> list[Violation]:
    W, H = b.width, b.height
    by_id = {d.eid: d for d in drawn if d.eid}
    max_c = b.rules["contrast"]["halftone_max"]
    out = []
    for d in drawn:
        if d.kind != "halftone":
            continue
        el: HalftoneEl = d.element
        x0, y0, x1, y1 = d.box
        if el.anchor == "canvas":
            edge_ok = {"left": x0 <= 0, "right": x1 >= W, "top": y0 <= 0, "bottom": y1 >= H}[
                el.grow_from
            ]
            if not edge_ok:
                out.append(
                    Violation(
                        "retícula",
                        d.where,
                        f"ancorada na borda ({el.grow_from}) mas não chega até ela: a retícula "
                        "nasce da borda e sangra",
                    )
                )
        else:
            a = by_id.get(el.anchor)
            if a is None or a is d:
                out.append(
                    Violation("retícula", d.where, f"âncora {el.anchor!r} não existe na composição")
                )
                continue
            if a.kind not in ("shape", "outline", "line"):
                out.append(
                    Violation(
                        "retícula",
                        d.where,
                        f"âncora {el.anchor!r} não é estrutura (bloco, moldura, fio ou borda)",
                    )
                )
                continue
            ax0, ay0, ax1, ay1 = a.box
            tol = el.step
            if el.grow_from in ("left", "right"):
                gap = x0 - ax1 if el.grow_from == "left" else ax0 - x1
                along = min(y1, ay1) - max(y0, ay0)
            else:
                gap = y0 - ay1 if el.grow_from == "top" else ay0 - y1
                along = min(x1, ax1) - max(x0, ax0)
            base = (y1 - y0) if el.grow_from in ("left", "right") else (x1 - x0)
            inside = _contains(a.box, d.box)
            if not inside and along < base / 2:
                out.append(
                    Violation(
                        "retícula",
                        d.where,
                        f"{a.where} é pequena demais para sustentar a retícula: ela precisa "
                        f"cobrir ao menos metade da base ({max(along, 0):.0f} de {base:.0f} px)",
                    )
                )
            elif not inside and (gap > tol or gap < -tol):
                out.append(
                    Violation(
                        "retícula",
                        d.where,
                        f"solta no espaço: o lado {el.grow_from} precisa encostar em {a.where} "
                        f"(distância {gap:.0f} px, tolerância de um passo, {tol:g} px)",
                    )
                )
        ratio = contrast_ratio(b.c(el.color), b.c(_color_below(drawn, d, background)))
        if ratio > max_c:
            out.append(
                Violation(
                    "retícula",
                    d.where,
                    f"{el.color} tem contraste {ratio:.2f}:1 com o fundo; a retícula é textura "
                    f"(máximo {max_c}:1)",
                )
            )
    return out


def _color_below(drawn: list[_Drawn], d: _Drawn, background: str) -> str:
    i = drawn.index(d)
    cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
    for e in reversed(drawn[:i]):
        if e.kind == "shape" and _contains(e.box, (cx, cy, cx, cy)):
            return e.paint
    return background


def _validate(c: Composition, b: Brand) -> tuple[list[Violation], list[_Drawn]]:
    c = _resolve_theme(c, b)
    brand_errors = _check_brand(c, b)
    if brand_errors:
        return brand_errors, []  # sem tokens válidos não dá para medir o resto
    try:
        drawn = _expand(c, b)
    except LayoutError as exc:
        return [Violation("margem", "manchete", str(exc))], []
    under, collisions = _backdrops(drawn, b)
    violations = (
        _check_margins(drawn, b)
        + collisions
        + _check_contrast(drawn, under, c.background, b)
        + _check_lime(drawn, b)
        + _check_halftones(drawn, c.background, b)
    )
    if c.background == "lime":
        violations.append(Violation("lima", "fundo", "lima nunca é fundo (só detalhes pequenos)"))
    return violations, drawn


def piece_bounds(c: Composition, brand: Brand | None = None) -> dict[str, BBox]:
    """Caixa de cada peça (pelo nome), unindo o que ela desenha (tinta real no texto)."""
    b = brand or load_brand()
    out: dict[str, BBox] = {}
    for piece in _resolve_theme(c, b).pieces:
        drawn = _expand(Composition(theme=c.theme, pieces=[piece]), b)
        if drawn:
            out[piece.name] = _union(d.box for d in drawn)
    return out


def check(c: Composition, brand: Brand | None = None) -> list[Violation]:
    """Todas as violações das regras da marca, na ordem: marca, margem, colisão, contraste,
    lima e retícula. Lista vazia = composição válida."""
    return _validate(c, brand or load_brand())[0]


# ============================================================================ saída
def to_svg(c: Composition, brand: Brand | None = None, *, known: Iterable[str] = ()) -> str:
    """SVG da composição. Recusa (CompositionRejected) se houver violação fora de `known`.

    `known` são chaves (`Violation.key`) de achados já vistos e aceitos por uma pessoa; o
    agente nunca as preenche.
    """
    b = brand or load_brand()
    accepted = set(known)
    found, drawn = _validate(c, b)
    c = _resolve_theme(c, b)
    violations = [v for v in found if v.key not in accepted]
    if violations or not drawn:
        raise CompositionRejected(violations or found)
    body = rect(0, 0, b.width, b.height, b.c(c.background)) + "".join(d.svg for d in drawn)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{b.width}" height="{b.height}" '
        f'viewBox="0 0 {b.width} {b.height}">{body}</svg>'
    )


def to_png(c: Composition, brand: Brand | None = None, *, known: Iterable[str] = ()) -> bytes:
    svg = to_svg(c, brand, known=known)
    png = resvg_py.svg_to_bytes(
        svg_string=svg, font_dirs=[str(assets_dir() / "fonts")], skip_system_fonts=True
    )
    return bytes(png)


# ============================================================================ assinatura
def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())


def signature(c: Composition) -> str:
    """Assinatura da composição: fundo + conjunto das peças (sem texto e sem posição).

    Duas imagens com as mesmas peças sobre o mesmo fundo são a mesma composição, mesmo com
    outro texto, outras medidas ou as peças trocadas de lugar.
    """
    pieces = sorted(_norm(p.name) for p in c.pieces)
    raw = f"{c.theme}|{c.background or '@fundo'}|" + "+".join(pieces)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def describe(c: Composition) -> str:
    """Versão legível da assinatura (para os motivos de recusa)."""
    return f"tema {c.theme}, fundo {c.background or 'do tema'}: " + ", ".join(
        sorted(_norm(p.name) for p in c.pieces)
    )
