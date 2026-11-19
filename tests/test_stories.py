"""Agrupamento de itens por fato antes da triagem (etapa H), pela interface `group_stories`
e pelo `gold digest`. Os títulos são de itens reais do T2 (06 a 10/11/2026)."""

import json
import random

from linky_agents.gold import main as gold_main
from linky_agents.stories import group_stories, shared_terms, terms

_n = 0


def item(title, at, source="verge-ai", tier="press", url=None):
    global _n
    _n += 1
    return {
        "id": f"i{_n:03d}", "source": source, "tier": tier, "title": title,
        "url": url or f"https://example.test/{_n}", "summary": "",
        "published_utc": f"2026-11-{at}:00+00:00",
    }


# fundo do lote: notícias variadas, para os pesos de raridade parecerem com um dia real
BACKGROUND = [
    item("Palo Alto Networks in talks to buy AI agent security startup Clutch", "06T06:00"),
    item("Nubank demite funcionários após IA reduzir fila de fraudes", "06T13:00", "tecnoblog"),
    item("Microsoft is winding down Oracle deal to rent AI cloud capacity", "06T18:00"),
    item("Apple capped engineers at a $200 daily AI budget", "09T05:30"),
    item("Perplexity lança agentes de IA que trabalham 24/7", "06T17:00", "canaltech"),
    item("Microsoft quer patentear IA que altera falas ao vivo", "06T15:00", "tecnoblog"),
]


def ids(story):
    return [it["id"] for it in story.items]


def find(stories, it):
    return next(s for s in stories if it["id"] in ids(s))


def test_mesma_noticia_em_ingles_e_em_portugues_vira_um_fato_com_fontes_irmas():
    en = item("Claude Code is accidentally exposing secrets all over GitHub", "09T17:24",
              "ars-ai", url="https://ars.test/claude")
    pt = item("Alerta para devs: Claude Code vaza senhas e chaves de API em massa no GitHub",
              "09T21:03", "canaltech", "br", url="https://canaltech.test/claude")
    stories = group_stories([*BACKGROUND, en, pt])
    story = find(stories, en)
    assert sorted(ids(story)) == sorted([en["id"], pt["id"]])
    assert set(story.sources) == {"https://ars.test/claude", "https://canaltech.test/claude"}
    assert len(stories) == len(BACKGROUND) + 1


def test_fatos_diferentes_da_mesma_empresa_ficam_separados():
    korea = item("NVIDIA Announces New Planned Investments in Korean Startups", "09T08:00",
                 "nvidia", "primary")
    chips = item("The US let Nvidia sell chips to an empty office in China", "08T15:43")
    spy = item("Nvidia is investigating Jensen Huang's relationship with a Chinese spy",
               "08T20:22")
    stories = group_stories([*BACKGROUND, korea, chips, spy])
    assert len({find(stories, x).representative["id"] for x in (korea, chips, spy)}) == 3


def test_caso_que_se_desdobra_em_varios_dias_segue_no_mesmo_fato():
    saga = [
        item("China reportedly recruited AI exec to spy on Jensen Huang", "06T23:00"),
        item("Megaspeed exec was recruited to spy on Nvidia CEO, according to US intelligence",
             "07T21:17", "techcrunch-ai"),
        item("Nvidia will investigate CEO Jensen Huang's relationship with possible Chinese spy",
             "08T21:00", "techcrunch-ai"),
        item("Nvidia investiga relação de Jensen Huang com empresária chinesa", "09T11:10",
             "olhar-digital", "br"),
    ]
    stories = group_stories([*BACKGROUND, *saga])
    assert len({find(stories, x).representative["id"] for x in saga}) == 1


def test_fora_da_janela_de_tempo_e_outro_fato_mas_titulo_identico_e_sempre_o_mesmo():
    a = item("Amazon will let you text Alexa your shopping list", "06T14:00")
    b = item("Amazon now lets users text Alexa to help them shop", "09T14:10", "techcrunch-ai")
    promo1 = item("Hora de renovar a sala: TVs QLED em promoção na Amazon", "06T20:18",
                  "olhar-digital")
    promo2 = item("Hora de renovar a sala: TVs QLED em promoção na Amazon", "10T14:23",
                  "olhar-digital")
    stories = group_stories([*BACKGROUND, a, b, promo1, promo2])
    assert find(stories, a) is not find(stories, b)  # 72 h depois: notícia nova
    assert find(stories, promo1) is find(stories, promo2)


def test_um_nome_de_varias_palavras_conta_como_um_termo_so():
    a = terms("Taxbit Assist: a grounded AI agent on Amazon Bedrock AgentCore")
    b = terms("Serverless MCP server for agent data lake on Amazon Bedrock AgentCore")
    assert shared_terms(a, b) == 2  # "agent" e "amazon bedrock agentcore"
    stories = group_stories([
        *BACKGROUND,
        item("Taxbit Assist: a role-aware AI agent on Amazon Bedrock AgentCore", "06T16:49",
             "aws-ml", "primary"),
        item("Greenlight Financial built an autonomous SOC on Amazon Bedrock AgentCore",
             "06T16:55", "aws-ml", "primary"),
    ])
    assert len(stories) == len(BACKGROUND) + 2


def test_representante_e_o_item_mais_parecido_com_os_demais():
    a = item("Anthropic launches new Claude Fable and Mythos 5.2 models", "09T19:00")
    b = item("Introducing Claude Fable 5.2 on AWS", "09T20:04", "aws-ml", "primary")
    c = item("Anthropic lança Claude Fable 5.2, supera Opus 5.5", "10T14:03", "canaltech", "br")
    story = find(group_stories([*BACKGROUND, a, b, c]), a)
    assert story.representative["id"] == a["id"]
    assert [it["id"] for it in story.siblings] == [b["id"], c["id"]]  # em ordem de publicação


def test_resultado_nao_depende_da_ordem_de_entrada():
    pool = [*BACKGROUND,
            item("Apple is racing to make Siri more agentic", "08T19:18"),
            item("Apple vai transformar Siri em assistente que age sozinha", "09T16:12",
                 "canaltech", "br")]
    expected = [ids(s) for s in group_stories(pool)]
    shuffled = pool[:]
    random.Random(7).shuffle(shuffled)
    assert [ids(s) for s in group_stories(shuffled)] == expected


def test_fato_pronto_para_a_triagem():
    a = item("Apple is racing to make Siri more agentic", "08T19:18")
    b = item("Apple vai transformar Siri em assistente que age sozinha", "09T16:12",
             "canaltech", "br")
    data = find(group_stories([*BACKGROUND, a, b]), a).to_json()
    json.dumps(data)  # serializável
    assert data["id"] == data["representative"]["id"]
    assert [s["id"] for s in data["siblings"]] == [b["id"]]
    assert data["sources"] == [a["url"], b["url"]]
    assert (data["first_seen"], data["last_seen"]) == (a["published_utc"], b["published_utc"])


def test_digest_mostra_um_fato_por_numero_com_as_fontes_irmas(tmp_path, capsys):
    day1, day2 = tmp_path / "2026-11-08.jsonl", tmp_path / "2026-11-09.jsonl"
    a = item("Apple is racing to make Siri more agentic", "08T19:18")
    b = item("Apple vai transformar Siri em assistente que age sozinha", "09T16:12",
             "canaltech", "br")
    day1.write_text("".join(json.dumps(x) + "\n" for x in [*BACKGROUND, a]), encoding="utf-8")
    day2.write_text(json.dumps(b) + "\n", encoding="utf-8")
    assert gold_main(["digest", str(day1), str(day2)]) == 0
    out = capsys.readouterr().out
    assert "8 itens em 7 fatos" in out
    assert "06 " + a["id"] in out  # fatos em ordem de primeira publicação (08/11 19:18)
    assert "+ " + b["id"] + " [canaltech]" in out  # a irmã, com o ID para a triagem do gold set
    assert "08 " not in out

    assert gold_main(["digest", "--flat", str(day1)]) == 0
    assert "07 " + a["id"] in capsys.readouterr().out
