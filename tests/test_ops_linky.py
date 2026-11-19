"""Contrato do deploy do linky-agents na VPS (ops/linky).

Incidente de 17/11/2026: a rede `n8n_n8n-internal` é `internal: true` (sem saída para a
internet). Com o container só nela, toda chamada aos modelos falhou no DNS e a curadoria das
07:00 não saiu. O serviço precisa de duas redes: a do n8n (para ser chamado) e uma com saída
(para chamar os modelos e baixar as fontes).
"""

from pathlib import Path

import yaml

OPS = Path(__file__).resolve().parents[1] / "ops" / "linky"


def _compose() -> dict:
    return yaml.safe_load((OPS / "compose.yaml").read_text(encoding="utf-8"))


def _service(compose: dict) -> dict:
    return compose["services"]["linky-agents"]


def _networks(compose: dict) -> dict[str, dict]:
    """As redes do serviço, cada uma com a sua declaração no fim do compose."""
    return {n: compose["networks"][n] or {} for n in _service(compose)["networks"]}


def test_linky_agents_is_reachable_by_n8n():
    names = [spec.get("name", key) for key, spec in _networks(_compose()).items()]
    assert "n8n_n8n-internal" in names


def test_linky_agents_has_a_network_with_internet_egress():
    egress = [
        key
        for key, spec in _networks(_compose()).items()
        if not spec.get("external")
        and not spec.get("internal")
        and spec.get("driver_opts", {}).get("com.docker.network.bridge.enable_ip_masquerade")
        != "false"
    ]
    assert egress, "o linky-agents precisa de uma rede própria com saída (não internal)"


def test_linky_agents_accepts_no_connection_from_outside():
    # saída sim, entrada não: sem porta publicada, sem rota no Traefik, sem rede do host
    service = _service(_compose())
    assert "ports" not in service
    assert "network_mode" not in service
    assert not any("traefik" in str(label) for label in service.get("labels", []))


def test_deploy_and_shadow_check_egress_once_the_container_is_healthy():
    for script in ("deploy.sh", "shadow.sh"):
        text = (OPS / script).read_text(encoding="utf-8")
        call = next(
            (
                i
                for i, line in enumerate(text.splitlines())
                if "check-egress.sh" in line and not line.lstrip().startswith("#")
            ),
            None,
        )
        healthy = text.splitlines().index(
            next(line for line in text.splitlines() if '= "healthy"' in line)
        )
        assert call is not None and call > healthy, (
            f"{script} não confere a saída depois do healthy"
        )
    assert (OPS / "check-egress.sh").exists()
