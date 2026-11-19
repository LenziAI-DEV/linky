# /// script
# requires-python = ">=3.12"
# dependencies = ["resvg-py", "fonttools"]
# ///
"""Rodada 2 da identidade visual: menos escura, mais vibrante e com mais detalhes gráficos.

Referência de linguagem (não de marca): manchete condensada em caixa alta, palavras em blocos
de destaque, tachado, retícula de pontos (halftone), diagramas com números e conectores curvos.
Saída: docs/brand/explorations/v2-{1,2,3}.{svg,png}
"""

import math
from functools import cache
from pathlib import Path

import resvg_py
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "brand" / "explorations"
FONT_DIR = ROOT / "assets" / "fonts"
W, H = 1080, 1350
M = 72  # margem

# Paleta candidata
PAPER = "#F4F1EA"
INK = "#25222B"
CHARCOAL = "#2D2A33"
VIOLET = "#7C4DFF"
LAVENDER = "#C8B4FF"
LIME = "#D4F25A"
MUTED = "#6E6A78"

HEAD = ("Barlow Condensed", 800, "BarlowCondensed-ExtraBold.ttf")
HEAD_B = ("Barlow Condensed", 700, "BarlowCondensed-Bold.ttf")
BODY = ("Barlow", 400, "Barlow-Regular.ttf")
BODY_M = ("Barlow", 500, "Barlow-Medium.ttf")
BODY_SB = ("Barlow", 600, "Barlow-SemiBold.ttf")
BODY_B = ("Barlow", 700, "Barlow-Bold.ttf")

SOURCE = "Fonte: TechCrunch · carta aos acionistas da Airbnb (3º tri) · 05/11/2026"


@cache
def _font(file: str):
    f = TTFont(FONT_DIR / file)
    return f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm


def measure(text: str, font: tuple, size: float, spacing: float = 0) -> float:
    cmap, hmtx, upm = _font(font[2])
    width = sum(hmtx[cmap.get(ord(ch), cmap[ord("?")])][0] for ch in text)
    return width * size / upm + spacing * max(len(text) - 1, 0)


def t(x, y, text, font, size, fill, anchor="start", spacing=0, extra=""):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font[0]}" font-weight="{font[1]}" '
        f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" letter-spacing="{spacing}" {extra}>'
        f"{text}</text>"
    )


def highlight(x, y, text, font, size, box, color, pad_x=14, strike=None):
    """Palavra sobre bloco de cor (y = linha de base). strike = cor do tachado."""
    w = measure(text, font, size)
    cap = size * 0.70
    top = y - cap - size * 0.10
    h = cap + size * 0.20
    out = f'<rect x="{x - pad_x:.1f}" y="{top:.1f}" width="{w + 2 * pad_x:.1f}" height="{h:.1f}" fill="{box}"/>'
    out += t(x, y, text, font, size, color)
    if strike:
        sy = y - cap * 0.45
        out += f'<rect x="{x - 4:.1f}" y="{sy:.1f}" width="{w + 8:.1f}" height="{size * 0.07:.1f}" fill="{strike}"/>'
    return out, w


def halftone(x0, y0, cols, rows, step, color, direction="diag", rmax=None):
    """Retícula de pontos que diminui numa direção."""
    rmax = rmax or step * 0.42
    dots = []
    for i in range(cols):
        for j in range(rows):
            if direction == "diag":
                k = 1 - (i / cols + j / rows) / 2
            elif direction == "left":
                k = 1 - i / cols
            elif direction == "right":
                k = i / cols
            elif direction == "up":
                k = 1 - j / rows
            else:
                k = j / rows
            r = rmax * k**1.4
            if r > 0.6:
                dots.append(f'<circle cx="{x0 + i * step:.1f}" cy="{y0 + j * step:.1f}" r="{r:.2f}"/>')
    return f'<g fill="{color}">{"".join(dots)}</g>'


def check(x, y, size, box, mark):
    s = size
    return (
        f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="4" fill="{box}"/>'
        f'<path d="M{x + s * 0.22},{y + s * 0.52} L{x + s * 0.43},{y + s * 0.72} L{x + s * 0.80},{y + s * 0.30}" '
        f'fill="none" stroke="{mark}" stroke-width="{s * 0.14:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def company_mark(x, y, color, size=46):
    """Marcador de posição do logo da empresa (no template final: logo oficial em SVG)."""
    return t(x, y, "airbnb", BODY_B, size, color, spacing=-1)


def signature(x_right, y, name_color, tag_color):
    return t(x_right, y - 30, "Felipe Lenzi", BODY_B, 30, name_color, anchor="end") + t(
        x_right, y, "IA aplicada a negócios", BODY_M, 22, tag_color, anchor="end"
    )


def source_line(x, y, color):
    return t(x, y, SOURCE, BODY, 19, color)


def defs():
    return f"""<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{VIOLET}"/>
  </marker>
</defs>"""


# ---------------------------------------------------------------------------
def v1_paper() -> str:
    """Papel: manchete + escada de 3 decisões com números e conector curvo."""
    parts = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>', defs()]
    # retícula ancorada: nasce da faixa violeta do rodapé e some para cima (borda esquerda)
    parts.append(halftone(14, 1044, 16, 8, 24, VIOLET, "down", rmax=8))
    parts.append(company_mark(M, 140, INK))
    parts.append(t(M, 186, "anunciou seu agente de viagens para 2027", BODY_M, 28, MUTED))

    size, lh = 112, 100
    y = 310
    for line in ["AGENTE GENÉRICO", "NÃO RESOLVE", "PROBLEMA"]:
        parts.append(t(M, y, line, HEAD, size, INK, spacing=-1))
        y += lh
    hl, _ = highlight(M + 14, y, "ESPECÍFICO.", HEAD, size, VIOLET, "#FFFFFF")
    parts.append(hl)

    # escada (canto inferior direito): conectores -> blocos (de cima para baixo) -> números
    steps = [
        (410, 1040, "1", "ESPECIALIZADO", ["Monta a tela na hora:", "mapas, fotos, roteiros"]),
        (570, 880, "2", "JORNADA INTEIRA", ["Reembolso, trocas", "e suporte 24h"]),
        (730, 720, "3", "LIMITES CLAROS", ["Agente genérico", "não planeja viagem"]),
    ]
    bw, bh, depth = 250, 140, 24
    anchors = [(bx - 4, by - 4) for bx, by, *_ in steps]
    (x1, y1), (x2, y2), (x3, y3) = anchors
    parts.append(
        f'<path d="M{x1},{y1} C{x1 - 70},{y1 - 90} {x2 - 90},{y2 + 40} {x2},{y2} '
        f'M{x2},{y2} C{x2 - 70},{y2 - 90} {x3 - 90},{y3 + 40} {x3},{y3} '
        f'M{x3},{y3} C{x3 - 30},{y3 - 80} {x3 + 120},{y3 - 110} {x3 + 178},{y3 - 60}" fill="none" '
        f'stroke="{VIOLET}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow)"/>'
    )
    for bx, by, _num, title, lines in reversed(steps):
        parts.append(
            f'<path d="M{bx + bw},{by} l{depth},{depth} v{bh} l-{depth},-{depth} z" fill="{CHARCOAL}"/>'
            f'<path d="M{bx},{by + bh} l{depth},{depth} h{bw} l-{depth},-{depth} z" fill="{INK}"/>'
            f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="#FFFFFF" stroke="{INK}" stroke-width="3"/>'
        )
        parts.append(t(bx + 24, by + 52, title, HEAD_B, 33, INK))
        parts.append(t(bx + 24, by + 90, lines[0], BODY, 22, MUTED))
        parts.append(t(bx + 24, by + 117, lines[1], BODY, 22, MUTED))
    for (cx, cy), (*_, num, _t, _l) in zip(anchors, steps, strict=True):
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="25" fill="{VIOLET}" stroke="{PAPER}" stroke-width="4"/>')
        parts.append(t(cx, cy + 10, num, HEAD, 30, "#FFFFFF", anchor="middle"))
    fx, fy = 935, 560
    parts.append(
        f'<line x1="{fx}" y1="{fy}" x2="{fx}" y2="{y3 - 10}" stroke="{INK}" stroke-width="4"/>'
        f'<path d="M{fx},{fy} h84 l-20,24 l20,24 h-84 z" fill="{LIME}" stroke="{INK}" stroke-width="3"/>'
        + t(fx + 37, fy + 34, "2027", HEAD, 28, INK, anchor="middle")
    )
    parts.append(f'<rect x="0" y="1230" width="{W}" height="{H - 1230}" fill="{VIOLET}"/>')
    parts.append(source_line(M, 1300, "#EDE7FF"))
    parts.append(signature(W - M, 1302, "#FFFFFF", LIME))
    return _svg(parts)


def v2_charcoal() -> str:
    """Grafite (não preto): tachado + checklist + retícula lateral."""
    parts = [f'<rect width="{W}" height="{H}" fill="{CHARCOAL}"/>', defs()]
    parts.append(halftone(860, 120, 10, 46, 24, "#4A4554", "right", rmax=8))
    parts.append(company_mark(M, 150, "#FFFFFF"))

    size, lh = 124, 124
    y = 350
    parts.append(t(M, y, "NÃO É UM", HEAD, size, "#FFFFFF", spacing=-1))
    y += lh
    hl, _ = highlight(M + 14, y, "CHATBOT.", HEAD, size, LAVENDER, CHARCOAL, strike="#FFFFFF")
    parts.append(hl)
    y += lh
    parts.append(t(M, y, "É UM AGENTE", HEAD, size, "#FFFFFF", spacing=-1))
    y += lh
    hl, _ = highlight(M + 14, y, "ESPECIALIZADO.", HEAD, size, VIOLET, "#FFFFFF")
    parts.append(hl)

    items = [
        "Monta a tela na hora: mapas, fotos, roteiros",
        "Compara opções e mostra calendários",
        "Resolve reembolso, trocas e pagamento",
        "Suporte 24h durante a viagem",
    ]
    iy = 900
    for it in items:
        parts.append(check(M, iy - 30, 36, LAVENDER, CHARCOAL))
        parts.append(t(M + 56, iy, it, BODY_M, 34, "#F3F0FA"))
        iy += 64
    parts.append(f'<line x1="{M}" y1="1210" x2="{W - M}" y2="1210" stroke="#4A4554" stroke-width="2"/>')
    parts.append(source_line(M, 1290, "#A8A2B5"))
    parts.append(signature(W - M, 1292, "#FFFFFF", LAVENDER))
    return _svg(parts)


def v3_framed() -> str:
    """Moldura lilás com retícula violeta + painel claro; lima só nos operadores."""
    parts = [f'<rect width="{W}" height="{H}" fill="{LAVENDER}"/>', defs()]
    parts.append(halftone(10, 10, 46, 57, 24, VIOLET, "up", rmax=5))
    panel = (56, 56, W - 112, H - 112)
    parts.append(f'<rect x="{panel[0]}" y="{panel[1]}" width="{panel[2]}" height="{panel[3]}" fill="{PAPER}"/>')
    parts.append(company_mark(W / 2, 170, INK, size=44).replace('text-anchor="start"', 'text-anchor="middle"'))

    size, lh = 118, 108
    y = 340
    cx = W / 2
    for line in ["O DIFERENCIAL", "NÃO É O MODELO."]:
        parts.append(t(cx, y, line, HEAD, size, INK, anchor="middle", spacing=-1))
        y += lh
    # "É O CONTEXTO" com CONTEXTO em destaque, centralizado
    a, b = "É O ", "CONTEXTO"
    wa, wb = measure(a, HEAD, size), measure(b, HEAD, size)
    x0 = cx - (wa + wb + 14) / 2
    parts.append(t(x0, y, a, HEAD, size, INK))
    hl, _ = highlight(x0 + wa + 14, y, b, HEAD, size, VIOLET, "#FFFFFF")
    parts.append(hl)
    y += lh
    parts.append(t(cx, y, "DO NEGÓCIO.", HEAD, size, INK, anchor="middle", spacing=-1))

    # mini-diagrama: modelo genérico + contexto = agente que gera valor
    by = 880
    boxes = [(140, "MODELO", "genérico", "#FFFFFF", INK), (430, "CONTEXTO", "do negócio", "#E9E1FF", INK), (720, "AGENTE", "que gera valor", VIOLET, "#FFFFFF")]
    for i, (bx, title, sub, fill, color) in enumerate(boxes):
        parts.append(f'<rect x="{bx}" y="{by}" width="220" height="150" rx="18" fill="{fill}" stroke="{INK}" stroke-width="3"/>')
        parts.append(t(bx + 110, by + 70, title, HEAD, 40, color, anchor="middle"))
        parts.append(t(bx + 110, by + 108, sub, BODY_M, 24, color, anchor="middle"))
    for ox, op in ((395, "+"), (685, "=")):
        parts.append(f'<circle cx="{ox}" cy="{by + 75}" r="27" fill="{LIME}" stroke="{INK}" stroke-width="3"/>')
        parts.append(t(ox, by + 92, op, HEAD, 48, INK, anchor="middle"))
    parts.append(f'<line x1="{M + 30}" y1="1150" x2="{W - M - 30}" y2="1150" stroke="#D9D4C8" stroke-width="2"/>')
    parts.append(t(W / 2, 1200, SOURCE, BODY, 18, MUTED, anchor="middle"))
    parts.append(t(W / 2, 1250, "Felipe Lenzi  ·  IA aplicada a negócios", BODY_SB, 24, INK, anchor="middle"))
    return _svg(parts)


def _svg(parts) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "".join(parts) + "</svg>"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, build in enumerate((v1_paper, v2_charcoal, v3_framed), start=1):
        svg = build()
        (OUT / f"v2-{i}.svg").write_text(svg, encoding="utf-8")
        png = resvg_py.svg_to_bytes(svg_string=svg, font_dirs=[str(FONT_DIR)], skip_system_fonts=True)
        (OUT / f"v2-{i}.png").write_bytes(bytes(png))
        print(f"v2-{i}.png", len(png))


if __name__ == "__main__":
    main()
