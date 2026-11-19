"""Motor de composição: o JSON que o agente de arte envia, validado pelas regras da marca."""

import pytest

from linky_agents.render.compose import (
    Composition,
    CompositionRejected,
    check,
    signature,
    to_png,
    to_svg,
)


def comp(*pieces, background="paper"):
    return Composition.model_validate(
        {
            "background": background,
            "pieces": [{"name": name, "elements": list(els)} for name, *els in pieces],
        }
    )


def rect(x, y, w, h, fill="ink", **kw):
    return {"kind": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, **kw}


def txt(x, y, s, font="body", size=26, fill="ink", **kw):
    return {
        "kind": "text",
        "x": x,
        "y": y,
        "text": s,
        "font": font,
        "size": size,
        "fill": fill,
        **kw,
    }


def rules(c):
    return sorted({v.rule for v in check(c)})


FOOTER = (
    "rodapé com fio",
    {"kind": "line", "points": [[72, 1210], [1008, 1210]], "stroke": "rule_on_paper", "width": 2},
    txt(72, 1283, "Fonte: TechCrunch · 09/11/2026", size=19, fill="muted_on_paper"),
)


# ----------------------------------------------------------------------------- render
def test_valid_composition_renders_png_4x5():
    c = comp(("bloco", rect(72, 300, 400, 200, fill="violet")), FOOTER)
    assert check(c) == []
    png = to_png(c)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert to_svg(c) == to_svg(c)  # determinístico


def test_rejected_composition_explains_every_reason():
    c = comp(("bloco", rect(30, 300, 400, 200, fill="violet")))
    with pytest.raises(CompositionRejected) as err:
        to_svg(c)
    assert "bloco" in str(err.value) and "margem" in str(err.value)
    assert [v.rule for v in err.value.violations] == ["margem"]


def test_known_findings_can_be_accepted_explicitly():
    c = comp(("bloco", rect(30, 300, 400, 200, fill="violet", id="caixa")))
    [v] = check(c)
    assert v.key == "margem:bloco/caixa"
    assert to_svg(c, known=[v.key]).startswith("<svg")


# ----------------------------------------------------------------------------- tokens
def test_only_brand_color_tokens():
    c = comp(("bloco", rect(72, 300, 100, 100, fill="#FF0000")))
    [v] = check(c)
    assert v.rule == "marca" and "#FF0000" in v.message


def test_only_brand_fonts():
    c = comp(("texto", txt(72, 300, "Olá", font="Comic Sans")))
    assert rules(c) == ["marca"]


def test_unsupported_glyph_is_brand_violation():
    c = comp(("texto", txt(72, 300, "foguete 🚀")))
    assert rules(c) == ["marca"]


def test_unknown_element_kind_is_contract_error():
    with pytest.raises(ValueError):
        comp(("x", {"kind": "svg", "markup": "<svg/>"}))


# ----------------------------------------------------------------------------- margens
def test_text_must_stay_inside_72px_margin():
    c = comp(("texto", txt(40, 300, "Fora da margem")))
    assert rules(c) == ["margem"]


def test_text_on_the_right_edge_is_measured_with_real_width():
    # 26 px: ~"Uma frase comprida que encosta" passa de 1008 a partir de x=700
    c = comp(("texto", txt(700, 300, "Uma frase comprida que encosta na borda")))
    assert rules(c) == ["margem"]


def test_shapes_inside_margin_or_bleeding_are_fine():
    band = rect(0, 1230, 1080, 120, fill="violet")  # faixa que sangra
    assert check(comp(("faixa", band))) == []


def test_shape_stopping_inside_the_margin_is_rejected():
    almost = rect(20, 1230, 1060, 120, fill="violet")  # nem respeita nem sangra à esquerda
    [v] = check(comp(("faixa", almost)))
    assert v.rule == "margem" and "sangr" in v.message


# ----------------------------------------------------------------------------- assinatura
def test_signature_ignores_text_and_position_but_not_pieces():
    a = comp(("Manchete com destaque", txt(72, 300, "A")), ("pilhas", rect(72, 400, 50, 50)))
    b = comp(("pilhas", rect(600, 900, 80, 20)), ("manchete com destaque", txt(72, 300, "B")))
    c = comp(("manchete com destaque", txt(72, 300, "A")), ("linha do tempo", rect(72, 400, 5, 5)))
    assert signature(a) == signature(b)
    assert signature(a) != signature(c)
    assert signature(a) != signature(comp(*_pieces(a), background="charcoal"))


def _pieces(c):
    return [(p.name, *[e.model_dump(exclude_none=True) for e in p.elements]) for p in c.pieces]


def test_footer_piece_lives_in_the_footer_band_below_the_margin():
    """Fonte e assinatura ficam na faixa do rodapé (convenção aprovada desde a v1)."""
    sig = txt(
        1008, 1294, "IA aplicada a negócios", font="body_medium", size=22, fill="ink", anchor="end"
    )
    assert check(comp(("rodapé com fio", sig))) == []
    assert rules(comp(("assinatura", sig))) == ["margem"]  # fora da peça de rodapé, não
    too_low = txt(72, 1335, "Fonte: X · 09/11/2026", size=19, fill="muted_on_paper")
    assert rules(comp(("rodapé com fio", too_low))) == ["margem"]


# ----------------------------------------------------------------------------- colisão
def test_text_sitting_inside_a_block_is_fine():
    block = rect(72, 300, 500, 80, fill="violet")
    label = txt(96, 352, "Dentro do bloco", font="body_bold", size=30, fill="white")
    assert check(comp(("selo", block, label))) == []


def test_text_half_out_of_its_block_collides():
    block = rect(72, 300, 200, 80, fill="violet")
    label = txt(96, 352, "Texto que passa do bloco", font="body_bold", size=30, fill="white")
    [v] = [v for v in check(comp(("selo", block, label))) if v.rule == "colisão"]
    assert v.where == "selo/text2" and "borda" in v.message


def test_overlapping_texts_collide():
    a = txt(72, 300, "Primeira linha", size=30)
    b = txt(90, 310, "Segunda linha", size=30)
    assert rules(comp(("texto a", a), ("texto b", b))) == ["colisão"]


def test_line_crossing_text_collides():
    line = {"kind": "line", "points": [[60 + 40, 280], [400, 320]], "stroke": "violet", "width": 4}
    assert rules(comp(("texto", txt(72, 310, "Linha que atravessa", size=30)), ("fio", line))) == [
        "colisão"
    ]


def test_shape_drawn_over_text_collides():
    over = rect(100, 280, 50, 50, fill="lavender")
    [v] = check(comp(("texto", txt(72, 310, "Coberto", size=30)), ("caixa", over)))
    assert v.rule == "colisão" and "por cima" in v.message


def test_text_over_halftone_collides():
    dots = {
        "kind": "halftone",
        "x": 0,
        "y": 250,
        "w": 300,
        "h": 100,
        "color": "lavender",
        "grow_from": "left",
        "anchor": "canvas",
    }
    [v] = check(comp(("textura", dots), ("texto", txt(100, 310, "Sobre os pontos", size=30))))
    assert v.rule == "colisão" and "retícula" in v.message


def test_strikethrough_is_part_of_its_text():
    t = txt(72, 310, "Analisava caso a caso", fill="muted_on_paper", strike="muted_on_paper")
    assert check(comp(("linha do tempo", t))) == []


def test_headline_lines_never_reach_the_blocks_of_other_lines():
    """Acento, cedilha e o rabo do Q de uma linha não tocam o bloco da linha vizinha."""
    for markup in [
        "QUALQUER AÇÃO | **ATALHO**",
        "**ÊXITO** QUE | ==SÃO JOÃO==",
        "AQUI | ~~ÇQ~~ | **Q**",
    ]:
        head = {
            "kind": "headline",
            "markup": markup,
            "x": 72,
            "top": 240,
            "max_width": 900,
            "max_height": 600,
            "max_lines": 4,
        }
        assert check(comp(("manchete", head))) == [], markup


# ----------------------------------------------------------------------------- contraste
def test_small_text_needs_4_5_to_1():
    tag = txt(72, 300, "IA aplicada a negócios", font="body_medium", size=22, fill="violet")
    [v] = check(comp(("assinatura", tag)))
    assert v.rule == "contraste" and "4.27" in v.message and "4.5" in v.message


def test_large_text_needs_3_to_1():
    tag = txt(72, 300, "COM A IA", font="headline_alt", size=26, fill="violet")
    assert check(comp(("linha do tempo", tag))) == []


def test_contrast_is_measured_against_what_is_right_below_the_text():
    block = rect(72, 260, 600, 80, fill="violet")
    ok = txt(96, 310, "Texto claro", font="body_bold", size=30, fill="white")
    bad = txt(96, 310, "Texto apagado", font="body_bold", size=30, fill="lavender")
    assert check(comp(("selo", block, ok))) == []
    assert rules(comp(("selo", block, bad))) == ["contraste"]
    assert rules(comp(("fundo", txt(72, 310, "Branco no papel", size=30, fill="white")))) == [
        "contraste"
    ]


# ----------------------------------------------------------------------------- lima
def test_small_lime_details_are_fine():
    tag = rect(400, 700, 104, 48, fill="lime", stroke="ink", stroke_width=3)
    label = txt(452, 732, "-80%", font="headline", size=34, anchor="middle")
    assert check(comp(("etiqueta", tag, label))) == []


def test_lime_area_is_limited():
    [v] = check(comp(("faixa", rect(72, 700, 300, 120, fill="lime"))))
    assert v.rule == "lima" and "detalhes pequenos" in v.message


def test_long_thin_lime_shape_is_not_a_detail():
    [v] = check(comp(("fio", rect(72, 700, 600, 8, fill="lime"))))
    assert v.rule == "lima"


def test_lime_total_is_limited():
    tags = [rect(100 + i * 160, 700, 120, 70, fill="lime") for i in range(5)]
    assert [v.where for v in check(comp(("etiquetas", *tags)))] == ["composição"]


# ----------------------------------------------------------------------------- retícula
def halftone(**kw):
    base = {"kind": "halftone", "color": "lavender", "step": 24, "rmax": 7}
    return {**base, **kw}


def test_halftone_born_from_canvas_edge_and_bleeding_is_fine():
    h = halftone(x=-6, y=740, w=168, h=384, grow_from="left", anchor="canvas")
    assert check(comp(("retícula", h))) == []


def test_halftone_anchored_on_canvas_must_reach_the_edge():
    h = halftone(x=300, y=740, w=168, h=384, grow_from="left", anchor="canvas")
    [v] = [v for v in check(comp(("retícula", h))) if v.rule == "retícula"]
    assert "borda" in v.message


def test_halftone_grows_from_its_structure():
    box = rect(300, 1090, 300, 70, fill="ink", id="repositorio")
    ok = halftone(x=613, y=1092, w=467, h=66, grow_from="left", anchor="repositorio")
    assert check(comp(("repositório", box), ("vazamento", ok))) == []


def test_floating_halftone_is_rejected():
    box = rect(300, 1090, 300, 70, fill="ink", id="repositorio")
    far = halftone(x=700, y=1092, w=380, h=66, grow_from="left", anchor="repositorio")
    [v] = check(comp(("repositório", box), ("vazamento", far)))
    assert v.rule == "retícula" and "solta" in v.message


def test_halftone_dots_shrink_away_from_the_anchor():
    from linky_agents.render.compose import to_svg

    c = comp(("retícula", halftone(x=-6, y=740, w=168, h=48, grow_from="left", anchor="canvas")))
    import re

    radii = [float(r) for r in re.findall(r'<circle cx="[\d.]+" cy="752" r="([\d.]+)"', to_svg(c))]
    assert radii == sorted(radii, reverse=True) and radii[0] == pytest.approx(7)


def test_halftone_must_be_low_contrast_texture():
    h = halftone(x=-6, y=740, w=168, h=384, grow_from="left", anchor="canvas", color="violet")
    [v] = check(comp(("retícula", h)))
    assert v.rule == "retícula" and "textura" in v.message


@pytest.mark.parametrize("width", [900, 936])
@pytest.mark.parametrize("max_lines", [2, 3])
@pytest.mark.parametrize(
    "markup",
    [
        "QUEM GANHA | **É O ATALHO**",
        "QUALIDADE | ==SÃO JOÃO==",
        "QUALQUER UM | ~~QUASE NADA~~",
        "**QUEM PAGA** | ==A CONTA== | QUE",
    ],
)
def test_q_tail_never_reaches_the_block_below(markup, max_lines, width):
    """Relato do T2 dia 2 (rascunho perdido): não reproduzido no motor antigo numa varredura
    de 900 manchetes; fica coberto aqui, no tamanho que o ajuste escolhe no limite."""
    head = {
        "kind": "headline",
        "markup": markup,
        "x": 72,
        "top": 240,
        "max_width": width,
        "max_height": 300 if max_lines == 2 else 420,
        "max_lines": max_lines,
    }
    assert [v for v in check(comp(("manchete", head))) if v.rule == "colisão"] == []


# ----------------------------------------------------------------------------- revisão
def test_text_crossing_a_ring_collides():
    ring = {"kind": "circle", "cx": 540, "cy": 600, "r": 200, "stroke": "violet", "stroke_width": 6}
    t = txt(540, 440, "TESTE TESTE TESTE", size=40, anchor="middle")
    assert "colisão" in rules(comp(("anel", ring), ("texto", t)))


def test_text_inside_a_ring_is_fine():
    ring = {"kind": "circle", "cx": 540, "cy": 600, "r": 200, "stroke": "violet", "stroke_width": 6}
    assert (
        check(comp(("anel", ring), ("texto", txt(540, 610, "DENTRO", size=40, anchor="middle"))))
        == []
    )


def test_lime_outline_counts_only_its_stroke():
    ring = {"kind": "circle", "cx": 200, "cy": 300, "r": 60, "stroke": "lime", "stroke_width": 4}
    frame = rect(400, 300, 100, 100, stroke="lime", stroke_width=4)
    assert check(comp(("detalhes", ring, frame))) == []


def test_circle_without_paint_is_contract_error():
    with pytest.raises(ValueError):
        comp(("x1", {"kind": "circle", "cx": 200, "cy": 300, "r": 60}))


def test_registry_window_zero_is_respected(tmp_path):
    from linky_agents.render.registry import CompositionRegistry

    reg = CompositionRegistry(tmp_path / "c.db", window=0)
    c = comp(("peça", rect(72, 300, 50, 50)))
    reg.record("a", c)
    assert reg.check("b", c) == []


def test_text_outside_a_triangle_is_measured_against_the_paper():
    tri = {"kind": "polygon", "points": [[72, 72], [1008, 72], [72, 1100]], "fill": "violet"}
    t = txt(700, 1000, "Branco fora", font="body_bold", size=30, fill="white")
    assert "contraste" in rules(comp(("forma", tri), ("texto", t))) or "colisão" in rules(
        comp(("forma", tri), ("texto", t))
    )


def test_text_in_the_cut_corner_of_a_rounded_block_is_not_on_the_block():
    block = rect(72, 300, 400, 400, fill="violet", radius=150)
    t = txt(80, 330, "Canto", font="body_bold", size=30, fill="white")
    assert rules(comp(("selo", block, t))) != []


def test_lime_stroke_and_lime_background_count_as_lime():
    big = rect(100, 300, 800, 800, fill="violet", stroke="lime", stroke_width=40)
    assert "lima" in rules(comp(("moldura", big)))
    assert "lima" in rules(comp(("peça", rect(72, 300, 50, 50)), background="lime"))


def test_halftone_needs_a_real_structure_as_anchor():
    dot = {"kind": "circle", "cx": 200, "cy": 300, "r": 3, "fill": "ink", "id": "ponto"}
    big = halftone(x=203, y=150, w=700, h=700, grow_from="left", anchor="ponto")
    assert "retícula" in rules(comp(("ponto", dot), ("textura", big)))
    label = txt(100, 300, "Rótulo", id="rotulo")
    near = halftone(x=200, y=270, w=300, h=48, grow_from="left", anchor="rotulo")
    assert "retícula" in rules(comp(("rótulo", label), ("textura", near)))


# ----------------------------------------------------------------------------- tema escuro
def themed(*pieces, theme):
    return Composition.model_validate(
        {"theme": theme, "pieces": [{"name": n, "elements": list(els)} for n, *els in pieces]}
    )


def test_dark_theme_sets_charcoal_background_and_resolves_roles():
    t = txt(72, 300, "Texto do tema", size=30, fill="@texto")
    dark = themed(("texto", t), theme="escuro")
    assert check(dark) == []
    assert 'fill="#2D2A33"' in to_svg(dark)  # fundo grafite
    assert 'fill="#F3F0FA"' in to_svg(dark)  # @texto = text_on_charcoal
    light = themed(("texto", t), theme="claro")
    assert 'fill="#F4F1EA"' in to_svg(light) and 'fill="#25222B"' in to_svg(light)


def test_dark_theme_headline_defaults_read_on_charcoal():
    head = {
        "kind": "headline",
        "markup": "Texto | **claro**",
        "x": 72,
        "top": 240,
        "max_width": 900,
        "max_height": 300,
        "max_lines": 2,
    }
    assert check(themed(("manchete", head), theme="escuro")) == []


def test_ink_on_charcoal_is_caught_by_contrast():
    t = txt(72, 300, "Tinta escura no grafite", size=30, fill="ink")
    assert rules(themed(("texto", t), theme="escuro")) == ["contraste"]


def test_unknown_theme_role_is_brand_violation():
    t = txt(72, 300, "Papel?", size=30, fill="@inexistente")
    assert rules(themed(("texto", t), theme="escuro")) == ["marca"]


def test_theme_is_part_of_the_signature():
    t = txt(72, 300, "A", size=30, fill="@texto")
    assert signature(themed(("texto", t), theme="escuro")) != signature(
        themed(("texto", t), theme="claro")
    )


def test_halftone_fade_steps_sets_where_dots_vanish():
    import re

    h = halftone(
        x=0,
        y=740,
        w=240,
        h=24,
        grow_from="left",
        anchor="canvas",
        rmax=5,
        gamma=1,
        min_dot=0,
        fade_steps=10,
    )
    radii = [float(r) for r in re.findall(r' r="([\d.]+)"', to_svg(comp(("textura", h))))]
    assert radii == pytest.approx([5 * (1 - i / 10) for i in range(10)])
