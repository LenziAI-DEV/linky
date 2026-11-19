"""linky-render --spec exemplo.json --out imagem.png [--svg]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from linky_agents.render import ImageSpec, LayoutError, render_png, render_svg


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Renderiza a imagem de um post a partir de um spec JSON"
    )
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--svg", action="store_true", help="grava também o SVG ao lado do PNG")
    args = p.parse_args(argv)
    try:
        spec = ImageSpec.parse(json.loads(args.spec.read_text(encoding="utf-8")))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(render_png(spec))
        if args.svg:
            args.out.with_suffix(".svg").write_text(render_svg(spec), encoding="utf-8")
    except (LayoutError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
