"""Normalização determinística de itens: URL canônica, chave de título e texto limpo."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_", "mc_", "fbclid", "gclid", "ref", "source", "cmpid", "ocid")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]")


def canonical_url(url: str) -> str:
    """Remove parâmetros de rastreamento, fragmento e barra final; host em minúsculas."""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    return urlunsplit((scheme, parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def item_id(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()[:16]


def title_key(title: str) -> str:
    """Chave para detectar a mesma notícia com URLs diferentes."""
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = _NON_WORD_RE.sub(" ", text.lower())
    return _SPACE_RE.sub(" ", text).strip()


def clean_text(raw: str | None, limit: int = 600) -> str:
    """Remove HTML e entidades e corta no limite, sem quebrar palavra."""
    if not raw:
        return ""
    text = _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"
