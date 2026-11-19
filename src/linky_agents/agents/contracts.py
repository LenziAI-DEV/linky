"""Contratos entre os agentes e o serviço (produção do MVP, docs/ideas/producao-mvp.md).

Cada frente implementa o seu módulo contra estes tipos; o serviço (`linky_agents.service`)
só conhece estes tipos e as funções públicas de cada módulo:

- `linky_agents.agents.pautas.curate(items, *, harness, now, n_cards, exclude) -> list[CardOut]`
- `linky_agents.agents.post.fetch_sources(urls) -> list[WebDocument]`
- `linky_agents.agents.post.write(entry, sources, *, harness, recent_hooks) -> Draft`
- `linky_agents.agents.post.compose(draft, hook, reading) -> str`
- `linky_agents.agents.art.make_image(entry, draft, *, harness, data_dir) -> ImageResult`

Cada módulo também expõe `SPECS: dict[str, AgentSpec]` com os agentes que registra (o serviço
os expõe em `POST /agents/{nome}`, para depurar).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Pattern = str  # "P1" a "P6" (playbook.md §2) ou o ID de um padrão em teste
Audience = Literal["gestor", "builder", "estudante"]
HookKind = Literal["H1", "H2", "H3", "H4", "H5", "H6"]
Structure = Literal["E1", "E2", "E3", "E4", "E5"]
Closing = Literal["escolha", "publico", "experiencia", "sem_pergunta"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CardOut(_Model):
    """Uma pauta como a curadoria entrega ao `POST /propose` (os campos do `Card` do serviço)."""

    id: str = Field(min_length=1, max_length=120, pattern=r"^[\w.-]+$")
    title: str = Field(min_length=1)  # manchete em português, como Felipe lê no e-mail
    event_date: date  # dia do fato (publicação da fonte, fuso de Brasília)
    perishable: bool = True
    score: int = 0  # nota da rubrica (0 a 33)
    sources: list[str] = Field(default_factory=list)  # URLs, a do representante primeiro
    what: str = ""  # o fato em 1 a 2 frases
    why: str = ""  # por que importa para o público
    angle: str = ""  # a tese possível, em uma frase
    pattern: Pattern = ""
    audience: Audience | Literal[""] = ""


class Hook(_Model):
    kind: HookKind
    text: str = Field(min_length=1, max_length=200)


class Draft(_Model):
    """O post antes da escolha de Felipe. O texto final é
    `hook + "\n\n" + body + "\n\n" + leitura + "\n\n" + tail` (ver `post.compose`)."""

    structure: Structure
    hooks: list[Hook] = Field(min_length=1, max_length=5)  # 3 de tipos diferentes
    body: str = Field(min_length=1)  # do acompanhamento até antes da leitura
    readings: list[str] = Field(min_length=1, max_length=3)  # 2 leituras em voz neutra, ou
    # 1 leitura em primeira pessoa construída só com a opinião de Felipe (entry.opinion)
    reading_is_felipe: bool = False
    tail: str = Field(min_length=1)  # ressalva honesta + fechamento + hashtag (0 ou 1)
    closing: Closing
    headline: str = ""  # a ideia central em poucas palavras, para a imagem
    notes: list[str] = Field(default_factory=list)  # avisos da checagem que sobraram


def compose_text(hook: str, body: str, reading: str, tail: str) -> str:
    """O texto do post a partir das partes do `Draft` (a mesma regra para o redator, o serviço
    e o formulário de aprovação)."""
    return "\n\n".join(p.strip() for p in (hook, body, reading, tail) if p.strip())


class ImageResult(BaseModel):
    """A imagem pronta: PNG validado pelo motor (`render.compose.check`) e registrado."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    png: bytes
    alt_text: str = Field(min_length=1, max_length=4086)
    composition: dict
    theme: Literal["claro", "escuro"]
