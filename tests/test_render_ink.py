"""Medidas do motor x tinta real renderizada pelo resvg (kerning, descendentes)."""

import pytest
from pngink import ink_bbox

from linky_agents.render.brand import load_brand
from linky_agents.render.layouts import text
from linky_agents.render.text import measure

CASES = [
    ("headline", "ATALHO", 128, -1),
    ("headline", "AVATAR TÁ", 96, -1),
    ("headline_alt", "TAXA", 33, 0),
    ("body_medium", "Teste de programação", 26, 0),
    ("body_bold", "anthropic", 46, -1),
    ("body", "fio fluxo final", 40, -2),
    ("body", "fio fluxo final", 40, 0),
]


@pytest.mark.parametrize(("font", "word", "size", "tracking"), CASES)
def test_measured_width_matches_rendered_advance(font, word, size, tracking):
    """Com âncora no fim, a tinta começa em x_fim - largura: a largura medida tem que bater."""
    f = load_brand().f(font)
    start = ink_bbox(text(100, 200, word, f, size, "#000", tracking=tracking))[0]
    end = ink_bbox(text(1000, 200, word, f, size, "#000", anchor="end", tracking=tracking))[0]
    rendered_advance = 1000 - 100 - (end - start)
    assert measure(word, f, size, tracking) == pytest.approx(rendered_advance, abs=1.0)


@pytest.mark.parametrize("anchor", ["start", "middle", "end"])
@pytest.mark.parametrize(("font", "word", "size", "tracking"), CASES)
def test_ink_box_matches_rendered_ink(font, word, size, tracking, anchor):
    """A caixa de tinta calculada (base das verificações de colisão) é a tinta desenhada."""
    from linky_agents.render.text import ink_box

    f = load_brand().f(font)
    rx0, ry0, rx1, ry1 = ink_bbox(text(540, 200, word, f, size, "#000", anchor, tracking))
    x0, y0, x1, y1 = ink_box(word, f, size, tracking, anchor)
    assert (540 + x0, 200 + y0, 540 + x1, 200 + y1) == pytest.approx((rx0, ry0, rx1, ry1), abs=1.5)


HEADLINES = [
    "QUALQUER AÇÃO | **ATALHO**",
    "**ÊXITO** QUE | ==SÃO JOÃO==",
    "O ATALHO **QUE** | ==VAZOU== ÇQ",
]


@pytest.mark.parametrize("markup", HEADLINES)
def test_rendered_headline_ink_stays_off_other_lines_blocks(markup):
    """Pixel a pixel: tinta de uma linha nunca cai no bloco de outra linha, e a tinta de uma
    palavra destacada (acento, cedilha, rabo do Q) fica inteira dentro do próprio bloco."""
    from pngink import ink_pixels

    from linky_agents.render.layouts import fit_headline, headline_parts

    b = load_brand()
    h = fit_headline(markup, b, 936, 900, 4)
    parts = headline_parts(h, b, 72, 60, "start")
    boxes = [p for p in parts if p.kind == "box"]
    for t in (p for p in parts if p.kind == "text"):
        ink = ink_pixels(
            text(t.x, t.y, t.text, b.f("headline"), h.size, "#000", tracking=b.tracking), height=900
        )
        for box in boxes:
            inside = {
                (x, y) for x, y in ink if box.x <= x < box.x + box.w and box.y <= y < box.y + box.h
            }
            own = box.y < t.y < box.y + box.h and box.x <= t.x < box.x + box.w
            if own:
                assert inside == ink, f"{t.text}: tinta fora do próprio bloco"
            else:
                assert not inside, f"{t.text}: tinta sobre o bloco de outra linha"


def test_accent_box_padding_is_symmetric_around_rendered_ink():
    """Caso do ATALHO (T2 dia 2): sem kerning na medida, sobrava espaço à direita no bloco."""
    from linky_agents.render.layouts import fit_headline, headline_parts

    b = load_brand()
    h = fit_headline("**ATALHO** QUE VAZA", b, 936, 300, 2)
    box, word = (p for p in headline_parts(h, b, 72, 60, "start") if p.text in ("", "ATALHO"))
    x0, _, x1, _ = ink_bbox(
        text(word.x, word.y, word.text, b.f("headline"), h.size, "#000", tracking=b.tracking),
        height=400,
    )
    left, right = x0 - box.x, box.x + box.w - x1
    assert right == pytest.approx(left, abs=2.0)
