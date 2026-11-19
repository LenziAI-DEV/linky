"""Proteção contra SSRF para URLs que vêm de fora (links das notícias coletadas).

O serviço roda na rede interna do n8n: um link de notícia, ou um redirecionamento dele, não pode
alcançar o n8n, o próprio serviço, o Postgres, o metadata da nuvem nem nada fora da internet
pública. `check_url` recusa a URL antes de cada requisição (e de cada salto de redirecionamento):

- esquema diferente de http/https, porta fora de 80/443, usuário e senha na URL;
- host sem ponto (nome de serviço Docker, como `n8n` ou `linky-agents`), `localhost`, `.local`,
  `.internal`, `.localhost`;
- host que resolve para qualquer endereço não global: privado, loopback, link-local (inclui o
  metadata 169.254.169.254), CGNAT, reservado, multicast ou não especificado. Basta um endereço
  ruim para recusar.

Risco residual conhecido: o httpx resolve o nome de novo ao conectar (DNS rebinding entre a
checagem e a conexão). Para isso o atacante precisa controlar o DNS de um link que a curadoria
escolheu; o texto só chega à redação, e nada sai sem a aprovação de Felipe.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

Resolver = Callable[[str, int], Iterable[str]]

ALLOWED_SCHEMES = {"http": 80, "https": 443}
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home.arpa")


class BlockedURL(ValueError):
    """URL recusada pela proteção contra SSRF."""


def resolve_host(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]).split("%", 1)[0] for info in infos]


def _is_public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url: str, *, resolve: Resolver | None = None) -> None:
    """Levanta `BlockedURL` se a URL puder alcançar algo fora da internet pública."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise BlockedURL(f"URL inválida: {e}") from None
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise BlockedURL(f"esquema não permitido: {scheme or '(vazio)'}")
    if parts.username or parts.password:
        raise BlockedURL("URL com usuário ou senha")
    if port is not None and port not in ALLOWED_SCHEMES.values():
        raise BlockedURL(f"porta não permitida: {port}")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedURL("URL sem host")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addrs: Iterable[str] = [host]
    else:
        if "." not in host or host == "localhost" or host.endswith(BLOCKED_SUFFIXES):
            raise BlockedURL(f"host interno: {host}")
        try:
            addrs = list((resolve or resolve_host)(host, port or ALLOWED_SCHEMES[scheme]))
        except OSError as e:
            raise BlockedURL(f"host não resolve: {host} ({e})") from None
        if not addrs:
            raise BlockedURL(f"host não resolve: {host}")
    for addr in addrs:
        if not _is_public(addr):
            raise BlockedURL(f"host {host} aponta para endereço não público: {addr}")
