# /// script
# requires-python = ">=3.12"
# dependencies = ["resvg-py"]
# ///
"""Gera 3 direções visuais (exploração) para a identidade Felipe Lenzi, com o post da Airbnb.

Saída: docs/brand/explorations/direcao-{1,2,3}.{svg,png} (1080x1350, formato 4:5 do LinkedIn).
O logo real da empresa entra no template final. Aqui ele aparece como marcador de posição.
"""

from pathlib import Path

import resvg_py

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "brand" / "explorations"
FONTS = str(ROOT / "assets" / "fonts")
W, H = 1080, 1350

VIOLET = "#8B5CF6"
VIOLET_SOFT = "#A78BFA"
SOURCE = "Fonte: TechCrunch · carta aos acionistas da Airbnb (3º tri) · 05/11/2026"


def monogram(x: int, y: int, light: str = "#F5F3FF") -> str:
    return f"""
  <g transform="translate({x},{y})">
    <rect x="0" y="0" width="60" height="60" rx="14" fill="none" stroke="{VIOLET}" stroke-width="3"/>
    <text x="30" y="40" text-anchor="middle" font-family="Space Grotesk" font-weight="700"
          font-size="26" fill="{light}">FL</text>
    <text x="76" y="28" font-family="Inter" font-weight="600" font-size="22" fill="{light}">Felipe Lenzi</text>
    <text x="76" y="52" font-family="Inter" font-weight="400" font-size="17" fill="#9CA3AF">IA aplicada a negócios</text>
  </g>"""


def footer(source_color: str = "#9CA3AF") -> str:
    return f"""
  <line x1="72" y1="1218" x2="1008" y2="1218" stroke="#2A2540" stroke-width="2"/>
  <text x="72" y="1290" font-family="Inter" font-weight="400" font-size="19" fill="{source_color}">{SOURCE}</text>
  {monogram(760, 1250)}"""


def logo_placeholder(x: int, y: int) -> str:
    return f"""
  <g transform="translate({x},{y})">
    <rect width="190" height="56" rx="28" fill="#1C1830" stroke="#3B3360" stroke-width="2"/>
    <text x="95" y="36" text-anchor="middle" font-family="Inter" font-weight="800" font-size="24"
          fill="#F5F3FF">airbnb</text>
  </g>"""


def direction_1() -> str:
    """Manchete noturna: editorial, manchete gigante e comparação em cards."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="#0D0B14"/>
  <rect x="0" y="0" width="{W}" height="10" fill="{VIOLET}"/>
  {logo_placeholder(72, 92)}
  <text x="1008" y="128" text-anchor="end" font-family="JetBrains Mono" font-weight="500"
        font-size="22" fill="{VIOLET_SOFT}" letter-spacing="3">AGENTES DE IA</text>

  <g font-family="Inter" font-weight="800" font-size="92" fill="#FFFFFF" letter-spacing="-2">
    <text x="72" y="330">Agente genérico</text>
    <text x="72" y="432">não resolve</text>
    <text x="72" y="534">problema</text>
    <text x="72" y="636" fill="{VIOLET}">específico.</text>
  </g>
  <text x="72" y="712" font-family="Inter" font-weight="400" font-size="32" fill="#C4B5FD">
    A aposta da Airbnb para 2027</text>

  <g transform="translate(72,800)">
    <rect width="420" height="330" rx="24" fill="#15121F" stroke="#2A2540" stroke-width="2"/>
    <text x="36" y="70" font-family="JetBrains Mono" font-weight="500" font-size="20" fill="#9CA3AF" letter-spacing="2">GENÉRICO</text>
    <text x="36" y="130" font-family="Inter" font-weight="600" font-size="34" fill="#E5E7EB">Chat que</text>
    <text x="36" y="174" font-family="Inter" font-weight="600" font-size="34" fill="#E5E7EB">responde em texto</text>
    <rect x="36" y="220" width="300" height="16" rx="8" fill="#2A2540"/>
    <rect x="36" y="252" width="240" height="16" rx="8" fill="#2A2540"/>
    <rect x="36" y="284" width="270" height="16" rx="8" fill="#2A2540"/>
  </g>
  <text x="540" y="985" text-anchor="middle" font-family="Inter" font-weight="800" font-size="44" fill="{VIOLET}">→</text>
  <g transform="translate(588,800)">
    <rect width="420" height="330" rx="24" fill="#1A1430" stroke="{VIOLET}" stroke-width="3"/>
    <text x="36" y="70" font-family="JetBrains Mono" font-weight="500" font-size="20" fill="{VIOLET_SOFT}" letter-spacing="2">ESPECIALIZADO</text>
    <g font-family="Inter" font-weight="600" font-size="28" fill="#F5F3FF">
      <text x="36" y="132">• Mapas e fotos</text>
      <text x="36" y="182">• Roteiros e comparativos</text>
      <text x="36" y="232">• Reembolso e trocas</text>
      <text x="36" y="282">• Suporte 24h</text>
    </g>
  </g>
  {footer()}
</svg>"""


def direction_2() -> str:
    """Grade técnica: fundo com grid, brilho violeta e diagrama de componentes."""
    grid = "".join(
        f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="#17132A" stroke-width="1"/>'
        for x in range(0, W + 1, 54)
    ) + "".join(
        f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#17132A" stroke-width="1"/>'
        for y in range(0, H + 1, 54)
    )
    nodes = [("Mapas", 190, 900), ("Roteiros", 890, 900), ("Comparações", 190, 1120), ("Suporte 24h", 890, 1120)]
    node_svg = "".join(
        f"""<line x1="540" y1="1010" x2="{x}" y2="{y}" stroke="{VIOLET}" stroke-width="2" stroke-dasharray="6 8"/>
        <g transform="translate({x - 120},{y - 38})"><rect width="240" height="76" rx="16" fill="#120F22" stroke="#3B3360" stroke-width="2"/>
        <text x="120" y="48" text-anchor="middle" font-family="Space Grotesk" font-weight="500" font-size="28" fill="#E9E5FF">{label}</text></g>"""
        for label, x, y in nodes
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <radialGradient id="glow" cx="50%" cy="72%" r="45%">
      <stop offset="0%" stop-color="{VIOLET}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{VIOLET}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="#0A0814"/>
  {grid}
  <rect width="{W}" height="{H}" fill="url(#glow)"/>
  <text x="72" y="130" font-family="JetBrains Mono" font-weight="500" font-size="22" fill="{VIOLET_SOFT}" letter-spacing="2">// ANÁLISE · AGENTES DE IA</text>
  {logo_placeholder(818, 92)}
  <g font-family="Space Grotesk" font-weight="700" font-size="84" fill="#FFFFFF" letter-spacing="-1">
    <text x="72" y="300">O diferencial não</text>
    <text x="72" y="396">é o modelo. É o</text>
    <text x="72" y="492"><tspan fill="{VIOLET}">contexto</tspan> do negócio.</text>
  </g>
  <text x="72" y="580" font-family="Inter" font-weight="400" font-size="32" fill="#C4B5FD">Como a Airbnb montou seu agente de viagens</text>
  {node_svg}
  <g transform="translate(400,970)">
    <rect width="280" height="84" rx="20" fill="{VIOLET}"/>
    <text x="140" y="54" text-anchor="middle" font-family="Space Grotesk" font-weight="700" font-size="30" fill="#0A0814">Agente Airbnb</text>
  </g>
  {footer()}
</svg>"""


def direction_3() -> str:
    """Dado em destaque: número gigante, frase curta, minimalismo executivo."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="num" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#C4B5FD"/>
      <stop offset="100%" stop-color="{VIOLET}"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="#111014"/>
  <rect x="72" y="200" width="8" height="760" fill="{VIOLET}"/>
  {logo_placeholder(72, 92)}
  <text x="112" y="520" font-family="Inter" font-weight="800" font-size="330" fill="url(#num)" letter-spacing="-12">80%</text>
  <g font-family="Inter" font-weight="600" font-size="52" fill="#FFFFFF">
    <text x="112" y="640">dos viajantes gostam</text>
    <text x="112" y="706">de pesquisar viagens.</text>
  </g>
  <g font-family="Inter" font-weight="400" font-size="34" fill="#C4B5FD">
    <text x="112" y="820">Por isso o agente da Airbnb melhora a pesquisa</text>
    <text x="112" y="866">e automatiza só o que ninguém gosta de fazer.</text>
  </g>
  <g transform="translate(112,940)" font-family="JetBrains Mono" font-weight="500" font-size="22" letter-spacing="2">
    <rect width="300" height="54" rx="27" fill="#1C1830"/><text x="150" y="35" text-anchor="middle" fill="#E9E5FF">MELHORAR: PESQUISA</text>
    <rect x="320" width="360" height="54" rx="27" fill="{VIOLET}"/><text x="500" y="35" text-anchor="middle" fill="#111014">AUTOMATIZAR: PÓS-VENDA</text>
  </g>
  {footer()}
</svg>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, build in enumerate((direction_1, direction_2, direction_3), start=1):
        svg = build()
        (OUT / f"direcao-{i}.svg").write_text(svg, encoding="utf-8")
        png = resvg_py.svg_to_bytes(svg_string=svg, font_dirs=[FONTS], skip_system_fonts=True)
        (OUT / f"direcao-{i}.png").write_bytes(bytes(png))
        print(f"direcao-{i}.png", len(png), "bytes")


if __name__ == "__main__":
    main()
