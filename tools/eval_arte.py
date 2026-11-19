"""Avaliação da frente Imagem (agente de arte), para rodar no container do serviço na VPS.

Dois modos:

    python tools/eval_arte.py render
        Desenha os dois exemplos do prompt (sem modelo, sem custo) e mede o pico de memória:
        prova que o motor roda no container somente leitura, com /tmp de 16 MB e 256 MB.

    python tools/eval_arte.py eval [--model openai/gpt-6-luna] [--effort low] [--label nome]
        Gera as imagens de 4 posts do T2 a partir do gold set (eval/gold/2026-11-09.json e -10)
        com `make_image`, em ordem (o tema alterna pelo registro de /data), e grava em
        /data/eval-arte/<label>/ os PNGs, a composição, o texto alternativo, as tentativas e o
        custo medido pelo ledger. `--model` troca a cadeia do agente por um modelo só.

O gold set e este arquivo entram no container por volume, só leitura (ver
docs/editorial/calibracao/03-arte-v1.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

from linky_agents.agents import art
from linky_agents.agents.contracts import Draft, Hook
from linky_agents.editorial import Entry
from linky_agents.harness import Harness
from linky_agents.harness.config import ModelRef

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("LINKY_DATA_DIR", "/data"))

# (dia do gold, script da imagem do T2, data do fato) dos 4 posts avaliados. Uber e IPO ficam
# de fora: são os exemplos do prompt.
POSTS = [
    ("2026-11-09", "2026-11-11-claude-code-segredos", date(2026, 11, 9)),
    ("2026-11-09", "2026-11-11-cotas-de-ia", date(2026, 11, 9)),
    ("2026-11-10", "2026-11-12-adobe-agentes", date(2026, 11, 10)),
    ("2026-11-09", "2026-11-13-bain-brasil", date(2026, 11, 9)),
]
FORMAT_TO_PATTERN = {"tese": "P1", "dado": "P2", "caso": "P3", "lancamento": "P4",
                     "pesquisa": "P5"}
_MENTION = re.compile(r"@\[([^\]]+)\]\(urn:li:[^)]+\)")


def peak_memory() -> dict:
    import resource  # só existe no Linux (o container)

    out = {"ru_maxrss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
    for name in ("memory.peak", "memory.current"):
        p = Path("/sys/fs/cgroup") / name
        if p.exists():
            out[f"cgroup_{name.split('.')[1]}_mb"] = round(int(p.read_text()) / 2**20, 1)
    return out


def gold_case(day: str, script: str, event: date) -> tuple[Entry, Draft]:
    gold = json.loads((ROOT / "eval" / "gold" / f"{day}.json").read_text(encoding="utf-8"))
    pick = next(p for p in gold["picks"]
                if p["post"].get("image_spec", {}).get("script", "").endswith(f"{script}.py"))
    card = next(c for c in gold["cards"] if c["rank"] == pick["card_rank"])
    text = _MENTION.sub(r"\1", pick["post"]["final"])
    paras = [p for p in text.split("\n\n") if p.strip()]
    entry = Entry(
        id=script, title=card["title"], event_date=event, sources=card["sources"],
        what=card["what_happened"], why=card.get("why_it_matters", ""),
        angle=card["approach"], pattern=FORMAT_TO_PATTERN.get(card["format"], card["format"]),
        audience="gestor", batch="eval-arte", proposed_at=datetime.fromisoformat(pick["slot"]),
    )
    draft = Draft(
        structure="E2", hooks=[Hook(kind="H1", text=paras[0][:200])],
        body="\n\n".join(paras[1:-3]), readings=[paras[-3]], tail="\n\n".join(paras[-2:]),
        closing="publico", headline=card["title"],
    )
    return entry, draft


def cmd_render() -> None:
    from linky_agents.render.compose import check, to_png

    prompt = (ROOT / "prompts" / "arte" / "v1.md").read_text(encoding="utf-8")
    examples = re.findall(r"```json\n(.*?)\n```", prompt, re.S)
    t0 = time.perf_counter()
    for i, (raw, theme) in enumerate(zip(examples, ("claro", "escuro"), strict=True), start=1):
        c = art.build(art.ArtDesign.model_validate_json(raw), theme, date(2026, 11, 10))
        assert check(c) == [], check(c)
        png = to_png(c)
        out = DATA / "eval-arte" / "render" / f"exemplo{i}-{theme}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print(f"{out} ({len(png) // 1024} KB)")
    print(json.dumps({"seconds": round(time.perf_counter() - t0, 1), **peak_memory()}))


def cmd_eval(args) -> None:
    h = Harness.from_repo(data_dir=DATA)
    if args.model:
        provider, model = args.model.split("/", 1)
        params = {}
        if args.effort:
            params = ({"output_config": {"effort": args.effort}} if provider == "anthropic"
                      else {"reasoning_effort": args.effort})
        h.config.agents["arte"].chain = [ModelRef(provider=provider, model=model, params=params)]
    out = DATA / "eval-arte" / args.label
    out.mkdir(parents=True, exist_ok=True)
    data_dir = out / "estado"  # registro próprio: o tema alterna só dentro desta rodada
    report = []
    for day, script, event in POSTS:
        entry, draft = gold_case(day, script, event)
        before = h.spending()["month_usd"]
        seen = set((DATA / "runs").glob("*/*.json"))
        t0 = time.perf_counter()
        row = {"post": script, "model": args.model or "cadeia do models.yaml"}
        try:
            r = art.make_image(entry, draft, harness=h, data_dir=data_dir)
        except art.ArtRejected as e:
            row |= {"ok": False, "reasons": e.reasons}
        except Exception as e:  # noqa: BLE001 - a avaliação registra e segue
            row |= {"ok": False, "error": f"{type(e).__name__}: {e}"}
        else:
            (out / f"{script}.png").write_bytes(r.png)
            (out / f"{script}.json").write_text(
                json.dumps({"alt_text": r.alt_text, "theme": r.theme,
                            "composition": r.composition}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            row |= {"ok": True, "theme": r.theme, "alt_text": r.alt_text}
        after = h.spending()["month_usd"]
        row |= {"cost_usd": round(after - before, 5),
                "seconds": round(time.perf_counter() - t0, 1)}
        runs = sorted(set((DATA / "runs").glob("*/*.json")) - seen,
                      key=lambda p: p.stat().st_mtime)
        tries = [json.loads(p.read_text(encoding="utf-8")) for p in runs]
        row["attempts"] = [
            {"model": t["model"], "status": t["status"], "cost_usd": round(t["cost_usd"], 5),
             "tokens": t["tokens"],
             "rejections": (t["input"].get("rejections") or [])[:6]}
            for t in tries if t["agent"] == "arte"
        ]
        report.append(row)
        print(json.dumps(row, ensure_ascii=False)[:1500], flush=True)
    summary = {"label": args.label, "total_usd": round(sum(r["cost_usd"] for r in report), 5),
               "ok": sum(r["ok"] for r in report), **peak_memory()}
    (out / "relatorio.json").write_text(
        json.dumps({"summary": summary, "posts": report}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps(summary))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    ev = sub.add_parser("eval")
    ev.add_argument("--model")
    ev.add_argument("--effort")
    ev.add_argument("--label", default="cadeia")
    args = ap.parse_args(argv)
    if args.cmd == "render":
        cmd_render()
    else:
        cmd_eval(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
