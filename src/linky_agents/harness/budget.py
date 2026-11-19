"""Orçamento de tokens antes da chamada.

Sem tokenizador (dependência pesada e diferente por fornecedor): a estimativa usa ~3
caracteres por token, conservadora para português. Errar para mais só corta contexto cedo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .prompt import WebDocument

CHARS_PER_TOKEN = 3


def estimate_tokens(*texts: str) -> int:
    return sum(-(-len(t) // CHARS_PER_TOKEN) for t in texts)


@dataclass
class Trim:
    documents: list[WebDocument]
    estimated_input_tokens: int = 0
    documents_truncated: list[str] = field(default_factory=list)
    documents_dropped: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "estimated_input_tokens": self.estimated_input_tokens,
            "documents_truncated": self.documents_truncated,
            "documents_dropped": self.documents_dropped,
        }


class InputTooLarge(ValueError):
    pass


def fit(
    documents: list[WebDocument],
    max_doc_tokens: int,
    max_input_tokens: int,
    render,
) -> Trim:
    """Corta cada documento em `max_doc_tokens` e descarta documentos do fim até caber.

    `render(docs) -> str` monta o texto completo da entrada (parte fixa + variável).
    """
    limit = max_doc_tokens * CHARS_PER_TOKEN
    trim = Trim(documents=[])
    for d in documents:
        if len(d.text) > limit:
            trim.documents_truncated.append(d.id)
            d = d.model_copy(update={"text": d.text[:limit] + " [...]"})
        trim.documents.append(d)
    while True:
        trim.estimated_input_tokens = estimate_tokens(render(trim.documents))
        if trim.estimated_input_tokens <= max_input_tokens:
            return trim
        if not trim.documents:
            raise InputTooLarge(
                f"a entrada sem documentos já tem ~{trim.estimated_input_tokens} tokens, "
                f"acima do limite do agente ({max_input_tokens})"
            )
        trim.documents_dropped.insert(0, trim.documents.pop().id)
