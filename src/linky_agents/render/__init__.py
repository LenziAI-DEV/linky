"""Renderização das imagens dos posts (SVG -> PNG), sem navegador e sem IA."""

from linky_agents.render.layouts import render_png, render_svg
from linky_agents.render.spec import ImageSpec
from linky_agents.render.text import LayoutError

__all__ = ["ImageSpec", "LayoutError", "render_png", "render_svg"]
