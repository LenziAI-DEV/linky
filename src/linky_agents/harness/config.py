"""Configuração do harness: modelos por agente (`config/models.yaml`) e preços
(`config/prices.yaml`).

Os dois arquivos são versionados. Os preços valem por milhão de tokens, em dólares.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- modelos
class ProviderConfig(_Strict):
    kind: Literal["openai", "anthropic", "fake"]
    base_url: str | None = None
    api_key_env: str | None = None
    # Nome do parâmetro de saída máxima na API compatível com a OpenAI
    # (a OpenAI usa max_completion_tokens; a DeepSeek, max_tokens)
    max_tokens_param: str = "max_tokens"


class ModelRef(_Strict):
    provider: str
    model: str
    params: dict[str, Any] = {}  # repassados à API (temperatura, raciocínio...)

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


class AgentConfig(_Strict):
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_doc_tokens: int = Field(default=1200, gt=0)
    timeout_s: float = Field(default=60, gt=0)
    chain: list[ModelRef] = Field(min_length=1)


class Budget(_Strict):
    per_run_usd: float = Field(gt=0)
    per_day_usd: float = Field(gt=0)
    per_month_usd: float = Field(gt=0)
    warn_ratio: float = Field(default=0.8, gt=0, le=1)
    timezone: str = "America/Sao_Paulo"


class Retry(_Strict):
    max_retries: int = Field(default=2, ge=0)  # novas tentativas por modelo, além da primeira
    backoff_s: float = Field(default=1.0, ge=0)  # espera = backoff_s × 2^(tentativa-1)


class ModelsConfig(_Strict):
    providers: dict[str, ProviderConfig]
    budget: Budget
    retry: Retry = Retry()
    agents: dict[str, AgentConfig]

    def agent(self, name: str) -> AgentConfig:
        if name not in self.agents:
            raise KeyError(f"agente sem configuração em models.yaml: {name}")
        return self.agents[name]


# --------------------------------------------------------------------------- preços
def _window(v: str) -> tuple[time, time]:
    a, b = v.split("-")
    return time.fromisoformat(a), time.fromisoformat(b)


class OffPeak(_Strict):
    """Desconto fora do pico (DeepSeek: pico de 01–04h e 06–10h UTC, em dias úteis)."""

    factor: float = Field(gt=0, le=1)
    peak_utc: list[str]
    weekdays_only: bool = True

    @field_validator("peak_utc")
    @classmethod
    def _check(cls, v: list[str]) -> list[str]:
        for w in v:
            _window(w)
        return v

    def factor_at(self, at: datetime) -> float:
        t = at.astimezone(UTC)
        if self.weekdays_only and t.weekday() >= 5:
            return self.factor
        for w in self.peak_utc:
            a, b = _window(w)
            if a <= t.time() < b:
                return 1.0
        return self.factor


class ModelPrice(_Strict):
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cached_input: float | None = Field(default=None, ge=0)  # sem valor: cobra como entrada
    cache_write: float | None = Field(default=None, ge=0)  # sem valor: cobra como entrada
    offpeak: OffPeak | None = None


class PriceTable(_Strict):
    version: str
    currency: Literal["USD"] = "USD"
    per_tokens: int = 1_000_000
    models: dict[str, ModelPrice]

    def cost(self, key: str, usage, at: datetime) -> float:
        p = self.models[key]
        f = p.offpeak.factor_at(at) if p.offpeak else 1.0
        cached = p.input if p.cached_input is None else p.cached_input
        write = p.input if p.cache_write is None else p.cache_write
        total = (
            usage.input_tokens * p.input
            + usage.cached_input_tokens * cached
            + usage.cache_write_tokens * write
            + usage.output_tokens * p.output
        )
        return total * f / self.per_tokens


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_models(path: Path) -> ModelsConfig:
    return ModelsConfig.model_validate(_yaml(path))


def load_prices(path: Path) -> PriceTable:
    data = _yaml(path)
    data["version"] = str(data["version"])  # o YAML lê 2026-11-05 como data
    return PriceTable.model_validate(data)
