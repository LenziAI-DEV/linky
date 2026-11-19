"""Configuração comum dos testes."""

from pathlib import Path

import pytest

from linky_agents import editorial

# Os cenários da fila (test_editorial, test_service, test_forms) foram escritos com as datas do
# calendário v1 (seg, qua e sex, 18:30). Eles testam a mecânica da fila, não o calendário, então
# usam essa política congelada. O calendário em vigor (config/editorial.yaml) tem teste próprio.
V1_POLICY = Path(__file__).parent / "fixtures" / "editorial-seg-qua-sex.yaml"


@pytest.fixture(autouse=True)
def _politica_dos_cenarios(monkeypatch):
    monkeypatch.setattr(editorial.load_policy, "__defaults__", (V1_POLICY,))
