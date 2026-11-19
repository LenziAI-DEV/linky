"""Agrupamento determinístico de itens coletados por fato (sem LLM, sem dependência nova).

A mesma notícia chega por várias fontes, com URLs e títulos diferentes (às vezes em inglês e
em português), e escapa do dedupe por título do coletor: a Alexa no dia 1 do T2, ~25 itens
do caso do CEO da Nvidia no dia 2. Antes da triagem, os itens viram **fatos** (`Story`): um
item representante e as fontes irmãs, que entram como fontes do card.

Como funciona:
- cada item vira a sequência de termos do título (minúsculas, sem acento, sem palavras
  vazias em português e inglês; números e valores como "5.2" e "$11b" contam; um vocabulário
  curto de notícia leva o português ao inglês: "espiã" e "spy" são o mesmo termo);
- o peso de cada termo é a raridade dele no próprio lote (IDF): "nvidia" pesa pouco num dia
  em que todo mundo fala de Nvidia; "siri" ou "alexa" pesam muito;
- em ordem de publicação, o item entra no fato que tem o item mais parecido com ele, se a
  semelhança passar do limiar, se os dois dividirem pelo menos dois termos (um nome de várias
  palavras conta como um) e se o fato tiver item publicado dentro da janela; senão, abre um
  fato novo. Entrar uma vez, pelo item mais parecido, evita boa parte da corrente "A parece
  B, B parece C" de ligar todos os pares;
- títulos idênticos (mesma `title_key`) são sempre o mesmo fato, mesmo em dias diferentes.

O representante é o item mais parecido com os demais do fato (desempate: fonte primária,
depois o mais antigo). Calibrado com os itens reais de 06 a 10/11/2026 (ADR 0007).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .normalize import title_key

WINDOW = timedelta(hours=48)
THRESHOLD = 0.30
MIN_SHARED = 2  # um termo só em comum ("nvidia", "apple") não junta dois fatos
# Fonte primária primeiro no desempate do representante (sources/sources.yaml)
_TIER_ORDER = {"primary": 0, "press": 1, "analysis": 2, "br": 3}

# Palavras vazias (português e inglês), verbos de anúncio ("lança", "launches": dizem pouco
# sobre qual é o fato) e termos que todo item do coletor tem ("IA", "AI")
_STOP_WORDS = """
a o os as um uma uns umas de do da dos das em no na nos nas por para pra com sem sobre e ou
que se ao aos sao ser foi vai vao como mais menos seu sua seus suas ja ate apos entre
tem ter diz faz pode deve isso esse essa este esta nao sim quem qual onde quando porque
veja saiba confira entenda agora novo nova novos novas
the an of to in on for with by from at as is are be was were it its this that these and or
but not new how why what who when where your you our we they their them can will now after
into over about up out more than just has have had says said here vs via all most could would
may get gets make makes using use uses one first his her he she like
lanca lancam lancar lancamento apresenta revela anuncia
launch launches launched release releases released introduce introduces introducing
unveil unveils reveal reveals announce announces
ai ia inteligencia artificial intelligence
"""
_STOP = frozenset(_STOP_WORDS.split())
# Vocabulário de notícia levado a um termo só (quase sempre do português para o inglês): as
# fontes brasileiras repetem fatos da imprensa americana, e sem isto só os nomes próprios
# ligariam os dois idiomas. Chaves sem acento, no singular ou no plural (o plural simples é
# tirado depois de procurar a palavra como veio)
_EQUIVALENTS = {
    "espia": "spy", "espiao": "spy", "espionagem": "spy", "espionar": "spy",
    "espionage": "spy",
    "investiga": "investigate", "investigar": "investigate", "investigacao": "investigate",
    "investigating": "investigate", "investigation": "investigate",
    "chinesa": "china", "chines": "china", "chinese": "china",
    "processado": "sue", "processada": "sue", "processados": "sue", "processam": "sue",
    "lawsuit": "sue", "suing": "sue", "sued": "sue",
    "eua": "us", "usa": "us",
    "cobrar": "charge", "cobra": "charge", "charging": "charge",
    "filtro": "filter",
    "senha": "secret", "chave": "secret",
    "vaza": "leak", "vazam": "leak", "vazamento": "leak", "exposing": "leak",
    "gerador": "generator", "geradores": "generator",
    "eleicao": "election", "eleicoes": "election", "midterm": "election",
    "avaliacao": "valuation", "avaliada": "valuation",
    "trilhao": "trillion", "trilhoes": "trillion", "bilhao": "billion", "bilhoes": "billion",
}
_WORD = re.compile(r"\$?\w+(?:[.,]\d+)*\w*")


def _fold(text: str) -> str:
    text = text.replace("’", "'")  # antes de tirar o que não é ASCII
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def terms(title: str) -> tuple[str, ...]:
    """Termos de um título que servem para comparar fatos, na ordem em que aparecem."""
    out: list[str] = []
    for w in _WORD.findall(_fold(title)):
        has_digit = any(c.isdigit() for c in w)
        if w in _STOP or (len(w) < 3 and not has_digit):
            continue
        if w in _EQUIVALENTS:
            w = _EQUIVALENTS[w]
        elif not has_digit and len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # plural simples: "chips" e "chip", "agentes" e "agente"
            w = _EQUIVALENTS.get(w, w)
        if w not in _STOP and w not in out:
            out.append(w)
    return tuple(out)


def shared_terms(a: Sequence[str], b: Sequence[str]) -> int:
    """Quantos termos dois títulos dividem, contando uma expressão seguida nos dois como um
    termo só: "Amazon Bedrock AgentCore" ou "Hugging Face" são um nome, não três ou dois."""
    in_b, pairs_b = set(b), set(zip(b, b[1:], strict=False))
    count, prev = 0, None
    for t in a:
        if t in in_b and not (prev is not None and (prev, t) in pairs_b):
            count += 1
        prev = t if t in in_b else None
    return count


@dataclass(frozen=True)
class Story:
    """Um fato: o item representante e as fontes irmãs (itens do coletor, como gravados)."""

    representative: dict
    siblings: tuple[dict, ...] = ()

    @property
    def items(self) -> list[dict]:
        return [self.representative, *self.siblings]

    @property
    def sources(self) -> list[str]:
        """URLs para o card: a do representante primeiro, sem repetição."""
        return list(dict.fromkeys(it["url"] for it in self.items))

    @property
    def first_seen(self) -> datetime:
        return min(_published(it) for it in self.items)

    @property
    def last_seen(self) -> datetime:
        return max(_published(it) for it in self.items)

    def to_json(self) -> dict:
        """O fato como entrada da triagem: representante, irmãs e janela de publicação."""
        brief = ("id", "source", "title", "url", "published_utc")
        return {
            "id": self.representative["id"],
            "representative": self.representative,
            "siblings": [{k: it[k] for k in brief} for it in self.siblings],
            "sources": self.sources,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


def _published(it: dict) -> datetime:
    return datetime.fromisoformat(it["published_utc"])


class _Draft:
    """Fato em formação: os membros (índices no lote), o horário do item mais recente e as
    chaves de título já vistas (título idêntico entra direto)."""

    def __init__(self, i: int, at: datetime, key: str):
        self.members, self.last, self.keys = [i], at, {key}

    def add(self, i: int, at: datetime, key: str) -> None:
        self.members.append(i)
        self.last = max(self.last, at)
        self.keys.add(key)


def similarity(a: Sequence[str], b: Sequence[str], weight: dict[str, float]) -> float:
    """Semelhança entre dois títulos (0 a 1): o peso dos termos em comum sobre a média
    geométrica do peso de cada título. Termo raro no lote pesa mais."""
    common = set(a) & set(b)
    if not common:
        return 0.0
    wa, wb = sum(weight[t] for t in a), sum(weight[t] for t in b)
    return sum(weight[t] for t in common) / math.sqrt(wa * wb)


def group_stories(
    items: Iterable[dict],
    *,
    window: timedelta = WINDOW,
    threshold: float = THRESHOLD,
    min_shared: int = MIN_SHARED,
) -> list[Story]:
    """Agrupa itens do coletor por fato. Determinístico: a mesma entrada, em qualquer ordem,
    dá os mesmos fatos. Devolve os fatos em ordem de primeira publicação.

    Em ordem de publicação, cada item entra no fato que tem o item mais parecido com ele, se
    a semelhança passar de `threshold`, se os dois dividirem pelo menos `min_shared` termos e
    se o fato tiver item publicado até `window` antes; senão, abre um fato novo."""
    pool = sorted(items, key=lambda it: (_published(it), it["id"]))
    seqs = [terms(it["title"]) for it in pool]
    df = Counter(t for seq in seqs for t in seq)
    weight = {t: math.log((len(pool) + 1) / (d + 0.5)) for t, d in df.items()}
    drafts: list[_Draft] = []
    for i, it in enumerate(pool):
        at, key = _published(it), it.get("title_key") or title_key(it["title"])
        best, best_score = None, 0.0
        for d in drafts:
            if key in d.keys:  # mesmo título: mesmo fato, em qualquer dia
                best, best_score = d, math.inf
                break
            if at - d.last > window:
                continue
            for j in d.members:
                score = similarity(seqs[i], seqs[j], weight)
                if (score >= threshold and score > best_score
                        and shared_terms(seqs[i], seqs[j]) >= min_shared):
                    best, best_score = d, score
        if best is None:
            drafts.append(_Draft(i, at, key))
        else:
            best.add(i, at, key)
    stories = [_story(pool, seqs, weight, d) for d in drafts]
    return sorted(stories, key=lambda s: (s.first_seen, s.representative["id"]))


def _story(
    pool: Sequence[dict], seqs: Sequence[tuple[str, ...]], weight: dict[str, float], d: _Draft,
) -> Story:
    def rank(i: int) -> tuple:
        others = sum(similarity(seqs[i], seqs[j], weight) for j in d.members if j != i)
        tier = _TIER_ORDER.get(pool[i].get("tier", ""), len(_TIER_ORDER))
        return (-others, tier, _published(pool[i]), pool[i]["id"])

    order = sorted(d.members, key=rank)
    siblings = sorted(order[1:], key=lambda i: (_published(pool[i]), pool[i]["id"]))
    return Story(pool[order[0]], tuple(pool[i] for i in siblings))
