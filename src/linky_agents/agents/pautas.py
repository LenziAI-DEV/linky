"""Frente Pautas: triagem, curadoria e texto dos cards (produção do MVP).

    cards = curate(items, harness=harness, now=agora, n_cards=3, exclude=ja_propostos)

O caminho, do item coletado ao card do e-mail de pautas:

1. **Fatos** (sem modelo, ADR 0007): `stories.group_stories` junta as fontes do mesmo fato.
   Fatos já propostos (pelo ID de um item ou pelo título idêntico) saem aqui.
2. **Triagem** (`prompts/triagem/v1.md`, modelo barato): relevância 0 a 3, categoria e resumo
   de uma linha por fato, em lotes que cabem nos limites de `config/models.yaml`.
3. **Curadoria** (`prompts/curadoria/v1.md`): filtros e notas da rubrica v1
   (`docs/editorial/rubrica.md`), padrão P1 a P4 e público (`playbook.md` §2), tema e
   empresa, para **todos os candidatos numa chamada** (a nota é comparativa: em lotes
   pequenos, quase tudo virava 2 e 3). A curadoria também aponta o fato repetido que o
   agrupamento deixou passar (`same_as`), e as fontes se juntam.
4. **Regras da rubrica v1 no código** (decididas pelo padrão em 16/11): caso do fornecedor
   sem confirmação independente tem evidência no máximo 1; lançamento grande (2 de 3 sinais,
   um deles as 3 fontes independentes contadas aqui) tem posicionamento pelo menos 2; nota
   pelos pesos da v0 (sem mudança na v1) e desempate evidência > relevância > novidade.
5. **Montagem** (`assemble`): de cima para baixo, no máximo um card por tema e um por empresa
   principal; o fato pulado fica com o motivo. Só se faltarem fatos para `n_cards`, os
   pulados completam o lote (melhor 3 cards com um tema repetido que 2).
6. **Texto dos cards** (`prompts/pauta/v1.md`): título, o quê, por quê e ângulo em português,
   só para os escolhidos (e 2 reservas, caso um texto venha incompleto).

Notícia que não cabe em nenhum padrão não vira card, mesmo com nota alta.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ..harness import AgentSpec, Harness, RunFailed, WebDocument
from ..harness.budget import estimate_tokens
from ..harness.errors import BudgetExceeded
from ..harness.prompt import load_prompt, system_text, user_text
from ..normalize import title_key
from ..stories import Story, group_stories
from .contracts import Audience, CardOut

log = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")
RUBRIC_VERSION = "v1"
# Pesos da rubrica (v0, mantidos na v1: pergunta 7 decidida pelo padrão em 16/11). Máximo 33.
WEIGHTS: dict[str, int] = {
    "relevance": 3, "novelty": 2, "evidence": 2, "brazil": 1, "positioning": 2, "conversation": 1,
}
TIEBREAK = ("evidence", "relevance", "novelty")

# Lotes. A saída é o limite que aperta: ~60 tokens por fato na triagem (1.500 de saída) e
# ~80 por fato na curadoria (6.000 de saída, com o raciocínio).
TRIAGE_BATCH = 18
CURATION_BATCH = 30
MAX_CANDIDATES = 60  # fatos que vão à curadoria (os de maior relevância na triagem)
SPARE_CARDS = 2  # textos a mais, caso um venha incompleto
INPUT_MARGIN = 0.85  # fração do limite de entrada do agente usada pelos lotes
SUMMARY_CHARS_TRIAGE = 400
SUMMARY_CHARS_CURATION = 700
SUMMARY_CHARS_CARD = 1500
SUMMARY_CHARS_SIBLING = 300  # resumo das 2 primeiras fontes irmãs (só no texto do card)
MAX_SIBLINGS = 6
BIG_LAUNCH_SOURCES = 3  # sinal (a) do lançamento grande: 3 ou mais fontes independentes


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- triagem
Category = Literal[
    "lancamento", "caso", "pesquisa", "mercado", "regulacao", "risco", "preco", "opiniao",
    "tutorial", "consumo", "outro",
]


class TriageIn(_Model):
    today: date
    facts: list[WebDocument]


class TriageFact(_Model):
    id: str
    relevance: int = Field(ge=0, le=3, description="0 descartar, 1 fraca, 2 boa, 3 forte")
    category: Category = Field(
        description="lancamento (modelo ou produto), caso (empresa usando IA), pesquisa (dado "
        "ou relatório), mercado (investimento, IPO, aquisição, resultado), regulacao, risco "
        "(segurança, fraude, falha), preco (preço ou cobrança), opiniao, tutorial, consumo, "
        "outro"
    )
    summary: str = Field(default="", max_length=300, description="Uma linha, em português")
    reason: str = Field(default="", max_length=200, description="Motivo do descarte")


class TriageOut(_Model):
    facts: list[TriageFact]


# --------------------------------------------------------------------------- curadoria
Topic = Literal[
    "modelos", "agentes", "codigo", "seguranca", "custo", "investimento", "adocao", "trabalho",
    "regulacao", "infraestrutura", "saude", "financas", "varejo", "educacao", "criatividade",
    "industria", "ciencia", "outro",
]
_TOPIC_HELP = (
    "O assunto do fato: modelos (lançamento ou capacidade de modelos), agentes (agentes e "
    "automação), codigo (programação e ferramentas de dev), seguranca (segurança, fraude, "
    "privacidade, golpe), custo (preço, cobrança, cotas), investimento (rodada, IPO, "
    "aquisição), adocao (uso e retorno da IA nas empresas), trabalho (empregos, times), "
    "regulacao (leis, governo, justiça), infraestrutura (chips, data centers, energia), saude, "
    "financas (setor financeiro), varejo (varejo e consumo), educacao, criatividade (mídia, "
    "design, conteúdo), industria (indústria e logística), ciencia, outro"
)


class Scores(_Model):
    relevance: int = Field(ge=0, le=3)
    novelty: int = Field(ge=0, le=3)
    evidence: int = Field(ge=0, le=3)
    brazil: int = Field(ge=0, le=3)
    positioning: int = Field(ge=0, le=3)
    conversation: int = Field(ge=0, le=3)

    @property
    def total(self) -> int:
        return sum(getattr(self, k) * w for k, w in WEIGHTS.items())


class CurationIn(_Model):
    today: date
    already_proposed: list[str] = Field(default_factory=list)
    facts: list[WebDocument]


class CuratedFact(_Model):
    id: str
    same_as: str = Field(default="", description="ID do documento que é o mesmo acontecimento")
    eliminated: str = Field(default="", description="Filtro que eliminou o fato; vazio se passou")
    scores: Scores | None = None
    vendor: bool = Field(default=False, description="Caso de cliente publicado pelo fornecedor")
    leads_benchmark: bool = False
    available_now: bool = False
    pattern: Literal["P1", "P2", "P3", "P4", ""] = Field(
        default="", description="Vazio quando o fato não cabe em nenhum padrão"
    )
    audience: Audience | Literal[""] = ""
    topic: Topic = Field(default="outro", description=_TOPIC_HELP)
    company: str = Field(default="", max_length=60)
    perishable: bool = True
    note: str = Field(default="", max_length=300)


class CurationOut(_Model):
    facts: list[CuratedFact]


# --------------------------------------------------------------------------- texto do card
class Brief(_Model):
    id: str
    pattern: str
    audience: str
    company: str = ""


class CardIn(_Model):
    today: date
    briefs: list[Brief]
    facts: list[WebDocument]


class CardText(_Model):
    id: str
    title: str = Field(max_length=160)
    what: str = Field(max_length=700)
    why: str = Field(max_length=700)
    angle: str = Field(max_length=400)


class CardsOut(_Model):
    cards: list[CardText]


TRIAGE = AgentSpec("triagem", "v1", TriageIn, TriageOut)
CURATION = AgentSpec("curadoria", "v1", CurationIn, CurationOut)
CARDS = AgentSpec("pauta", "v1", CardIn, CardsOut)
SPECS: dict[str, AgentSpec] = {s.name: s for s in (TRIAGE, CURATION, CARDS)}


# --------------------------------------------------------------------------- resultado
@dataclass
class Candidate:
    """Um fato depois da triagem (e da curadoria, quando chegou lá)."""

    story: Story
    triage: TriageFact | None = None
    curated: CuratedFact | None = None
    score: int = 0
    skip: str = ""  # por que não virou card (vazio: é card possível)

    @property
    def id(self) -> str:
        return self.story.representative["id"]

    @property
    def item_ids(self) -> list[str]:
        return [it["id"] for it in self.story.items]

    @property
    def event_date(self) -> date:
        return self.story.first_seen.astimezone(TZ).date()

    def sort_key(self) -> tuple:
        s = self.curated.scores if self.curated and self.curated.scores else None
        tie = tuple(getattr(s, k) for k in TIEBREAK) if s else (0, 0, 0)
        triage = self.triage.relevance if self.triage else 0
        return (self.score, *tie, triage, len(_independent(self.story)))

    def card(self, text: CardText) -> CardOut:
        c = self.curated
        assert c is not None
        return CardOut(
            id=f"{self.event_date.isoformat()}-{self.id}",
            title=text.title.strip(),
            event_date=self.event_date,
            perishable=c.perishable,
            score=self.score,
            sources=self.story.sources,
            what=text.what.strip(),
            why=text.why.strip(),
            angle=text.angle.strip(),
            pattern=c.pattern,
            audience=c.audience,
        )


@dataclass
class Ranking:
    """Os fatos em ordem de nota, com o custo e as falhas das chamadas."""

    candidates: list[Candidate]
    today: date
    excluded: list[str] = field(default_factory=list)  # IDs dos fatos já propostos
    cost_usd: float = 0.0
    runs: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- público
def curate(
    items: Iterable[dict],
    *,
    harness: Harness,
    now: datetime,
    n_cards: int = 3,
    exclude: Iterable[str] = (),
) -> list[CardOut]:
    """As `n_cards` pautas do lote, da maior para a menor nota.

    `items`: itens do coletor já filtrados pela janela da pauta. `exclude`: IDs (de item ou
    de card, `AAAA-MM-DD-<id do item>`) e títulos de pautas propostas recentemente. Levanta
    `RunFailed` só quando nenhuma chamada deu certo (ou `BudgetExceeded`, no teto de custo)."""
    ranking = rank(items, harness=harness, now=now, exclude=exclude)
    chosen = assemble(ranking.candidates, n_cards + SPARE_CARDS)
    cards = write_cards(chosen, harness=harness, ranking=ranking)
    cards = _diverse(cards, n_cards)
    log.info(
        "pautas: %d fatos, %d cards, US$ %.4f, %d falhas",
        len(ranking.candidates), len(cards), ranking.cost_usd, len(ranking.failures),
    )
    return [card for _c, card in cards]


def rank(
    items: Iterable[dict],
    *,
    harness: Harness,
    now: datetime,
    exclude: Iterable[str] = (),
) -> Ranking:
    """Triagem e curadoria de todos os fatos. Devolve todos, em ordem (os sem card no fim)."""
    today = now.astimezone(TZ).date()
    ex_ids, ex_keys, ex_titles = _split_exclude(exclude)
    ranking = Ranking(candidates=[], today=today)
    fresh: list[Story] = []
    for s in group_stories(items):
        keys = {it.get("title_key") or title_key(it["title"]) for it in s.items}
        if ex_ids & set(it["id"] for it in s.items) or ex_keys & keys:
            ranking.excluded.append(s.representative["id"])
        else:
            fresh.append(s)
    cands = {s.representative["id"]: Candidate(s) for s in fresh}

    # Triagem
    trusted = {"today": today.isoformat()}
    for batch in _batches(harness, TRIAGE, fresh, _triage_doc, trusted, TRIAGE_BATCH):
        out = _run(harness, ranking, TRIAGE, TriageIn(today=today, facts=batch))
        for f in out.facts if out else []:
            if f.id in cands:
                cands[f.id].triage = f
    for c in cands.values():
        if c.triage is None:
            c.skip = "sem triagem"
        elif c.triage.relevance == 0:
            c.skip = f"triagem: {c.triage.reason or 'descartado'}"

    # Curadoria: todos os candidatos de uma vez (ou em poucos lotes grandes)
    pool = sorted(
        (c for c in cands.values() if not c.skip),
        key=lambda c: (-c.triage.relevance, -len(_independent(c.story)), c.id),  # type: ignore[union-attr]
    )
    for c in pool[MAX_CANDIDATES:]:
        c.skip = "fora do limite de candidatos da curadoria"
    pool = pool[:MAX_CANDIDATES]
    by_id = {c.id: c for c in pool}
    trusted = {"today": today.isoformat(), "already_proposed": ex_titles}
    docs = lambda s: _curation_doc(by_id[s.representative["id"]])  # noqa: E731
    for batch in _batches(harness, CURATION, [c.story for c in pool], docs, trusted,
                          CURATION_BATCH):
        inp = CurationIn(today=today, already_proposed=ex_titles, facts=batch)
        out = _run(harness, ranking, CURATION, inp)
        for f in out.facts if out else []:
            if f.id in by_id:
                by_id[f.id].curated = f
    _merge_same_facts(pool, by_id)
    for c in pool:
        if not c.skip:
            _apply_rubric(c)

    if not ranking.runs and ranking.failures:
        raise RunFailed("pautas: nenhuma chamada deu certo: " + "; ".join(ranking.failures))
    ranking.candidates = sorted(
        cands.values(), key=lambda c: (c.skip == "", c.sort_key()), reverse=True
    )
    return ranking


def assemble(candidates: Sequence[Candidate], n_cards: int) -> list[Candidate]:
    """Os cards do lote: de cima para baixo, no máximo um por tema e um por empresa
    principal (rubrica v1, regra de montagem). Os fatos pulados recebem o motivo e só voltam
    se faltar fato diferente para completar `n_cards`."""
    ok = sorted((c for c in candidates if not c.skip), key=Candidate.sort_key, reverse=True)
    chosen: list[Candidate] = []
    skipped: list[Candidate] = []
    for c in ok:
        if len(chosen) >= n_cards:
            break
        clash = _clash(c, chosen)
        if clash:
            c.skip = clash
            skipped.append(c)
        else:
            chosen.append(c)
    for c in skipped:
        if len(chosen) >= n_cards:
            break
        c.skip = ""
        chosen.append(c)
    return sorted(chosen, key=Candidate.sort_key, reverse=True)


def write_cards(
    chosen: Sequence[Candidate], *, harness: Harness, ranking: Ranking
) -> list[tuple[Candidate, CardOut]]:
    """O texto dos cards escolhidos, na ordem recebida. Card sem texto completo fica de fora
    (com o motivo em `skip`)."""
    if not chosen:
        return []
    briefs = [Brief(id=c.id, pattern=c.curated.pattern, audience=c.curated.audience,  # type: ignore[union-attr]
                    company=c.curated.company) for c in chosen]  # type: ignore[union-attr]
    inp = CardIn(today=ranking.today, briefs=briefs, facts=[_card_doc(c) for c in chosen])
    out = _run(harness, ranking, CARDS, inp)
    texts = {t.id: t for t in out.cards} if out else {}
    cards: list[tuple[Candidate, CardOut]] = []
    for c in chosen:
        t = texts.get(c.id)
        if t is None or not (t.title.strip() and t.what.strip()):
            c.skip = "card sem texto"
            continue
        cards.append((c, c.card(t)))
    if not cards and not out:
        raise RunFailed("pautas: o texto dos cards falhou: " + "; ".join(ranking.failures[-1:]))
    return cards


# --------------------------------------------------------------------------- regras
def _merge_same_facts(pool: Sequence[Candidate], by_id: dict[str, Candidate]) -> None:
    """Junta o fato que a curadoria apontou como repetido (`same_as`) ao fato principal: as
    fontes se somam, e quem decide o resto (notas, filtros) é o principal."""
    for c in pool:
        target = _same_root(c, by_id)
        if target is None or by_id[target].skip:  # ciclo: o outro já foi juntado
            continue
        main = by_id[target]
        main.story = Story(main.story.representative, (*main.story.siblings, *c.story.items))
        c.skip = f"mesmo fato de {target}"


def _same_root(c: Candidate, by_id: dict[str, Candidate]) -> str | None:
    seen = {c.id}
    cur = c
    for _ in range(5):
        nxt = cur.curated.same_as.strip() if cur.curated else ""
        if not nxt or nxt not in by_id or nxt in seen:
            break
        seen.add(nxt)
        cur = by_id[nxt]
    return cur.id if cur is not c else None


def _apply_rubric(c: Candidate) -> None:
    """Filtros, regras da rubrica v1 e nota final de um fato que passou pela curadoria."""
    f = c.curated
    if f is None:
        c.skip = "sem curadoria"
        return
    if f.eliminated.strip():
        c.skip = f"eliminado: {f.eliminated.strip()}"
        return
    if f.scores is None:
        c.skip = "curadoria sem notas"
        return
    s = f.scores
    # Caso do fornecedor sem confirmação independente: evidência no máximo 1
    if f.vendor and len(_independent(c.story)) < 2:
        s.evidence = min(s.evidence, 1)
    # Lançamento grande: 2 de 3 sinais garantem posicionamento 2
    signals = (
        int(len(_independent(c.story)) >= BIG_LAUNCH_SOURCES)
        + int(f.leads_benchmark)
        + int(f.available_now)
    )
    launch = c.triage is not None and c.triage.category in ("lancamento", "preco")
    if launch and signals >= 2:
        s.positioning = max(s.positioning, 2)
    c.score = s.total
    if not f.pattern:
        c.skip = f"sem padrão{': ' + f.note if f.note else ''}"
    elif not f.audience:
        c.skip = "sem público"


def _clash(c: Candidate, chosen: Sequence[Candidate]) -> str:
    f = c.curated
    assert f is not None
    for n, other in enumerate(chosen, 1):
        o = other.curated
        assert o is not None
        if f.topic != "outro" and f.topic == o.topic:
            return f"mesmo tema do card {n} ({f.topic})"
        if f.company and _fold(f.company) == _fold(o.company):
            return f"mesma empresa do card {n} ({f.company})"
    return ""


def _diverse(
    cards: Sequence[tuple[Candidate, CardOut]], n_cards: int
) -> list[tuple[Candidate, CardOut]]:
    """Os `n_cards` primeiros com texto, de novo pela regra de diversidade (uma reserva que
    entrou no lugar de um card sem texto não pode repetir tema nem empresa)."""
    picked = assemble([c for c, _ in cards], n_cards)
    order = {id(c): card for c, card in cards}
    return [(c, order[id(c)]) for c in picked]


def _independent(story: Story) -> set[str]:
    """Fontes distintas do fato (o ID da fonte no coletor)."""
    return {it["source"] for it in story.items}


_HEX_ID = re.compile(r"(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])")


def _split_exclude(exclude: Iterable[str]) -> tuple[set[str], set[str], list[str]]:
    """IDs de item (soltos ou dentro do ID de um card), chaves de título e títulos."""
    ids: set[str] = set()
    keys: set[str] = set()
    titles: list[str] = []
    for x in exclude:
        x = (x or "").strip()
        if not x:
            continue
        found = _HEX_ID.findall(x.lower())
        if found and re.fullmatch(r"[\w.-]+", x):
            ids.update(found)
            continue
        keys.add(title_key(x))
        if " " in x and x not in titles:
            titles.append(x)
    return ids, keys, titles


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()


# --------------------------------------------------------------------------- chamadas
def _run(harness: Harness, ranking: Ranking, spec: AgentSpec, inp: BaseModel):
    """Uma chamada. Falha de um lote não derruba os outros; o teto de custo, sim."""
    try:
        result = harness.run(spec, inp)
    except BudgetExceeded:
        raise
    except RunFailed as e:
        ranking.failures.append(str(e))
        log.warning("pautas: chamada falhou: %s", e)
        return None
    ranking.runs.append(result.run_id)
    ranking.cost_usd += result.cost_usd
    return result.output


def _batches(
    harness: Harness, spec: AgentSpec, stories: Sequence[Story],
    to_doc: Callable[[Story], WebDocument], trusted: dict, max_facts: int,
) -> list[list[WebDocument]]:
    """Lotes de no máximo `max_facts` documentos que cabem no limite de entrada do agente
    (com margem), para o harness nunca descartar um fato calado."""
    if not stories:
        return []
    cfg = harness.config.agent(spec.name)
    system = system_text(
        load_prompt(harness.prompts_dir, spec.name, spec.version),
        spec.output.model_json_schema(),
    )
    limit = int(cfg.max_input_tokens * INPUT_MARGIN)
    out: list[list[WebDocument]] = []
    cur: list[WebDocument] = []
    for s in stories:
        doc = to_doc(s)
        if cur and (
            len(cur) >= max_facts
            or estimate_tokens(system + user_text(trusted, [*cur, doc])) > limit
        ):
            out.append(cur)
            cur = []
        cur.append(doc)
    if cur:
        out.append(cur)
    return out


def _brt(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d/%m %H:%M")


def _sources_line(s: Story) -> str:
    srcs = ", ".join(sorted({f"{it['source']} ({it.get('tier', '?')})" for it in s.items}))
    return f"fontes independentes: {len(_independent(s))}: {srcs}"


def _triage_doc(s: Story) -> WebDocument:
    rep = s.representative
    lines = [(rep.get("summary") or "")[:SUMMARY_CHARS_TRIAGE]]
    if s.siblings:
        lines.append(f"Outras fontes do mesmo fato ({len(s.siblings)}):")
        lines += [f"- [{it['source']}] {it['title']}" for it in s.siblings[:MAX_SIBLINGS]]
    return WebDocument(
        id=rep["id"], source=rep["source"], url=rep["url"], title=rep["title"],
        text="\n".join(lines).strip(),
    )


def _curation_doc(c: Candidate) -> WebDocument:
    s, t = c.story, c.triage
    rep = s.representative
    lines = [f"publicado: {_brt(rep['published_utc'])} (Brasília)", _sources_line(s)]
    if t is not None:
        lines.append(f"triagem: relevância {t.relevance}, categoria {t.category}")
        if t.summary:
            lines.append(f"resumo da triagem: {t.summary}")
    lines.append(f"resumo da fonte: {(rep.get('summary') or '')[:SUMMARY_CHARS_CURATION]}")
    if s.siblings:
        lines.append("outras fontes do mesmo fato:")
        lines += [f"- [{it['source']}] {it['title']}" for it in s.siblings[:MAX_SIBLINGS]]
    return WebDocument(
        id=rep["id"], source=rep["source"], url=rep["url"], title=rep["title"],
        text="\n".join(lines),
    )


def _card_doc(c: Candidate) -> WebDocument:
    s = c.story
    rep = s.representative
    lines = [
        f"publicado: {_brt(rep['published_utc'])} (Brasília)",
        _sources_line(s),
        f"resumo da fonte: {(rep.get('summary') or '')[:SUMMARY_CHARS_CARD]}",
    ]
    if s.siblings:
        lines.append("outras fontes do mesmo fato:")
        for n, it in enumerate(s.siblings[:MAX_SIBLINGS]):
            lines.append(f"- [{it['source']}] {it['title']} ({_brt(it['published_utc'])})")
            if n < 2 and it.get("summary"):
                lines.append(f"  {it['summary'][:SUMMARY_CHARS_SIBLING]}")
    return WebDocument(
        id=rep["id"], source=rep["source"], url=rep["url"], title=rep["title"],
        text="\n".join(lines),
    )
