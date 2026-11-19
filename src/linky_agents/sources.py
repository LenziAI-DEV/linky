"""Leitura e validação de sources.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl

Tier = Literal["primary", "press", "analysis", "br"]
Status = Literal["active", "probation", "disabled"]


class Source(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    url: HttpUrl
    tier: Tier
    filter: bool = False
    status: Status = "active"


class Keywords(BaseModel):
    case_insensitive: list[str] = []
    case_sensitive: list[str] = []


class Defaults(BaseModel):
    max_items_per_run: int = Field(default=30, ge=1, le=200)


class SourcesConfig(BaseModel):
    defaults: Defaults = Defaults()
    keywords: Keywords = Keywords()
    sources: list[Source]

    def enabled(self) -> list[Source]:
        return [s for s in self.sources if s.status != "disabled"]


class KeywordMatcher:
    """Decide se um texto fala de IA, com regras separadas para siglas (case-sensitive)."""

    def __init__(self, keywords: Keywords) -> None:
        self._ci = [re.compile(p, re.IGNORECASE) for p in keywords.case_insensitive]
        self._cs = [re.compile(p) for p in keywords.case_sensitive]

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self._ci) or any(p.search(text) for p in self._cs)


def load_sources(path: Path) -> SourcesConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = SourcesConfig.model_validate(data)
    ids = [s.id for s in config.sources]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        raise ValueError(f"IDs de fonte duplicados: {sorted(duplicated)}")
    return config
