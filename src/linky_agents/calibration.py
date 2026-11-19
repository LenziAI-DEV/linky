"""Calibração do fim do T2: funil por fonte e posição das escolhas de Felipe na rubrica.

Cruza os itens coletados (`data/items/*.jsonl`, copiados da VPS) com o gold set
(`eval/gold/*.json`) e as fontes (`sources/sources.yaml`). Só lê: não poda fonte nem muda
peso; o relatório lista candidatas e números para a decisão com Felipe.

Uso:
    python -m linky_agents.calibration <itens.jsonl...> [--gold eval/gold]
        [--sources sources/sources.yaml] [--out relatorio.md]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .gold import GoldDay, load_items
from .sources import SourcesConfig, load_sources


@dataclass
class SourceRow:
    """O funil de uma fonte: do item coletado ao post."""

    source_id: str
    tier: str
    status: str
    collected: int = 0
    triaged: int = 0
    relevant: int = 0
    scored: int = 0
    in_card: int = 0  # itens da fonte em algum card (principal ou fonte irmã)
    lead_card: int = 0  # itens da fonte como item principal de um card
    posted: int = 0  # itens da fonte numa pauta que virou post


def _posted_items(day: GoldDay) -> set[str]:
    cards = {c.rank: c.item_ids for c in day.cards}
    out: set[str] = set()
    if day.choice and day.choice.card_rank and day.post:
        out.update(cards[day.choice.card_rank])
    for p in day.picks:
        if p.post is None:
            continue
        out.update(cards[p.card_rank] if p.card_rank else p.item_ids)
    return out


def source_table(
    sources: SourcesConfig, items: list[dict], days: list[GoldDay]
) -> list[SourceRow]:
    """Uma linha por fonte de `sources.yaml` (inclusive as desligadas), na ordem do arquivo.
    Itens de fontes fora do arquivo ganham linha própria no fim, com status `ausente`."""
    rows = {s.id: SourceRow(s.id, s.tier, s.status) for s in sources.sources}
    source_of: dict[str, str] = {}
    for it in items:
        if it["id"] in source_of:
            continue  # o mesmo item em dois arquivos conta uma vez
        source_of[it["id"]] = it["source"]
        row = rows.setdefault(it["source"], SourceRow(it["source"], it.get("tier", "?"), "ausente"))
        row.collected += 1

    def bump(item_ids, field: str) -> None:
        for i in item_ids:
            if i in source_of:
                row = rows[source_of[i]]
                setattr(row, field, getattr(row, field) + 1)

    for day in days:
        bump({t.item_id for t in day.triage}, "triaged")
        bump({t.item_id for t in day.triage if t.relevant}, "relevant")
        bump({s.item_id for s in day.scored if s.scores is not None}, "scored")
        bump({i for c in day.cards for i in c.item_ids}, "in_card")
        bump({c.item_ids[0] for c in day.cards}, "lead_card")
        bump(_posted_items(day), "posted")
    return list(rows.values())


TOP = 3  # meta da rubrica: a escolha no top 3 em pelo menos 80% dos dias


@dataclass
class PickRank:
    """Onde uma escolha de Felipe ficou no ranking da rubrica, contado por fato (os itens de
    um mesmo card, ou de uma mesma pauta pedida fora dos cards, contam uma vez só)."""

    day: str
    label: str  # "card N" ou "fora dos cards"
    slot: str | None
    position: int | None  # None: nenhum item da escolha recebeu nota
    top3: bool


def _fact_ranking(day: GoldDay) -> list[object]:
    fact_of: dict[str, object] = {}
    for c in day.cards:
        for i in c.item_ids:
            fact_of.setdefault(i, ("card", c.rank))
    for n, p in enumerate(day.picks):
        if p.card_rank is None:
            for i in p.item_ids:
                fact_of.setdefault(i, ("pick", n))
    facts: list[object] = []
    for s in day.ranking():
        fact = fact_of.get(s.item_id, s.item_id)
        if fact not in facts:
            facts.append(fact)
    return facts


def pick_positions(day: GoldDay) -> list[PickRank]:
    """As escolhas do dia (a `choice` de um dia simples ou os `picks` de um lote), na ordem
    do registro, com a posição de cada uma no ranking por fato."""
    facts = _fact_ranking(day)

    def rank(fact: object, label: str, slot: str | None) -> PickRank:
        pos = facts.index(fact) + 1 if fact in facts else None
        return PickRank(str(day.date), label, slot, pos, pos is not None and pos <= TOP)

    if day.choice and day.choice.card_rank:
        return [rank(("card", day.choice.card_rank), f"card {day.choice.card_rank}", None)]
    out = []
    for n, p in enumerate(day.picks):
        slot = f"{p.slot:%d/%m %H:%M}"
        if p.card_rank:
            out.append(rank(("card", p.card_rank), f"card {p.card_rank}", slot))
        else:
            out.append(rank(("pick", n), "fora dos cards", slot))
    return out


MIN_TRIAGED = 5  # abaixo disso, "nenhum relevante" ainda é amostra pequena demais


@dataclass
class PruneCandidate:
    source_id: str
    strength: str  # "forte": podar salvo motivo contrário; "observar": decidir com Felipe
    reason: str


def prune_candidates(rows: list[SourceRow]) -> list[PruneCandidate]:
    """Fontes ligadas que não geraram nenhum card no T2. Só lista: quem poda é Felipe."""
    out = []
    for r in rows:
        if r.status in ("disabled", "ausente") or r.in_card:
            continue
        if r.collected == 0:
            out.append(PruneCandidate(r.source_id, "forte", "nenhum item coletado no período"))
        elif r.triaged >= MIN_TRIAGED and r.relevant == 0:
            out.append(PruneCandidate(
                r.source_id, "forte", f"nenhum relevante em {r.triaged} itens triados"))
        else:
            out.append(PruneCandidate(
                r.source_id, "observar",
                f"nenhum card; {r.relevant} relevantes em {r.triaged} triados "
                f"({r.collected} coletados)"))
    return out


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def render_report(
    sources: SourcesConfig, items: list[dict], days: list[GoldDay], generated: date
) -> str:
    """O relatório da calibração em markdown: escolhas no top 3, funil por fonte e
    candidatas à poda."""
    rows = source_table(sources, items, days)
    picks = [p for d in days for p in pick_positions(d)]
    hits = sum(p.top3 for p in picks)
    dates = sorted({it["published_brt_date"] for it in items if it.get("published_brt_date")})
    period = f"{dates[0]} a {dates[-1]}" if dates else "-"
    lines = [
        f"# Calibração do fim do T2 (gerado em {generated:%d/%m/%Y})",
        "",
        f"Gerado por `linky_agents.calibration`. {len({it['id'] for it in items})} itens "
        f"coletados (publicados de {period}); {len(days)} dias no gold set "
        f"({', '.join(str(d.date) for d in days)}). Só os itens das janelas do gold set têm "
        'triagem: os coletados fora delas contam só em "coletados".',
        "",
        f"## 1. Escolha no top {TOP} da rubrica",
        "",
        f"**{hits} de {len(picks)} escolhas no top {TOP} ({_pct(hits, len(picks))})** · "
        "meta da rubrica: 80%. Posição contada por fato (itens do mesmo card valem um).",
        "",
        f"| Dia do gold set | Escolha | Horário | Posição na rubrica | No top {TOP}? |",
        "|---|---|---|---|---|",
    ]
    for p in picks:
        pos = str(p.position) if p.position else "sem nota"
        lines.append(f"| {p.day} | {p.label} | {p.slot or '-'} | {pos} | "
                     f"{'sim' if p.top3 else '**não**'} |")
    lines += ["", "Por dia:", ""]
    for d in days:
        dp = [p for p in picks if p.day == str(d.date)]
        top_n = max(TOP, len(dp))
        all_in = bool(dp) and all(p.position is not None and p.position <= top_n for p in dp)
        lines.append(f"- {d.date}: {sum(p.top3 for p in dp)} de {len(dp)} no top {TOP}; "
                     f"todas no top {top_n} (uma vaga por escolha): {'sim' if all_in else 'não'}")
    lines += [
        "",
        "## 2. Funil por fonte",
        "",
        "Em card: itens da fonte em algum card (entre parênteses, como item principal). "
        "Post: itens numa pauta que virou post aprovado, inclusive como fonte irmã.",
        "",
        "| Fonte | Tier | Status | Coletados | Triados | Relevantes | Com nota | Em card "
        "| Post | % relevantes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (-r.posted, -r.in_card, -r.relevant, -r.collected)):
        lines.append(
            f"| {r.source_id} | {r.tier} | {r.status} | {r.collected} | {r.triaged} | "
            f"{r.relevant} | {r.scored} | {r.in_card} ({r.lead_card}) | {r.posted} | "
            f"{_pct(r.relevant, r.triaged)} |"
        )
    cands = prune_candidates(rows)
    lines += [
        "",
        "## 3. Candidatas à poda (nada foi podado)",
        "",
        "Fontes ligadas sem nenhum card no T2. **forte**: nada coletado, ou nenhum relevante "
        f"em pelo menos {MIN_TRIAGED} triados. **observar**: nenhum card, mas teve "
        "relevantes ou triou poucos itens.",
        "",
        "| Fonte | Força | Motivo |",
        "|---|---|---|",
    ]
    cands.sort(key=lambda c: c.strength != "forte")
    lines += [f"| {c.source_id} | {c.strength} | {c.reason} |" for c in cands]
    if not cands:
        lines.append("| - | - | nenhuma |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibração do fim do T2 (linky-dev)")
    parser.add_argument("items", nargs="+", help="arquivos data/items/*.jsonl")
    parser.add_argument("--gold", default="eval/gold", help="pasta do gold set")
    parser.add_argument("--sources", default="sources/sources.yaml")
    parser.add_argument("--out", help="grava o relatório aqui (padrão: imprime)")
    args = parser.parse_args(argv)
    items = [it for p in sorted(args.items) for it in load_items(Path(p))]
    days = [
        GoldDay.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(Path(args.gold).glob("*.json"))
    ]
    report = render_report(load_sources(Path(args.sources)), items, days, date.today())
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8", newline="\n")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # console do Windows usa cp1252
        print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
