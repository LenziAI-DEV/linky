"""Camada fina de adaptação por fornecedor.

Todo fornecedor recebe um `Request` neutro e devolve um `Reply` com o texto e o uso real de
tokens informado pela API. Erros viram `ProviderError`, que diz se vale tentar de novo.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Request:
    model: str
    system: str  # parte fixa: vem primeiro para aproveitar o cache de prefixo
    messages: list[Message]  # parte variável, no fim
    max_output_tokens: int
    timeout_s: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Reply:
    text: str
    input_tokens: int  # entrada cobrada a preço cheio (sem leitura nem escrita de cache)
    output_tokens: int  # inclui tokens de raciocínio
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0


class ProviderError(Exception):
    """Falha do fornecedor. `retryable` vale para timeout, 429 e 5xx."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class Provider(Protocol):
    def complete(self, request: Request) -> Reply: ...


# --------------------------------------------------------------------------- falso
Scripted = Reply | ProviderError | Callable[[Request], Reply]


class FakeProvider:
    """Fornecedor de teste: devolve respostas roteirizadas por modelo, em ordem.

    `scripts` = {"modelo": [Reply | ProviderError | função(request) -> Reply, ...]}.
    Guarda os requests recebidos em `requests`. Roteiro esgotado é erro do teste.
    """

    def __init__(self, scripts: dict[str, list[Scripted]]):
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self.requests: list[Request] = []

    def complete(self, request: Request) -> Reply:
        self.requests.append(request)
        queue = self._scripts.get(request.model)
        if not queue:
            raise AssertionError(f"FakeProvider sem resposta roteirizada para {request.model}")
        step = queue.pop(0)
        if isinstance(step, ProviderError):
            raise step
        if isinstance(step, Reply):
            return step
        return step(request)


# --------------------------------------------------------------------------- HTTP
_RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}


def _post(client: httpx.Client, url: str, headers: dict, body: dict, timeout: float) -> dict:
    """POST com erros normalizados. A mensagem nunca inclui cabeçalhos (onde vai a chave)."""
    try:
        r = client.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        raise ProviderError(f"timeout após {timeout}s ({type(e).__name__})", retryable=True) from e
    except httpx.TransportError as e:
        raise ProviderError(f"falha de rede ({type(e).__name__})", retryable=True) from e
    if r.status_code >= 400:
        raise ProviderError(
            f"HTTP {r.status_code}: {r.text[:300]}", retryable=r.status_code in _RETRYABLE
        )
    try:
        return r.json()
    except ValueError as e:
        raise ProviderError("resposta não é JSON", retryable=True) from e


class OpenAICompatible:
    """OpenAI e DeepSeek (API de chat compatível com a da OpenAI)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_tokens_param: str = "max_tokens",
        client: httpx.Client | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self.max_tokens_param = max_tokens_param
        self.client = client or httpx.Client()

    def complete(self, request: Request) -> Reply:
        body = {
            "model": request.model,
            "messages": [{"role": "system", "content": request.system}]
            + [{"role": m.role, "content": m.content} for m in request.messages],
            self.max_tokens_param: request.max_output_tokens,
            "response_format": {"type": "json_object"},
            **request.params,
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        data = _post(self.client, self.url, headers, body, request.timeout_s)
        try:
            text = data["choices"][0]["message"]["content"] or ""
            u = data["usage"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("resposta sem choices/usage", retryable=True) from e
        details = u.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens") or u.get("prompt_cache_hit_tokens") or 0
        return Reply(
            text=text,
            input_tokens=u["prompt_tokens"] - cached,
            output_tokens=u["completion_tokens"],
            cached_input_tokens=cached,
        )


class AnthropicProvider:
    """API de mensagens da Anthropic. A parte fixa vai marcada para cache."""

    VERSION = "2023-06-01"

    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None):
        self.url = base_url.rstrip("/") + "/v1/messages"
        self._key = api_key
        self.client = client or httpx.Client()

    def complete(self, request: Request) -> Reply:
        body = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "system": [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            **request.params,
        }
        headers = {"x-api-key": self._key, "anthropic-version": self.VERSION}
        data = _post(self.client, self.url, headers, body, request.timeout_s)
        try:
            text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
            u = data["usage"]
        except (KeyError, TypeError) as e:
            raise ProviderError("resposta sem content/usage", retryable=True) from e
        return Reply(
            text=text,
            input_tokens=u["input_tokens"],
            output_tokens=u["output_tokens"],
            cached_input_tokens=u.get("cache_read_input_tokens") or 0,
            cache_write_tokens=u.get("cache_creation_input_tokens") or 0,
        )


class MissingKey:
    """Fornecedor sem chave no ambiente: falha sem retentativa, e a cadeia segue."""

    def __init__(self, name: str, env_var: str | None):
        self.message = f"{name}: variável de ambiente {env_var or '(não definida)'} ausente"

    def complete(self, request: Request) -> Reply:
        raise ProviderError(self.message, retryable=False)


def build_providers(
    config, env: Mapping[str, str] | None = None, client: httpx.Client | None = None
) -> dict[str, Provider]:
    """Monta os fornecedores de `models.yaml`. Fornecedores `fake` ficam de fora."""
    env = os.environ if env is None else env
    out: dict[str, Provider] = {}
    for name, p in config.providers.items():
        if p.kind == "fake":
            continue
        key = env.get(p.api_key_env or "")
        if not key or not p.base_url:
            out[name] = MissingKey(name, p.api_key_env)
        elif p.kind == "anthropic":
            out[name] = AnthropicProvider(p.base_url, key, client)
        else:
            out[name] = OpenAICompatible(p.base_url, key, p.max_tokens_param, client)
    return out
