"""Frente Pautas: `curate()` pela interface pública, com o fornecedor falso (sem rede).

O "modelo" falso lê os documentos do pedido e responde por uma tabela de fatos: assim os
testes conferem o que chega a cada agente e o que o código faz com a resposta.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from linky_agents.agents import pautas
from linky_agents.agents.contracts import CardOut
from linky_agents.harness import (
    FakeProvider,
    Harness,
    ProviderError,
    Reply,
    RunFailed,
    load_models,
    load_prices,
)
from linky_agents.normalize import title_key

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 10, 9, 40, tzinfo=UTC)  # 06:40 em Brasília
DOC = re.compile(r'<documento id="([^"]+)"')


def item(id_, title, source="techcrunch-ai", hours=-5, summary="", tier="press"):
    at = NOW + timedelta(hours=hours)
    return {
        "id": id_, "source": source, "tier": tier, "title": title,
        "title_key": title_key(title), "url": f"https://{source}.example/{id_}",
        "summary": summary or f"Resumo de {title}.",
        "published_utc": at.isoformat(), "published_brt_date": at.date().isoformat(),
        "collected_utc": at.isoformat(),
    }


def triage(relevance=2, category="caso", summary="fato em uma linha", reason=""):
    return {"relevance": relevance, "category": category, "summary": summary,
            "reason": reason or ("fora" if relevance == 0 else "")}


def scores(relevance=2, novelty=2, evidence=2, brazil=1, positioning=2, conversation=1):
    return {"relevance": relevance, "novelty": novelty, "evidence": evidence,
            "brazil": brazil, "positioning": positioning, "conversation": conversation}


def curated(title="Manchete", topic="outro", company="", pattern="P3", **over):
    out = {"scores": scores(), "pattern": pattern, "audience": "gestor", "topic": topic,
           "company": company, "title": title, "what": "O fato.", "why": "Importa.",
           "angle": "A tese."}
    out.update(over)
    return out


CARD_KEYS = {"title", "what", "why", "angle"}
AGENTS = {"Triagem de notícias": "triagem", "Curadoria de pautas": "curadoria",
          "Texto dos cards": "pauta"}


class Model:
    """Fornecedor falso que responde por fato. Guarda o que cada agente recebeu.

    A tabela da curadoria leva também o texto do card (`curated()`): a curadoria responde
    com as notas, e o agente da pauta, com o texto."""

    def __init__(self, triage_table, curation_table):
        self.triage_table = triage_table
        self.curation_table = curation_table
        self.seen: dict[str, list[list[str]]] = {a: [] for a in AGENTS.values()}
        self.inputs: dict[str, list[dict]] = {a: [] for a in AGENTS.values()}

    def __call__(self, request):
        agent = next(a for k, a in AGENTS.items() if k in request.system)
        text = request.messages[-1].content
        ids = DOC.findall(text)
        self.seen[agent].append(ids)
        self.inputs[agent].append(json.loads(text.split("## Entrada\n", 1)[1].split("\n\n<")[0]))
        if agent == "triagem":
            body = {"facts": [{"id": i, **self.triage_table[i]} for i in ids
                              if i in self.triage_table]}
        elif agent == "curadoria":
            body = {"facts": [{"id": i, **{k: v for k, v in self.curation_table[i].items()
                                           if k not in CARD_KEYS}}
                              for i in ids if i in self.curation_table]}
        else:
            body = {"cards": [{"id": i, **{k: v for k, v in self.curation_table[i].items()
                                           if k in CARD_KEYS}}
                              for i in ids if i in self.curation_table]}
        return Reply(text=json.dumps(body, ensure_ascii=False),
                     input_tokens=len(request.system + text) // 4, output_tokens=60 * len(ids))


def harness(tmp_path, model, *, openai=None, deepseek=None, anthropic=None):
    return Harness(
        config=load_models(ROOT / "config" / "models.yaml"),
        prices=load_prices(ROOT / "config" / "prices.yaml"),
        prompts_dir=ROOT / "prompts",
        providers={
            "openai": FakeProvider(openai or {"gpt-6-luna": [model] * 200}),
            "deepseek": FakeProvider(deepseek or {}),
            "anthropic": FakeProvider(anthropic or {}),
        },
        data_dir=tmp_path / "data",
        clock=lambda: NOW,
        sleep=lambda _s: None,
    )


def run(tmp_path, items, triage_table, curation_table, **kw):
    model = Model(triage_table, curation_table)
    h = harness(tmp_path, model)
    cards = pautas.curate(items, harness=h, now=NOW, n_cards=kw.pop("n_cards", 3), **kw)
    return cards, model


# --------------------------------------------------------------------------- casos
def test_cards_come_ranked_by_rubric_score_with_stable_ids_and_sources(tmp_path):
    items = [item("a" * 16, "Nubank corta fila de fraude com IA"),
             item("b" * 16, "Uber registra 4 corridas pedidas por agentes"),
             item("c" * 16, "Adobe abre Photoshop para ChatGPT")]
    tt = {i["id"]: triage() for i in items}
    ct = {
        "a" * 16: curated("Nubank corta fila", topic="seguranca",
                          scores=scores(relevance=3, evidence=3, brazil=3)),
        "b" * 16: curated("Uber e agentes", topic="agentes", pattern="P2"),
        "c" * 16: curated("Adobe abre apps", topic="criatividade",
                          scores=scores(relevance=3)),
    }
    cards, _ = run(tmp_path, items, tt, ct)
    assert [c.title for c in cards] == ["Nubank corta fila", "Adobe abre apps", "Uber e agentes"]
    assert all(isinstance(c, CardOut) for c in cards)
    first = cards[0]
    assert first.id == "2026-11-10-" + "a" * 16
    assert first.event_date.isoformat() == "2026-11-10"
    assert first.score == 3 * 3 + 2 * 2 + 3 * 2 + 3 + 2 * 2 + 1
    assert first.sources == ["https://techcrunch-ai.example/" + "a" * 16]
    assert (first.pattern, first.audience, first.what, first.why, first.angle) == (
        "P3", "gestor", "O fato.", "Importa.", "A tese.")


def test_the_same_fact_from_several_sources_is_one_fact_before_any_model_call(tmp_path):
    items = [item("a" * 16, "Anthropic files for IPO at $1.4 trillion valuation", hours=-8),
             item("b" * 16, "Anthropic IPO $1.4 trillion valuation filing", "verge-ai", hours=-6),
             item("c" * 16, "Google lança Gemini para hospitais")]
    tt = {"a" * 16: triage(category="mercado"), "b" * 16: triage(),
          "c" * 16: triage()}
    ct = {"a" * 16: curated("IPO", topic="investimento"), "b" * 16: curated("IPO"),
          "c" * 16: curated("Gemini", topic="saude")}
    cards, model = run(tmp_path, items, tt, ct)
    sent = [i for batch in model.seen["triagem"] for i in batch]
    assert len(sent) == 2 and "c" * 16 in sent
    ipo = next(c for c in cards if c.title == "IPO")
    assert len(ipo.sources) == 2


def test_discarded_in_triage_never_reaches_curation(tmp_path):
    items = [item("a" * 16, "Tutorial: deploy no SageMaker"), item("b" * 16, "Nubank e fraude")]
    tt = {"a" * 16: triage(0, "tutorial", reason="tutorial"), "b" * 16: triage()}
    ct = {"a" * 16: curated("Tutorial"), "b" * 16: curated("Nubank")}
    cards, model = run(tmp_path, items, tt, ct)
    assert [c.title for c in cards] == ["Nubank"]
    assert model.seen["curadoria"] == [["b" * 16]]


def test_fact_without_a_pattern_or_eliminated_does_not_become_a_card(tmp_path):
    items = [item("a" * 16, "Fofoca de executivo"), item("b" * 16, "Pesquisa patrocinada"),
             item("c" * 16, "Caso concreto")]
    tt = {i["id"]: triage() for i in items}
    ct = {"a" * 16: curated("Sem padrão", pattern="", scores=scores(3, 3, 3, 3, 3, 3)),
          "b" * 16: {"eliminated": "patrocinado"},
          "c" * 16: curated("Caso", scores=scores(1, 1, 1, 0, 1, 0))}
    cards, _ = run(tmp_path, items, tt, ct)
    assert [c.title for c in cards] == ["Caso"]


def test_diversity_skips_same_topic_or_company_but_fills_the_batch_if_needed(tmp_path):
    items = [item(c * 16, f"Fato {c}") for c in "abcd"]
    tt = {i["id"]: triage() for i in items}
    ct = {"a" * 16: curated("Nubank fraude", topic="seguranca", company="Nubank",
                            scores=scores(relevance=3)),
          "b" * 16: curated("Greenlight fraude", topic="seguranca", company="Greenlight"),
          "c" * 16: curated("Nubank crédito", topic="financas", company="nubank"),
          "d" * 16: curated("Uber agentes", topic="agentes", company="Uber",
                            scores=scores(novelty=1))}
    cards, _ = run(tmp_path, items, tt, ct)
    assert [c.title for c in cards] == ["Nubank fraude", "Greenlight fraude", "Uber agentes"]

    model = Model(tt, ct)
    ranking = pautas.rank(items, harness=harness(tmp_path / "2", model), now=NOW)
    chosen = pautas.assemble(ranking.candidates, 2)
    assert [c.id for c in chosen] == ["a" * 16, "d" * 16]
    reasons = {c.id: c.skip for c in ranking.candidates}
    assert reasons["b" * 16] == "mesmo tema do card 1 (seguranca)"
    assert reasons["c" * 16] == "mesma empresa do card 1 (nubank)"


def test_vendor_case_without_independent_source_has_evidence_capped_at_1(tmp_path):
    items = [item("a" * 16, "Fintech resolve alertas com agentes", "aws-ml", tier="primary")]
    tt = {"a" * 16: triage()}
    ct = {"a" * 16: curated("Fintech", vendor=True, scores=scores(evidence=3))}
    cards, _ = run(tmp_path, items, tt, ct)
    assert cards[0].score == 3 * 2 + 2 * 2 + 1 * 2 + 1 + 2 * 2 + 1


def test_big_launch_with_two_signals_gets_positioning_at_least_2(tmp_path):
    titles = ["Anthropic launches Claude Fable 5.2"] * 3  # mesmo título: mesmo fato
    items = [item(c * 16, t, s, hours=-6 + n)
             for n, (c, t, s) in enumerate(zip("abc", titles, ["verge-ai", "techcrunch-ai",
                                                                "canaltech"], strict=True))]
    model = Model({}, {})
    stories = pautas.group_stories(items)
    assert len(stories) == 1
    rep = stories[0].representative["id"]
    model.triage_table = {rep: triage(3, "lancamento")}
    model.curation_table = {rep: curated("Fable", topic="modelos", available_now=True,
                                         scores=scores(positioning=0))}
    cards = pautas.curate(items, harness=harness(tmp_path, model), now=NOW)
    assert cards[0].score == 3 * 2 + 2 * 2 + 2 * 2 + 1 + 2 * 2 + 1


def test_tiebreak_is_evidence_then_relevance_then_novelty(tmp_path):
    items = [item("a" * 16, "Fato A"), item("b" * 16, "Fato B")]
    tt = {i["id"]: triage() for i in items}
    # mesma nota (relevância vale 3, evidência vale 2): 3*1+2*3 = 3*3+2*0 = 9 (+ resto igual)
    ct = {"a" * 16: curated("A", topic="agentes", scores=scores(relevance=3, evidence=0,
                                                                  novelty=3, brazil=0)),
          "b" * 16: curated("B", topic="custo", scores=scores(relevance=1, evidence=3,
                                                                novelty=3, brazil=0))}
    cards, _ = run(tmp_path, items, tt, ct)
    assert cards[0].score == cards[1].score
    assert [c.title for c in cards] == ["B", "A"]


def test_already_proposed_ids_and_titles_are_excluded(tmp_path):
    items = [item("a" * 16, "Nubank corta fila de fraude"),
             item("b" * 16, "Uber registra 4 corridas"),
             item("c" * 16, "Adobe abre Photoshop")]
    tt = {i["id"]: triage() for i in items}
    ct = {i["id"]: curated(i["title"], topic="outro") for i in items}
    exclude = ["2026-11-09-" + "a" * 16, "Uber registra 4 corridas", "Anthropic vai à bolsa"]
    cards, model = run(tmp_path, items, tt, ct, exclude=exclude)
    assert [c.title for c in cards] == ["Adobe abre Photoshop"]
    assert model.seen["triagem"] == [["c" * 16]]
    assert model.inputs["curadoria"][0]["already_proposed"] == [
        "Uber registra 4 corridas", "Anthropic vai à bolsa"]


def test_many_facts_go_in_batches_that_fit_and_nothing_is_dropped(tmp_path):
    words = [f"termo{chr(97 + n // 26)}{chr(97 + n % 26)}" for n in range(70)]
    items = [item(f"{n:016x}", f"{w} {w}zeta {w}omega", summary="x" * 900, hours=-n / 10)
             for n, w in enumerate(words)]
    tt = {i["id"]: triage(relevance=1 + n % 3) for n, i in enumerate(items)}
    ct = {i["id"]: curated(i["title"]) for i in items}
    model = Model(tt, ct)
    h = harness(tmp_path, model)
    ranking = pautas.rank(items, harness=h, now=NOW)
    triaged = [i for b in model.seen["triagem"] for i in b]
    assert sorted(triaged) == sorted(i["id"] for i in items)
    assert all(len(b) <= pautas.TRIAGE_BATCH for b in model.seen["triagem"])
    curated_ids = [i for b in model.seen["curadoria"] for i in b]
    assert len(curated_ids) == pautas.MAX_CANDIDATES
    assert all(len(b) <= pautas.CURATION_BATCH for b in model.seen["curadoria"])
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in (tmp_path / "data").rglob("runs/**/*.json")]
    assert records and all(not r["budget"]["documents_dropped"] for r in records)
    assert ranking.cost_usd > 0 and len(ranking.runs) == len(records)
    # os de relevância 3 na triagem têm prioridade na curadoria
    top = {i["id"] for n, i in enumerate(items) if n % 3 == 2}
    assert top <= set(curated_ids)


BAD = ProviderError("HTTP 400", retryable=False)


def test_total_failure_of_every_model_raises(tmp_path):
    items = [item("a" * 16, "Fato A")]
    h = harness(tmp_path, None, openai={"gpt-6-luna": [BAD]},
                deepseek={"deepseek-flash": [BAD]}, anthropic={"claude-haiku-5-5": [BAD]})
    with pytest.raises(RunFailed):
        pautas.curate(items, harness=h, now=NOW)


def test_reserve_models_take_over_when_the_first_fails(tmp_path):
    items = [item("a" * 16, "Fato A")]
    model = Model({"a" * 16: triage()}, {"a" * 16: curated("A")})
    h = harness(tmp_path, model, openai={"gpt-6-luna": [BAD] * 3},
                deepseek={"deepseek-flash": [BAD], "deepseek-v4-pro": [BAD]},
                anthropic={"claude-haiku-5-5": [model] * 3})
    assert [c.title for c in pautas.curate(items, harness=h, now=NOW)] == ["A"]


def test_curation_sees_all_candidates_in_one_call_and_merges_the_same_fact(tmp_path):
    items = [item("a" * 16, "Anthropic sets IPO price range", "techcrunch-ai"),
             item("b" * 16, "Anthropic mira trilhão na bolsa", "olhar-digital", tier="br"),
             item("c" * 16, "Uber registra 4 corridas", "tecnoblog", tier="br")]
    tt = {i["id"]: triage() for i in items}
    ct = {"a" * 16: curated("IPO", topic="investimento", company="Anthropic"),
          "b" * 16: curated("IPO de novo", same_as="a" * 16, topic="investimento"),
          "c" * 16: curated("Uber", topic="agentes", scores=scores(novelty=1))}
    cards, model = run(tmp_path, items, tt, ct)
    assert len(model.seen["curadoria"]) == 1 and len(model.seen["curadoria"][0]) == 3
    assert [c.title for c in cards] == ["IPO", "Uber"]
    assert len(cards[0].sources) == 2
    assert model.seen["pauta"] == [["a" * 16, "c" * 16]]


def test_card_without_text_gives_its_place_to_a_spare(tmp_path):
    items = [item(c * 16, f"Fato {c}") for c in "abcde"]
    tt = {i["id"]: triage() for i in items}
    ct = {"a" * 16: curated("A", topic="agentes", scores=scores(relevance=3)),
          "b" * 16: {**curated("", topic="custo"), "what": ""},
          "c" * 16: curated("C", topic="saude", scores=scores(novelty=1)),
          "d" * 16: curated("D", topic="agentes", scores=scores(novelty=0)),
          "e" * 16: curated("E", topic="codigo", scores=scores(novelty=0, conversation=0))}
    cards, model = run(tmp_path, items, tt, ct)
    assert [c.title for c in cards] == ["A", "C", "E"]  # D repete o tema do A
    assert len(model.seen["pauta"]) == 1 and len(model.seen["pauta"][0]) == 5


def test_no_items_means_no_cards_and_no_calls(tmp_path):
    cards, model = run(tmp_path, [], {}, {})
    assert cards == [] and not any(model.seen.values())


def test_specs_load_their_prompts_and_the_output_schema_fits_the_prompt():
    assert set(pautas.SPECS) == {"triagem", "curadoria", "pauta"}
    for spec in pautas.SPECS.values():
        text = (ROOT / "prompts" / spec.name / f"{spec.version}.md").read_text(encoding="utf-8")
        assert text.strip()
    schema = json.dumps(pautas.CurationOut.model_json_schema())
    for word in ("leads_benchmark", "available_now", "vendor", "eliminated", "topic"):
        assert word in schema


def test_gold_set_evaluation_runs_offline_and_counts_picks(tmp_path, monkeypatch):
    from linky_agents.agents import pautas_eval

    items = [item("a" * 16, "Nubank corta fila de fraude"), item("b" * 16, "Tutorial")]
    (tmp_path / "items").mkdir()
    (tmp_path / "items" / "2026-11-10.jsonl").write_text(
        "\n".join(json.dumps(i) for i in items), encoding="utf-8")
    gold = {
        "date": "2026-11-10", "items_file": "data/items/2026-11-10.jsonl", "items_count": 2,
        "triage": [{"item_id": "a" * 16, "relevant": True},
                   {"item_id": "b" * 16, "relevant": False, "reason": "tutorial"}],
        "scored": [{"item_id": "a" * 16, "scores": {
            "relevance": 3, "novelty": 3, "evidence": 3, "brazil": 3, "positioning": 3,
            "conversation": 3}}],
        "cards": [{"rank": 1, "item_ids": ["a" * 16], "title": "Nubank corta fila",
                   "what_happened": "x", "why_it_matters": "y", "approach": "z",
                   "format": "caso", "sources": ["https://x"]}],
        "choice": {"card_rank": 1},
    }
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "2026-11-10.json").write_text(json.dumps(gold), encoding="utf-8")
    model = Model({"a" * 16: triage(), "b" * 16: triage(0, "tutorial")},
                  {"a" * 16: curated("Nubank")})
    monkeypatch.setattr(pautas_eval.Harness, "from_repo",
                        staticmethod(lambda **_kw: harness(tmp_path, model)))
    out = tmp_path / "out.json"
    pautas_eval.main(["--items", str(tmp_path / "items"), "--gold", str(tmp_path / "gold"),
                      "--data", str(tmp_path / "data"), "--out", str(out)])
    [day] = json.loads(out.read_text(encoding="utf-8"))
    assert day["picks"][0]["top3"] is True
    assert day["cards"][0]["title"] == "Nubank" and day["cost_usd"] > 0
