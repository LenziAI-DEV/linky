"""Tokens de marca (cores, fontes, medidas) lidos de assets/brand/tokens.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path


def assets_dir() -> Path:
    override = os.environ.get("LINKY_ASSETS")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "assets"


@dataclass(frozen=True)
class Font:
    family: str
    weight: int
    file: str

    @property
    def path(self) -> Path:
        return assets_dir() / "fonts" / self.file


@dataclass(frozen=True)
class Brand:
    width: int
    height: int
    margin: int
    colors: dict[str, str]
    fonts: dict[str, Font]
    headline_max: int
    headline_min: int
    line_height: float
    tracking: float
    name: str
    tagline: str
    rules: dict  # limites das verificações do motor de composição (tokens.json, "rules")
    themes: dict[str, dict[str, str]]  # tema -> papel (fundo, texto, apoio...) -> token

    def c(self, key: str) -> str:
        return self.colors[key]

    def f(self, key: str) -> Font:
        return self.fonts[key]


@cache
def load_brand() -> Brand:
    raw = json.loads((assets_dir() / "brand" / "tokens.json").read_text(encoding="utf-8"))
    fonts = {k: Font(**v) for k, v in raw["fonts"].items()}
    missing = [f.file for f in fonts.values() if not f.path.exists()]
    if missing:
        raise FileNotFoundError(f"Fontes ausentes em assets/fonts: {missing}")
    return Brand(
        width=raw["canvas"]["width"],
        height=raw["canvas"]["height"],
        margin=raw["canvas"]["margin"],
        colors=raw["colors"],
        fonts=fonts,
        headline_max=raw["headline"]["max_size"],
        headline_min=raw["headline"]["min_size"],
        line_height=raw["headline"]["line_height"],
        tracking=raw["headline"]["tracking"],
        name=raw["signature"]["name"],
        tagline=raw["signature"]["tagline"],
        rules=raw["rules"],
        themes=raw["themes"],
    )
