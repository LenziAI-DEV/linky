"""Frente Imagem: `make_image`, o laço de validação e a montagem, com o fornecedor falso.

Nada aqui chama API real. Os exemplos do prompt (`prompts/arte/v1.md`) também passam pelo
motor: se um deles quebrar uma regra, o agente aprenderia o erro.
"""

import copy
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from linky_agents.agents import art
from linky_agents.agents.contracts import Draft, Hook
from linky_agents.editorial import Entry
from linky_agents.harness import FakeProvider, Harness, ModelsConfig, PriceTable, Reply
from linky_agents.render.compose import Composition, check
from linky_agents.render.registry import CompositionRegistry

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "prompts" / "arte" / "v1.md"
EXAMPLES = [
    json.loads(m) for m in re.findall(r"```json\n(.*?)\n```", PROMPT.read_text("utf-8"), re.S)
]
EX_CLARO, EX_ESCURO = EXAMPLES
EX_OUTRA = copy.deepcopy(EX_CLARO)  # outra composição clara (uma peça diferente)
EX_OUTRA["pieces"][2]["name"] = "números em colunas com fio"


def harness(tmp_path, replies) -> tuple[Harness, FakeProvider]:
    config = ModelsConfig.model_validate({
        "providers": {"fake": {"kind": "fake"}},
        "budget": {"per_run_usd": 0.10, "per_day_usd": 0.30, "per_month_usd": 3.00},
        "agents": {"arte": {
            "max_input_tokens": 16000, "max_output_tokens": 8000, "timeout_s": 30,
            "chain": [{"provider": "fake", "model": "barato"}],
        }},
    })
    prices = PriceTable.model_validate(
        {"version": "teste", "models": {"fake/barato": {"input": 0.1, "output": 0.5}}}
    )
    fake = FakeProvider({"barato": [
        Reply(json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r, 5000, 1500)
        for r in replies
    ]})
    h = Harness(config, prices, ROOT / "prompts", {"fake": fake}, tmp_path / "data",
                clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC), sleep=lambda _s: None)
    return h, fake


def entry(eid="2026-11-17-ipo") -> Entry:
    return Entry(
        id=eid, title="Anthropic vai à bolsa valendo US$ 1,4 trilhão",
        event_date=date(2026, 11, 10), sources=["https://techcrunch.com/2026/11/10/anthropic-ipo"],
        what="Faixa de US$ 70 a 78 por ação.", angle="A conta da IA ficou pública.",
        pattern="P2", audience="gestor", batch="-",
        proposed_at=datetime(2026, 11, 16, 7, tzinfo=UTC),
    )


DRAFT = Draft(
    structure="E2",
    hooks=[Hook(kind="H2", text="A Anthropic vai à bolsa perdendo mais do que fatura."),
           Hook(kind="H1", text="O IPO mais caro da IA.")],
    body="Receita de US$ 33,2 bilhões e prejuízo de US$ 104 bilhões em nove meses.",
    readings=["Leitura um.", "Leitura dois."],
    tail="Ressalva. #InteligenciaArtificial",
    closing="sem_pergunta",
    headline="Vale US$ 1,4 tri e perde mais do que fatura",
)


def first_user(fake: FakeProvider, i: int) -> dict:
    text = fake.requests[i].messages[0].content
    return json.loads(text.removeprefix("## Entrada\n"))


# --------------------------------------------------------------------------- exemplos do prompt
@pytest.mark.parametrize("ex,theme", [(EX_CLARO, "claro"), (EX_ESCURO, "escuro")])
def test_exemplos_do_prompt_passam_no_motor(ex, theme):
    c = art.build(art.ArtDesign.model_validate(ex), theme, date(2026, 11, 10))
    assert check(c) == []


# --------------------------------------------------------------------------- caminho feliz
def test_make_image_devolve_png_validado_e_registra(tmp_path):
    h, fake = harness(tmp_path, [EX_CLARO])
    r = art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")

    assert r.png.startswith(b"\x89PNG\r\n\x1a\n")
    assert r.theme == "claro"  # registro vazio: começa no papel
    assert r.alt_text == EX_CLARO["alt_text"]
    c = Composition.model_validate(r.composition)
    assert check(c) == []
    footer = next(p for p in c.pieces if p.name == "rodapé com fio")
    texts = [e.text for e in footer.elements if e.kind == "text"]
    assert "10/11/2026 · valor no topo da faixa" in texts  # a data vem da pauta, não do modelo
    rec = CompositionRegistry(tmp_path / "data" / "compositions.db").recent()
    assert [x.post for x in rec] == ["2026-11-17-ipo"]

    sent = first_user(fake, 0)
    assert sent["theme"] == "claro"
    assert sent["idea"] == DRAFT.headline
    assert "hook" not in sent  # Felipe pode trocar o hook na aprovação: a imagem não depende dele
    assert sent["event_date"] == "10/11/2026"
    assert sent["post"] == DRAFT.body
    assert "previous" in sent and sent["previous"] is None
    assert art.SPECS == {"arte": art.SPEC}


def test_tema_alterna_com_o_ultimo_registrado(tmp_path):
    data = tmp_path / "data"
    h, _ = harness(tmp_path, [EX_CLARO, EX_ESCURO, EX_OUTRA])
    assert art.make_image(entry("a"), DRAFT, harness=h, data_dir=data).theme == "claro"
    assert art.make_image(entry("b"), DRAFT, harness=h, data_dir=data).theme == "escuro"
    # refazer o post "b" (ajuste de Felipe) olha o post anterior a ele, não a versão antiga
    reg = CompositionRegistry(data / "compositions.db")
    assert art.next_theme(reg, "b") == "escuro"
    assert art.next_theme(reg, "c") == "claro"
    assert art.make_image(entry("c"), DRAFT, harness=h, data_dir=data).theme == "claro"


# --------------------------------------------------------------------------- laço de validação
def test_recusa_do_motor_volta_ao_agente_com_os_motivos(tmp_path):
    bad = copy.deepcopy(EX_CLARO)
    trio = bad["pieces"][2]["elements"]
    trio[4]["x"] = 900  # o 3º número sai pela margem direita
    h, fake = harness(tmp_path, [bad, EX_CLARO])
    r = art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")

    assert r.png and len(fake.requests) == 2
    retry = first_user(fake, 1)
    assert retry["previous"]["pieces"][2]["elements"][4]["x"] == 900
    assert any("[margem]" in m and "c3" in m for m in retry["rejections"])


def test_erro_de_montagem_tambem_volta_legivel(tmp_path):
    bad = copy.deepcopy(EX_CLARO)
    bad["pieces"][0]["args"]["altura"] = 90  # argumento que o componente não tem
    bad["pieces"].append({"component": "retícula ancorada", "args": {"anchor": "nada"}})
    h, fake = harness(tmp_path, [bad, EX_CLARO])
    art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")
    reasons = first_user(fake, 1)["rejections"]
    assert any("barras sangrando" in m and "altura" in m for m in reasons)
    assert any("'nada'" in m for m in reasons)


def test_tres_recusas_levantam_art_rejected_sem_registrar(tmp_path):
    bad = copy.deepcopy(EX_CLARO)
    bad["pieces"][2]["elements"][0]["y"] = 1180  # números em cima do rodapé
    h, fake = harness(tmp_path, [bad, bad, bad])
    with pytest.raises(art.ArtRejected) as exc:
        art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")
    assert len(fake.requests) == 1 + art.MAX_REJECTIONS
    assert exc.value.reasons and exc.value.cost_usd > 0
    assert CompositionRegistry(tmp_path / "data" / "compositions.db").recent() == []


def test_repeticao_recente_e_recusada(tmp_path):
    data = tmp_path / "data"
    h, fake = harness(tmp_path, [EX_CLARO, EX_ESCURO, EX_CLARO, EX_CLARO, EX_CLARO])
    art.make_image(entry("a"), DRAFT, harness=h, data_dir=data)  # claro, composição 1
    art.make_image(entry("b"), DRAFT, harness=h, data_dir=data)  # escuro, composição 2
    # "c" é clara de novo: a composição 1 está a 2 posts, então é recusada
    with pytest.raises(art.ArtRejected) as exc:
        art.make_image(entry("c"), DRAFT, harness=h, data_dir=data)
    assert any("[repetição]" in m for m in exc.value.reasons)
    assert first_user(fake, 2)["avoid"][0].startswith("tema claro")


# --------------------------------------------------------------------------- rodapé
def test_rodape_numa_linha_quando_cabe_e_em_duas_quando_nao():
    d = date(2026, 11, 9)
    assert art.footer_lines("Tecnoblog", "", d) == ["Fonte: Tecnoblog · 09/11/2026"]
    src = "Fontes: Uber (teleconferência de resultados) e Tecnoblog"
    assert art.footer_lines(src, "citação em tradução livre", d) == [
        src, "09/11/2026 · citação em tradução livre"]
    with pytest.raises(art.DesignError, match="encurte"):
        art.footer_lines("Fonte: " + "veículo muito comprido " * 4, "", d)


# --------------------------------------------------------------------------- ocupação
def test_esquema_curto_ou_longe_da_manchete_volta_ao_agente(tmp_path):
    short = copy.deepcopy(EX_CLARO)
    del short["pieces"][2]  # sem o trio de números, o esquema acaba em y 790
    c = art.build(art.ArtDesign.model_validate(short), "claro", date(2026, 11, 10))
    assert check(c) == []  # a marca aceita...
    (reason,) = art.space_reasons(c)  # ...mas a direção de arte não
    assert "termina em y 790" in reason

    far = copy.deepcopy(EX_CLARO)
    far["pieces"][0]["args"]["top"] = 640
    c = art.build(art.ArtDesign.model_validate(far), "claro", date(2026, 11, 10))
    assert any("entre a manchete" in r for r in art.space_reasons(c))

    h, fake = harness(tmp_path, [short, EX_CLARO])
    art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")
    assert any("[espaço]" in m for m in first_user(fake, 1)["rejections"])


def test_manchete_que_nao_cabe_volta_como_motivo_e_nao_como_erro(tmp_path):
    long = copy.deepcopy(EX_CLARO)
    long["headline"] = {"markup": "O próximo usuário do Photoshop pode **não ser uma pessoa.**",
                        "max_lines": 2, "max_height": 200}
    h, fake = harness(tmp_path, [long, EX_CLARO])
    art.make_image(entry(), DRAFT, harness=h, data_dir=tmp_path / "data")
    assert any("Manchete não cabe" in m for m in first_user(fake, 1)["rejections"])
