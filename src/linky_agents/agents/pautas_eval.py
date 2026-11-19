"""Avaliação da frente Pautas contra o gold set (com modelo de verdade: só na VPS).

Reproduz cada dia do gold set com os mesmos itens que a curadoria do T2 viu (os IDs da
triagem do dia), roda `pautas.rank` e mede quantas escolhas de Felipe caem nos cards:
- **top 3**: a meta da rubrica (80%), contada por escolha (rubrica v1, pergunta 1);
- **top N**: N = cards oferecidos naquele dia do gold set (os lotes tinham 4 e 5).
Exclui, em cada dia, os cards dos dias anteriores do gold set (como o serviço faria).

Uso (dentro da imagem do serviço, com as chaves no ambiente):
    python -m linky_agents.agents.pautas_eval --items /items --gold /eval/gold \
        --data /data --out /data/pautas-eval.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

from ..gold import GoldDay, load_items
from ..harness import Harness
from . import pautas
from .contracts import CardOut

TOP = 3


def day_items(day: GoldDay, items_dir: Path) -> list[dict]:
    """Os itens que a curadoria do T2 viu naquele dia (os IDs da triagem do gold set)."""
    wanted = {t.item_id for t in day.triage}
    seen: dict[str, dict] = {}
    for path in sorted(items_dir.glob("*.jsonl")):
        for it in load_items(path):
            if it["id"] in wanted:
                seen.setdefault(it["id"], it)
    return list(seen.values())


def picks(day: GoldDay) -> list[tuple[str, set[str]]]:
    """As escolhas de Felipe: rótulo e IDs dos itens do fato escolhido. Num card, ficam de
    fora os itens que o gold set marca como contexto de outro dia (o CoreWeave no card do
    IPO da Anthropic); fora dos cards, os itens que Felipe pediu."""
    context = {s.item_id for s in day.scored if s.note and "contexto" in s.note}
    cards = {c.rank: {i for i in c.item_ids if i not in context} for c in day.cards}
    if day.choice and day.choice.card_rank:
        return [(f"card {day.choice.card_rank}", cards[day.choice.card_rank])]
    out = []
    for p in day.picks:
        if p.card_rank:
            out.append((f"card {p.card_rank}", cards[p.card_rank]))
        else:
            out.append(("fora dos cards", set(p.item_ids)))
    return out


def _position(cands: list[pautas.Candidate], ids: set[str]) -> int | None:
    for n, c in enumerate(cands, 1):
        if ids & set(c.item_ids):
            return n
    return None


def evaluate_day(day: GoldDay, items: list[dict], harness: Harness, exclude: list[str]) -> dict:
    now = max(datetime.fromisoformat(it["published_utc"]) for it in items)
    ranking = pautas.rank(items, harness=harness, now=now, exclude=exclude)
    n_gold = max(TOP, len(day.cards))
    top3 = pautas.assemble(copy.deepcopy(ranking.candidates), TOP)
    top_n = pautas.assemble(copy.deepcopy(ranking.candidates), n_gold)
    # O texto dos cards, como o curate() faria (entra no custo do dia)
    chosen = pautas.assemble(copy.deepcopy(ranking.candidates), n_gold + pautas.SPARE_CARDS)
    written = pautas.write_cards(chosen, harness=harness, ranking=ranking)
    written = pautas._diverse(written, n_gold)
    eligible = [c for c in ranking.candidates if not c.skip]
    result = {
        "date": str(day.date),
        "items": len(items),
        "items_expected": day.items_count,
        "facts": len(ranking.candidates),
        "excluded": ranking.excluded,
        "cost_usd": round(ranking.cost_usd, 5),
        "runs": len(ranking.runs),
        "failures": ranking.failures,
        "n_gold_cards": n_gold,
        "picks": [],
        "cards": [_card(c, card) for c, card in written],
        "ranking": [_row(c) for c in ranking.candidates if c.triage and c.triage.relevance > 0],
    }
    for label, ids in picks(day):
        found = next((c for c in ranking.candidates if ids & set(c.item_ids)), None)
        result["picks"].append({
            "pick": label,
            "items": sorted(ids),
            "top3": _position(top3, ids) is not None,
            "top_n": _position(top_n, ids) is not None,
            "rank_by_score": _position(eligible, ids),
            "skip": found.skip if found else "não encontrado",
            "fact": _row(found) if found else None,
        })
    return result


def _card(c: pautas.Candidate, card: CardOut) -> dict:
    return {"score": card.score, "title": card.title, "pattern": card.pattern,
            "audience": card.audience, "what": card.what, "why": card.why,
            "angle": card.angle, "topic": c.curated.topic if c.curated else "",
            "items": c.item_ids}


def _row(c: pautas.Candidate) -> dict:
    f = c.curated
    return {
        "id": c.id, "title": c.story.representative["title"], "sources": len(c.story.items),
        "triage": c.triage.relevance if c.triage else None,
        "category": c.triage.category if c.triage else None,
        "score": c.score, "skip": c.skip,
        "pattern": f.pattern if f else None, "topic": f.topic if f else None,
        "company": f.company if f else None,
        "scores": f.scores.model_dump() if f and f.scores else None,
        "same_as": f.same_as if f else None,
        "note": f.note if f else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliação da frente Pautas no gold set")
    parser.add_argument("--items", required=True, help="pasta com data/items/*.jsonl")
    parser.add_argument("--gold", default="eval/gold")
    parser.add_argument("--data", required=True, help="pasta de dados do harness (ledger)")
    parser.add_argument("--out", help="grava o resultado completo em JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    harness = Harness.from_repo(data_dir=Path(args.data))
    days = [GoldDay.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(Path(args.gold).glob("*.json"))]
    exclude: list[str] = []
    results = []
    for day in days:
        items = day_items(day, Path(args.items))
        res = evaluate_day(day, items, harness, list(exclude))
        results.append(res)
        print(f"{res['date']}: {res['items']}/{res['items_expected']} itens, {res['facts']} "
              f"fatos, US$ {res['cost_usd']:.4f} em {res['runs']} chamadas, "
              f"{len(res['failures'])} falhas")
        for p in res["picks"]:
            print(f"  {p['pick']}: top3={p['top3']} topN={p['top_n']} "
                  f"posição={p['rank_by_score']} {p['skip']}")
        for c in res["cards"]:
            print(f"  card {c['score']:2d} {c['pattern']} {c['audience']}: {c['title']}")
        exclude += [f"{day.date}-{i}" for c in day.cards for i in c.item_ids[:1]]
        exclude += [c.title for c in day.cards]
        off = [i for p in day.picks if p.card_rank is None for i in p.item_ids]
        exclude += [f"{day.date}-{i}" for i in off]
        exclude += [it["title"] for it in items if it["id"] in off]
    all_picks = [p for r in results for p in r["picks"]]
    hits3 = sum(p["top3"] for p in all_picks)
    hits_n = sum(p["top_n"] for p in all_picks)
    cost = sum(r["cost_usd"] for r in results)
    print(f"top 3: {hits3}/{len(all_picks)}; top N: {hits_n}/{len(all_picks)}; "
          f"custo total US$ {cost:.4f} ({cost / max(1, len(results)):.4f} por dia)")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
