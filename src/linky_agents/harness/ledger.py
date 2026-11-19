"""Ledger de custo: cada chamada paga vira uma linha em `data/ledger/AAAA-MM.jsonl`.

O custo vem do uso real devolvido pela API × tabela de preços versionada. Antes de cada
chamada, o pior caso (entrada estimada + saída máxima) é comparado com os tetos da execução,
do dia e do mês (no fuso do orçamento). Se estourar, a chamada não acontece.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Budget

_EPS = 1e-12


@dataclass(frozen=True)
class Alert:
    """Aviso para o gancho de alerta (no MVP, vira e-mail pelo n8n)."""

    kind: str  # "budget_warning" | "budget_blocked"
    scope: str  # "run" | "day" | "month"
    spent_usd: float
    cap_usd: float
    message: str


class Ledger:
    def __init__(self, data_dir: Path, budget: Budget):
        self.dir = Path(data_dir) / "ledger"
        self.budget = budget
        self.tz = ZoneInfo(budget.timezone)

    def _file(self, at: datetime) -> Path:
        return self.dir / f"{at.astimezone(self.tz):%Y-%m}.jsonl"

    def _rows(self, at: datetime) -> list[dict]:
        f = self._file(at)
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]

    def spent(self, at: datetime) -> dict[str, float]:
        """Gasto do dia e do mês de `at`, no fuso do orçamento."""
        day = at.astimezone(self.tz).date().isoformat()
        rows = self._rows(at)
        return {
            "day_usd": sum(r["cost_usd"] for r in rows if r["day"] == day),
            "month_usd": sum(r["cost_usd"] for r in rows),
        }

    def caps(self, run_spent: float, at: datetime) -> list[tuple[str, float, float]]:
        s = self.spent(at)
        b = self.budget
        return [
            ("run", run_spent, b.per_run_usd),
            ("day", s["day_usd"], b.per_day_usd),
            ("month", s["month_usd"], b.per_month_usd),
        ]

    def check(self, run_spent: float, worst_case: float, at: datetime) -> Alert | None:
        """Devolve um alerta de bloqueio se a próxima chamada puder estourar algum teto."""
        for scope, spent, cap in self.caps(run_spent, at):
            if spent + worst_case > cap + _EPS:
                return Alert(
                    "budget_blocked", scope, spent, cap,
                    f"teto de {scope} (US$ {cap:.4f}) seria estourado: gasto US$ {spent:.4f} "
                    f"+ pior caso US$ {worst_case:.4f}. Chamada cancelada.",
                )
        return None

    def add(self, at: datetime, run_spent_before: float, entry: dict) -> list[Alert]:
        """Registra uma chamada paga e devolve os avisos de teto cruzados por ela."""
        before = self.caps(run_spent_before, at)
        self.dir.mkdir(parents=True, exist_ok=True)
        row = {"at": at.isoformat(), "day": at.astimezone(self.tz).date().isoformat(), **entry}
        with self._file(at).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        warns = []
        for scope, spent, cap in before:
            limit = cap * self.budget.warn_ratio
            after = spent + entry["cost_usd"]
            if scope != "run" and spent < limit - _EPS and after >= limit - _EPS:
                warns.append(
                    Alert(
                        "budget_warning", scope, after, cap,
                        f"gasto de {scope} chegou a US$ {after:.4f} "
                        f"({after / cap:.0%} do teto de US$ {cap:.2f})",
                    )
                )
        return warns
