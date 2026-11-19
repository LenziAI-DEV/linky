"""Frente Post: fontes, redação, checagem e montagem do texto (docs/ideas/producao-mvp.md).

    docs = fetch_sources(entry.sources)
    draft = write(entry, docs, harness=harness, recent_hooks=hooks)
    texto = compose(draft, hook=0, reading=0)          # ou o texto que Felipe escreveu

O `write` roda dois agentes, de fornecedores diferentes (`config/models.yaml`):
- **redação** (`prompts/redacao/v1.md`): hooks, corpo, leituras e cauda, nas regras do
  `voz.md` v2 e do `playbook.md` v2;
- **checagem** (`prompts/checagem/v1.md`): cada número, nome e afirmação contra as fontes.

Entre os dois, a **validação em código** (`check_draft`): tamanho, hashtag, link, emoji,
hook de até 120 caracteres, primeira pessoa e a lista de cortes do playbook §7. Falhou: 1 nova
tentativa com o motivo. Problema grave na checagem: 1 refação com os problemas. O que sobrar
vai para `Draft.notes`, que Felipe vê no e-mail de aprovação.

A menção à empresa principal (`voz.md` §7) sai do mapa `config/companies.yaml`, no formato
little `@[Nome](urn:li:organization:ID)`, na primeira vez que a empresa aparece no texto final.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from functools import cache
from html.parser import HTMLParser
from itertools import product
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..editorial import Entry
from ..harness import AgentSpec, Harness, RunFailed, WebDocument
from ..harness.budget import CHARS_PER_TOKEN
from ..harness.config import load_models
from ..harness.core import ROOT
from ..netguard import Resolver, check_url
from .contracts import Closing, Draft, Hook, Structure, compose_text

log = logging.getLogger(__name__)

COMPANIES_PATH = ROOT / "config" / "companies.yaml"
MAX_SOURCES = 3
MAX_REDIRECTS = 5
MIN_CHARS, MAX_CHARS = 500, 1300
E2_MAX_CHARS = 800  # playbook §4: o número com virada é curto
HOOK_LINE_MAX, HOOK_MAX = 120, 200
RECENT_HOOKS_MAX = 15


# =========================================================================== contratos
class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pauta(_In):
    title: str
    what: str = ""
    why: str = ""
    angle: str = ""
    pattern: str = ""
    audience: str = ""
    event_date: str = ""


class Ajuste(_In):
    post_anterior: str  # o texto que Felipe viu
    pedido: str  # o pedido mais recente
    pedidos_anteriores: list[str] = Field(default_factory=list)  # já atendidos


class WriteIn(_In):
    pauta: Pauta
    opiniao_de_felipe: str | None = None
    ajuste: Ajuste | None = None
    hooks_recentes: list[str] = Field(default_factory=list)
    correcoes: list[str] = Field(default_factory=list)
    rascunho_anterior: dict | None = None
    documents: list[WebDocument] = Field(default_factory=list)


class WriterOut(BaseModel):
    """Saída da redação. A ordem dos campos é a ordem em que o modelo escreve: o corpo antes
    dos hooks, porque o hook resume o que o corpo sustenta."""

    model_config = ConfigDict(extra="ignore")

    structure: Structure = Field(description="Estrutura usada, E1 a E5")
    body: str = Field(min_length=1, description="Do acompanhamento do hook até antes da leitura")
    readings: list[str] = Field(
        min_length=1, max_length=2,
        description="1 leitura em primeira pessoa (com opinião de Felipe) ou 2 neutras",
    )
    tail: str = Field(min_length=1, description="Ressalva honesta + fechamento + 0 ou 1 hashtag")
    closing: Closing
    hooks: list[Hook] = Field(min_length=3, max_length=3, description="3 hooks de tipos diferentes")
    headline: str = Field(min_length=1, max_length=80, description="Ideia central, até 8 palavras")
    main_company: str = Field(default="", description="Empresa principal do post, ou vazio")


class CheckIn(_In):
    opiniao_de_felipe: str | None = None
    hooks: list[str]
    body: str
    readings: list[str]
    tail: str
    documents: list[WebDocument] = Field(default_factory=list)


class Problem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    part: Literal["hook", "body", "reading", "tail"]
    excerpt: str
    issue: str
    severity: Literal["grave", "leve"]


class CheckOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    problems: list[Problem] = Field(default_factory=list)


REDACAO = AgentSpec(name="redacao", version="v1", input=WriteIn, output=WriterOut)
CHECAGEM = AgentSpec(name="checagem", version="v1", input=CheckIn, output=CheckOut)
SPECS: dict[str, AgentSpec] = {s.name: s for s in (REDACAO, CHECAGEM)}


# =========================================================================== fontes
USER_AGENT = f"linky-dev/{__version__} (personal news curation; article reader)"
_MAX_BYTES = 3_000_000
_SKIP_TAGS = {
    "script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form",
    "button", "iframe", "figure", "template", "select", "dialog",
}
_SKIP_HINT = re.compile(
    r"related|recomend|comment|coment|share|compartilh|newsletter|promo|advert|publicidade|"
    r"cookie|menu|sidebar|footer|breadcrumb|banner|social|leia-?tamb|veja-?tamb|tags?\b",
    re.IGNORECASE,
)
_BLOCKS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"}
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
    "track", "wbr",
}


class _Extractor(HTMLParser):
    """Texto principal por heurística: blocos de texto fora de menus, rodapés e afins,
    marcados por estarem dentro de <article> ou <main>; mais título, metadados e JSON-LD."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.blocks: list[tuple[str, str, bool, bool]] = []  # (tag, texto, article, main)
        self.ld: list[str] = []
        self._skip: tuple[str, int] | None = None
        self._article = 0
        self._main = 0
        self._block: tuple[str, list[str]] | None = None
        self._in_title = False
        self._ld: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
            return
        if tag in _VOID:
            if tag == "br" and self._block and not self._skip:
                self._block[1].append(" ")
            return
        if self._skip:
            if tag == self._skip[0]:
                self._skip = (tag, self._skip[1] + 1)
            return
        if tag == "script" and "ld+json" in a.get("type", ""):
            self._ld = []
            return
        hint = f"{a.get('class', '')} {a.get('id', '')} {a.get('role', '')}"
        if tag in _SKIP_TAGS or (tag in {"div", "section", "ul", "ol"} and _SKIP_HINT.search(hint)):
            self._skip = (tag, 1)
            return
        if tag == "title":
            self._in_title = True
        elif tag == "article":
            self._article += 1
        elif tag == "main":
            self._main += 1
        elif tag in _BLOCKS:
            self._flush()
            self._block = (tag, [])

    def handle_endtag(self, tag):
        if self._ld is not None and tag == "script":
            self.ld.append("".join(self._ld))
            self._ld = None
            return
        if self._skip:
            if tag == self._skip[0]:
                n = self._skip[1] - 1
                self._skip = (tag, n) if n else None
            return
        if tag == "title":
            self._in_title = False
        elif tag == "article":
            self._article = max(0, self._article - 1)
        elif tag == "main":
            self._main = max(0, self._main - 1)
        elif self._block and tag == self._block[0]:
            self._flush()

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        elif self._skip:
            return
        elif self._in_title:
            self.title += data
        elif self._block:
            self._block[1].append(data)

    def _flush(self) -> None:
        if self._block:
            tag, parts = self._block
            text = re.sub(r"\s+", " ", "".join(parts)).strip()
            if text:
                self.blocks.append((tag, text, self._article > 0, self._main > 0))
        self._block = None


def _ld_body(scripts: list[str]) -> str:
    """O `articleBody` do JSON-LD (muitos sites de notícia publicam o texto inteiro ali)."""

    def walk(node):
        if isinstance(node, dict):
            body = node.get("articleBody")
            if isinstance(body, str):
                yield body
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    best = ""
    for raw in scripts:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for body in walk(data):
            if len(body) > len(best):
                best = body
    return re.sub(r"[ \t]+", " ", best).strip()


def _useful(tag: str, text: str) -> bool:
    if tag in {"h1", "h2", "h3", "h4"}:
        return len(text) >= 15
    if tag == "li":
        return len(text) >= 60
    return len(text) >= 40


def extract_text(html: str) -> tuple[str, str, dict[str, str]]:
    """(título, texto principal, metadados) de uma página HTML."""
    p = _Extractor()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 - HTML quebrado: fica com o que deu para ler
        log.debug("HTML com erro de parse", exc_info=True)
    p._flush()
    title = p.meta.get("og:title") or re.sub(r"\s+", " ", p.title).strip()
    text = _ld_body(p.ld)
    if len(text) < 400:
        blocks = [(t, s, a, m) for t, s, a, m in p.blocks if _useful(t, s)]
        for scope in (lambda b: b[2], lambda b: b[3], lambda b: True):
            chosen: list[str] = []
            for b in filter(scope, blocks):
                if not chosen or chosen[-1] != b[1]:
                    chosen.append(b[1])
            if sum(map(len, chosen)) >= 400:
                break
        if sum(map(len, chosen)) > len(text):
            text = "\n\n".join(chosen)
    if len(text) < 200:
        desc = p.meta.get("og:description") or p.meta.get("description") or ""
        text = "\n\n".join(x for x in (text, desc) if x)
    return title, text, p.meta


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.8 else cut).rstrip() + " [...]"


@cache
def _default_doc_tokens() -> int:
    return load_models(ROOT / "config" / "models.yaml").agent(REDACAO.name).max_doc_tokens


def fetch_sources(
    urls: Sequence[str],
    *,
    max_doc_tokens: int | None = None,
    client: httpx.Client | None = None,
    timeout_s: float = 15.0,
    resolve: Resolver | None = None,
) -> list[WebDocument]:
    """Baixa até 3 URLs e extrai o texto principal de cada uma.

    O texto é cortado em `max_doc_tokens` (o da redação em `config/models.yaml`). Uma fonte que
    falha (rede, bloqueio, página sem texto, URL recusada pela proteção contra SSRF) fica de
    fora sem derrubar as outras. Os redirecionamentos são seguidos à mão, até
    `MAX_REDIRECTS`, e cada salto passa pelo `netguard.check_url`.
    """
    limit = (max_doc_tokens or _default_doc_tokens()) * CHARS_PER_TOKEN
    own = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        timeout=httpx.Timeout(timeout_s),
        follow_redirects=False,
    )
    docs: list[WebDocument] = []
    try:
        for url in list(dict.fromkeys(u for u in urls if u))[:MAX_SOURCES]:
            try:
                doc = _fetch_one(client, url, limit, len(docs) + 1, resolve)
            except Exception as e:  # noqa: BLE001 - uma fonte ruim não derruba o post
                log.warning("fonte ignorada: %s (%s: %s)", url, type(e).__name__, e)
                continue
            if doc:
                docs.append(doc)
    finally:
        if own:
            client.close()
    return docs


def _get_guarded(client: httpx.Client, url: str, resolve: Resolver | None) -> httpx.Response:
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url, resolve=resolve)
        r = client.get(url, follow_redirects=False)
        if not r.is_redirect:
            return r
        url = urljoin(str(r.url), r.headers["location"])
    raise httpx.TooManyRedirects(f"mais de {MAX_REDIRECTS} redirecionamentos", request=r.request)


def _fetch_one(
    client: httpx.Client, url: str, limit: int, n: int, resolve: Resolver | None = None
) -> WebDocument | None:
    r = _get_guarded(client, url, resolve)
    r.raise_for_status()
    kind = r.headers.get("content-type", "").lower()
    if kind and "html" not in kind and "text/plain" not in kind:
        log.warning("fonte ignorada: %s (tipo %s)", url, kind)
        return None
    body = r.content[:_MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
    if "html" in kind or body.lstrip()[:1] == "<":
        title, text, meta = extract_text(body)
    else:
        title, text, meta = "", body.strip(), {}
    if len(text) < 80:
        log.warning("fonte ignorada: %s (sem texto legível)", url)
        return None
    published = (meta.get("article:published_time") or "")[:10]
    if published:
        text = f"Publicado em {published}.\n\n{text}"
    host = urlparse(str(r.url)).hostname or ""
    return WebDocument(
        id=f"fonte{n}",
        source=meta.get("og:site_name") or host.removeprefix("www."),
        url=url,
        title=title,
        text=_cut(text, limit),
    )


# =========================================================================== empresas
class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    id: int
    aliases: list[str] = Field(default_factory=list)

    @property
    def urn(self) -> str:
        return f"urn:li:organization:{self.id}"

    @property
    def mention(self) -> str:
        return f"@[{self.name}]({self.urn})"

    @property
    def names(self) -> list[str]:
        return sorted({self.name, *self.aliases}, key=len, reverse=True)


def load_companies(path: Path = COMPANIES_PATH) -> list[Company]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Company.model_validate(c) for c in data.get("companies") or []]


def find_company(name: str, companies: Sequence[Company]) -> Company | None:
    """A empresa do mapa com esse nome (ou apelido). Sem correspondência, nenhuma."""
    key = name.strip().casefold()
    if not key:
        return None
    for c in companies:
        if key in {n.casefold() for n in c.names}:
            return c
    for c in companies:  # "Uber Eats" → Uber; "a Bain & Company" → Bain & Company
        if any(_name_re(n).search(name) for n in c.names):
            return c
    return None


MENTION = re.compile(r"@\[([^\[\]\n]+)\]\((urn:li:(?:organization|person):[\w-]+)\)")


def _name_re(name: str) -> re.Pattern:
    return re.compile(rf"(?<![\w@\[]){re.escape(name)}(?![\w\]])")


def display(text: str) -> str:
    """O texto como o leitor vê: a menção vira só o nome."""
    return MENTION.sub(r"\1", text)


def _mention_first(text: str, company: Company) -> str:
    """Troca a primeira ocorrência do nome (ou de um apelido) pela menção."""
    hits = [m for n in company.names if (m := _name_re(n).search(text))]
    if not hits:
        return text
    m = min(hits, key=lambda h: h.start())
    return text[: m.start()] + company.mention + text[m.end() :]


def _with_mention(out: WriterOut, companies: Sequence[Company]) -> WriterOut:
    """Põe a menção à empresa principal de modo que **qualquer** combinação de hook e leitura
    (`contracts.compose_text`) tenha exatamente uma.

    - Os 3 hooks citam a empresa: a menção vai em cada hook (a primeira vez no texto).
    - Senão, na primeira vez que ela aparece no corpo; sem corpo, na cauda. Se um hook também
      cita a empresa, a menção fica no corpo: uma só, ainda que não seja a primeira vez.
    - As leituras ficam sem menção, porque Felipe pode trocá-las ou reescrevê-las.
    """
    company = find_company(out.main_company, companies) if out.main_company else None
    if company is None:
        return out
    hooks = [h.model_copy(update={"text": _mention_first(h.text, company)}) for h in out.hooks]
    if all(MENTION.search(h.text) and len(h.text) <= HOOK_MAX for h in hooks):
        return out.model_copy(update={"hooks": hooks})
    body = _mention_first(out.body, company)
    if body != out.body:
        return out.model_copy(update={"body": body})
    return out.model_copy(update={"tail": _mention_first(out.tail, company)})


# =========================================================================== montagem
def compose(draft: Draft, hook: int | str | Hook, reading: int | str) -> str:
    """O texto final pela regra única de `contracts.compose_text`.

    `hook` e `reading` são o índice no rascunho ou o texto que Felipe escreveu.
    """
    if isinstance(hook, int):
        hook = draft.hooks[hook]
    hook_text = hook.text if isinstance(hook, Hook) else hook
    reading_text = draft.readings[reading] if isinstance(reading, int) else reading
    return compose_text(hook_text, draft.body, reading_text, draft.tail)


# =========================================================================== validação
_URL = re.compile(
    r"https?://|\bwww\.|\b[\w-]+\.(?:com|com\.br|br|io|ai|org|net|dev|app|co)(?:/|\b(?!\.\w))",
    re.IGNORECASE,
)
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff️‍⌀-⏿]"
)
_HASHTAG = re.compile(r"(?<![\w&])#[^\W\d_]\w*")
_GENERIC_TAGS = {
    "#inovacao", "#tecnologia", "#negocios", "#ia", "#ai", "#futuro", "#transformacaodigital",
    "#lideranca", "#empreendedorismo", "#gestao",
}
_AT = re.compile(r"(?<![\w.])@(?!\[)")
_DASH = re.compile(r"\s[—–]\s|—")
_QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”|«[^»\n]*»")
_FIRST_PERSON = re.compile(
    r"\b(eu|minha|minhas|meu|meus|comigo|construo|acredito|vejo|acho)\b|\bpra mim\b|"
    r"\bpara mim\b|\bme parece\b",
    re.IGNORECASE,
)
_LIST_LINE = re.compile(r"^\s*(?:[•→\-*]|\d+[.)])\s")
_LABEL = re.compile(r"^(?:[•→]\s*)?[A-ZÀ-Ý][^\n:.?!,;]{1,40}:\s", re.MULTILINE)
_CAPS = re.compile(r"\b[A-ZÀ-Ý]{3,}\s+[A-ZÀ-Ý]{3,}\b")

# Lista de cortes (playbook.md §7 e voz.md §8): uma ocorrência já reprova
_CUTS: list[tuple[str, re.Pattern]] = [
    (label, re.compile(rx, re.IGNORECASE))
    for label, rx in [
        ("frase de moral", r"\b(essa|esta) é a lição\b|\bfica a reflexão\b|\bo recado é claro\b|"
                           r"\blição de negócio\b|\ba lição aqui\b"),
        ("pergunta retórica com resposta", r"\be o (mais|melhor|pior) [^?\n]{0,30}\?"),
        ("\"Em um mundo onde\"", r"\bem um mundo (onde|em que)\b"),
        ("\"cada vez mais\"", r"\bcada vez mais\b"),
        ("\"vale ressaltar\"", r"\bvale (ressaltar|destacar|lembrar)\b"),
        ("\"Na prática,\" abrindo parágrafo", r"(^|\n)\s*na prática,"),
        ("\"Spoiler:\"", r"\bspoiler:"),
        ("\"Resumindo:\"", r"\bresumindo:"),
        ("\"Vamos lá\"", r"\bvamos lá\b"),
        ("\"E aqui está o ponto\"", r"\baqui está o ponto\b"),
        ("\"nesse sentido\"", r"\b(nesse|neste) sentido\b"),
        ("\"no cenário atual\"", r"\bno cenário atual\b"),
        ("\"sem dúvida\"", r"\bsem dúvidas?\b"),
        ("\"o futuro chegou\"", r"\bo futuro chegou\b"),
        ("\"opinião impopular\"", r"\bopinião impopular\b|\bninguém está falando\b"),
        ("isca de comentário",
         r"\bo que vocês acham\b|\bconcorda\?|\bcomente\b|\bmarque (alguém|um)"),
        ("mergulhar", r"\bmergulh\w*"),
        ("jornada", r"\bjornadas?\b(?! d[oe]s? clientes?)"),
        ("potencializar", r"\bpotencializ\w*"),
        ("alavancar", r"\balavanc\w*"),
        ("robusto", r"\brobust[oa]s?\b"),
        ("crucial", r"\bcruciais\b|\bcrucial\b"),
        ("fundamental", r"\bfundamenta(l|is)\b"),
        ("transformador", r"\btransformador(a|es|as)?\b"),
        ("\"sem precedentes\"", r"\bsem precedentes\b"),
        ("revolucionário", r"\brevolucionári[oa]s?\b"),
        ("disruptivo", r"\bdisruptiv[oa]s?\b"),
        ("game changer", r"\bgame[- ]changer\b"),
        ("incrível", r"\bincríve(l|is)\b"),
        ("mindset", r"\bmindset\b"),
    ]
]
_NOT_X_IS_Y = re.compile(r"\bnão é sobre\b|\bnão é [^.!?\n]{1,60}?[,;]\s*(é|mas)\b", re.IGNORECASE)
_GERA_VALOR = re.compile(r"\bgera(m)? valor\b|\bo diferencial não é\b", re.IGNORECASE)


def _hooks_alike(a: str, b: str) -> bool:
    def norm(s: str) -> list[str]:
        return re.findall(r"\w+", display(s).casefold())

    x, y = norm(a), norm(b)
    return bool(x and y) and (x == y or x[:5] == y[:5])


def _lists(text: str) -> int:
    runs, inside = 0, False
    for line in text.splitlines():
        if _LIST_LINE.match(line):
            runs += 0 if inside else 1
            inside = True
        elif line.strip():
            inside = False
    return runs


def check_draft(
    draft: Draft | WriterOut,
    *,
    opinion: str | None = None,
    recent_hooks: Sequence[str] = (),
    pattern: str = "",
    first_person_ok: bool = False,
) -> list[str]:
    """Regras determinísticas do post. Devolve os problemas, em frases para o redator."""
    out: list[str] = []
    hooks = [h for h in draft.hooks]
    kinds = [h.kind for h in hooks]
    if len(hooks) != 3 or len(set(kinds)) != len(kinds):
        out.append(f"escreva 3 hooks de tipos diferentes (vieram {', '.join(kinds)})")
    for h in hooks:
        text = display(h.text).strip()
        first = text.split("\n", 1)[0]
        if len(first) > HOOK_LINE_MAX:
            out.append(f"o hook {h.kind} tem {len(first)} caracteres na primeira linha "
                       f"(máximo {HOOK_LINE_MAX}): \"{first}\"")
        if len(text) > HOOK_MAX:
            out.append(f"o hook {h.kind} passa de {HOOK_MAX} caracteres com a linha de apoio")
        if h.kind in {"H3", "H4"} and not opinion:
            out.append(f"o hook {h.kind} exige a opinião ou a experiência de Felipe, e esta "
                       "pauta não tem: use H1, H2, H5 ou H6")
        if text.endswith("?") or re.match(r"^(você|vocês)\b[^.!]*\?", text, re.IGNORECASE):
            out.append(f"o hook {h.kind} abre com pergunta; troque por afirmação")
        for old in recent_hooks:
            if _hooks_alike(h.text, old):
                out.append(f"o hook {h.kind} repete um hook recente: \"{old}\"")
                break
    want = 1 if opinion else 2
    if len(draft.readings) != want:
        out.append(f"escreva {want} leitura{'s' if want > 1 else ''} (vieram "
                   f"{len(draft.readings)}): " + ("só a de Felipe, em primeira pessoa"
                                                  if opinion else "duas em voz neutra"))
    if draft.structure in {"E4", "E5"} and not (opinion and pattern in {"P5", "P6"}):
        out.append(f"a estrutura {draft.structure} exige material de Felipe; use E1, E2 ou E3")

    raw = [compose_text(h.text, draft.body, r, draft.tail)
           for h, r in product(hooks, draft.readings)]
    shown = [len(display(t)) for t in raw]
    longest = max(len(t) for t in raw)  # o limite vale para o texto enviado, com a menção
    if longest > MAX_CHARS:
        out.append(
            f"o texto final chega a {longest} caracteres e o máximo é {MAX_CHARS}: corte pelo "
            f"menos {longest - MAX_CHARS + 100} caracteres (o corpo tem {len(draft.body)}, as "
            f"leituras {', '.join(str(len(r)) for r in draft.readings)}, a cauda "
            f"{len(draft.tail)}). Tire os detalhes que não sustentam a ideia central"
        )
    elif min(shown) < MIN_CHARS:
        out.append(f"o texto final tem só {min(shown)} caracteres com o hook e a leitura mais "
                   f"curtos; o mínimo é {MIN_CHARS}")

    everything = display("\n\n".join(
        [*(h.text for h in hooks), draft.body, *draft.readings, draft.tail]
    ))
    before_tail = display("\n\n".join([*(h.text for h in hooks), draft.body, *draft.readings]))
    if _HASHTAG.search(before_tail):
        out.append("hashtag só na última linha da cauda")
    tags = _HASHTAG.findall(display(draft.tail))
    if len(tags) > 1:
        out.append(f"use 0 ou 1 hashtag (vieram {len(tags)}: {' '.join(tags)})")
    generic = [t for t in tags if t.casefold() in _GENERIC_TAGS]
    if generic:
        out.append(f"hashtag genérica ({' '.join(generic)}); use uma específica ou nenhuma")
    if _URL.search(everything):
        out.append(f"tire o link do texto (\"{_URL.search(everything).group(0)}\")")
    if _EMOJI.search(everything):
        out.append("tire os emojis")
    if _AT.search(everything):
        out.append("não use @: escreva o nome da empresa (a menção é colocada pelo sistema)")
    if len(_DASH.findall(everything)) > 1:
        out.append("tire os travessões: use vírgula, ponto ou dois-pontos")
    if _CAPS.search(everything):
        out.append(f"sem caixa alta para dar ênfase (\"{_CAPS.search(everything).group(0)}\")")
    body = display(draft.body)
    if _lists(body + "\n\n" + display(draft.tail)) > 1:
        out.append("no máximo uma lista por post")
    labels = _LABEL.findall(body)
    if len(labels) > 1:
        out.append(f"rótulo antes de dois-pontos no máximo uma vez no corpo (vieram {len(labels)})")

    unquoted = _QUOTED.sub("", everything)
    for label, rx in _CUTS:
        if rx.search(unquoted):
            out.append(f"corte {label} (\"{rx.search(unquoted).group(0).strip()}\"): soa como IA")
    if len(_NOT_X_IS_Y.findall(unquoted)) > 1:
        out.append("\"não é X, é Y\" no máximo uma vez")
    if len(_GERA_VALOR.findall(unquoted)) > 1:
        out.append("\"gera valor\" e \"o diferencial não é\" no máximo uma vez")

    if not first_person_ok:
        outside = [*(h.text for h in hooks if h.kind not in {"H3", "H4"}), draft.body, draft.tail]
        if not opinion:
            outside += list(draft.readings)
        hit = _FIRST_PERSON.search(_QUOTED.sub("", display("\n".join(outside))))
        if hit:
            where = "na leitura e no hook H3" if opinion else "em nenhum lugar"
            out.append(f"primeira pessoa (\"{hit.group(0)}\") só pode aparecer {where}: "
                       "Felipe não disse isso; use voz neutra")
    return out


# =========================================================================== redação
def write(
    entry: Entry,
    sources: Sequence[WebDocument],
    *,
    harness: Harness,
    recent_hooks: Sequence[str] = (),
    companies: Sequence[Company] | None = None,
) -> Draft:
    """Escreve o rascunho do post: redação, validação, checagem e, se preciso, 1 refação.

    Falha da redação levanta `RunFailed`. Falha da checagem (ou da refação) não derruba o post:
    o rascunho segue com o aviso em `notes`.
    """
    companies = load_companies() if companies is None else companies
    opinion = (entry.opinion or "").strip() or None
    recent = [h for h in recent_hooks if h.strip()][-RECENT_HOOKS_MAX:]
    ajuste = None
    if entry.adjustments and entry.post:
        ajuste = Ajuste(
            post_anterior=entry.post.commentary,
            pedido=entry.adjustments[-1],
            pedidos_anteriores=list(entry.adjustments[:-1]),
        )
    base = WriteIn(
        pauta=Pauta(
            title=entry.title, what=entry.what, why=entry.why, angle=entry.angle,
            pattern=entry.pattern, audience=entry.audience,
            event_date=entry.event_date.isoformat(),
        ),
        opiniao_de_felipe=opinion,
        ajuste=ajuste,
        hooks_recentes=recent,
        documents=list(sources),
    )
    # Num ajuste, a leitura que Felipe já aprovou ou escreveu pode estar em primeira pessoa
    first_person_ok = bool(ajuste and _FIRST_PERSON.search(_QUOTED.sub("", ajuste.post_anterior)))

    def validate(out: WriterOut) -> list[str]:
        return check_draft(_with_mention(out, companies), opinion=opinion,
                           recent_hooks=recent, pattern=entry.pattern,
                           first_person_ok=first_person_ok)

    def redo(prev: WriterOut, fixes: list[str]) -> WriterOut:
        inp = base.model_copy(update={
            "correcoes": fixes,
            "rascunho_anterior": prev.model_dump(mode="json", exclude={"main_company"}),
        })
        return harness.run(REDACAO, inp).output

    notes: list[str] = []
    out: WriterOut = harness.run(REDACAO, base).output
    problems = validate(out)
    if problems:
        new, new_problems = _redo(redo, out, problems, validate, notes)
        if new is not None and len(new_problems) < len(problems):
            out, problems = new, new_problems

    found = _check(harness, out, opinion, sources, notes)
    graves = [p for p in found or [] if p.severity == "grave"]
    if graves:
        fixes = [f"checagem: {_fmt(p)}" for p in graves]
        new, new_problems = _redo(redo, out, fixes, validate, notes)
        if new is not None and len(new_problems) <= len(problems):
            out, problems = new, new_problems
            found = _check(harness, out, opinion, sources, notes)
        elif new is not None:
            notes.append("A refação pedida pela checagem não passou na validação; "
                         "ficou o rascunho anterior")

    notes += [f"Validação: {p}" for p in problems]
    notes += [f"Checagem ({p.severity}): {_fmt(p)}" for p in found or []]
    return _to_draft(_with_mention(out, companies), opinion, notes)


def _redo(redo, prev: WriterOut, fixes: list[str], validate, notes: list[str]):
    """1 nova tentativa da redação com os motivos. Devolve (rascunho, problemas) ou
    (None, []) se a chamada falhar: o rascunho anterior continua valendo."""
    try:
        new = redo(prev, fixes)
    except RunFailed as e:
        notes.append(f"A nova tentativa da redação falhou ({e}); ficou o rascunho anterior")
        return None, []
    return new, validate(new)


def _check(harness: Harness, out: WriterOut, opinion, sources, notes) -> list[Problem] | None:
    inp = CheckIn(
        opiniao_de_felipe=opinion,
        hooks=[display(h.text) for h in out.hooks],
        body=display(out.body),
        readings=[display(r) for r in out.readings],
        tail=display(out.tail),
        documents=list(sources),
    )
    if not sources:
        notes.append("Checagem sem fontes: nenhuma fonte foi lida, os fatos não foram conferidos")
    try:
        return harness.run(CHECAGEM, inp).output.problems
    except RunFailed as e:
        notes.append(f"A checagem não rodou ({e}); confira os números antes de aprovar")
        return None


def _fmt(p: Problem) -> str:
    return f"{p.part}, \"{p.excerpt}\": {p.issue}"


def _structure(out: WriterOut) -> Structure:
    """O E2 é curto (playbook §4). Um "E2" que passou de 800 caracteres é, na prática, uma
    análise: a marcação vira E1, para a medição do playbook (§8) não misturar os dois."""
    if out.structure == "E2":
        longest = max(len(display(compose_text(h.text, out.body, r, out.tail)))
                      for h, r in product(out.hooks, out.readings))
        if longest > E2_MAX_CHARS:
            return "E1"
    return out.structure


def _to_draft(out: WriterOut, opinion, notes: list[str]) -> Draft:
    return Draft(
        structure=_structure(out),
        hooks=[h.model_copy(update={"text": h.text.strip()}) for h in out.hooks],
        body=out.body.strip(),
        readings=[r.strip() for r in out.readings],
        reading_is_felipe=bool(opinion),
        tail=out.tail.strip(),
        closing=out.closing,
        headline=out.headline.strip(),
        notes=list(dict.fromkeys(notes)),
    )
