"""Escape do formato *little* do LinkedIn, usado no campo `commentary` de `/rest/posts`.

No *little*, `| { } @ [ ] ( ) < > # \\ * _ ~` são reservados (menções, links, ênfase).
Sem escape, o LinkedIn corta ou deforma o texto. Exceções deliberadas: `#` seguido de letra
fica como está, porque é hashtag e o T3 mostrou que ela sai clicável sem escape; e a menção
aprovada `@[Nome](urn:li:organization:ID)` (ou `urn:li:person:ID`) passa inteira, porque é
assim que o LinkedIn marca a empresa (posts do T2 de 12 e 13/11).

O texto aprovado por Felipe é guardado sem escape; o escape acontece só na hora de
publicar (`GET /due`). Assim o que ele lê no e-mail é exatamente o que escreveu.
"""

from __future__ import annotations

import re

_RESERVED = re.compile(r"[\\|{}@\[\]()<>*_~]|#(?![^\W\d_])")


_MENTION = re.compile(r"@\[[^\[\]\n]+\]\(urn:li:(?:organization|person):[\w-]+\)")


def _escape(text: str) -> str:
    return _RESERVED.sub(lambda m: "\\" + m.group(0), text)


def escape_little(text: str) -> str:
    out, last = [], 0
    for m in _MENTION.finditer(text):
        out.append(_escape(text[last : m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_escape(text[last:]))
    return "".join(out)
