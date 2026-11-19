"""Contrato da imagem: o que o agente de direção de arte preenche (e nada além disso).

A manchete usa marcação simples:
    **texto**  -> bloco violeta (destaque principal; obrigatório pelo menos um)
    ==texto==  -> bloco lilás
    ~~texto~~  -> tachado (para o padrão "não é X, é Y")
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from linky_agents.render.text import parse_markup, plain_text

Short = Annotated[str, Field(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Company(_Strict):
    name: Annotated[str, Field(min_length=1, max_length=32)]
    logo_svg: str | None = Field(
        default=None, description="Caminho para o SVG oficial do logo, relativo a assets/logos"
    )


class _Base(_Strict):
    company: Company | None = None
    headline: Annotated[str, Field(min_length=3, max_length=90)]
    source: Annotated[str, Field(min_length=8, max_length=95)]

    @field_validator("headline")
    @classmethod
    def _headline(cls, v: str) -> str:
        units = parse_markup(v)
        text = plain_text(v)
        if len(text) > 64:
            raise ValueError(f"Manchete longa demais ({len(text)} > 64 caracteres sem marcação)")
        if not any(u.style == "accent" for u in units):
            raise ValueError("A manchete precisa de pelo menos um destaque **assim**")
        return v

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if not v.lower().startswith("fonte:"):
            v = f"Fonte: {v}"
        return v


class Step(_Strict):
    title: Annotated[str, Field(min_length=2, max_length=18)]
    text: Annotated[str, Field(min_length=2, max_length=48)]


class EscadaSpec(_Base):
    """Layout 1: etapas, evolução, decisões em sequência."""

    layout: Literal["escada"]
    context: Annotated[str, Field(max_length=60)] | None = None
    steps: Annotated[list[Step], Field(min_length=3, max_length=3)]
    milestone: Annotated[str, Field(max_length=6)] | None = None


class ContrasteSpec(_Base):
    """Layout 2: lançamentos e capacidades, padrão "não é X, é Y"."""

    layout: Literal["contraste"]
    items: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=52)]], Field(min_length=3, max_length=5)
    ]


class Term(_Strict):
    title: Annotated[str, Field(min_length=2, max_length=12)]
    subtitle: Annotated[str, Field(min_length=2, max_length=20)]


class TeseSpec(_Base):
    """Layout 3: conceito, opinião, lição de negócio. Equação visual A + B = C."""

    layout: Literal["tese"]
    equation: Annotated[list[Term], Field(min_length=3, max_length=3)]


class ImageSpec(_Strict):
    spec: Annotated[EscadaSpec | ContrasteSpec | TeseSpec, Field(discriminator="layout")]

    @classmethod
    def parse(cls, data: dict) -> EscadaSpec | ContrasteSpec | TeseSpec:
        return cls.model_validate({"spec": data}).spec
