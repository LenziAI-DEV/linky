"""Biblioteca de componentes visuais, extraída das composições do T2 (ADR 0002 e ADR 0006).

Um **componente** é uma função que devolve uma `Piece` já montada; o nome da peça é o ID do
componente (é ele que entra na assinatura da composição, então renomear não escapa da
repetição). Não são moldes: cada componente cuida de uma parte da imagem, com as medidas e a
tipografia que Felipe aprovou no T2, e o agente de arte escolhe quais usar, onde e com que
texto. O resto da imagem continua livre, feito de primitivos (`rect`, `text`, `line`).

Duas camadas:

- **peças** (`CATALOG`): `header`, `headline`, `footer`, `anchored_halftone`,
  `bleeding_bars`, `pass_through_diagram`, `big_number`;
- **partes**, listas de elementos para montar peças livres: `stat` (número com legenda) e os
  primitivos.

Nenhum componente valida a marca: quem decide é `compose.check`, sobre a composição inteira.
Cores aceitam papéis do tema (`@texto`, `@apoio`...), então a mesma peça serve aos dois temas.
"""

from __future__ import annotations

from linky_agents.render.brand import load_brand
from linky_agents.render.compose import Piece
from linky_agents.render.text import ink_box, measure


# ============================================================================ primitivos
def rect(x, y, w, h, fill=None, **kw) -> dict:
    return {"kind": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, **kw}


def text(x, y, s, font, size, fill, anchor="start", **kw) -> dict:
    return {"kind": "text", "x": x, "y": y, "text": s, "font": font, "size": size,
            "fill": fill, "anchor": anchor, **kw}


def line(points, stroke, width, **kw) -> dict:
    return {"kind": "line", "points": points, "stroke": stroke, "width": width, **kw}


def piece(name: str, elements: list) -> Piece:
    """Peça livre (fora da biblioteca), feita de primitivos."""
    return Piece.model_validate({"name": name, "elements": elements})


# ============================================================================ peças
def header(company: str, context: str, *, size: float = 46, tracking: float = -1) -> Piece:
    """Empresa (ou empresas) no topo, em negrito, e uma linha de contexto em `@apoio`."""
    m = load_brand().margin
    return piece("empresa e contexto", [
        text(m, 140, company, "body_bold", size, "@texto", tracking=tracking),
        text(m, 186, context, "body_medium", 28, "@apoio"),
    ])


def headline(markup: str, *, top: float = 236, max_width: float = 936,
             max_height: float = 300, max_lines: int = 2, **style) -> Piece:
    """Manchete com bloco de destaque (`**forte**`, `==suave==`, `~~tachado~~`, `|` quebra).

    Logo abaixo do `header`. O motor escolhe o corpo, faz o bloco cobrir a tinta da palavra e
    afasta as linhas; `style` repassa as cores do `HeadlineEl` (`accent_box`...).
    """
    m = load_brand().margin
    return piece("manchete com destaque", [
        {"kind": "headline", "markup": markup, "x": m, "top": top, "max_width": max_width,
         "max_height": max_height, "max_lines": max_lines, **style},
    ])


def footer(sources: str | list[str], *, tagline_size: float = 24,
           tagline_color: str = "violet") -> Piece:
    """Fio, fonte(s) à esquerda e a assinatura do post ("Felipe Lenzi" + tagline) à direita.

    Fica na faixa do rodapé (y >= 1200), a única área em que o motor deixa texto na margem.
    Uma fonte fica centrada na altura da assinatura; duas ficam empilhadas. A tagline em
    violeta só passa no contraste do tema claro a partir de 24 px; no escuro, use `lavender`.
    """
    b = load_brand()
    m, w = b.margin, b.width
    lines = [sources] if isinstance(sources, str) else list(sources)
    if not 1 <= len(lines) <= 2:
        raise ValueError("o rodapé tem uma ou duas linhas de fonte")
    ys = [1283] if len(lines) == 1 else [1262, 1290]
    return piece("rodapé com fio", [
        line([[m, 1210], [w - m, 1210]], "@fio", 2),
        *(text(m, y, s, "body", 19, "@apoio") for y, s in zip(ys, lines, strict=True)),
        text(w - m, 1262, b.name, "body_bold", 30, "@texto", "end"),
        text(w - m, 1272 + tagline_size, b.tagline, "body_medium", tagline_size, tagline_color,
             "end", id="tagline"),
    ])


_GROWS_FROM = {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}


def anchored_halftone(anchor: Piece, element_id: str, *, side: str = "right",
                      start: float | None = None, extent: float | None = None,
                      step: float = 20, rmax: float = 7.5, gamma: float = 1.4,
                      min_dot: float = 0.7, fade_steps: int | None = None,
                      color: str = "@reticula") -> Piece:
    """Retícula que nasce de um lado de um bloco (`element_id` dentro de `anchor`) e vai até a
    borda da imagem desse lado, diminuindo para longe do bloco.

    Por padrão ocupa todo o lado do bloco; `start` e `extent` (no eixo do lado) recortam um
    trecho dele. Some em `fade_steps` passos (padrão: a profundidade inteira).
    """
    if side not in _GROWS_FROM:
        raise ValueError(f"lado desconhecido: {side!r}")
    el = next((e for e in anchor.elements if e.id == element_id), None)
    if el is None or el.kind != "rect":
        raise ValueError(f"peça {anchor.name!r} sem elemento {element_id!r} (um bloco)")
    b = load_brand()
    if side in ("left", "right"):
        y, h = (el.y, el.h) if start is None else (start, extent)
        x = el.x + el.w if side == "right" else 0
        w = b.width - x if side == "right" else el.x
        depth = w
    else:
        x, w = (el.x, el.w) if start is None else (start, extent)
        y = el.y + el.h if side == "bottom" else 0
        h = b.height - y if side == "bottom" else el.y
        depth = h
    return piece("retícula ancorada", [
        {"kind": "halftone", "x": x, "y": y, "w": w, "h": h, "step": step, "rmax": rmax,
         "gamma": gamma, "min_dot": min_dot,
         "fade_steps": fade_steps if fade_steps is not None else int(depth // step),
         "color": color, "grow_from": _GROWS_FROM[side], "anchor": element_id},
    ])


# texto sobre um bloco dessa cor (o par que passa no contraste)
_ON_BLOCK = {"violet": "white", "ink": "white", "charcoal": "white", "lavender": "ink",
             "lavender_soft": "ink"}


def bleeding_bars(rows: list[tuple[float, str, str, str]], *, top: float,
                  label: str | None = None, longest: float = 800, height: float = 100,
                  gap: float = 34, size: float = 56,
                  inside_color: str | None = None) -> Piece:
    """Barras horizontais em escala real, saindo da borda esquerda (comparação de grandezas).

    `rows`: (valor, número escrito, legenda, cor da barra), de cima para baixo. A maior barra
    mede `longest` px e as outras, a proporção exata. Número e legenda vão dentro da barra
    (em `inside_color`; por padrão branco no violeta e tinta no lilás, legenda ao lado do
    número) quando cabem com folga; senão, logo depois
    dela, nas cores do tema (legenda embaixo). `label` é o período ou a unidade, em versalete,
    acima da primeira barra. Para ancorar uma retícula, os blocos são `barra1`, `barra2`...
    """
    b = load_brand()
    m, pad = b.margin, 28
    peak = max(r[0] for r in rows)
    out = []
    if label is not None:
        out.append(text(m, top - 26, label, "body_semibold", 19, "@apoio", tracking=1.5,
                        id="rotulo"))
    for i, (value, number, caption, color) in enumerate(rows, start=1):
        y = top + (i - 1) * (height + gap)
        mid = y + height / 2
        length = round(longest * value / peak)
        out.append(rect(0, y, length, height, color, id=f"barra{i}"))
        wn = measure(number, b.f("headline"), size)
        wc = measure(caption, b.f("body_semibold"), 28)
        fg = inside_color or _ON_BLOCK.get(color, "white")
        if m + wn + pad + wc + pad <= length:
            out += [
                text(m, mid + 16, number, "headline", size, fg, id=f"barra{i}-numero"),
                text(m + round(wn) + pad, mid + 11, caption, "body_semibold", 28, fg,
                     id=f"barra{i}-legenda"),
            ]
        else:
            out += [
                text(length + pad, mid + 8, number, "headline", size, "@texto",
                     id=f"barra{i}-numero"),
                text(length + pad, mid + 40, caption, "body_medium", 24, "@apoio",
                     id=f"barra{i}-legenda"),
            ]
    return piece("barras sangrando", out)


def pass_through_diagram(left: list[str], right: list[str], center: str, *,
                         center_caption: list[str] = (), left_label: str | None = None,
                         right_label: str | None = None, note: str | None = None,
                         top: float = 580, chip_h: float = 72, gap: float = 28,
                         col_w: float = 278, center_w: float = 176) -> Piece:
    """Diagrama de passagem: itens de um lado, um bloco violeta no meio (o que faz a ponte)
    e itens do outro lado, cada item ligado ao bloco por um fio.

    As colunas encostam na margem; o bloco fica centrado na imagem e tem a altura da coluna
    mais longa. `left_label`/`right_label` vão em versalete acima das colunas; `note`, alinhada
    à direita, abaixo de tudo. Blocos: `esquerda1`..., `direita1`..., `centro`.
    """
    b = load_brand()
    m, w = b.margin, b.width
    n = max(len(left), len(right))
    bottom = top + n * chip_h + (n - 1) * gap
    lx, rx = m + 1, w - m - 1 - col_w
    bx0, bx1 = w / 2 - center_w / 2, w / 2 + center_w / 2
    cx, cy = (bx0 + bx1) / 2, (top + bottom) / 2
    out = []
    if left_label is not None:
        out.append(text(lx, top - 26, left_label, "body_semibold", 19, "@apoio", tracking=1.5,
                        id="rotulo-esquerda"))
    if right_label is not None:
        out.append(text(rx + col_w, top - 26, right_label, "body_semibold", 19, "@apoio", "end",
                        tracking=1.5, id="rotulo-direita"))
    out += [
        rect(bx0, top, bx1 - bx0, bottom - top, "violet", id="centro"),
        text(cx, cy + 24, center, "headline", 64, "white", "middle", id="centro-titulo"),
    ]
    for k, s in enumerate(center_caption, start=1):
        out.append(text(cx, cy + 38 + 30 * k, s, "body_medium", 24, "white", "middle",
                        id=f"centro-legenda{k}"))

    def chip(x, y, s, name):
        return [
            rect(x, y, col_w, chip_h, "@superficie", stroke="@fio", stroke_width=2, radius=8,
                 id=name),
            text(x + 28, y + chip_h / 2 + 9, s, "body_semibold", 27, "@texto", id=f"{name}-nome"),
        ]

    for k in range(n):
        y = top + k * (chip_h + gap)
        mid = y + chip_h / 2
        if k < len(left):
            out += chip(lx, y, left[k], f"esquerda{k + 1}")
            out.append(line([[lx + col_w, mid], [bx0, mid]], "@texto", 2,
                            id=f"fio-esquerda{k + 1}"))
        if k < len(right):
            out += chip(rx, y, right[k], f"direita{k + 1}")
            out.append(line([[bx1, mid], [rx, mid]], "@texto", 2, id=f"fio-direita{k + 1}"))
    if note is not None:
        out.append(text(rx + col_w, bottom + 40, note, "body", 21, "@apoio", "end", id="nota"))
    return piece("diagrama de passagem", out)


def big_number(value: str, caption: str | list[str] = (), *, top: float, height: float,
               width: float, side: str = "left", color: str = "violet",
               max_size: float = 560) -> Piece:
    """Número gigante num bloco que sangra pela borda (o placar do Uber, o "9×" da Bain).

    O bloco vai de `top` a `top + height` e mede `width` a partir da borda `side` ("left" ou
    "right"). O número ocupa o maior corpo que cabe na área do bloco dentro da margem (até
    `max_size`), centrado; a legenda (uma ou duas linhas) fica no pé do bloco. O texto vai em
    branco sobre violeta, tinta ou grafite, e em tinta sobre lilás. Bloco: `bloco`.
    """
    if side not in ("left", "right"):
        raise ValueError(f"lado desconhecido: {side!r} (use left ou right)")
    if color not in _ON_BLOCK:
        raise ValueError(f"cor do bloco {color!r}: use {sorted(_ON_BLOCK)}")
    lines = [caption] if isinstance(caption, str) else list(caption)
    if len(lines) > 2:
        raise ValueError("a legenda do número tem no máximo duas linhas")
    b = load_brand()
    w, m = b.width, b.margin
    x0 = 0 if side == "left" else w - width
    left = max(x0, m) + (0 if side == "left" else 44)
    right = min(x0 + width, w - m) - (44 if side == "left" else 0)
    if right - left < 120:
        raise ValueError(f"bloco estreito demais para o número ({width:g} px)")
    ink = b.f("headline")
    fg = _ON_BLOCK[color]
    pad, cap_size, cap_gap = 40, 26, 34
    caps_h = len(lines) * cap_gap
    area_top, area_bottom = top + pad, top + height - pad - (caps_h + 16 if lines else 0)
    # corpo: o maior que cabe na largura e na altura livres (a tinta escala com o corpo)
    x_0, y_0, x_1, y_1 = ink_box(value, ink, 100)
    if x_1 <= x_0 or y_1 <= y_0:
        raise ValueError("número sem tinta")
    size = min(max_size, 100 * (right - left) / (x_1 - x_0),
               100 * (area_bottom - area_top) / (y_1 - y_0))
    size = float(int(size))
    if size < 80:
        raise ValueError(f"bloco pequeno demais: o número ficaria com {size:g} px (mínimo 80)")
    k = size / 100
    cx = (left + right) / 2 - (x_0 + x_1) / 2 * k
    baseline = (area_top + area_bottom) / 2 - (y_0 + y_1) / 2 * k
    out = [
        rect(x0, top, width, height, color, id="bloco"),
        text(round(cx, 1), round(baseline, 1), value, "headline", size, fg, id="numero"),
    ]
    for i, s in enumerate(lines):
        y = top + height - pad - (len(lines) - 1 - i) * cap_gap
        out.append(text(left, y, s, "body_semibold", cap_size, fg, id=f"legenda{i + 1}"))
    return piece("número em bloco sangrando", out)


# ============================================================================ partes
_STAT = {  # marcador -> (corpo do número, linhas de base, corpo da 1ª linha)
    "side": (62, (50, 92, 122), 25),
    "top": (50, (82, 122, 154), 24),
    None: (62, (50, 92, 122), 25),
}


def stat(x: float, y: float, value: str, lines: list[str], *, marker: str | None = "side",
         size: float | None = None, baselines: tuple[float, ...] | None = None,
         indent: float = 28, emphasis: str = "body_semibold", line_size: float | None = None,
         value_color: str = "@texto", label: str | None = None, label_color: str = "@apoio",
         id: str | None = None) -> list[dict]:
    """Número com legenda: o átomo das listas, grades e trios de números do T2.

    Marcador quadrado violeta de 14 px no canto (`y` é o topo dele): ao lado (`"side"`, número e
    legenda recuados em `indent`), em cima (`"top"`, com `label` opcional ao lado do
    marcador, em versalete) ou nenhum (`None`). Uma ou duas linhas de legenda: a 1ª em
    `emphasis`/`@texto`, a 2ª em `body` 22 px/`@apoio`. `baselines` são as linhas de base do
    número e das legendas, medidas a partir de `y`. Devolve elementos: monte a peça com eles.
    """
    if marker not in _STAT:
        raise ValueError(f"marcador desconhecido: {marker!r}")
    if label is not None and marker != "top":
        raise ValueError("rótulo só com o marcador em cima")
    if not 1 <= len(lines) <= 2:
        raise ValueError("o número tem uma ou duas linhas de legenda")
    d_size, d_base, d_line = _STAT[marker]
    size, base, line_size = size or d_size, baselines or d_base, line_size or d_line
    tx = x + indent if marker == "side" else x

    def ident(part):
        return {"id": f"{id}-{part}"} if id else {}

    out = []
    if marker:
        out.append(rect(x, y, 14, 14, "violet", **ident("marcador")))
    if label is not None:
        out.append(text(x + 26, y + 13, label, "body_semibold", 20, label_color, tracking=1.5,
                        **ident("rotulo")))
    out.append(text(tx, y + base[0], value, "headline", size, value_color, **ident("numero")))
    styles = [(emphasis, line_size, "@texto"), ("body", 22, "@apoio")][: len(lines)]
    for k, (s, (font, fsize, color)) in enumerate(zip(lines, styles, strict=True), start=1):
        out.append(text(tx, y + base[k], s, font, fsize, color, **ident(f"linha{k}")))
    return out


# ID do componente -> função. O ID é o nome da peça que a função monta.
CATALOG = {
    "empresa e contexto": header,
    "manchete com destaque": headline,
    "rodapé com fio": footer,
    "retícula ancorada": anchored_halftone,
    "barras sangrando": bleeding_bars,
    "diagrama de passagem": pass_through_diagram,
    "número em bloco sangrando": big_number,
}
