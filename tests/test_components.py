"""Biblioteca de componentes (render.components): peças que o agente de arte combina."""

import pytest

from linky_agents.render.brand import load_brand
from linky_agents.render.components import (
    CATALOG,
    anchored_halftone,
    big_number,
    bleeding_bars,
    footer,
    header,
    headline,
    pass_through_diagram,
    piece,
    rect,
    stat,
)
from linky_agents.render.compose import Composition, check


def _alone(*pieces, theme="claro"):
    return Composition(theme=theme, pieces=list(pieces))


@pytest.mark.parametrize("theme", ["claro", "escuro"])
def test_header_names_the_company_above_the_context_and_passes_the_rules(theme):
    p = header("nubank", "equipe de investigação de fraudes")
    assert p.name == "empresa e contexto"
    company, context = p.elements
    assert (company.text, company.x, company.y) == ("nubank", 72, 140)
    assert (context.text, context.y) == ("equipe de investigação de fraudes", 186)
    assert check(_alone(p, theme=theme)) == []


def test_headline_starts_below_the_header_at_the_margin():
    p = headline("Mesma nota. | **Metade** do custo.")
    assert p.name == "manchete com destaque"
    (h,) = p.elements
    assert (h.x, h.top, h.max_width, h.max_lines) == (72, 236, 936, 2)
    assert check(_alone(header("nubank", "fraudes"), p)) == []


def test_footer_with_one_source_centers_it_beside_the_signature():
    p = footer("Fonte: Anthropic e TechCrunch · 09/11/2026")
    assert p.name == "rodapé com fio"
    rule, source, name, tagline = p.elements
    assert rule.points == [(72, 1210), (1008, 1210)]
    assert (source.y, name.text, name.y) == (1283, "Felipe Lenzi", 1262)
    assert (tagline.text, tagline.size, tagline.y, tagline.anchor) == (
        "IA aplicada a negócios", 24, 1296, "end")
    assert check(_alone(p)) == []


def test_footer_with_two_sources_stacks_them():
    p = footer(["Fontes: Adobe e TechCrunch", "04 e 10/11/2026"], tagline_size=22)
    _, first, second, _, tagline = p.elements
    assert (first.y, second.y, tagline.y) == (1262, 1290, 1294)


def test_violet_signature_disappears_on_charcoal_and_lavender_does_not():
    on_dark = check(_alone(footer("Fonte: Uber"), theme="escuro"))
    assert [v.key for v in on_dark] == ["contraste:rodapé com fio/tagline"]
    assert check(_alone(footer("Fonte: Uber", tagline_color="lavender"), theme="escuro")) == []


def _band():
    return piece("faixa", [rect(0, 560, 700, 170, "violet", id="faixa")])


def test_anchored_halftone_grows_from_the_anchor_to_the_canvas_edge():
    band = _band()
    p = anchored_halftone(band, "faixa", step=20)
    assert p.name == "retícula ancorada"
    (h,) = p.elements
    assert (h.x, h.y, h.w, h.h) == (700, 560, 380, 170)
    assert (h.grow_from, h.anchor, h.fade_steps) == ("left", "faixa", 19)
    assert check(_alone(band, p)) == []


def test_anchored_halftone_can_use_a_slice_of_the_anchor_and_go_down():
    band = _band()
    p = anchored_halftone(band, "faixa", side="bottom", start=72, extent=200)
    (h,) = p.elements
    assert (h.x, h.y, h.w, h.h, h.grow_from, h.fade_steps) == (72, 730, 200, 620, "top", 31)
    assert check(_alone(band, p)) == []


def test_anchored_halftone_needs_an_anchor_that_exists():
    with pytest.raises(ValueError, match="sem elemento 'bloco'"):
        anchored_halftone(_band(), "bloco")


def test_stat_with_side_marker_indents_the_number_and_its_two_lines():
    els = piece("sinais", stat(520, 550, "~500", ["pedidos no Uber Eats", "na semana"],
                               id="sinal1")).elements
    marker, value, first, second = els
    assert (marker.x, marker.y, marker.w, marker.fill) == (520, 550, 14, "violet")
    assert (value.x, value.y, value.size, value.font) == (548, 600, 62, "headline")
    assert (first.y, first.font, second.y, second.fill) == (642, "body_semibold", 672, "@apoio")
    assert [e.id for e in els] == ["sinal1-marcador", "sinal1-numero", "sinal1-linha1",
                                   "sinal1-linha2"]


def test_stat_with_top_marker_and_label_sits_in_a_column():
    marker, label, value, only = piece("trio", stat(
        72, 900, "US$ 81 bi", ["receita anualizada"], marker="top", label="RECEITA")).elements
    assert (marker.x, value.x, value.y, value.size, only.y) == (72, 72, 982, 50, 1022)
    assert (label.text, label.x, label.y, label.fill) == ("RECEITA", 98, 913, "@apoio")


def test_stat_without_marker_is_just_number_and_caption():
    value, caption = piece("números", stat(690, 570, "2.539", ["credenciais"], marker=None,
                                     baselines=(58, 90), size=70)).elements
    assert (value.x, value.y, caption.y) == (690, 628, 660)


def test_stats_side_by_side_pass_the_rules():
    trio = piece("trio de números", [
        *stat(72, 900, "US$ 81 bi", ["receita anualizada", "no fim de outubro"], marker="top"),
        *stat(412, 900, "US$ 901 bi", ["em compromissos", "de computação"], marker="top"),
    ])
    assert check(_alone(trio)) == []


def test_bleeding_bars_are_in_true_scale_and_write_inside_when_there_is_room():
    p = bleeding_bars([(33.2, "US$ 33,2 bi", "de receita", "lavender"),
                       (104, "US$ 104 bi", "de prejuízo", "violet")],
                      top=556, label="NOS NOVE PRIMEIROS MESES DE 2026")
    assert p.name == "barras sangrando"
    label, short, s_value, s_caption, long, l_value, l_caption = p.elements
    assert (label.y, short.x, short.w, long.w, long.y) == (530, 0, 255, 800, 690)
    # curta: número e legenda depois da barra, em cores do tema
    assert (s_value.x, s_value.y, s_value.fill, s_caption.y) == (283, 614, "@texto", 646)
    # longa: dentro da barra, em branco, legenda logo depois do número
    assert (l_value.x, l_value.y, l_value.fill) == (72, 756, "white")
    assert (l_caption.x, l_caption.y) == (308, 751)
    assert check(_alone(p)) == []


def test_pass_through_diagram_links_each_side_to_the_central_block():
    p = pass_through_diagram(["ChatGPT", "Claude", "Gemini", "Outros agentes"],
                             ["Photoshop", "Illustrator", "Premiere", "After Effects"],
                             "MCP", center_caption=["o padrão de", "conexão"],
                             left_label="AGENTES", right_label="ARQUIVOS NATIVOS",
                             note="camadas seguem editáveis")
    assert p.name == "diagrama de passagem"
    els = {e.id: e for e in p.elements}
    gate = els["centro"]
    assert (gate.x, gate.y, gate.w, gate.h, gate.fill) == (452, 580, 176, 372, "violet")
    assert (els["centro-titulo"].x, els["centro-titulo"].y) == (540, 790)
    assert [els[f"centro-legenda{k}"].y for k in (1, 2)] == [834, 864]
    assert (els["esquerda1"].x, els["direita1"].x, els["esquerda4"].y) == (73, 729, 880)
    assert (els["esquerda1-nome"].x, els["esquerda1-nome"].y) == (101, 625)
    assert els["fio-esquerda1"].points == [(351, 616), (452, 616)]
    assert els["fio-direita1"].points == [(628, 616), (729, 616)]
    assert (els["nota"].x, els["nota"].y, els["nota"].anchor) == (1007, 992, "end")
    assert check(_alone(p)) == []


def test_catalog_ids_are_the_names_of_the_pieces_they_build():
    samples = {
        header: ("x", "y"), headline: ("**x**",), footer: ("Fonte: x",),
        anchored_halftone: (_band(), "faixa"),
        bleeding_bars: ([(1, "1", "um", "violet")],),
        pass_through_diagram: (["a"], ["b"], "c"),
        big_number: ("4",),
    }
    assert set(CATALOG.values()) == set(samples)
    for component_id, build in CATALOG.items():
        kw = {"top": 600} if build is bleeding_bars else {}
        if build is big_number:
            kw = {"top": 560, "height": 500, "width": 400}
        assert build(*samples[build], **kw).name == component_id


@pytest.mark.parametrize("theme", ["claro", "escuro"])
@pytest.mark.parametrize("side", ["left", "right"])
def test_big_number_fills_the_bleeding_block_and_passes_the_rules(theme, side):
    from linky_agents.render.text import ink_box

    p = big_number("9×", ["mais escala com", "a diretoria"], top=600, height=520, width=460,
                   side=side)
    els = {e.id: e for e in p.elements}
    block, number = els["bloco"], els["numero"]
    assert block.x == (0 if side == "left" else 1080 - 460)  # sangra pela borda
    x0, y0, x1, y1 = ink_box(number.text, load_brand().f("headline"), number.size)
    assert number.x + x0 >= 72 and number.x + x1 <= 1008  # tinta dentro da margem
    assert block.y < number.y + y0 and number.y + y1 < els["legenda1"].y - 26
    assert number.size >= 200
    assert check(_alone(p, theme=theme)) == []


def test_big_number_refuses_a_block_too_small_for_it():
    with pytest.raises(ValueError, match="pequeno demais"):
        big_number("1.994", top=600, height=110, width=300)
    with pytest.raises(ValueError, match="lado"):
        big_number("4", top=600, height=500, width=400, side="top")


def test_bleeding_bars_write_ink_inside_a_lavender_bar():
    p = bleeding_bars([(95, "95%", "usam IA", "lavender"), (80, "80%", "escalaram", "violet")],
                      top=560)
    els = {e.id: e for e in p.elements}
    assert els["barra1-numero"].fill == "ink" and els["barra2-numero"].fill == "white"
    assert check(_alone(p)) == []
