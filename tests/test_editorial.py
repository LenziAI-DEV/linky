from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from linky_agents.editorial import (
    DEFAULT_POLICY,
    EditorialError,
    Entry,
    Post,
    Queue,
    State,
    load_policy,
)

BRT = ZoneInfo("America/Sao_Paulo")


def at(d: str, hm: str = "12:00") -> datetime:
    return datetime.fromisoformat(f"{d}T{hm}").replace(tzinfo=BRT)


def entry(eid: str, event: str = "2026-11-09", perishable=True, score=20) -> Entry:
    return Entry(
        id=eid, title=f"pauta {eid}", event_date=date.fromisoformat(event),
        perishable=perishable, score=score, batch="-", proposed_at=at(event),
    )


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "ed.db", load_policy())


def propose(q, batch, now, *entries):
    q.propose(batch, list(entries), now)


POST = Post(commentary="Legenda.", alt_text="Arte.", image="a.png")


def approved(q, eid, when=None):
    q.choose(eid, at("2026-11-09", "08:00"), when=when)
    q.drafted(eid, at("2026-11-09", "09:00"), POST)
    return q.approve(eid, at("2026-11-09", "10:00"))


def test_nada_e_aprovado_sem_post(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    q.choose("a", at("2026-11-09", "08:00"))
    q.drafted("a", at("2026-11-09", "09:00"))
    with pytest.raises(EditorialError, match="não tem post"):
        q.approve("a", at("2026-11-09", "10:00"))


# ------------------------------------------------------------------ calendário
def test_slots_are_mon_wed_fri_1830():
    # Política dos cenários (calendário v1, tests/conftest.py)
    gen = load_policy().slots_from(at("2026-11-06", "19:00"))  # sexta, depois do horário
    got = [next(gen).strftime("%a %d %H:%M") for _ in range(4)]
    assert got == ["Mon 09 18:30", "Wed 11 18:30", "Fri 13 18:30", "Mon 16 18:30"]


def test_calendario_em_vigor_e_seg_a_sex_1830():
    # config/editorial.yaml desde 16/11/2026 (playbook.md §10): 5 posts por semana, 1 por dia
    p = load_policy(DEFAULT_POLICY)
    gen = p.slots_from(at("2026-11-13", "19:00"))  # sexta, depois do horário
    got = [next(gen).strftime("%a %d %H:%M") for _ in range(6)]
    assert got == [
        "Mon 16 18:30", "Tue 17 18:30", "Wed 18 18:30", "Thu 19 18:30", "Fri 20 18:30",
        "Mon 23 18:30",
    ]
    assert p.slots.max_per_day == 1


def test_saturday_has_no_proposals_and_sunday_has_five_covering_three_days(q):
    assert q.proposal_plan(at("2026-11-07", "07:00")) is None
    plan = q.proposal_plan(at("2026-11-08", "21:00"))
    assert plan["cards"] == 5
    assert plan["coverage_start"].startswith("2026-11-06T00:00")


def test_weekday_proposal_covers_since_previous_run(q):
    tuesday = q.proposal_plan(at("2026-11-10", "07:00"))
    assert tuesday["cards"] == 3
    assert tuesday["coverage_start"].startswith("2026-11-09T07:00")
    monday = q.proposal_plan(at("2026-11-09", "07:00"))
    assert monday["coverage_start"].startswith("2026-11-08T21:00")  # desde o e-mail de domingo


# ------------------------------------------------------------------ escolha e agenda
def test_scenario_liked_every_day_queue_spreads_without_collision(q):
    propose(q, "seg", at("2026-11-09", "07:00"), entry("a", "2026-11-08"))
    assert q.choose("a", at("2026-11-09", "08:00")).slot == at("2026-11-09", "18:30")
    propose(q, "ter", at("2026-11-10", "07:00"), entry("b", "2026-11-09"))
    b = q.choose("b", at("2026-11-10", "08:00"), when=date(2026, 11, 11))
    assert b.slot == at("2026-11-11", "18:30")
    propose(q, "qua", at("2026-11-11", "07:00"),
            entry("c", "2026-11-10"), entry("d", "2026-11-10", perishable=False))
    assert q.choose("c", at("2026-11-11", "08:00")).slot == at("2026-11-13", "18:30")
    assert q.choose("d", at("2026-11-11", "08:05")).slot == at("2026-11-16", "18:30")


def test_two_choices_never_share_a_day(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"), entry("b"))
    q.choose("a", at("2026-11-09", "08:00"), when=date(2026, 11, 11))
    with pytest.raises(EditorialError, match="já tem post"):
        q.choose("b", at("2026-11-09", "08:00"), when=date(2026, 11, 11))


def test_non_slot_day_is_rejected(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    with pytest.raises(EditorialError, match="não é dia de publicação"):
        q.choose("a", at("2026-11-09", "08:00"), when=date(2026, 11, 10))


def test_perishable_cannot_be_scheduled_after_validity(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a", "2026-11-09"))
    with pytest.raises(EditorialError, match="vence"):
        q.choose("a", at("2026-11-09", "08:00"), when=date(2026, 11, 16))


def test_choose_late_in_the_day_skips_slot_without_time_to_approve(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    assert q.choose("a", at("2026-11-09", "15:00")).slot == at("2026-11-11", "18:30")


# ------------------------------------------------------------------ e-mail não visto
def test_unanswered_card_stays_in_inbox_until_it_expires(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a", "2026-11-08"))
    assert [e.id for e in q.inbox(at("2026-11-11", "07:00"))] == ["a"]
    events = q.tick(at("2026-11-13", "00:30"))  # 08/11 + 4 dias: válida até 12/11 23:59
    assert [(ev.kind, ev.entry_id) for ev in events] == [("expired", "a")]
    assert q.inbox(at("2026-11-13", "07:00")) == []


def test_late_choice_from_old_email_still_works_while_valid(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a", "2026-11-09"))
    assert q.choose("a", at("2026-11-11", "20:00")).slot == at("2026-11-13", "18:30")


def test_no_approval_by_deadline_postpones_never_publishes(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a", "2026-11-09"))
    q.choose("a", at("2026-11-09", "08:00"))
    q.drafted("a", at("2026-11-09", "09:00"))
    events = q.tick(at("2026-11-09", "16:30"))
    assert [ev.kind for ev in events] == ["postponed"]
    e = q.get("a")
    assert e.state == State.AWAITING_APPROVAL and e.slot == at("2026-11-11", "18:30")
    assert q.due(at("2026-11-09", "18:30")) == []


def test_no_approval_and_no_valid_slot_expires(q):
    propose(q, "b1", at("2026-11-13", "07:00"), entry("a", "2026-11-12"))  # vale até 16/11
    q.choose("a", at("2026-11-13", "08:00"))
    q.drafted("a", at("2026-11-13", "09:00"))
    q.tick(at("2026-11-13", "16:30"))
    assert q.get("a").slot == at("2026-11-16", "18:30")
    assert [ev.kind for ev in q.tick(at("2026-11-16", "16:30"))] == ["expired"]
    assert q.get("a").state == State.EXPIRED


def test_reminder_once_on_slot_day(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    q.choose("a", at("2026-11-09", "08:00"))
    q.drafted("a", at("2026-11-09", "09:00"))
    assert q.tick(at("2026-11-09", "11:00")) == []
    assert [ev.kind for ev in q.tick(at("2026-11-09", "12:00"))] == ["reminder"]
    assert q.tick(at("2026-11-09", "13:00")) == []


def test_empty_slot_pulls_forward_flexible_approved_post(q):
    propose(q, "b1", at("2026-11-09", "07:00"),
            entry("a", "2026-11-09"), entry("b", "2026-11-09", perishable=False))
    q.choose("a", at("2026-11-09", "08:00"))  # seg 09
    approved(q, "b")  # qua 11 (próximo livre)
    q.discard("a", at("2026-11-09", "11:00"))  # segunda ficou vazia
    assert [ev.kind for ev in q.tick(at("2026-11-09", "12:00"))] == ["pulled_forward"]
    assert q.get("b").slot == at("2026-11-09", "18:30")
    assert [e.id for e in q.due(at("2026-11-09", "18:30"))] == ["b"]


def test_fixed_date_post_is_never_pulled_forward(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("b", "2026-11-09", perishable=False))
    approved(q, "b", when=date(2026, 11, 13))
    assert q.tick(at("2026-11-09", "12:00")) == []
    assert q.get("b").slot == at("2026-11-13", "18:30")


def test_old_approval_is_rechecked_before_publishing(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a", "2026-11-09", perishable=False))
    approved(q, "a", when=date(2026, 11, 13))
    assert q.tick(at("2026-11-13", "10:00")) == []
    assert [ev.kind for ev in q.tick(at("2026-11-13", "12:30"))] == ["recheck"]


def test_silent_mode_after_three_unanswered_emails(q):
    for i, d in enumerate(["2026-11-09", "2026-11-10", "2026-11-11"]):
        propose(q, f"b{i}", at(d, "07:00"), entry(f"x{i}", d))
    assert q.proposal_plan(at("2026-11-12", "07:00")) is None  # quinta: silêncio
    assert q.proposal_plan(at("2026-11-15", "21:00"))["silent_mode"] is True  # domingo vai
    q.bank("x2", at("2026-11-12", "09:00"))  # qualquer resposta tira do silêncio
    assert q.proposal_plan(at("2026-11-13", "07:00")) is not None


def test_failed_publication_is_not_retried(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    approved(q, "a")
    q.failed("a", at("2026-11-09", "18:31"), "HTTP 401")
    assert q.due(at("2026-11-09", "19:00")) == []
    assert q.get("a").state == State.FAILED


def test_publish_records_urn(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    approved(q, "a")
    assert q.due(at("2026-11-09", "18:29")) == []
    q.published("a", at("2026-11-09", "18:31"), "urn:li:share:1")
    assert q.get("a").linkedin_urn == "urn:li:share:1"
    assert q.agenda(at("2026-11-09", "08:00"), 1)[0][1].state == State.PUBLISHED


# ------------------------------------------------------------------ repetição de chamadas
def test_repeated_batch_or_entry_never_resets_an_entry(q):
    now = at("2026-11-09", "07:00")
    propose(q, "b1", now, entry("a"))
    q.choose("a", at("2026-11-09", "08:00"))
    with pytest.raises(EditorialError, match="lote b1 já foi registrado"):
        propose(q, "b1", now, entry("x"))
    with pytest.raises(EditorialError, match="pauta a já está na fila"):
        propose(q, "b2", now, entry("b"), entry("a"))
    assert q.get("a").state == State.CHOSEN
    with pytest.raises(EditorialError):
        q.get("b")  # o lote inteiro foi recusado


def test_none_today_requires_a_known_batch(q):
    with pytest.raises(EditorialError, match="lote zz não existe"):
        q.none_today("zz", at("2026-11-09", "08:00"))


# ------------------------------------------------------------------ etapa D: decisões
def test_opiniao_em_uma_linha_acompanha_a_pauta_escolhida(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"), entry("b"))
    assert q.choose("a", at("2026-11-09", "08:00"), opinion="Isso muda o varejo.").opinion == (
        "Isso muda o varejo."
    )
    assert q.bank("b", at("2026-11-09", "08:00"), opinion="Guardar para sexta.").opinion == (
        "Guardar para sexta."
    )


def test_pedido_de_ajuste_volta_para_redacao_ate_tres_vezes(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    q.choose("a", at("2026-11-09", "08:00"))
    for n in range(1, 4):
        q.drafted("a", at("2026-11-09", "09:00"), POST)
        e = q.request_changes("a", at("2026-11-09", "09:30"), f"ajuste {n}")
        assert e.state == State.CHOSEN
        assert e.adjustments == [f"ajuste {k}" for k in range(1, n + 1)]
    q.drafted("a", at("2026-11-09", "10:00"), POST)
    with pytest.raises(EditorialError, match="3 ajustes"):
        q.request_changes("a", at("2026-11-09", "10:30"), "mais um")
    assert q.approve("a", at("2026-11-09", "11:00")).state == State.APPROVED


def test_cada_decisao_muda_a_versao_da_pauta(q):
    propose(q, "b1", at("2026-11-09", "07:00"), entry("a"))
    versions = [q.get("a").version]
    versions.append(q.choose("a", at("2026-11-09", "08:00")).version)
    versions.append(q.reschedule("a", at("2026-11-09", "08:10"), date(2026, 11, 11)).version)
    versions.append(q.drafted("a", at("2026-11-09", "09:00"), POST).version)
    versions.append(q.approve("a", at("2026-11-09", "10:00")).version)
    assert versions == sorted(set(versions))
