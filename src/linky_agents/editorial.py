"""Fila editorial: separa "gostei desta pauta" de "quando ela sai".

Cada pauta vira uma `Entry` que percorre estados bem definidos:

    PROPOSED ──choose──> CHOSEN ──drafted──> AWAITING_APPROVAL ──approve──> APPROVED ─┐
       │  └──bank──> BANKED ──choose──┘                                              │
       │                       PUBLISHED <──published── PUBLISHING <──publishing─────┘
       │                       FAILED    <──failed────────┘
       └─────────────(validade estourou)──────────> EXPIRED          discard ──> DISCARDED

`drafted` grava o post (legenda, texto alternativo, imagem); sem post não há aprovação.
`request_changes` (pedir ajuste, até 3 vezes) devolve AWAITING_APPROVAL para CHOSEN, com o
horário ainda reservado; o próximo `drafted` traz a nova versão do post. Toda mudança sobe a
`version` da pauta, à qual o token de uso único dos formulários é atrelado (ADR 0005).

Regras (config/editorial.yaml):
- publicação só em horários fixos (seg a sex, 18:30), no máximo 1 por dia;
- a pauta reserva o horário quando é escolhida, então duas escolhas nunca disputam o mesmo dia;
- cada pauta tem validade (perecível ou duradoura) contada da data do fato;
- nada é publicado sem aprovação: post não aprovado até o prazo é adiado para o próximo
  horário livre (se ainda válido) ou vence;
- horário vazio puxa para a frente um post já aprovado com "próximo horário livre";
- post aprovado que perdeu o horário (sombra, n8n fora do ar) nunca passa à frente do post de
  outro dia: o flexível vai para o próximo horário livre dentro da validade; o de data escolhida
  por Felipe volta para aprovação; sem horário válido, vence (ADR 0004, etapa H);
- sem resposta a vários e-mails seguidos, o sistema entra em modo silencioso (só domingo).

O n8n só agenda e entrega e-mails; quem decide é este módulo, que é testável.
Uso: python -m linky_agents.editorial {agenda,tick,inbox} --db data/editorial.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .little import escape_little

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config" / "editorial.yaml"
_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
# Pautas registradas até 30 min antes do horário de um envio contam como novas nele
RUN_LEAD = timedelta(minutes=30)
# Tempo mínimo entre escolher a pauta e o prazo de aprovação (produção + leitura de Felipe)
PRODUCTION_LEAD = timedelta(hours=2)
LINKEDIN_MAX_COMMENTARY = 3000
MAX_ADJUSTMENTS = 3  # rodadas de "pedir ajuste" na decisão 2 (PRD §7.1)
# Registros que não mudam nada que Felipe decide: não mudam a versão da pauta, então um
# formulário aberto não fica velho por causa de um lembrete
_NOT_A_CHANGE = {"reminder", "recheck"}


class EditorialError(ValueError):
    """Operação inválida na fila (estado errado, data sem horário, pauta vencida...)."""


class NotFoundError(EditorialError):
    """Pauta ou lote que não existe na fila."""


# --------------------------------------------------------------------------- política
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _weekdays(v: list[str]) -> list[str]:
    bad = [d for d in v if d not in _DAYS]
    if bad:
        raise ValueError(f"dias inválidos: {bad}")
    return v


class SlotPolicy(_Strict):
    weekdays: list[str]
    time: time
    max_per_day: Literal[1] = 1  # um horário por dia; mais que isso exigiria outra modelagem

    _v = field_validator("weekdays")(_weekdays)


class ProposalRun(_Strict):
    weekdays: list[str]
    time: time
    cards: int = Field(ge=1, le=5)
    coverage_days: int | None = Field(default=None, ge=1)

    _v = field_validator("weekdays")(_weekdays)


class Validity(_Strict):
    perishable_days: int = Field(ge=1)
    durable_days: int = Field(ge=1)


def _hhmm(v: object) -> timedelta:
    if isinstance(v, timedelta):
        return v
    h, m = str(v).split(":")
    return timedelta(hours=int(h), minutes=int(m))


class Approval(_Strict):
    deadline_before_slot: timedelta
    reminder_at: time
    recheck_after_hours: int = Field(ge=1)

    _v = field_validator("deadline_before_slot", mode="before")(_hhmm)


class Silence(_Strict):
    unanswered_batches: int = Field(ge=1)
    carry_over_cards: int = Field(ge=0)


class Policy(_Strict):
    timezone: str
    slots: SlotPolicy
    proposals: list[ProposalRun]
    validity: Validity
    approval: Approval
    silence: Silence

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    # ---- calendário de publicação
    def is_slot_day(self, d: date) -> bool:
        return d.weekday() in {_DAYS[x] for x in self.slots.weekdays}

    def slot_on(self, d: date) -> datetime:
        if not self.is_slot_day(d):
            raise EditorialError(f"{d:%d/%m} ({_dname(d)}) não é dia de publicação")
        return datetime.combine(d, self.slots.time, tzinfo=self.tz)

    def slots_from(self, start: datetime) -> Iterator[datetime]:
        """Horários de publicação estritamente depois de `start`, em ordem."""
        d = start.astimezone(self.tz).date()
        while True:
            if self.is_slot_day(d):
                s = self.slot_on(d)
                if s > start:
                    yield s
            d += timedelta(days=1)

    def deadline(self, slot: datetime) -> datetime:
        return slot - self.approval.deadline_before_slot

    # ---- calendário de pautas
    def proposal_run(self, d: date) -> ProposalRun | None:
        for run in self.proposals:
            if d.weekday() in {_DAYS[x] for x in run.weekdays}:
                return run
        return None

    def previous_run_at(self, at: datetime) -> datetime:
        """Momento do envio de pautas anterior a `at` (início da janela de cobertura)."""
        d = at.astimezone(self.tz).date()
        for back in range(0, 8):
            day = d - timedelta(days=back)
            run = self.proposal_run(day)
            if run:
                t = datetime.combine(day, run.time, tzinfo=self.tz)
                if t < at:
                    return t
        raise EditorialError("nenhum envio de pautas configurado na última semana")


def load_policy(path: Path = DEFAULT_POLICY) -> Policy:
    return Policy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _dname(d: date) -> str:
    return ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][d.weekday()]


# --------------------------------------------------------------------------- entradas
class State(StrEnum):
    PROPOSED = "proposed"
    BANKED = "banked"
    CHOSEN = "chosen"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    EXPIRED = "expired"
    DISCARDED = "discarded"


class Post(BaseModel):
    """O post como Felipe aprova: legenda e texto alternativo sem escape, e o nome do
    arquivo da imagem (só o nome: o n8n lê de uma pasta fixa)."""

    model_config = ConfigDict(extra="forbid")

    commentary: str = Field(min_length=1)
    alt_text: str = Field(min_length=1, max_length=4086)
    image: str = Field(pattern=r"^[\w-][\w.-]*\.(png|jpe?g)$")
    # Variantes do redator (playbook.md §3 e §4): Felipe escolhe o hook e a leitura no
    # formulário de aprovação, e `commentary` é recomposto antes de aprovar. Vazias nos posts
    # feitos à mão (T2): aí `commentary` é o texto inteiro.
    hooks: list[str] = Field(default_factory=list)
    readings: list[str] = Field(default_factory=list)
    reading_is_felipe: bool = False
    body: str = ""
    tail: str = ""
    notes: list[str] = Field(default_factory=list)  # avisos da checagem de fatos

    @field_validator("commentary")
    @classmethod
    def _cabe_no_linkedin(cls, v: str) -> str:
        # O limite do LinkedIn vale para o texto enviado, que leva as barras do escape
        n = len(escape_little(v))
        if n > LINKEDIN_MAX_COMMENTARY:
            raise ValueError(
                f"a legenda tem {n} caracteres depois do escape; o LinkedIn aceita "
                f"{LINKEDIN_MAX_COMMENTARY}"
            )
        return v


OCCUPYING = {
    State.CHOSEN, State.AWAITING_APPROVAL, State.APPROVED, State.PUBLISHING, State.PUBLISHED,
}
SlotMode = Literal["fixed", "next_free"]


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    event_date: date
    perishable: bool = True
    score: int = 0
    sources: list[str] = Field(default_factory=list)
    # O card como Felipe lê no e-mail de pautas (vazio nas pautas anteriores à etapa D)
    what: str = ""
    why: str = ""
    angle: str = ""
    # Padrão de pauta (P1 a P6 ou um padrão em teste) e público do post (playbook.md §2)
    pattern: str = ""
    audience: str = ""
    batch: str
    proposed_at: datetime
    state: State = State.PROPOSED
    slot: datetime | None = None
    slot_mode: SlotMode | None = None
    approved_at: datetime | None = None
    post: Post | None = None
    postponed: int = 0
    reminded_for: datetime | None = None
    rechecked_for: datetime | None = None
    linkedin_urn: str | None = None
    error: str | None = None
    opinion: str | None = None  # a linha de Felipe na decisão 1
    adjustments: list[str] = Field(default_factory=list)  # pedidos de ajuste da decisão 2
    # Sobe a cada mudança que Felipe decide ou vê; o token de formulário é atrelado a ela
    version: int = 0

    def valid_until(self, p: Policy) -> datetime:
        days = p.validity.perishable_days if self.perishable else p.validity.durable_days
        last = self.event_date + timedelta(days=days)
        return datetime.combine(last, time(23, 59), tzinfo=p.tz)


class Event(BaseModel):
    """Algo que o n8n precisa comunicar ou executar (e-mail, lembrete, revalidação)."""

    kind: Literal[
        "expired", "postponed", "reminder", "pulled_forward", "recheck",
        "missed_rescheduled", "missed_reapproval",
    ]
    entry_id: str | None = None
    detail: str


# --------------------------------------------------------------------------- fila
class Queue:
    """Fila editorial persistida em SQLite (um arquivo, sem servidor)."""

    def __init__(self, db: Path | str, policy: Policy | None = None):
        self.p = policy or load_policy()
        self.con = sqlite3.connect(str(db))
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, state TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, sent_at TEXT, answered INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS log (at TEXT, entry_id TEXT, kind TEXT, detail TEXT);
            """
        )

    # ---- persistência
    @contextmanager
    def _tx(self) -> Iterator[None]:
        with self.con:
            yield

    def get(self, entry_id: str) -> Entry:
        row = self.con.execute("SELECT data FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise NotFoundError(f"pauta {entry_id} não existe")
        return Entry.model_validate_json(row[0])

    def all(self, *states: State) -> list[Entry]:
        rows = self.con.execute("SELECT data FROM entries").fetchall()
        items = [Entry.model_validate_json(r[0]) for r in rows]
        return [e for e in items if not states or e.state in states]

    def _save(self, e: Entry, now: datetime, kind: str, detail: str = "") -> None:
        if kind not in _NOT_A_CHANGE:
            e.version += 1
        self.con.execute(
            "INSERT INTO entries(id, state, data) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET state=excluded.state, data=excluded.data",
            (e.id, e.state.value, e.model_dump_json()),
        )
        self.con.execute(
            "INSERT INTO log VALUES(?,?,?,?)", (now.isoformat(), e.id, kind, detail)
        )

    # ---- ocupação dos horários
    def _occupied(self, exclude: str | None = None) -> set[date]:
        tz = self.p.tz
        return {
            e.slot.astimezone(tz).date()
            for e in self.all(*OCCUPYING)
            if e.slot and e.id != exclude
        }

    def next_free_slot(
        self, after: datetime, until: datetime | None = None, exclude: str | None = None,
        approved: bool = False,
    ) -> datetime | None:
        """Primeiro horário livre cujo prazo de aprovação ainda dá tempo de cumprir (para um
        post já aprovado, `approved=True`, basta o horário ainda não ter passado)."""
        busy = self._occupied(exclude)
        for s in self.p.slots_from(after):
            if until and s > until:
                return None
            if s.astimezone(self.p.tz).date() not in busy and (
                approved or self.p.deadline(s) > after
            ):
                return s
        return None  # pragma: no cover (gerador infinito)

    def free_slots(self, e: Entry, now: datetime, n: int = 6) -> list[datetime]:
        """Horários que a pauta ainda pode pegar: livres (ou já dela), com prazo de
        aprovação no futuro e antes de ela vencer. São as datas oferecidas nos formulários."""
        valid, busy, out = e.valid_until(self.p), self._occupied(exclude=e.id), []
        for s in self.p.slots_from(now):
            if s > valid or len(out) == n:
                break
            if s.astimezone(self.p.tz).date() not in busy and self.p.deadline(s) > now:
                out.append(s)
        return out

    def _resolve_slot(self, e: Entry, now: datetime, when: date | None) -> datetime:
        valid = e.valid_until(self.p)
        if when is None:
            slot = self.next_free_slot(now + PRODUCTION_LEAD, until=valid, exclude=e.id)
            if slot is None:
                raise EditorialError(
                    f"nenhum horário livre antes de a pauta vencer ({valid:%d/%m})"
                )
            return slot
        slot = self.p.slot_on(when)
        if slot > valid:
            raise EditorialError(f"a pauta vence em {valid:%d/%m}, antes de {when:%d/%m}")
        if self.p.deadline(slot) <= now:
            raise EditorialError(f"o prazo de aprovação de {when:%d/%m} já passou")
        if when in self._occupied(exclude=e.id):
            raise EditorialError(f"{when:%d/%m} ({_dname(when)}) já tem post")
        return slot

    # ---- decisão 1
    def has_batch(self, batch: str) -> bool:
        return self.con.execute("SELECT 1 FROM batches WHERE id=?", (batch,)).fetchone() is not None

    def propose(self, batch: str, entries: list[Entry], now: datetime) -> None:
        """Registra um lote de pautas. Lote ou pauta repetidos são recusados por inteiro:
        uma chamada repetida pelo n8n nunca devolve uma pauta já escolhida ao início."""
        if self.con.execute("SELECT 1 FROM batches WHERE id=?", (batch,)).fetchone():
            raise EditorialError(f"lote {batch} já foi registrado")
        ids = [e.id for e in entries]
        if len(set(ids)) != len(ids):
            raise EditorialError(f"lote {batch} tem pautas repetidas")
        for eid in ids:
            if self.con.execute("SELECT 1 FROM entries WHERE id=?", (eid,)).fetchone():
                raise EditorialError(f"pauta {eid} já está na fila")
        with self._tx():
            self.con.execute(
                "INSERT INTO batches(id, sent_at) VALUES(?,?)", (batch, now.isoformat())
            )
            for e in entries:
                e.batch, e.proposed_at, e.state = batch, now, State.PROPOSED
                self._save(e, now, "proposed")

    def _answered(self, batch: str) -> None:
        """Qualquer resposta conta para o lote da pauta e para o lote mais recente: responder
        a uma pauta da repescagem também tira do modo silencioso (PRD §7.6)."""
        self.con.execute(
            "UPDATE batches SET answered=1 WHERE id=? OR id=(SELECT id FROM batches "
            "ORDER BY sent_at DESC LIMIT 1)", (batch,),
        )

    def choose(
        self, entry_id: str, now: datetime, when: date | None = None,
        opinion: str | None = None,
    ) -> Entry:
        e = self._require(entry_id, State.PROPOSED, State.BANKED)
        self._require_valid(e, now)
        with self._tx():
            e.opinion = opinion or e.opinion
            e.slot = self._resolve_slot(e, now, when)
            e.slot_mode = "fixed" if when else "next_free"
            e.state = State.CHOSEN
            self._answered(e.batch)
            self._save(e, now, "chosen", f"{e.slot:%d/%m %H:%M}")
        return e

    def bank(self, entry_id: str, now: datetime, opinion: str | None = None) -> Entry:
        e = self._require(entry_id, State.PROPOSED)
        self._require_valid(e, now)
        with self._tx():
            e.opinion = opinion or e.opinion
            e.state = State.BANKED
            self._answered(e.batch)
            self._save(e, now, "banked")
        return e

    def discard(self, entry_id: str, now: datetime) -> Entry:
        e = self._require(
            entry_id, State.PROPOSED, State.BANKED, State.CHOSEN, State.AWAITING_APPROVAL,
            State.APPROVED,
        )
        with self._tx():
            e.state, e.slot = State.DISCARDED, None
            self._answered(e.batch)
            self._save(e, now, "discarded")
        return e

    def none_today(self, batch: str, now: datetime) -> None:
        """'Nenhuma hoje' também é resposta: conta como interação."""
        if not self.con.execute("SELECT 1 FROM batches WHERE id=?", (batch,)).fetchone():
            raise NotFoundError(f"lote {batch} não existe")
        with self._tx():
            self._answered(batch)

    def release(self, entry_id: str, now: datetime) -> Entry:
        """A redação falhou de vez: a pauta escolhida volta ao banco e libera o horário (Felipe
        pode escolhê-la de novo na repescagem do e-mail de pautas)."""
        e = self._require(entry_id, State.CHOSEN)
        with self._tx():
            e.state, e.slot = State.BANKED, None
            self._save(e, now, "released")
        return e

    # ---- decisão 2
    def drafted(self, entry_id: str, now: datetime, post: Post | None = None) -> Entry:
        e = self._require(entry_id, State.CHOSEN)
        with self._tx():
            e.state, e.post = State.AWAITING_APPROVAL, post
            self._save(e, now, "drafted")
        return e

    def request_changes(self, entry_id: str, now: datetime, note: str) -> Entry:
        """Pedir ajuste: o post volta para a redação (escolhida, com o horário reservado).
        Até `MAX_ADJUSTMENTS` rodadas; depois, só aprovar ou descartar."""
        e = self._require(entry_id, State.AWAITING_APPROVAL)
        if len(e.adjustments) >= MAX_ADJUSTMENTS:
            raise EditorialError(
                f"pauta {entry_id} já teve {MAX_ADJUSTMENTS} ajustes: aprove ou descarte"
            )
        with self._tx():
            e.state = State.CHOSEN
            e.adjustments = [*e.adjustments, note]
            self._save(e, now, "changes_requested", note[:200])
        return e

    def approve(self, entry_id: str, now: datetime, when: date | None = None,
                commentary: str | None = None) -> Entry:
        """Aprova o post. `commentary` é a legenda com o hook e a leitura que Felipe marcou no
        formulário: ela só é gravada junto com a aprovação (se a aprovação falha, nada muda)."""
        e = self._require(entry_id, State.AWAITING_APPROVAL)
        self._require_valid(e, now)
        if e.post is None:
            raise EditorialError(f"pauta {entry_id} não tem post para aprovar")
        post = e.post
        if commentary is not None and commentary != post.commentary:
            post = post.model_copy(update={"commentary": commentary})
            Post.model_validate(post.model_dump())  # o mesmo limite do LinkedIn
        with self._tx():
            if when is not None:
                e.slot, e.slot_mode = self._resolve_slot(e, now, when), "fixed"
            elif e.slot is None or self.p.deadline(e.slot) <= now:
                e.slot = self._resolve_slot(e, now, None)
            e.post = post
            e.state, e.approved_at = State.APPROVED, now
            self._save(e, now, "approved", f"{e.slot:%d/%m %H:%M}")
        return e

    def reschedule(self, entry_id: str, now: datetime, when: date | None) -> Entry:
        e = self._require(entry_id, State.CHOSEN, State.AWAITING_APPROVAL, State.APPROVED)
        with self._tx():
            e.slot = self._resolve_slot(e, now, when)
            e.slot_mode = "fixed" if when else "next_free"
            self._save(e, now, "rescheduled", f"{e.slot:%d/%m %H:%M}")
        return e

    # ---- publicação
    def due(self, now: datetime) -> list[Entry]:
        """Posts aprovados cujo horário chegou hoje (até o fim do dia, para uma execução
        atrasada do n8n). O de um dia anterior perdeu o horário e é tratado pelo `tick`:
        nunca sai no horário de outro post (ADR 0004, etapa H)."""
        today = now.astimezone(self.p.tz).date()
        due = [e for e in self.all(State.APPROVED)
               if e.slot and e.slot <= now and e.slot.astimezone(self.p.tz).date() == today]
        return sorted(due, key=lambda e: e.slot)

    def publishing(self, entry_id: str, now: datetime) -> Entry:
        """Marca o post como em publicação antes de chamar o LinkedIn: ele sai do `due`, e uma
        execução repetida ou concorrente do n8n não publica duas vezes."""
        e = self._require(entry_id, State.APPROVED)
        with self._tx():
            e.state = State.PUBLISHING
            self._save(e, now, "publishing")
        return e

    def stuck_publishing(self, now: datetime, after: timedelta) -> list[tuple[Entry, datetime]]:
        """Posts em publicação há mais de `after` (o n8n não confirmou o resultado), com o
        momento em que foram marcados. Nunca voltam sozinhos para a fila: alguém confere."""
        out = []
        for e in self.all(State.PUBLISHING):
            row = self.con.execute(
                "SELECT max(at) FROM log WHERE entry_id=? AND kind='publishing'", (e.id,)
            ).fetchone()
            since = datetime.fromisoformat(row[0]) if row and row[0] else None
            if since and now - since >= after:
                out.append((e, since))
        return out

    def published(self, entry_id: str, now: datetime, urn: str) -> Entry:
        e = self._require(entry_id, State.APPROVED, State.PUBLISHING)
        with self._tx():
            e.state, e.linkedin_urn = State.PUBLISHED, urn
            self._save(e, now, "published", urn)
        return e

    def failed(self, entry_id: str, now: datetime, error: str) -> Entry:
        """Falha não reenvia sozinha (evita post duplicado): Felipe decide o que fazer."""
        e = self._require(entry_id, State.APPROVED, State.PUBLISHING)
        with self._tx():
            e.state, e.error = State.FAILED, error[:500]
            self._save(e, now, "failed", error[:200])
        return e

    # ---- relógio: roda de hora em hora (n8n) e devolve o que precisa ser comunicado
    def tick(self, now: datetime) -> list[Event]:
        events: list[Event] = []
        tz = self.p.tz
        with self._tx():
            # 1. pautas não usadas que venceram
            for e in self.all(State.PROPOSED, State.BANKED):
                if now > e.valid_until(self.p):
                    e.state = State.EXPIRED
                    self._save(e, now, "expired")
                    events.append(Event(kind="expired", entry_id=e.id, detail=e.title))
            # 1b. post aprovado cujo dia de publicação passou sem que ele saísse. Antes do
            # adiamento: quem já foi aprovado tem preferência nos horários livres, e quem vence
            # primeiro escolhe primeiro
            today = now.astimezone(tz).date()
            missed = [e for e in self.all(State.APPROVED)
                      if e.slot and e.slot.astimezone(tz).date() < today]
            for e in sorted(missed, key=lambda e: (e.valid_until(self.p), e.id)):
                events.append(self._missed(e, now))
            # 2. sem aprovação no prazo: adia (se ainda válida) ou vence. Nunca publica.
            for e in self.all(State.CHOSEN, State.AWAITING_APPROVAL):
                if e.slot and now >= self.p.deadline(e.slot):
                    old = e.slot
                    nxt = self.next_free_slot(now, until=e.valid_until(self.p), exclude=e.id)
                    if nxt:
                        e.slot, e.postponed = nxt, e.postponed + 1
                        e.slot_mode = "next_free"
                        self._save(e, now, "postponed", f"{old:%d/%m} -> {nxt:%d/%m}")
                        events.append(Event(
                            kind="postponed", entry_id=e.id,
                            detail=f"{e.title}: sem aprovação para {old:%d/%m}, "
                                   f"remarcado para {nxt:%d/%m}",
                        ))
                    else:
                        e.state, e.slot = State.EXPIRED, None
                        self._save(e, now, "expired", "sem aprovação e sem horário válido")
                        events.append(Event(kind="expired", entry_id=e.id, detail=e.title))
            # 3. lembrete no dia do horário
            for e in self.all(State.CHOSEN, State.AWAITING_APPROVAL):
                if not e.slot or e.reminded_for == e.slot:
                    continue
                local = now.astimezone(tz)
                if local.date() == e.slot.astimezone(tz).date() and (
                    local.time() >= self.p.approval.reminder_at
                ):
                    e.reminded_for = e.slot
                    self._save(e, now, "reminder")
                    events.append(Event(
                        kind="reminder", entry_id=e.id,
                        detail=f"{e.title}: aprovar até {self.p.deadline(e.slot):%H:%M}",
                    ))
            # 4. horário vazio puxa um post aprovado e flexível que estava mais adiante
            events += self._pull_forward(now)
            # 5. revalidação de post aprovado há muito tempo, perto de sair
            hours = timedelta(hours=self.p.approval.recheck_after_hours)
            for e in self.all(State.APPROVED):
                if (
                    e.slot and e.approved_at and e.rechecked_for != e.slot
                    and e.slot - e.approved_at > hours
                    and now >= self.p.deadline(e.slot) - timedelta(hours=4)
                ):
                    e.rechecked_for = e.slot
                    self._save(e, now, "recheck")
                    events.append(Event(kind="recheck", entry_id=e.id, detail=e.title))
        return events

    def _missed(self, e: Entry, now: datetime) -> Event:
        """Horário perdido: nada foi publicado e o dia passou. Nunca toma o horário de outro
        post; data escolhida por Felipe nunca é movida sem ele aprovar de novo."""
        assert e.slot is not None  # o tick só passa post com horário
        day = e.slot.astimezone(self.p.tz).date()
        lost = f"perdeu o horário de {_dname(day)} {day:%d/%m}"
        fixed = e.slot_mode == "fixed"
        nxt = self.next_free_slot(now, until=e.valid_until(self.p), exclude=e.id,
                                  approved=not fixed)
        if nxt is None:
            e.state, e.slot = State.EXPIRED, None
            self._save(e, now, "expired", lost)
            return Event(kind="expired", entry_id=e.id,
                         detail=f"{e.title}: {lost} e não há horário livre antes de vencer")
        e.slot = nxt
        if fixed:
            # Continua "data escolhida": aprovar o horário sugerido é aceitar uma nova data
            # fixa; só vira flexível se Felipe pedir o próximo horário livre
            e.state, e.approved_at = State.AWAITING_APPROVAL, None
            self._save(e, now, "missed_reapproval", f"-> {nxt:%d/%m}")
            return Event(kind="missed_reapproval", entry_id=e.id,
                         detail=f"{e.title}: {lost}; horário sugerido: {self._when(nxt)}")
        self._save(e, now, "missed_rescheduled", f"-> {nxt:%d/%m}")
        return Event(kind="missed_rescheduled", entry_id=e.id,
                     detail=f"{e.title}: {lost}; continua aprovado e sai em {self._when(nxt)}")

    def _when(self, dt: datetime) -> str:
        """'seg 09/11 18:30' no fuso da política."""
        local = dt.astimezone(self.p.tz)
        return f"{_dname(local.date())} {local:%d/%m %H:%M}"

    def awaiting_since(self, entry_id: str) -> datetime | None:
        """Quando a pauta passou a aguardar aprovação pela última vez (post novo ou horário
        perdido com data escolhida): um e-mail de aprovação anterior a isso já não vale."""
        row = self.con.execute(
            "SELECT max(at) FROM log WHERE entry_id=? AND kind IN "
            "('drafted', 'missed_reapproval')", (entry_id,),
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def _pull_forward(self, now: datetime) -> list[Event]:
        events = []
        busy = self._occupied()
        horizon = now + timedelta(days=7)
        for s in self.p.slots_from(now):
            if s > horizon:
                break
            if s.astimezone(self.p.tz).date() in busy:
                continue
            later = sorted(
                (e for e in self.all(State.APPROVED)
                 if e.slot_mode == "next_free" and e.slot and e.slot > s),
                key=lambda e: e.valid_until(self.p),
            )
            if later:
                e, old = later[0], later[0].slot
                e.slot = s
                self._save(e, now, "pulled_forward", f"{old:%d/%m} -> {s:%d/%m}")
                events.append(Event(
                    kind="pulled_forward", entry_id=e.id,
                    detail=f"{e.title}: antecipado de {old:%d/%m} para {s:%d/%m}",
                ))
                busy = self._occupied()
        return events

    # ---- o que vai no e-mail de pautas
    def silent(self, n: int | None = None) -> bool:
        n = n or self.p.silence.unanswered_batches
        rows = self.con.execute(
            "SELECT answered FROM batches ORDER BY sent_at DESC LIMIT ?", (n,)
        ).fetchall()
        return len(rows) == n and not any(r[0] for r in rows)

    def proposal_plan(self, now: datetime) -> dict | None:
        """O que enviar no horário de pautas de `now` (ou None: hoje não tem e-mail)."""
        local = now.astimezone(self.p.tz)
        run = self.proposal_run_for(local)
        if run is None:
            return None
        silent = self.silent()
        if silent and run.coverage_days is None:
            return None  # em silêncio, só o e-mail de domingo
        # Tudo se ancora no horário agendado deste envio, e não no relógio: o n8n chama a
        # curadoria e o e-mail alguns segundos ou minutos depois do horário
        this_run = datetime.combine(local.date(), run.time, tzinfo=self.p.tz)
        start = (
            datetime.combine(local.date() - timedelta(days=run.coverage_days - 1), time(0),
                             tzinfo=self.p.tz)
            if run.coverage_days
            else self.p.previous_run_at(this_run)
        )
        # Pautas novas: as registradas para este envio (a curadoria roda pouco antes ou logo
        # depois do horário). A repescagem são as outras pautas ainda válidas e sem resposta,
        # das que vencem primeiro
        since = this_run - RUN_LEAD
        new = sorted((e for e in self.all(State.PROPOSED) if e.proposed_at > since),
                     key=lambda e: -e.score)[: run.cards]  # as que sobram vão à repescagem
        new_ids = {e.id for e in new}
        carry = [e for e in self.inbox(now, limit=len(self.all()))
                 if e.id not in new_ids][: self.p.silence.carry_over_cards]
        upcoming = []
        for s in self.p.slots_from(now):
            if len(upcoming) == 3:
                break
            taken = [e for e in self.all(*OCCUPYING) if e.slot == s]
            upcoming.append({"slot": s.isoformat(), "entry": taken[0].title if taken else None})
        return {
            "cards": run.cards,
            "batch": f"{this_run:%Y-%m-%d-%H%M}",
            "coverage_start": start.isoformat(),
            "coverage_end": now.isoformat(),
            "silent_mode": silent,
            "new": [e.id for e in new],
            "carry_over": [e.id for e in carry],
            "agenda": upcoming,
        }

    def proposal_run_for(self, local: datetime) -> ProposalRun | None:
        return self.p.proposal_run(local.date())

    def inbox(self, now: datetime, limit: int | None = None) -> list[Entry]:
        """Pautas ainda válidas e sem resposta (repetidas no próximo e-mail)."""
        limit = self.p.silence.carry_over_cards if limit is None else limit
        open_ = [e for e in self.all(State.PROPOSED, State.BANKED)
                 if e.valid_until(self.p) >= now]
        open_.sort(key=lambda e: (e.valid_until(self.p), -e.score))
        return open_[:limit]

    def agenda(self, now: datetime, n: int = 6) -> list[tuple[datetime, Entry | None]]:
        by_slot = {e.slot: e for e in self.all(*OCCUPYING) if e.slot}
        out = []
        for s in self.p.slots_from(now):
            if len(out) == n:
                break
            out.append((s, by_slot.get(s)))
        return out

    # ---- validações
    def _require(self, entry_id: str, *states: State) -> Entry:
        e = self.get(entry_id)
        if e.state not in states:
            allowed = ", ".join(s.value for s in states)
            raise EditorialError(f"pauta {entry_id} está em '{e.state}', esperado: {allowed}")
        return e

    def _require_valid(self, e: Entry, now: datetime) -> None:
        if now > e.valid_until(self.p):
            raise EditorialError(f"a pauta venceu em {e.valid_until(self.p):%d/%m}")


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fila editorial do linky-dev")
    ap.add_argument("cmd", choices=["agenda", "tick", "inbox", "plan"])
    ap.add_argument("--db", default="data/editorial.db")
    ap.add_argument("--now", help="ISO 8601 (padrão: agora)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    q = Queue(args.db)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(q.p.tz)
    if args.cmd == "agenda":
        for s, e in q.agenda(now):
            print(f"{_dname(s.date())} {s:%d/%m %H:%M}  "
                  f"{(e.state.value + ' · ' + e.title) if e else '(livre)'}")
    elif args.cmd == "inbox":
        for e in q.inbox(now, limit=50):
            print(f"{e.id}  vence {e.valid_until(q.p):%d/%m}  {e.state.value}  {e.title}")
    elif args.cmd == "plan":
        print(json.dumps(q.proposal_plan(now), ensure_ascii=False, indent=2))
    else:
        print(json.dumps([ev.model_dump() for ev in q.tick(now)], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
