import json

import yaml

from linky_agents.calibration import (
    SourceRow,
    main,
    pick_positions,
    prune_candidates,
    source_table,
)
from linky_agents.gold import GoldDay
from linky_agents.sources import SourcesConfig


def _scores(total_relevance: int = 0) -> dict:
    return dict(
        relevance=total_relevance, novelty=0, evidence=0, brazil=0, positioning=0, conversation=0
    )


def _sources() -> SourcesConfig:
    return SourcesConfig.model_validate(
        {
            "sources": [
                {"id": "alfa", "name": "Alfa", "url": "https://alfa.test/rss", "tier": "press"},
                {
                    "id": "beta",
                    "name": "Beta",
                    "url": "https://beta.test/rss",
                    "tier": "br",
                    "status": "probation",
                },
                {
                    "id": "gama",
                    "name": "Gama",
                    "url": "https://gama.test/rss",
                    "tier": "primary",
                },
            ]
        }
    )


def _item(item_id: str, source: str) -> dict:
    return {"id": item_id, "source": source, "title": item_id, "url": f"https://x.test/{item_id}"}


def _card(rank: int, item_ids: list[str]) -> dict:
    return {
        "rank": rank,
        "item_ids": item_ids,
        "title": f"Card {rank}",
        "what_happened": "x",
        "why_it_matters": "y",
        "approach": "z",
        "format": "caso",
        "sources": ["https://x.test"],
    }


def _day(**overrides) -> GoldDay:
    """a1, a2 (alfa) e b1 (beta) triados; a1 e b1 relevantes; card 1 = [a1, b1], escolhido."""
    day = {
        "date": "2026-11-06",
        "items_file": "x.jsonl",
        "items_count": 3,
        "triage": [
            {"item_id": "a1", "relevant": True},
            {"item_id": "a2", "relevant": False, "reason": "tutorial"},
            {"item_id": "b1", "relevant": True},
        ],
        "scored": [
            {"item_id": "a1", "scores": _scores(3)},
            {"item_id": "b1", "scores": _scores(2)},
        ],
        "cards": [_card(1, ["a1", "b1"])],
        "choice": {"card_rank": 1},
        "post": {"draft": "texto"},
    }
    return GoldDay.model_validate(day | overrides)


def test_source_table_counts_funnel_per_source():
    items = [_item("a1", "alfa"), _item("a2", "alfa"), _item("a3", "alfa"), _item("b1", "beta")]
    rows = {r.source_id: r for r in source_table(_sources(), items, [_day()])}

    alfa = rows["alfa"]
    assert (alfa.collected, alfa.triaged, alfa.relevant, alfa.scored) == (3, 2, 1, 1)
    assert (alfa.in_card, alfa.lead_card, alfa.posted) == (1, 1, 1)

    beta = rows["beta"]
    assert (beta.collected, beta.relevant, beta.in_card, beta.lead_card, beta.posted) == (
        1, 1, 1, 0, 1,
    )
    assert beta.status == "probation"

    gama = rows["gama"]
    assert (gama.collected, gama.triaged, gama.in_card) == (0, 0, 0)


def _batch_day() -> GoldDay:
    """Ranking por fato: card 2 (a, b) > card 1 (c) > d > e (pedida fora dos cards)."""
    ids = ["a", "b", "c", "d", "e"]
    relevance = {"a": 3, "b": 3, "c": 2, "d": 1, "e": 0}
    return GoldDay.model_validate(
        {
            "date": "2026-11-09",
            "items_file": "x.jsonl",
            "items_count": 5,
            "triage": [{"item_id": i, "relevant": True} for i in ids],
            "scored": [{"item_id": i, "scores": _scores(relevance[i])} for i in ids],
            "cards": [_card(1, ["c"]), _card(2, ["a", "b"])],
            "picks": [
                {"card_rank": 1, "slot": "2026-11-11T18:30:00-03:00"},
                {"item_ids": ["e"], "slot": "2026-11-10T18:30:00-03:00"},
            ],
        }
    )


def test_pick_positions_rank_by_fact_and_mark_top3():
    picks = pick_positions(_batch_day())

    assert [(p.label, p.position, p.top3) for p in picks] == [
        ("card 1", 2, True),
        ("fora dos cards", 4, False),
    ]


def test_single_choice_day_counts_as_one_pick():
    picks = pick_positions(_day())

    assert [(p.label, p.position, p.top3) for p in picks] == [("card 1", 1, True)]


def test_prune_candidates_flag_sources_without_cards_and_skip_disabled():
    rows = [
        SourceRow("com-card", "press", "active", collected=9, triaged=8, relevant=3, in_card=1),
        SourceRow("muda", "primary", "active", collected=0),
        SourceRow("ruido", "press", "probation", collected=12, triaged=10, relevant=0),
        SourceRow("morna", "br", "active", collected=4, triaged=3, relevant=1),
        SourceRow("desligada", "br", "disabled"),
    ]

    found = {c.source_id: c.strength for c in prune_candidates(rows)}

    assert found == {"muda": "forte", "ruido": "forte", "morna": "observar"}


def test_cli_writes_markdown_report(tmp_path):
    items = tmp_path / "2026-11-06.jsonl"
    items.write_text(
        "\n".join(json.dumps(_item(i, s)) for i, s in [("a1", "alfa"), ("a2", "alfa"),
                                                         ("b1", "beta")]),
        encoding="utf-8",
    )
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "2026-11-06.json").write_text(_day().model_dump_json(), encoding="utf-8")
    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump(_sources().model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "relatorio.md"

    assert main([str(items), "--gold", str(gold), "--sources", str(sources),
                 "--out", str(out)]) == 0

    report = out.read_text(encoding="utf-8")
    assert "1 de 1 escolhas no top 3 (100%)" in report
    assert "| alfa | press | active | 2 | 2 | 1 | 1 | 1 (1) | 1 |" in report
    assert "| gama | forte | nenhum item coletado no período |" in report
