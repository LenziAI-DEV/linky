"""Frente Post (agents/post.py), testada com o fornecedor falso: nada aqui chama API real."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest

from linky_agents.agents import post
from linky_agents.agents.contracts import Draft, Hook
from linky_agents.editorial import Entry, Post
from linky_agents.harness import (
    FakeProvider,
    Harness,
    ModelsConfig,
    PriceTable,
    ProviderError,
    Reply,
    WebDocument,
    load_models,
)
from linky_agents.harness.core import ROOT
from linky_agents.harness.prompt import load_prompt

NOON = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
UBER = post.Company(name="Uber", id=1815218)
BAIN = post.Company(name="Bain & Company", id=2114, aliases=["Bain"])
COMPANIES = [UBER, BAIN]

BODY = (
    "O número saiu na apresentação de resultados do 3º trimestre. No Uber Eats, foram cerca "
    "de 500 pedidos na semana do Halloween, uma das mais movimentadas do ano.\n\n"
    "O CEO, que já comandou a Expedia, disse por que não quer um intermediário: lá, dependia "
    "\"dos Googles do mundo\", e não quer voltar a isso. No Brasil, a dona da 99 disse ao "
    "Tecnoblog que o volume pedido por agentes é insignificante."
)
READINGS = [
    "O ponto que importa: antes de preparar a empresa para ser comprada por agentes, vale "
    "perguntar se o seu cliente já quer delegar a compra. Por enquanto, os dados dizem que não.",
    "Para quem decide: agente de IA ainda não é canal de venda. É um teste barato para "
    "acompanhar de perto, com métrica, sem mexer na operação.",
]
TAIL = (
    "Uma ressalva: são números da própria Uber, que tem todo o interesse em mostrar que o app "
    "continua sendo a porta de entrada.\n\n"
    "Você deixaria um agente pedir seu almoço hoje? Sim ou ainda não?\n\n#AgentesDeIA"
)
HOOKS = [
    {"kind": "H2", "text": "Agentes de IA de outras empresas pediram 4 corridas na Uber. Quatro."},
    {"kind": "H1", "text": "A Uber recebeu 4 corridas pedidas por agentes de IA. A dona da 99 "
                           "chama o volume de insignificante."},
    {"kind": "H5", "text": "O cliente ainda não quer que um agente peça o carro por ele."},
]


def writer_json(**over) -> str:
    data = {
        "structure": "E1",
        "body": BODY,
        "readings": READINGS,
        "tail": TAIL,
        "closing": "escolha",
        "hooks": HOOKS,
        "headline": "Agentes pediram 4 corridas na Uber",
        "main_company": "Uber",
    }
    data.update(over)
    return json.dumps(data, ensure_ascii=False)


def check_json(*problems) -> str:
    return json.dumps({"problems": list(problems)}, ensure_ascii=False)


GRAVE = {"part": "body", "excerpt": "cerca de 500 pedidos", "issue": "a fonte diz 400",
         "severity": "grave"}
LEVE = {"part": "tail", "excerpt": "números da própria Uber", "issue": "não deu para conferir",
        "severity": "leve"}


def reply(text: str, inp=6000, out=900) -> Reply:
    return Reply(text=text, input_tokens=inp, output_tokens=out)


def harness(tmp_path, writer: list, checker: list) -> tuple[Harness, FakeProvider]:
    agent = {"max_input_tokens": 14000, "max_output_tokens": 3000, "max_doc_tokens": 1600,
             "timeout_s": 30}
    config = ModelsConfig.model_validate({
        "providers": {"fake": {"kind": "fake"}},
        "budget": {"per_run_usd": 0.15, "per_day_usd": 1.0, "per_month_usd": 3.0,
                   "warn_ratio": 0.8, "timezone": "America/Sao_Paulo"},
        "retry": {"max_retries": 0, "backoff_s": 0},
        "agents": {
            "redacao": {**agent, "chain": [{"provider": "fake", "model": "escritor"}]},
            "checagem": {**agent, "chain": [{"provider": "fake", "model": "checador"}]},
        },
    })
    prices = PriceTable.model_validate({"version": "teste", "models": {
        "fake/escritor": {"input": 2.0, "output": 10.0},
        "fake/checador": {"input": 0.1, "output": 0.5},
    }})
    fake = FakeProvider({"escritor": writer, "checador": checker})
    h = Harness(config, prices, ROOT / "prompts", {"fake": fake}, tmp_path / "data",
                clock=lambda: NOON, sleep=lambda _s: None)
    return h, fake


def entry(**over) -> Entry:
    data = dict(
        id="uber-agentes", title="Agentes de IA quase não pedem corridas na Uber",
        event_date=date(2026, 11, 9), batch="2026-11-10", proposed_at=NOON,
        what="A Uber registrou 4 corridas pedidas por agentes de IA externos.",
        why="A economia agêntica ainda não chegou ao consumidor.",
        angle="Antes de preparar a empresa para agentes, pergunte se o cliente quer delegar.",
        pattern="P2", audience="gestor",
        sources=["https://tecnoblog.net/a"],
    )
    data.update(over)
    return Entry(**data)


DOCS = [WebDocument(id="fonte1", source="Tecnoblog", url="https://tecnoblog.net/a",
                    title="Dona da 99", text="A Uber registrou 4 corridas pedidas por agentes.")]


def requests_to(fake: FakeProvider, model: str):
    return [r for r in fake.requests if r.model == model]


def user_input(request) -> dict:
    text = request.messages[0].content
    raw = text.split("## Entrada\n", 1)[1].split("\n\n<documentos_nao_confiaveis>", 1)[0]
    return json.loads(raw)


# ===================================================================== contratos e config
def test_specs_expose_both_agents_with_prompts_v1_in_the_repo():
    assert set(post.SPECS) == {"redacao", "checagem"}
    for spec in post.SPECS.values():
        assert spec.version == "v1"
        assert load_prompt(ROOT / "prompts", spec.name, spec.version).text.strip()


def test_models_yaml_starts_the_writer_on_sonnet_and_checks_with_another_provider():
    cfg = load_models(ROOT / "config" / "models.yaml")
    writer = cfg.agent("redacao").chain
    checker = cfg.agent("checagem").chain
    assert writer[0].key == "anthropic/claude-sonnet-5-5"
    assert all(r.provider != "deepseek" for r in writer)  # D19
    assert all(r.provider != writer[0].provider for r in checker)


def test_companies_yaml_has_the_t2_ids():
    by_name = {c.name: c.id for c in post.load_companies()}
    assert by_name == {
        "Uber": 1815218, "Adobe": 1480, "Bain & Company": 2114,
        "MIT Technology Review Brasil": 65473714, "Anthropic": 74126343,
    }


# ===================================================================== fontes
ARTICLE = """<html><head><title>Título da aba</title>
<meta property="og:title" content="Dona da 99 vê número insignificante de corridas">
<meta property="og:site_name" content="Tecnoblog">
<meta property="article:published_time" content="2026-11-09T10:00:00-03:00">
<script>var x = "nao deve aparecer";</script><style>p{}</style></head>
<body><nav><p>Menu com um texto comprido o bastante para parecer um parágrafo de verdade</p></nav>
<div class="share-buttons"><p>Compartilhe no WhatsApp e nas redes, texto comprido de propósito</p>
</div>
<article><h1>Dona da 99 vê número insignificante</h1>
<p>A Uber revelou que só 4 viagens foram pedidas por agentes de IA externos no trimestre.<br>
O número saiu nos resultados.</p>
<p>O vice-presidente da DiDi disse ao Tecnoblog que o volume deles também é insignificante.</p>
<p>Curta.</p>
<ul><li>Menu</li></ul>
<p>Mais um parágrafo para passar do mínimo de texto do artigo, com detalhes do caso inteiro.
""" + "Texto de enchimento do artigo com informação. " * 8 + """</p>
</article><footer><p>Todos os direitos reservados, texto longo de rodapé que não importa</p>
</footer></body></html>"""

LD = """<html><head><title>Bain</title>
<script type="application/ld+json">{"@graph": [{"@type": "NewsArticle",
"articleBody": "%s"}]}</script></head><body><p>curto</p></body></html>""" % (
    "A pesquisa da Bain mostra que 95% das empresas usam IA. " * 12
)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Os hosts `.test` dos testes resolvem para um IP público, sem rede."""
    import linky_agents.netguard as netguard

    def resolve(host, port):
        if host.startswith("interno"):
            return ["172.18.0.3"]
        return ["93.184.216.34"]

    monkeypatch.setattr(netguard, "resolve_host", resolve)


def transport(pages: dict[str, tuple[int, str]]):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        status, body = pages[str(request.url)]
        return httpx.Response(status, text=body, headers={"content-type": "text/html"})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_fetch_sources_reads_up_to_three_urls_and_survives_a_failing_one():
    client, seen = transport({
        "https://a.test/1": (200, ARTICLE),
        "https://a.test/2": (500, "erro"),
        "https://a.test/3": (200, LD),
        "https://a.test/4": (200, ARTICLE),
    })
    urls = ["https://a.test/1", "https://a.test/2", "https://a.test/3", "https://a.test/4"]
    docs = post.fetch_sources(urls, client=client, max_doc_tokens=1000)
    assert seen == urls[:3]
    assert [d.id for d in docs] == ["fonte1", "fonte2"]
    first = docs[0]
    assert first.source == "Tecnoblog"
    assert first.title == "Dona da 99 vê número insignificante de corridas"
    assert first.text.startswith("Publicado em 2026-11-09.")
    assert "só 4 viagens foram pedidas por agentes de IA externos no trimestre. O número" in (
        first.text
    )
    for junk in ("nao deve aparecer", "Menu com", "Compartilhe", "direitos reservados", "Curta."):
        assert junk not in first.text
    assert docs[1].text.startswith("A pesquisa da Bain mostra")


def test_fetch_sources_cuts_each_document_to_max_doc_tokens():
    client, _ = transport({"https://a.test/3": (200, LD)})
    [doc] = post.fetch_sources(["https://a.test/3"], client=client, max_doc_tokens=50)
    assert len(doc.text) <= 50 * 3 + len(" [...]")
    assert doc.text.endswith("[...]")


def test_fetch_sources_skips_pages_without_text_and_network_errors():
    def handler(request):
        if "rede" in str(request.url):
            raise httpx.ConnectError("sem rede")
        return httpx.Response(200, text="<html><body><p>oi</p></body></html>",
                              headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert post.fetch_sources(["https://rede.test/", "https://vazio.test/"], client=client,
                              max_doc_tokens=500) == []


def redirecting(routes: dict[str, tuple[int, dict, str]]):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        status, headers, body = routes[str(request.url)]
        return httpx.Response(status, text=body,
                              headers={"content-type": "text/html", **headers})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_fetch_sources_follows_redirects_to_public_hosts():
    client, seen = redirecting({
        "https://curto.test/x": (301, {"location": "https://a.test/3"}, ""),
        "https://a.test/3": (200, {}, LD),
    })
    [doc] = post.fetch_sources(["https://curto.test/x"], client=client, max_doc_tokens=1000)
    assert seen == ["https://curto.test/x", "https://a.test/3"]
    assert doc.text.startswith("A pesquisa da Bain mostra")


@pytest.mark.parametrize("location", [
    "http://n8n:5678/rest/workflows",
    "http://linky-agents:8080/agenda",
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1/",
    "https://interno.test/",
    "file:///etc/passwd",
])
def test_fetch_sources_never_follows_a_redirect_into_the_internal_network(location):
    client, seen = redirecting({
        "https://malicioso.test/a": (302, {"location": location}, ""),
    })
    assert post.fetch_sources(["https://malicioso.test/a"], client=client,
                              max_doc_tokens=500) == []
    assert seen == ["https://malicioso.test/a"]


def test_fetch_sources_blocks_internal_urls_without_a_request():
    client, seen = redirecting({})
    urls = ["http://n8n:5678/", "http://10.0.0.1/", "https://interno.test/"]
    assert post.fetch_sources(urls, client=client, max_doc_tokens=500) == []
    assert seen == []


def test_fetch_sources_gives_up_after_too_many_redirects():
    routes = {f"https://loop.test/{i}": (302, {"location": f"https://loop.test/{i + 1}"}, "")
              for i in range(post.MAX_REDIRECTS + 2)}
    client, seen = redirecting(routes)
    assert post.fetch_sources(["https://loop.test/0"], client=client, max_doc_tokens=500) == []
    assert len(seen) == post.MAX_REDIRECTS + 1


def test_extract_text_falls_back_to_the_meta_description():
    html = ('<html><head><meta name="description" content="A Adobe abriu o Photoshop para '
            'agentes de IA de outras empresas, em teste."></head><body></body></html>')
    title, text, _ = post.extract_text(html)
    assert text.startswith("A Adobe abriu o Photoshop")


# ===================================================================== montagem
def draft(**over) -> Draft:
    data = dict(structure="E1", hooks=[Hook(**h) for h in HOOKS], body=BODY, readings=READINGS,
                tail=TAIL, closing="escolha", headline="4 corridas")
    data.update(over)
    return Draft(**data)


def test_compose_joins_hook_body_reading_and_tail_with_blank_lines():
    d = draft()
    text = post.compose(d, 2, 1)
    assert text == "\n\n".join([HOOKS[2]["text"], BODY, READINGS[1], TAIL])


def test_compose_takes_felipes_own_hook_and_reading_text():
    text = post.compose(draft(), "Meu hook.", "Minha leitura: escrita por mim.")
    assert text.startswith("Meu hook.\n\n")
    assert "\n\nMinha leitura: escrita por mim.\n\n" in text


def writer_out(**over) -> post.WriterOut:
    return post.WriterOut.model_validate_json(writer_json(**over))


def mentions_per_combo(d) -> list[int]:
    return [post.compose(d, i, j).count("@[")
            for i in range(len(d.hooks)) for j in range(len(d.readings))]


def test_when_every_hook_names_the_company_the_mention_goes_in_the_hooks():
    out = post._with_mention(writer_out(hooks=[HOOKS[0], HOOKS[1],
                                               {"kind": "H5", "text": "A Uber ainda espera."}]),
                             COMPANIES)
    assert all(h.text.count(UBER.mention) == 1 for h in out.hooks)
    assert UBER.mention not in out.body + out.tail + "".join(out.readings)
    assert mentions_per_combo(out) == [1] * 6


def test_otherwise_the_mention_goes_once_in_the_body():
    out = post._with_mention(writer_out(), COMPANIES)  # o hook H5 não cita a Uber
    assert out.body.count(UBER.mention) == 1
    assert out.body.startswith("O número saiu") and f"No {UBER.mention} Eats" in out.body
    assert all("@[" not in h.text for h in out.hooks)
    assert "@[" not in out.tail + "".join(out.readings)
    assert mentions_per_combo(out) == [1] * 6


def test_without_the_company_in_the_map_there_is_no_mention():
    assert post._with_mention(writer_out(main_company="DiDi"), COMPANIES) == writer_out(
        main_company="DiDi")


def test_mention_uses_aliases_and_the_canonical_name():
    text = post._mention_first("A Bain ouviu 200 empresas.", BAIN)
    assert text == "A @[Bain & Company](urn:li:organization:2114) ouviu 200 empresas."
    assert post.find_company("bain & company", COMPANIES) is BAIN
    assert post.find_company("Uber Eats", COMPANIES) is UBER
    assert post.find_company("99", COMPANIES) is None


# ===================================================================== validação
def problems(**over) -> list[str]:
    opinion = over.pop("opinion", None)
    recent = over.pop("recent", ())
    return post.check_draft(draft(**over), opinion=opinion, recent_hooks=recent)


def test_a_good_draft_passes_the_deterministic_rules():
    assert problems() == []


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"tail": TAIL + " #Negocios"}, "0 ou 1 hashtag"),
        ({"tail": TAIL.replace("#AgentesDeIA", "#Inovacao")}, "hashtag genérica"),
        ({"body": BODY + " #IA"}, "hashtag só na última linha"),
        ({"body": BODY + " Veja em tecnoblog.net/uber."}, "link"),
        ({"body": BODY + " https://x.test"}, "link"),
        ({"body": BODY + " 🚀"}, "emojis"),
        ({"body": BODY + " Fale com @uber."}, "não use @"),
        ({"body": BODY + " Vale ressaltar que é cedo."}, "vale ressaltar"),
        ({"body": BODY + " Isso é crucial."}, "crucial"),
        ({"body": BODY + " Essa é a lição de negócio: medir."}, "frase de moral"),
        ({"body": BODY + " Cada vez mais empresas testam."}, "cada vez mais"),
        ({"body": BODY + " E o mais interessante? Ninguém mediu."}, "pergunta retórica"),
        ({"body": BODY + " Isso é MUITO IMPORTANTE."}, "caixa alta"),
        ({"body": BODY + " Um ponto — outro ponto — e mais."}, "travessões"),
        ({"body": "Curto."}, "o mínimo é 500"),
        ({"body": BODY + " Mais texto." * 60}, "corte pelo menos"),
        ({"body": BODY + " Eu vejo isso nos meus projetos."}, "primeira pessoa"),
        ({"readings": READINGS[:1]}, "escreva 2 leituras"),
        ({"hooks": [Hook(kind="H2", text="a"), Hook(kind="H2", text="b"),
                    Hook(kind="H5", text="c")]}, "tipos diferentes"),
        ({"hooks": [Hook(kind="H3", text="Nos agentes que construo, o modelo não é o gargalo."),
                    *[Hook(**h) for h in HOOKS[1:]]]}, "exige a opinião"),
        ({"hooks": [Hook(kind="H1", text="x" * 121), *[Hook(**h) for h in HOOKS[1:]]]},
         "121 caracteres"),
        ({"hooks": [Hook(kind="H1", text="Você já pensou em deixar um agente pedir o carro?"),
                    *[Hook(**h) for h in HOOKS[1:]]]}, "abre com pergunta"),
        ({"structure": "E4"}, "exige material de Felipe"),
        ({"body": "• Um: a\n• Dois: b\n\nTexto no meio.\n\n• Três: c\n• Quatro: d\n\n" + BODY},
         "no máximo uma lista"),
        ({"body": "O atalho: a.\n\nA brecha: b.\n\n" + BODY}, "rótulo antes de dois-pontos"),
    ],
)
def test_the_rules_catch_each_problem(over, expected):
    found = problems(**over)
    assert any(expected.casefold() in p.casefold() for p in found), found


def test_quotes_from_the_source_do_not_count_as_first_person_or_cuts():
    body = BODY + ' O executivo disse: "eu acho que é crucial".'
    assert problems(body=body) == []


def test_jornada_do_cliente_is_allowed():
    assert problems(body=BODY + " Muda a jornada do cliente.") == []


def test_first_person_is_allowed_only_in_felipes_reading_and_h3():
    felipe = ["Minha leitura: nos projetos que construo, o cliente ainda prefere o app."]
    hooks = [Hook(kind="H3", text="Eu ainda não vi cliente pedir corrida por agente."),
             *[Hook(**h) for h in HOOKS[1:]]]
    assert problems(readings=felipe, hooks=hooks, opinion="o cliente prefere o app") == []
    found = problems(readings=felipe, hooks=hooks, opinion="x", body=BODY + " Eu acho.")
    assert any("primeira pessoa" in p for p in found)


def test_a_hook_that_repeats_a_recent_one_is_refused():
    found = problems(recent=["Agentes de IA de outras empresas pediram 4 corridas na Uber."])
    assert any("repete um hook recente" in p for p in found)


# ===================================================================== redação + checagem
def test_write_returns_a_draft_with_the_mention_and_no_notes(tmp_path):
    h, fake = harness(tmp_path, [reply(writer_json())], [reply(check_json())])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=["Um hook antigo."],
                   companies=COMPANIES)
    assert d.notes == []
    assert d.reading_is_felipe is False
    assert len(d.readings) == 2 and [x.kind for x in d.hooks] == ["H2", "H1", "H5"]
    assert UBER.mention in d.body
    assert d.headline == "Agentes pediram 4 corridas na Uber"
    assert mentions_per_combo(d) == [1] * 6
    for i in range(3):
        for j in range(2):
            text = post.compose(d, i, j)
            assert len(post.display(text)) >= post.MIN_CHARS and len(text) <= post.MAX_CHARS
    [w] = requests_to(fake, "escritor")
    assert w.system.startswith("# Redação: o post de LinkedIn de Felipe Lenzi")
    sent = user_input(w)
    assert sent["pauta"]["pattern"] == "P2" and sent["pauta"]["audience"] == "gestor"
    assert sent["hooks_recentes"] == ["Um hook antigo."]
    assert sent["opiniao_de_felipe"] is None and sent["ajuste"] is None
    assert "<documentos_nao_confiaveis>" in w.messages[0].content
    [c] = requests_to(fake, "checador")
    checked = user_input(c)
    assert checked["body"] == post.display(d.body)  # a checagem lê o texto sem a menção
    assert "Dona da 99" in c.messages[0].content


def test_with_felipes_opinion_there_is_one_first_person_reading(tmp_path):
    felipe = ["Minha leitura: o cliente ainda prefere abrir o app, e isso deve durar."]
    hooks = [{"kind": "H3", "text": "Eu ainda não vejo cliente pedindo corrida por agente."},
             *HOOKS[1:]]
    h, fake = harness(tmp_path, [reply(writer_json(readings=felipe, hooks=hooks))],
                      [reply(check_json())])
    d = post.write(entry(opinion="o cliente ainda prefere o app"), DOCS, harness=h,
                   recent_hooks=[], companies=COMPANIES)
    assert d.reading_is_felipe is True and d.readings == felipe
    assert d.notes == []
    assert user_input(fake.requests[0])["opiniao_de_felipe"] == "o cliente ainda prefere o app"


def test_a_draft_that_breaks_the_rules_gets_one_retry_with_the_reasons(tmp_path):
    bad = writer_json(body=BODY + " Isso é crucial.")
    h, fake = harness(tmp_path, [reply(bad), reply(writer_json())], [reply(check_json())])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert d.notes == [] and "crucial" not in d.body
    first, second = requests_to(fake, "escritor")
    sent = user_input(second)
    assert any("crucial" in c for c in sent["correcoes"])
    assert "crucial" in sent["rascunho_anterior"]["body"]


def test_a_second_failure_goes_to_the_notes(tmp_path):
    bad = writer_json(body=BODY + " Isso é crucial.")
    h, _ = harness(tmp_path, [reply(bad), reply(bad)], [reply(check_json())])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert any(n.startswith("Validação:") and "crucial" in n for n in d.notes)


def test_a_grave_problem_from_the_check_triggers_one_rewrite_and_a_recheck(tmp_path):
    fixed = writer_json(body=BODY.replace("cerca de 500", "cerca de 400"))
    h, fake = harness(
        tmp_path,
        [reply(writer_json()), reply(fixed)],
        [reply(check_json(GRAVE, LEVE)), reply(check_json(LEVE))],
    )
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert "cerca de 400" in d.body
    assert d.notes == [f"Checagem (leve): tail, \"{LEVE['excerpt']}\": {LEVE['issue']}"]
    sent = user_input(requests_to(fake, "escritor")[1])
    assert sent["correcoes"] == ["checagem: body, \"cerca de 500 pedidos\": a fonte diz 400"]
    assert len(requests_to(fake, "checador")) == 2


def test_leve_problems_go_straight_to_the_notes_without_a_rewrite(tmp_path):
    h, fake = harness(tmp_path, [reply(writer_json())], [reply(check_json(LEVE))])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert len(d.notes) == 1 and d.notes[0].startswith("Checagem (leve)")
    assert len(requests_to(fake, "escritor")) == 1


def test_a_rewrite_that_breaks_the_rules_keeps_the_first_draft(tmp_path):
    bad = writer_json(body=BODY.replace("cerca de 500", "cerca de 400") + " Isso é crucial.")
    h, _ = harness(tmp_path, [reply(writer_json()), reply(bad)], [reply(check_json(GRAVE))])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert "cerca de 500" in d.body
    assert any("não passou na validação" in n for n in d.notes)
    assert any(n.startswith("Checagem (grave)") for n in d.notes)


def test_a_failing_check_does_not_lose_the_post(tmp_path):
    h, _ = harness(tmp_path, [reply(writer_json())],
                   [ProviderError("HTTP 400: modelo fora do ar", retryable=False)])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert any("checagem não rodou" in n for n in d.notes)


def test_without_sources_the_notes_say_nothing_was_checked(tmp_path):
    h, _ = harness(tmp_path, [reply(writer_json())], [reply(check_json())])
    d = post.write(entry(), [], harness=h, recent_hooks=[], companies=COMPANIES)
    assert any("nenhuma fonte foi lida" in n for n in d.notes)


def test_an_adjustment_rewrites_from_the_previous_post_with_the_latest_request(tmp_path):
    previous = post.compose(draft(), 0, 0)
    e = entry(
        post=Post(commentary=previous, alt_text="arte", image="x.png"),
        adjustments=["tire a ressalva", "troque a pergunta por uma de experiência"],
    )
    h, fake = harness(tmp_path, [reply(writer_json(closing="experiencia"))],
                      [reply(check_json())])
    d = post.write(e, DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert d.closing == "experiencia"
    ajuste = user_input(fake.requests[0])["ajuste"]
    assert ajuste == {
        "post_anterior": previous,
        "pedido": "troque a pergunta por uma de experiência",
        "pedidos_anteriores": ["tire a ressalva"],
    }


def test_the_writer_failing_raises_run_failed(tmp_path):
    h, _ = harness(tmp_path, [ProviderError("HTTP 400", retryable=False)], [])
    with pytest.raises(post.RunFailed):
        post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)


def test_a_long_e2_is_marked_as_e1_without_a_retry(tmp_path):
    h, fake = harness(tmp_path, [reply(writer_json(structure="E2"))], [reply(check_json())])
    d = post.write(entry(), DOCS, harness=h, recent_hooks=[], companies=COMPANIES)
    assert d.structure == "E1" and d.notes == []
    assert len(requests_to(fake, "escritor")) == 1


def test_a_short_e2_stays_e2():
    out = post.WriterOut.model_validate_json(writer_json(structure="E2", body="Curto. " * 20))
    assert post._structure(out) == "E2"
