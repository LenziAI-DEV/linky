from pathlib import Path

import pytest
from pydantic import ValidationError

from linky_agents.gold import GoldDay, Scores

ROOT = Path(__file__).resolve().parents[1]


def _scores(**kw) -> dict:
    base = dict(relevance=0, novelty=0, evidence=0, brazil=0, positioning=0, conversation=0)
    return base | kw


def _day(**overrides) -> dict:
    day = {
        "date": "2026-11-06",
        "items_file": "data/items/2026-11-06.jsonl",
        "items_count": 3,
        "triage": [
            {"item_id": "a", "relevant": True},
            {"item_id": "b", "relevant": True},
            {"item_id": "c", "relevant": False, "reason": "oferta de varejo"},
        ],
        "scored": [
            {"item_id": "a", "scores": _scores(relevance=3, evidence=3)},
            {"item_id": "b", "scores": _scores(relevance=3, evidence=2)},
        ],
        "cards": [
            {
                "rank": 1,
                "item_ids": ["a"],
                "title": "Título do card",
                "what_happened": "x",
                "why_it_matters": "y",
                "approach": "z",
                "format": "caso",
                "sources": ["https://exemplo.test/a"],
            }
        ],
    }
    return day | overrides


def test_max_score_is_33():
    assert Scores(**_scores(**dict.fromkeys(_scores(), 3))).total == 33


def test_ranking_uses_weights_and_tiebreak():
    day = GoldDay.model_validate(
        _day(
            scored=[
                {"item_id": "a", "scores": _scores(relevance=2, evidence=1)},  # 6+2 = 8
                {"item_id": "b", "scores": _scores(relevance=1, evidence=2)},  # 3+4 = 7
            ]
        )
    )
    assert [s.item_id for s in day.ranking()] == ["a", "b"]


def test_triage_must_cover_every_item():
    with pytest.raises(ValidationError, match="triage cobre"):
        GoldDay.model_validate(_day(items_count=4))


def test_discarded_item_needs_reason():
    bad = _day()
    bad["triage"][2] = {"item_id": "c", "relevant": False}
    with pytest.raises(ValidationError, match="precisa de motivo"):
        GoldDay.model_validate(bad)


def test_scores_xor_elimination():
    bad = _day()
    bad["scored"][1] = {"item_id": "b"}
    with pytest.raises(ValidationError, match="scores OU eliminated"):
        GoldDay.model_validate(bad)


def test_card_must_reference_scored_item():
    bad = _day()
    bad["cards"][0]["item_ids"] = ["c"]
    with pytest.raises(ValidationError):
        GoldDay.model_validate(bad)


def _card(rank: int, item: str) -> dict:
    return _day()["cards"][0] | {"rank": rank, "item_ids": [item]}


def test_batch_day_accepts_five_cards_and_picks_with_slots():
    """Lote de domingo (ou de recuperação): até 5 cards e uma escolha por horário."""
    day = GoldDay.model_validate(
        _day(
            items_file=["data/items/2026-11-06.jsonl", "data/items/2026-11-07.jsonl"],
            cards=[_card(1, "a"), _card(2, "b"), _card(3, "a"), _card(4, "b"), _card(5, "a")],
            picks=[
                {"card_rank": 3, "slot": "2026-11-11T18:30:00-03:00"},
                {"card_rank": None, "item_ids": ["b"], "slot": "2026-11-10T18:30:00-03:00",
                 "reason": "pauta sugerida por Felipe, fora dos cards"},
            ],
        )
    )
    assert [p.card_rank for p in day.picks] == [3, None]


def test_pick_outside_cards_needs_items():
    with pytest.raises(ValidationError, match="fora dos cards"):
        GoldDay.model_validate(_day(picks=[{"slot": "2026-11-10T18:30:00-03:00"}]))


def test_pick_must_point_to_existing_card():
    with pytest.raises(ValidationError, match="card inexistente"):
        GoldDay.model_validate(_day(picks=[{"card_rank": 2, "slot": "2026-11-10T18:30:00-03:00"}]))


def test_pick_items_must_be_relevant():
    with pytest.raises(ValidationError, match="não relevante"):
        GoldDay.model_validate(
            _day(picks=[{"item_ids": ["c"], "slot": "2026-11-10T18:30:00-03:00"}])
        )


def test_choice_and_picks_are_exclusive():
    with pytest.raises(ValidationError, match="choice OU picks"):
        GoldDay.model_validate(
            _day(choice={"card_rank": 1},
                 picks=[{"card_rank": 1, "slot": "2026-11-10T18:30:00-03:00"}])
        )


@pytest.mark.parametrize("path", sorted((ROOT / "eval" / "gold").glob("*.json")))
def test_versioned_gold_files_are_valid(path):
    GoldDay.model_validate_json(path.read_text(encoding="utf-8"))
