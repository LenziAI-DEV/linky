"""Adaptadores HTTP dos fornecedores, testados com httpx.MockTransport (sem rede)."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import BaseModel

from linky_agents.harness import (
    AgentSpec,
    FakeProvider,
    Harness,
    Message,
    ModelsConfig,
    PriceTable,
    ProviderError,
    Reply,
    Request,
    build_providers,
)
from linky_agents.harness.providers import AnthropicProvider, OpenAICompatible

REQ = Request(
    model="m", system="FIXO", messages=[Message("user", "VARIÁVEL")],
    max_output_tokens=300, timeout_s=12, params={"reasoning_effort": "minimal"},
)


def client(handler, seen):
    def wrap(request: httpx.Request):
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrap))


def openai_ok(_req):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 800},
            },
        },
    )


# ------------------------------------------------------------------ OpenAI e DeepSeek
def test_openai_request_puts_fixed_part_first_and_always_limits_output():
    seen = []
    p = OpenAICompatible(
        "https://api.openai.com/v1", "sk-x", "max_completion_tokens", client(openai_ok, seen)
    )
    reply = p.complete(REQ)
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer sk-x"
    assert body["messages"][0] == {"role": "system", "content": "FIXO"}
    assert body["messages"][-1] == {"role": "user", "content": "VARIÁVEL"}
    assert body["max_completion_tokens"] == 300
    assert body["reasoning_effort"] == "minimal"
    assert body["response_format"] == {"type": "json_object"}
    # o uso cobrado separa entrada cheia de entrada em cache
    assert reply == Reply('{"a": 1}', input_tokens=200, output_tokens=50, cached_input_tokens=800)


def test_deepseek_cache_hit_fields_are_read():
    def handler(_req):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {
                    "prompt_tokens": 1000, "completion_tokens": 10,
                    "prompt_cache_hit_tokens": 600, "prompt_cache_miss_tokens": 400,
                },
            },
        )

    p = OpenAICompatible("https://api.deepseek.com", "k", "max_tokens", client(handler, []))
    r = p.complete(REQ)
    assert (r.input_tokens, r.cached_input_tokens) == (400, 600)


# ------------------------------------------------------------------ Anthropic
def test_anthropic_request_marks_the_fixed_part_for_cache_and_reads_usage():
    seen = []

    def handler(_req):
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"a": 1}'}],
                "usage": {
                    "input_tokens": 100, "output_tokens": 40,
                    "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0,
                },
            },
        )

    p = AnthropicProvider("https://api.anthropic.com", "sk-ant", client(handler, seen))
    r = p.complete(REQ)
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.anthropic.com/v1/messages"
    assert seen[0].headers["x-api-key"] == "sk-ant"
    assert seen[0].headers["anthropic-version"]
    assert body["system"] == [
        {"type": "text", "text": "FIXO", "cache_control": {"type": "ephemeral"}}
    ]
    assert body["max_tokens"] == 300
    assert r == Reply('{"a": 1}', input_tokens=100, output_tokens=40, cached_input_tokens=900)


# ------------------------------------------------------------------ erros
@pytest.mark.parametrize(("status", "retryable"), [(429, True), (503, True), (529, True),
                                                   (400, False), (401, False)])
def test_http_errors_say_whether_a_retry_makes_sense(status, retryable):
    p = OpenAICompatible(
        "https://x", "k", "max_tokens", client(lambda r: httpx.Response(status, text="erro"), [])
    )
    with pytest.raises(ProviderError) as exc:
        p.complete(REQ)
    assert exc.value.retryable is retryable


def test_timeout_is_retryable():
    def handler(req):
        raise httpx.ReadTimeout("lento", request=req)

    p = AnthropicProvider("https://x", "k", client(handler, []))
    with pytest.raises(ProviderError) as exc:
        p.complete(REQ)
    assert exc.value.retryable is True


# ------------------------------------------------------------------ montagem
class In(BaseModel):
    q: str


class Out(BaseModel):
    a: int


def config(chain):
    return ModelsConfig.model_validate(
        {
            "providers": {
                "openai": {"kind": "openai", "base_url": "https://api.openai.com/v1",
                           "api_key_env": "OPENAI_API_KEY"},
                "fake": {"kind": "fake"},
            },
            "budget": {"per_run_usd": 1, "per_day_usd": 1, "per_month_usd": 3},
            "agents": {"eco": {"max_input_tokens": 4000, "max_output_tokens": 100,
                               "chain": chain}},
        }
    )


PRICES = PriceTable.model_validate(
    {"version": "t", "models": {"openai/m": {"input": 1, "output": 1},
                                "fake/reserva": {"input": 1, "output": 1}}}
)


@pytest.fixture
def prompts(tmp_path):
    (tmp_path / "p" / "eco").mkdir(parents=True)
    (tmp_path / "p" / "eco" / "v1.md").write_text("Eco.", encoding="utf-8")
    return tmp_path / "p"


def test_api_keys_never_reach_the_run_record_or_the_ledger(tmp_path, prompts):
    secret = "sk-SEGREDO-123"
    cfg = config([{"provider": "openai", "model": "m"}])
    providers = build_providers(
        cfg, env={"OPENAI_API_KEY": secret},
        client=httpx.Client(transport=httpx.MockTransport(openai_ok)),
    )
    h = Harness(cfg, PRICES, prompts, providers, tmp_path / "data",
                clock=lambda: datetime(2026, 11, 9, tzinfo=UTC))
    assert h.run(AgentSpec("eco", "v1", In, Out), In(q="oi")).output == Out(a=1)
    written = [p.read_text(encoding="utf-8") for p in (tmp_path / "data").rglob("*.*")]
    assert len(written) == 2  # registro da execução + ledger
    assert all(secret not in text for text in written)


def test_missing_api_key_falls_back_to_the_next_model(tmp_path, prompts):
    cfg = config([{"provider": "openai", "model": "m"}, {"provider": "fake", "model": "reserva"}])
    fake = FakeProvider({"reserva": [Reply('{"a": 2}', 10, 1)]})
    providers = build_providers(cfg, env={}) | {"fake": fake}
    h = Harness(cfg, PRICES, prompts, providers, tmp_path / "data")
    result = h.run(AgentSpec("eco", "v1", In, Out), In(q="oi"))
    assert result.model == "fake/reserva"


def test_repository_config_is_consistent_and_caps_the_month_at_3_dollars(tmp_path):
    h = Harness.from_repo(data_dir=tmp_path, env={})
    assert h.config.budget.per_month_usd == 3.0
    assert set(h.config.agents) >= {"triagem", "curadoria", "redacao", "checagem", "arte"}
    for agent in h.config.agents.values():
        providers = [r.provider for r in agent.chain]
        assert all(p in h.config.providers for p in providers)


# Conferido na documentação dos fornecedores em 10/11/2026 (docs/discovery/g-pesquisas.md §3).
RETIRED = {"openai/gpt-5-nano", "openai/gpt-5-mini"}  # saem da API em 11/12/2026
EFFORTS = {
    "openai": {"none", "low", "medium", "high", "xhigh", "max"},  # gpt-6-luna: sem minimal
    "deepseek": {"none", "low", "high", "max"},
    "anthropic": {"low", "medium", "high", "xhigh", "max"},
}


def test_repository_chains_use_live_models_with_cache_prices_and_valid_effort(tmp_path):
    h = Harness.from_repo(data_dir=tmp_path, env={})
    for name, agent in h.config.agents.items():
        for ref in agent.chain:
            assert ref.key not in RETIRED, f"{name}: {ref.key} sai da API em 11/12/2026"
            price = h.prices.models[ref.key]
            assert price.cached_input is not None, f"{ref.key} sem preço de leitura de cache"
            assert "temperature" not in ref.params  # recusada ou ignorada nos modelos atuais
            if ref.provider == "anthropic":
                effort = ref.params.get("output_config", {}).get("effort")
            else:
                effort = ref.params.get("reasoning_effort")
            assert effort in EFFORTS[ref.provider], f"{name}/{ref.key}: effort {effort!r}"


def test_deepseek_cache_hit_is_billed_at_the_cache_price_with_offpeak_discount(tmp_path):
    h = Harness.from_repo(data_dir=tmp_path, env={})
    usage = Reply("", 0, 0, cached_input_tokens=1_000_000)
    peak = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)  # terça, 02:00 UTC
    offpeak = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    assert h.prices.cost("deepseek/deepseek-v4-pro", usage, peak) == pytest.approx(0.044)
    assert h.prices.cost("deepseek/deepseek-v4-pro", usage, offpeak) == pytest.approx(0.022)
