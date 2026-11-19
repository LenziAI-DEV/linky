"""Proteção contra SSRF (linky_agents.netguard): tudo offline, com resolvedor falso."""

import pytest

from linky_agents.netguard import BlockedURL, check_url

DNS = {
    "noticia.com.br": ["93.184.216.34"],
    "v6.noticia.com": ["2606:2800:220:1:248:1893:25c8:1946"],
    "rebind.example": ["93.184.216.34", "10.0.0.5"],
    "interno.example": ["172.18.0.3"],
    "mapeado.example": ["::ffff:127.0.0.1"],
    "cgnat.example": ["100.64.0.1"],
}


def fake(host, port):
    if host not in DNS:
        raise OSError("nome não resolve")
    return DNS[host]


@pytest.mark.parametrize("url", [
    "https://noticia.com.br/materia",
    "http://noticia.com.br:80/a?b=c",
    "https://NOTICIA.com.br./x",
    "https://v6.noticia.com/",
    "https://93.184.216.34/",
])
def test_public_urls_pass(url):
    check_url(url, resolve=fake)


@pytest.mark.parametrize("url, motivo", [
    ("file:///etc/passwd", "esquema"),
    ("gopher://noticia.com.br/", "esquema"),
    ("ftp://noticia.com.br/", "esquema"),
    ("https://noticia.com.br:5678/", "porta"),
    ("http://noticia.com.br:8080/", "porta"),
    ("https://user:pw@noticia.com.br/", "usuário"),
    ("http://n8n:5678/webhook/x", "porta"),
    ("http://n8n/rest", "host interno"),
    ("http://linky-agents/agenda", "host interno"),
    ("http://localhost/", "host interno"),
    ("http://painel.internal/", "host interno"),
    ("http://impressora.local/", "host interno"),
    ("http://127.0.0.1/", "não público"),
    ("http://10.1.2.3/", "não público"),
    ("http://192.168.0.1/", "não público"),
    ("http://169.254.169.254/latest/meta-data/", "não público"),
    ("http://0.0.0.0/", "não público"),
    ("http://[::1]/", "não público"),
    ("http://[fd00::1]/", "não público"),
    ("http://interno.example/", "não público"),
    ("http://rebind.example/", "não público"),
    ("http://mapeado.example/", "não público"),
    ("http://cgnat.example/", "não público"),
    ("http://nao-existe.example/", "não resolve"),
    ("https:///sem-host", "sem host"),
    ("http://noticia.com.br:99999/", "inválida"),
])
def test_internal_or_odd_urls_are_blocked(url, motivo):
    with pytest.raises(BlockedURL, match=motivo):
        check_url(url, resolve=fake)
