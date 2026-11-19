import json
import struct
from pathlib import Path

import pytest
from pydantic import ValidationError

from linky_agents.render import ImageSpec, LayoutError, render_png, render_svg
from linky_agents.render.brand import load_brand
from linky_agents.render.layouts import fit_headline
from linky_agents.render.text import parse_markup, plain_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples" / "images").glob("*.json"))
SOURCE = "TechCrunch · 05/11/2026"


def _load(path: Path):
    return ImageSpec.parse(json.loads(path.read_text(encoding="utf-8")))


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_render_to_4x5_png(path):
    w, h = _png_size(render_png(_load(path)))
    assert (w, h) == (1080, 1350)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_render_is_deterministic(path):
    spec = _load(path)
    assert render_svg(spec) == render_svg(spec)


def test_examples_cover_all_layouts():
    assert {_load(p).layout for p in EXAMPLES} == {"escada", "contraste", "tese"}


def test_markup_styles_and_forced_breaks():
    units = parse_markup("Não é um | ~~chatbot.~~ | É um **agente** ==novo==")
    assert [u.style for u in units] == [
        "plain",
        "plain",
        "plain",
        "break",
        "strike",
        "break",
        "plain",
        "plain",
        "accent",
        "soft",
    ]
    assert plain_text("Não é | **isso**") == "Não é isso"


def test_forced_breaks_define_headline_lines():
    b = load_brand()
    h = fit_headline("Não é um | ~~chatbot.~~ | É um agente | **especializado.**", b, 780, 900, 5)
    texts = [" ".join(u.text for u in line) for line in h.lines]
    assert texts == ["NÃO É UM", "CHATBOT.", "É UM AGENTE", "ESPECIALIZADO."]


def test_headline_requires_accent():
    with pytest.raises(ValidationError, match="destaque"):
        ImageSpec.parse(
            {
                "layout": "contraste",
                "headline": "Sem destaque nenhum",
                "items": ["a1", "b2", "c3"],
                "source": SOURCE,
            }
        )


def test_malformed_markup_is_rejected():
    with pytest.raises(ValueError):
        parse_markup("**aberto sem fechar")


def test_source_gets_prefix():
    spec = ImageSpec.parse(
        {
            "layout": "contraste",
            "headline": "É **isso**",
            "items": ["um item", "dois itens", "três"],
            "source": SOURCE,
        }
    )
    assert spec.source.startswith("Fonte: ")


def test_item_count_limits():
    with pytest.raises(ValidationError):
        ImageSpec.parse(
            {
                "layout": "contraste",
                "headline": "É **isso**",
                "items": ["um", "dois", "três"] * 2,
                "source": SOURCE,
            }
        )


def test_overflow_raises_layout_error():
    spec = ImageSpec.parse(
        {
            "layout": "contraste",
            "headline": "**Inconstitucionalissimamente**extraordinário",
            "items": ["um item", "dois itens", "três itens"],
            "source": SOURCE,
        }
    )
    with pytest.raises(LayoutError):
        render_svg(spec)


def test_text_is_xml_escaped():
    spec = ImageSpec.parse(
        {
            "layout": "contraste",
            "company": {"name": "AT&T"},
            "headline": "É **<isso>**",
            "items": ["a < b", "c & d", "e > f"],
            "source": SOURCE,
        }
    )
    svg = render_svg(spec)
    assert "AT&amp;T" in svg and "&lt;ISSO&gt;" in svg and "c &amp; d" in svg


def test_unsupported_glyph_raises():
    spec = ImageSpec.parse(
        {
            "layout": "contraste",
            "headline": "É **isso** 🚀",
            "items": ["um item", "dois itens", "três"],
            "source": SOURCE,
        }
    )
    with pytest.raises(LayoutError, match="sem suporte"):
        render_svg(spec)


def test_headline_gap_grows_only_where_accent_meets_box():
    from linky_agents.render.brand import load_brand
    from linky_agents.render.layouts import fit_headline

    b = load_brand()
    tight = fit_headline("IA também é | **redesenho** | de tarefas.", b, 830, 640, 4)
    accented = fit_headline("IA também é | **redesenho** | de funções.", b, 830, 640, 4)
    lh = tight.size * b.line_height
    assert tight.gaps == [lh, lh]  # sem acento colado ao bloco: entrelinha da marca
    assert accented.gaps[0] == lh  # "É" na linha do bloco fica dentro do próprio bloco
    assert accented.gaps[1] > lh  # o til de "FUNÇÕES" empurra a linha para baixo do bloco
