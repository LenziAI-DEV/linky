"""Execução de um agente: a única interface que o resto do sistema precisa conhecer.

    result = harness.run(spec, entrada)

Por trás dela: prompt versionado, orçamento de tokens, chamada ao fornecedor, validação da
saída contra o contrato, nova tentativa, fallback, ledger de custo e registro JSON.
"""

from __future__ import annotations

import json
import re
import time as _time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .budget import InputTooLarge, estimate_tokens, fit
from .config import ModelRef, ModelsConfig, PriceTable, load_models, load_prices
from .errors import BudgetExceeded, RunFailed
from .ledger import Alert, Ledger
from .prompt import Prompt, WebDocument, load_prompt, system_text, user_text
from .providers import Message, Provider, ProviderError, Reply, Request, build_providers

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AgentSpec:
    """Contrato de um agente: nome, versão do prompt e os tipos de entrada e saída."""

    name: str
    version: str
    input: type[BaseModel]
    output: type[BaseModel]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    output: BaseModel
    model: str
    cost_usd: float
    record_path: Path


class Harness:
    def __init__(
        self,
        config: ModelsConfig,
        prices: PriceTable,
        prompts_dir: Path,
        providers: dict[str, Provider],
        data_dir: Path,
        alert: Callable[[Alert], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self.config = config
        self.prices = prices
        self.prompts_dir = Path(prompts_dir)
        self.providers = providers
        self.data_dir = Path(data_dir)
        self.alert = alert or (lambda _a: None)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep or _time.sleep
        self.ledger = Ledger(self.data_dir, config.budget)
        missing = sorted(
            {r.key for a in config.agents.values() for r in a.chain} - set(prices.models)
        )
        if missing:
            raise ValueError(f"modelos da cadeia sem preço em prices.yaml: {missing}")

    @classmethod
    def from_repo(
        cls,
        root: Path = ROOT,
        data_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
        alert: Callable[[Alert], None] | None = None,
    ) -> Harness:
        """Harness de produção: `config/models.yaml`, `config/prices.yaml` e `prompts/`."""
        config = load_models(root / "config" / "models.yaml")
        return cls(
            config=config,
            prices=load_prices(root / "config" / "prices.yaml"),
            prompts_dir=root / "prompts",
            providers=build_providers(config, env),
            data_dir=data_dir or root / "data",
            alert=alert,
        )

    def spending(self) -> dict[str, float]:
        """Gasto do dia e do mês corrente, segundo o ledger."""
        return self.ledger.spent(self.clock())

    def run(self, spec: AgentSpec, inp: BaseModel, run_id: str | None = None) -> RunResult:
        """Executa o agente e devolve a saída validada. Falhas levantam `RunFailed`."""
        cfg = self.config.agent(spec.name)
        prompt = load_prompt(self.prompts_dir, spec.name, spec.version)
        run = _Run(run_id or uuid.uuid4().hex[:12], spec, prompt, self.clock())
        run.input = inp.model_dump(mode="json")
        system = system_text(prompt, spec.output.model_json_schema())
        doc_field = _documents_field(spec.input)
        trusted = {k: v for k, v in run.input.items() if k != doc_field}
        documents = list(getattr(inp, doc_field)) if doc_field else []
        try:
            try:
                trim = fit(
                    documents, cfg.max_doc_tokens, cfg.max_input_tokens,
                    lambda docs: system + user_text(trusted, docs),
                )
            except InputTooLarge as e:
                raise RunFailed(f"{spec.name}: {e}") from e
            run.budget = trim.summary()
            user = user_text(trusted, trim.documents)
            for i, ref in enumerate(cfg.chain):
                reason = self._try_model(run, spec, ref, cfg, system, user)
                if run.output is not None:
                    run.status = "ok"
                    return RunResult(
                        run.run_id, run.output, ref.key, run.cost, self._write(run)
                    )
                if i + 1 < len(cfg.chain):
                    run.switches.append(
                        {"from": ref.key, "to": cfg.chain[i + 1].key, "reason": reason}
                    )
            raise RunFailed(f"{spec.name}: nenhum modelo da cadeia entregou saída válida")
        except RunFailed as e:
            run.status = "budget_blocked" if isinstance(e, BudgetExceeded) else "failed"
            run.error = str(e)
            e.record_path = self._write(run)
            raise

    def _try_model(self, run, spec, ref: ModelRef, cfg, system: str, user: str) -> str:
        """Tenta um modelo. Preenche `run.output` em caso de sucesso; senão devolve o motivo."""
        provider = self.providers[ref.provider]
        messages = [Message("user", user)]
        retries = 0
        repaired = False
        while True:
            t0 = _time.perf_counter()
            request = Request(
                model=ref.model,
                system=system,
                messages=list(messages),
                max_output_tokens=cfg.max_output_tokens,
                timeout_s=cfg.timeout_s,
                params=dict(ref.params),
            )
            now = self.clock()
            est = estimate_tokens(system, *(m.content for m in messages))
            worst = self.prices.cost(ref.key, Reply("", est, cfg.max_output_tokens), now)
            blocked = self.ledger.check(run.cost, worst, now)
            if blocked:
                self._alert(run, blocked)
                raise BudgetExceeded(f"{spec.name}: {blocked.message}", blocked.scope)
            try:
                reply = provider.complete(request)
            except ProviderError as e:
                run.attempt(ref.key, "provider_error", t0, error=str(e))
                if e.retryable and retries < self.config.retry.max_retries:
                    retries += 1
                    self.sleep(self.config.retry.backoff_s * 2 ** (retries - 1))
                    continue
                return "provider_error"
            cost = self.prices.cost(ref.key, reply, now)
            warns = self.ledger.add(
                now, run.cost,
                {"run_id": run.run_id, "agent": spec.name, "model": ref.key,
                 "tokens": _tokens(reply), "cost_usd": cost},
            )
            for w in warns:
                self._alert(run, w)
            try:
                output = _parse(spec.output, reply.text)
            except ValidationError as e:
                run.attempt(ref.key, "invalid_output", t0, reply, cost, error=_short(e))
                if repaired:
                    return "invalid_output"
                repaired = True
                messages += [Message("assistant", reply.text), Message("user", _repair(e))]
                continue
            run.attempt(ref.key, "ok", t0, reply, cost)
            run.output = output
            run.model = ref.key
            return "ok"

    def _alert(self, run: _Run, alert: Alert) -> None:
        """Chama o gancho de alerta sem deixar uma falha dele derrubar a execução."""
        try:
            self.alert(alert)
            delivered = True
        except Exception:  # noqa: BLE001 - o alerta não pode perder um resultado já pago
            delivered = False
        run.alerts.append(
            {"kind": alert.kind, "scope": alert.scope, "message": alert.message,
             "delivered": delivered}
        )

    def _write(self, run: _Run) -> Path:
        path = self.data_dir / "runs" / run.started.date().isoformat() / f"{run.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = run.record(self.prices.version)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        return path


# --------------------------------------------------------------------------- execução
def _documents_field(model: type[BaseModel]) -> str | None:
    """Campo da entrada com texto da web (`list[WebDocument]`). No máximo um por contrato."""
    names = [n for n, f in model.model_fields.items() if f.annotation == list[WebDocument]]
    if len(names) > 1:
        raise TypeError(f"{model.__name__}: só um campo list[WebDocument] é permitido")
    return names[0] if names else None


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _parse(model: type[BaseModel], text: str) -> BaseModel:
    m = _FENCE.match(text)
    return model.model_validate_json(m.group(1) if m else text.strip())


def _short(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(x) for x in err['loc']) or '(raiz)'}: {err['msg']}" for err in e.errors()
    )


def _repair(e: ValidationError) -> str:
    return (
        "Sua resposta não passou na validação do contrato: "
        f"{_short(e)}. Responda de novo só com o objeto JSON válido."
    )


@dataclass
class _Run:
    run_id: str
    spec: AgentSpec
    prompt: Prompt
    started: datetime
    input: dict = field(default_factory=dict)
    status: str = "running"
    error: str | None = None
    model: str | None = None
    output: BaseModel | None = None
    attempts: list[dict] = field(default_factory=list)
    switches: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    t0: float = field(default_factory=_time.perf_counter)

    @property
    def cost(self) -> float:
        return sum(a["cost_usd"] for a in self.attempts)

    def attempt(self, model, outcome, t0, reply: Reply | None = None, cost=0.0, error=None):
        tokens = _tokens(reply) if reply else _tokens(None)
        self.attempts.append(
            {
                "model": model,
                "outcome": outcome,
                "error": error,
                "tokens": tokens,
                "cost_usd": cost,
                "latency_ms": round((_time.perf_counter() - t0) * 1000),
            }
        )

    def record(self, price_version: str) -> dict:
        tokens = {k: sum(a["tokens"][k] for a in self.attempts) for k in _tokens(None)}
        return {
            "run_id": self.run_id,
            "agent": self.spec.name,
            "status": self.status,
            "error": self.error,
            "started_at": self.started.isoformat(),
            "prompt": {
                "id": self.prompt.id,
                "version": self.prompt.version,
                "sha256": self.prompt.sha256,
            },
            "contract": {
                "input": self.spec.input.__name__,
                "output": self.spec.output.__name__,
            },
            "price_table": price_version,
            "input": self.input,
            "model": self.model,
            "attempts": self.attempts,
            "switches": self.switches,
            "budget": self.budget,
            "alerts": self.alerts,
            "tokens": tokens,
            "cost_usd": self.cost,
            "latency_ms": round((_time.perf_counter() - self.t0) * 1000),
            "output": self.output.model_dump(mode="json") if self.output else None,
        }


def _tokens(reply: Reply | None) -> dict[str, int]:
    if reply is None:
        return {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0}
    return {
        "input": reply.input_tokens,
        "cached_input": reply.cached_input_tokens,
        "cache_write": reply.cache_write_tokens,
        "output": reply.output_tokens,
    }
