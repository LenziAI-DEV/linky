"""Registro de composições: a mesma composição não se repete num intervalo de 5 posts."""

from linky_agents.render.compose import Composition
from linky_agents.render.registry import CompositionRegistry


def comp(*names, background="paper"):
    el = {"kind": "rect", "x": 72, "y": 300, "w": 50, "h": 50, "fill": "ink"}
    return Composition.model_validate(
        {"background": background, "pieces": [{"name": n, "elements": [el]} for n in names]}
    )


STACKS = comp("manchete com destaque", "pilhas antes e hoje", "linha do tempo", "rodapé com fio")


def others(n):
    return [comp("manchete com destaque", f"peça {i}", "rodapé com fio") for i in range(n)]


def test_same_composition_within_five_posts_is_refused_with_reason(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("nubank", STACKS)
    for i, c in enumerate(others(3)):
        reg.record(f"post-{i}", c)
    [v] = reg.check("novo", STACKS)
    assert v.rule == "repetição"
    assert "nubank" in v.message and "4 posts" in v.message and "pilhas antes e hoje" in v.message


def test_same_composition_is_allowed_after_five_other_posts(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("nubank", STACKS)
    for i, c in enumerate(others(5)):
        reg.record(f"post-{i}", c)
    assert reg.check("novo", STACKS) == []


def test_same_pieces_in_another_order_or_case_are_the_same_composition(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("nubank", STACKS)
    shuffled = comp(
        "Rodapé com fio", "Linha do tempo", "MANCHETE com destaque", "pilhas antes e hoje"
    )
    assert [v.rule for v in reg.check("novo", shuffled)] == ["repetição"]


def test_new_version_of_the_same_post_does_not_block_itself(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("nubank", STACKS)
    reg.record("fable", others(1)[0])
    assert reg.check("nubank", STACKS) == []
    reg.record("nubank", comp("manchete com destaque", "funil"))  # ajuste trocou a imagem
    assert reg.check("outro", STACKS) == []
    assert [r.post for r in reg.recent()] == ["nubank", "fable"]  # mantém a ordem dos posts


def test_forgotten_post_no_longer_counts(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("descartado", STACKS)
    reg.forget("descartado")
    assert reg.check("novo", STACKS) == []


def test_registry_persists_across_instances(tmp_path):
    CompositionRegistry(tmp_path / "compositions.db").record("nubank", STACKS)
    assert CompositionRegistry(tmp_path / "compositions.db").check("novo", STACKS) != []


def test_background_is_part_of_the_composition(tmp_path):
    reg = CompositionRegistry(tmp_path / "compositions.db")
    reg.record("nubank", STACKS)
    dark = comp(*[p.name for p in STACKS.pieces], background="charcoal")
    assert reg.check("novo", dark) == []
