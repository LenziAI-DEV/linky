"""Frente Imagem: o agente de direção de arte e o laço de validação do motor (ADR 0006).

    result = make_image(entry, draft, harness=harness, data_dir=data_dir)

1. O tema alterna em relação ao último post registrado (`render.registry`): claro, escuro,
   claro... O primeiro post do registro é claro (o papel é o fundo principal do guia).
2. O agente `arte` (`prompts/arte/v1.md`) recebe a ideia central do post (`draft.headline`,
   nunca o hook, que Felipe escolhe depois) e o corpo, e devolve um
   `ArtDesign`: manchete, empresa (opcional), peças da biblioteca (`render.components`) e
   peças livres de primitivos, a fonte e o texto alternativo.
3. `build` monta a `Composition`. O rodapé (fio, fonte com a data do fato e assinatura) é
   sempre do código: a data vem de `entry.event_date`, nunca do modelo (voz.md §7).
4. `compose.check` e o registro anti-repetição julgam a composição. Recusa volta ao agente
   com os motivos legíveis e a proposta anterior, até `MAX_REJECTIONS` vezes.
5. Aceita, a composição vira PNG e é registrada para o post (`entry.id`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from linky_agents.agents.contracts import Draft, ImageResult
from linky_agents.harness import AgentSpec, Harness, RunFailed
from linky_agents.render import components as lib
from linky_agents.render.brand import load_brand
from linky_agents.render.compose import Composition, Piece, check, piece_bounds, to_png
from linky_agents.render.registry import CompositionRegistry
from linky_agents.render.text import measure

VERSION = "v1"
MAX_REJECTIONS = 2  # recusas do motor que voltam ao agente (3 propostas no total)
MAX_REASONS = 12  # motivos por recusa (os primeiros explicam o resto)
REGISTRY_FILE = "compositions.db"

Theme = Literal["claro", "escuro"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ============================================================================ contrato do agente
class ArtInput(_Model):
    """O que o agente de arte recebe. Só dados confiáveis (nada vem cru da web)."""

    theme: Theme
    idea: str  # a ideia central do post (draft.headline); o hook não entra: Felipe pode trocá-lo
    pattern: str = ""  # padrão da pauta (playbook.md §2)
    audience: str = ""
    title: str  # a manchete da pauta
    what: str = ""  # o fato em 1 a 2 frases
    angle: str = ""  # a tese
    post: str  # corpo do post: os únicos números e fatos que a imagem pode usar
    sources: list[str]  # URLs das fontes, a principal primeiro
    event_date: str  # dd/mm/aaaa: o rodapé já leva, não escreva de novo
    avoid: list[str] = Field(default_factory=list)  # composições dos últimos posts
    previous: dict | None = None  # a proposta recusada
    rejections: list[str] = Field(default_factory=list)  # por que o motor recusou


class HeaderDesign(_Model):
    company: Annotated[str, Field(min_length=1, max_length=32)]
    context: Annotated[str, Field(min_length=1, max_length=64)]


class HeadlineDesign(_Model):
    markup: Annotated[str, Field(min_length=3, max_length=90)]
    top: float = 236
    max_lines: Annotated[int, Field(ge=1, le=4)] = 2
    max_height: Annotated[float, Field(gt=0, le=520)] = 300


ComponentName = Literal[
    "barras sangrando", "número em bloco sangrando", "diagrama de passagem", "retícula ancorada"
]


class ComponentUse(_Model):
    component: ComponentName
    args: dict[str, Any] = Field(default_factory=dict)


class FreePiece(_Model):
    name: Annotated[str, Field(min_length=2, max_length=60)]
    elements: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=40)]


class ArtDesign(_Model):
    """A proposta do agente: o que a imagem diz e como, sem o rodapé (que é do código)."""

    idea: Annotated[str, Field(min_length=3, max_length=160)]  # o que se lê em 2 segundos
    header: HeaderDesign | None = None
    headline: HeadlineDesign
    pieces: Annotated[list[ComponentUse | FreePiece], Field(min_length=1, max_length=6)]
    source: Annotated[str, Field(min_length=3, max_length=80)]  # "Fonte: Veículo"
    source_note: Annotated[str, Field(max_length=48)] = ""  # ex.: "citação em tradução livre"
    alt_text: Annotated[str, Field(min_length=40, max_length=1000)]


SPEC = AgentSpec(name="arte", version=VERSION, input=ArtInput, output=ArtDesign)
SPECS: dict[str, AgentSpec] = {"arte": SPEC}


class ArtRejected(RunFailed):
    """O agente não chegou a uma composição válida dentro das tentativas."""

    def __init__(self, message: str, reasons: list[str], cost_usd: float):
        super().__init__(message)
        self.reasons = reasons
        self.cost_usd = cost_usd


class DesignError(ValueError):
    """A proposta não vira composição (peça desconhecida, argumento errado...)."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# ============================================================================ montagem
def footer_lines(source: str, note: str, event_date) -> list[str]:
    """Linhas de fonte do rodapé: "Fonte: X · dd/mm/aaaa" numa linha quando cabe, senão duas.

    Levanta `DesignError` se a fonte não cabe ao lado da assinatura.
    """
    b = load_brand()
    font = b.f("body")
    s = " ".join(source.split())
    if not s.lower().startswith(("fonte:", "fontes:")):
        s = f"Fonte: {s}"
    date = event_date.strftime("%d/%m/%Y")
    room = b.width - 2 * b.margin - measure(b.tagline, b.f("body_medium"), 24) - 40
    tail = f"{date} · {note}" if note else date
    one = f"{s} · {tail}"
    if measure(one, font, 19) <= room:
        return [one]
    for line in (s, tail):
        w = measure(line, font, 19)
        if w > room:
            raise DesignError(
                [f"[rodapé] a linha {line!r} mede {w:.0f} px e cabem {room:.0f} px ao lado da "
                 "assinatura: encurte a fonte (só o nome do veículo) ou a nota"]
            )
    return [s, tail]


def _expand_elements(name: str, elements: list[dict]) -> list[dict]:
    """Troca o pseudoelemento `stat` (número com legenda) pelos elementos que ele gera."""
    out = []
    for i, el in enumerate(elements, start=1):
        if el.get("kind") == "stat":
            args = {k: v for k, v in el.items() if k != "kind"}
            try:
                out += lib.stat(**args)
            except (TypeError, ValueError) as e:
                raise DesignError([f"[peça] {name}/stat{i}: {e}"]) from e
        else:
            out.append(el)
    return out


def _component(use: ComponentUse, built: list[Piece]) -> Piece:
    args = dict(use.args)
    if use.component == "barras sangrando":
        rows = args.get("rows")
        if isinstance(rows, list):
            args["rows"] = [
                (r["value"], r["number"], r["caption"], r.get("color", "violet"))
                if isinstance(r, dict) else tuple(r)
                for r in rows
            ]
        return lib.bleeding_bars(**args)
    if use.component == "número em bloco sangrando":
        return lib.big_number(**args)
    if use.component == "diagrama de passagem":
        return lib.pass_through_diagram(**args)
    # retícula ancorada: a âncora é o id de um bloco de uma peça já montada
    element_id = args.pop("anchor", None) or args.pop("element_id", None)
    owner = next((p for p in built if any(e.id == element_id for e in p.elements)), None)
    if owner is None:
        raise ValueError(
            f"âncora {element_id!r} não é o id de um bloco das peças anteriores "
            "(a retícula vem depois da peça em que nasce)"
        )
    return lib.anchored_halftone(owner, element_id, **args)


def build(design: ArtDesign, theme: Theme, event_date) -> Composition:
    """Monta a composição da proposta. Erros de montagem levantam `DesignError`."""
    reasons: list[str] = []
    pieces: list[Piece] = []
    if design.header:
        pieces.append(lib.header(design.header.company, design.header.context))
    h = design.headline
    try:
        pieces.append(lib.headline(h.markup, top=h.top, max_lines=h.max_lines,
                                   max_height=h.max_height))
    except ValidationError as e:
        reasons.append(f"[peça] manchete: {_errors(e)}")
    for k, p in enumerate(design.pieces, start=1):
        label = p.component if isinstance(p, ComponentUse) else p.name
        try:
            if isinstance(p, ComponentUse):
                pieces.append(_component(p, pieces))
            else:
                elements = _expand_elements(p.name, p.elements)
                pieces.append(Piece.model_validate({"name": p.name, "elements": elements}))
        except DesignError as e:
            reasons += e.reasons
        except ValidationError as e:
            reasons.append(f"[peça] {label} (peça {k}): {_errors(e)}")
        except (TypeError, ValueError, KeyError) as e:
            reasons.append(f"[peça] {label} (peça {k}): {type(e).__name__}: {e}")
    try:
        lines = footer_lines(design.source, design.source_note, event_date)
    except DesignError as e:
        reasons += e.reasons
        lines = ["Fonte"]
    if reasons:
        raise DesignError(reasons)
    color = "violet" if theme == "claro" else "lavender"
    pieces.append(lib.footer(lines, tagline_color=color))
    names = [p.name for p in pieces]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise DesignError([f"[peça] nomes de peça repetidos: {dup} (cada peça tem nome próprio)"])
    try:
        return Composition(theme=theme, pieces=pieces)
    except ValidationError as e:
        raise DesignError([f"[composição] {_errors(e)}"]) from e


def _errors(e: ValidationError, limit: int = 4) -> str:
    out = []
    for err in e.errors()[:limit]:
        loc = ".".join(str(x) for x in err["loc"])
        out.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    more = len(e.errors()) - limit
    return "; ".join(out) + (f" (e mais {more})" if more > 0 else "")


# ============================================================================ ocupação
FRAME = ("empresa e contexto", "manchete com destaque", "rodapé com fio")
SCHEME_MIN_BOTTOM = 1000  # o esquema desce ao menos até aqui (o fio do rodapé fica em 1210)
SCHEME_MAX_GAP = 170  # vão máximo entre a manchete e o começo do esquema


def space_reasons(c: Composition) -> list[str]:
    """Composição que deixa a tela vazia: o esquema curto demais ou longe da manchete.

    Não é regra da marca (o motor aceita), é direção de arte: no T2, todo esquema ocupou a
    faixa entre a manchete e o rodapé. Volta ao agente como os outros motivos.
    """
    bounds = piece_bounds(c)
    scheme = [box for name, box in bounds.items() if name not in FRAME]
    if not scheme:
        return ["[espaço] a imagem não tem esquema visual além da manchete"]
    top, bottom = min(b[1] for b in scheme), max(b[3] for b in scheme)
    out = []
    if bottom < SCHEME_MIN_BOTTOM:
        out.append(
            f"[espaço] o esquema termina em y {bottom:.0f} e deixa {1210 - bottom:.0f} px vazios "
            f"até o rodapé: ocupe a faixa até ~1150 (aumente as peças, espace-as ou desça-as)"
        )
    head = bounds.get("manchete com destaque")
    if head and top - head[3] > SCHEME_MAX_GAP:
        out.append(
            f"[espaço] {top - head[3]:.0f} px vazios entre a manchete (termina em y "
            f"{head[3]:.0f}) e o esquema (começa em y {top:.0f}): aproxime-os (até "
            f"{SCHEME_MAX_GAP} px)"
        )
    return out


# ============================================================================ tema
def next_theme(registry: CompositionRegistry, post: str) -> Theme:
    """O contrário do tema do último post registrado (fora este); claro se não há nenhum."""
    recent = registry.recent(excluding=post)
    if not recent:
        return "claro"
    return "claro" if recent[-1].description.startswith("tema escuro") else "escuro"


# ============================================================================ esteira
def make_image(entry, draft: Draft, *, harness: Harness, data_dir: Path) -> ImageResult:
    """Imagem do post: proposta do agente, validação do motor e registro (ver o módulo).

    `entry` é a pauta da fila (`editorial.Entry`: id, title, what, angle, pattern, audience,
    sources, event_date). Falha levanta `RunFailed` (do harness) ou `ArtRejected`.
    """
    registry = CompositionRegistry(Path(data_dir) / REGISTRY_FILE)
    theme = next_theme(registry, entry.id)
    inp = ArtInput(
        theme=theme,
        idea=draft.headline or entry.title,
        pattern=entry.pattern,
        audience=entry.audience,
        title=entry.title,
        what=entry.what,
        angle=entry.angle,
        post=draft.body,
        sources=list(entry.sources),
        event_date=entry.event_date.strftime("%d/%m/%Y"),
        avoid=[r.description for r in registry.recent(excluding=entry.id)],
    )
    cost = 0.0
    reasons: list[str] = []
    for _ in range(MAX_REJECTIONS + 1):
        run = harness.run(SPEC, inp)
        cost += run.cost_usd
        design: ArtDesign = run.output
        try:
            comp = build(design, theme, entry.event_date)
        except DesignError as e:
            reasons = e.reasons
        else:
            reasons = [str(v) for v in check(comp)]
            reasons += [str(v) for v in registry.check(entry.id, comp)]
            if not reasons:  # o espaço só se mede numa composição que o motor desenha
                reasons = space_reasons(comp)
            if not reasons:
                png = to_png(comp)
                registry.record(entry.id, comp)
                return ImageResult(
                    png=png,
                    alt_text=design.alt_text,
                    composition=comp.model_dump(mode="json"),
                    theme=theme,
                )
        inp = inp.model_copy(update={
            "previous": design.model_dump(mode="json"),
            "rejections": reasons[:MAX_REASONS]
            + ([f"(e mais {len(reasons) - MAX_REASONS} motivos)"]
               if len(reasons) > MAX_REASONS else []),
        })
    raise ArtRejected(
        f"arte: o motor recusou {MAX_REJECTIONS + 1} propostas para {entry.id}: "
        + "; ".join(reasons[:3]),
        reasons,
        cost,
    )


__all__ = [
    "SPEC",
    "SPECS",
    "ArtDesign",
    "ArtInput",
    "ArtRejected",
    "build",
    "footer_lines",
    "make_image",
    "next_theme",
]
