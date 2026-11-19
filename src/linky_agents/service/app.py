"""Aplicação do serviço: recebe um pedido no formato HTTP e devolve (status, JSON).

Não conhece sockets. O adaptador em `server.py` só traduz a conexão para `App.handle`,
então os testes exercitam tudo (rotas, autenticação, erros, fila e ledger) sem rede.

Toda operação da fila abre a conexão SQLite, faz o trabalho e fecha, sob uma trava: o
volume de chamadas é de poucas por hora, e assim não há conexão compartilhada entre threads.
"""

from __future__ import annotations

import base64
import hmac
import json
import re
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..editorial import (
    EditorialError,
    Entry,
    NotFoundError,
    Policy,
    Post,
    Queue,
    State,
    load_policy,
)
from ..harness import AgentSpec, Alert, BudgetExceeded, Harness, RunFailed
from ..little import escape_little
from . import messages, pipeline
from .alerts import AlertInbox
from .forms import Forms

TOKEN_HEADER = "X-Linky-Token"
# Pasta das imagens dentro do container do n8n (o nó de leitura de arquivo só lê daqui)
N8N_IMAGE_DIR = "/home/node/.n8n-files/linky"
# Webhook do n8n que serve os formulários (workflow linkyForms, ADR 0005)
DEFAULT_FORMS_URL = "https://n8n.example.com/webhook/linky-form"
Response = tuple[int, dict]
# Post em publicação há mais que isto sem published/failed: o n8n caiu no meio (ADR 0004)
STUCK_PUBLISHING_AFTER = timedelta(minutes=30)
# Avisos de validade do token do LinkedIn: (etapa, avisa quando faltam até N dias), do mais
# grave ao mais brando. -1 = já venceu; "1d" cobre a véspera e o próprio dia. Cada etapa avisa
# uma vez por validade registrada.
TOKEN_WARNINGS = (("expired", -1), ("1d", 1), ("7d", 7))
# Tentativas de redação da mesma versão de um post antes de parar e avisar Felipe
MAX_DRAFT_FAILURES = 2


# --------------------------------------------------------------------------- corpos
class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Card(_Body):
    """Pauta como chega da curadoria: o lote e o momento vêm do pedido, não do card."""

    id: str = Field(min_length=1, max_length=120, pattern=r"^[\w.-]+$")
    title: str = Field(min_length=1)
    event_date: date
    perishable: bool = True
    score: int = 0
    sources: list[str] = []
    what: str = ""
    why: str = ""
    angle: str = ""
    pattern: str = ""
    audience: str = ""


class ProposeBody(_Body):
    batch: str = Field(min_length=1, max_length=120)
    entries: list[Card] = Field(min_length=1)


class WhenBody(_Body):
    when: date | None = None  # sem data: próximo horário livre


class PublishedBody(_Body):
    urn: str = Field(min_length=1)


class FailedBody(_Body):
    error: str = Field(min_length=1)


class _Empty(_Body):
    pass


class AgendaQuery(_Body):
    n: int = Field(default=6, ge=1, le=30)


class InboxQuery(_Body):
    limit: int | None = Field(default=None, ge=1, le=100)


class AckBody(_Body):
    ids: list[int] = Field(min_length=1)


class TokenBody(_Body):
    expires_on: date


class FormSubmitBody(_Body):
    # os campos do formulário como o webhook do n8n os entrega (valor ou lista de valores)
    fields: dict[str, str | int | float | None | list[str | int | float | None]]


class ImageName(_Body):
    name: str = Field(pattern=pipeline.IMAGE_NAME)


class AgentFailed(Exception):
    def __init__(self, status: int, body: dict):
        self.status, self.body = status, body


def _fail_key(e: Entry) -> str:
    """Uma escolha da pauta (a versão muda a cada escolha, ajuste ou liberação)."""
    return f"{e.id}:{e.version}"


def entry_json(e: Entry, policy: Policy) -> dict:
    return {**e.model_dump(mode="json"), "valid_until": e.valid_until(policy).isoformat()}


def linkedin_post_json(post: Post) -> dict:
    """O post no formato do LinkedIn: legenda já escapada e caminho da imagem no n8n."""
    return {
        "commentary": escape_little(post.commentary),
        "alt_text": post.alt_text,
        "image_path": f"{N8N_IMAGE_DIR}/{post.image}",
        "image_url_path": f"/images/{post.image}",  # imagens da esteira (GET /images/{nome})
    }


# --------------------------------------------------------------------------- aplicação
class App:
    def __init__(
        self,
        data_dir: Path,
        token: str,
        clock: Callable[[], datetime],
        policy: Policy | None = None,
        harness_factory: Callable[[Callable[[Alert], None]], Harness] | None = None,
        agents: Mapping[str, AgentSpec] | None = None,
        shadow: bool = True,
        forms_url: str = DEFAULT_FORMS_URL,
        items_dir: Path | None = None,
        pipeline_agents: pipeline.Agents | None = None,
    ):
        if not token:
            raise ValueError("o segredo compartilhado não pode ser vazio")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        # Modo sombra (ADR 0004): e-mails com "[sombra]" e publicação sem LinkedIn.
        # Ligado por padrão: publicar de verdade exige desligar explicitamente.
        self.shadow = shadow
        self.clock = clock
        self.policy = policy or load_policy()
        self.db = self.data_dir / "editorial.db"
        self._lock = threading.Lock()
        self._agent_lock = threading.Lock()  # uma execução por vez: o teto vê o gasto real
        self.alerts = AlertInbox(self.data_dir / "alerts.db", clock)
        factory = harness_factory or (
            lambda alert: Harness.from_repo(data_dir=self.data_dir, alert=alert)
        )
        self.harness = factory(self.alerts.push)
        self.agents = dict(agents or {})
        # Esteira (docs/ideas/producao-mvp.md): itens da coleta montados só leitura e agentes
        self.items_dir = Path(items_dir) if items_dir else self.data_dir / "items"
        self.images_dir = self.data_dir / "images"
        self.pipeline = pipeline_agents or pipeline.RealAgents(self.harness, self.data_dir)
        self.forms = Forms(self.data_dir / "forms.db", token, forms_url, self.policy, shadow,
                           clock)
        self._routes: list[tuple[str, re.Pattern, Callable[..., dict]]] = []
        self._route("POST", "/propose", self._propose)
        self._route("GET", "/entries/{id}", self._get)
        for action in ("choose", "bank", "discard", "drafted", "approve", "reschedule",
                       "publishing", "published", "failed"):
            self._route("POST", "/entries/{id}/" + action, getattr(self, "_" + action))
        self._route("POST", "/batches/{batch}/none_today", self._none_today)
        self._route("GET", "/due", self._due)
        self._route("POST", "/tick", self._tick)
        self._route("GET", "/proposal_plan", self._proposal_plan)
        self._route("GET", "/agenda", self._agenda)
        self._route("GET", "/inbox", self._inbox)
        self._route("GET", "/alerts", self._alerts)
        self._route("POST", "/alerts/ack", self._ack)
        self._route("GET", "/spending", self._spending)
        self._route("GET", "/linkedin/token", self._token)
        self._route("POST", "/linkedin/token", self._set_token)
        self._route("POST", "/agents/{name}", self._agent)
        self._route("POST", "/proposal_email", self._proposal_email)
        self._route("POST", "/approval_emails", self._approval_emails)
        self._route("GET", "/forms/{id}", self._form_page)
        self._route("POST", "/forms/{id}", self._form_submit)
        self._route("POST", "/forms/{id}/sent", self._form_sent)
        self._route("POST", "/curate", self._curate)
        self._route("POST", "/draft_next", self._draft_next)
        self._route("GET", "/images/{name}", self._image)

    # ---- roteamento
    def _route(self, method: str, template: str, fn: Callable[..., dict]) -> None:
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", template)
        self._routes.append((method, re.compile(f"^{pattern}$"), fn))

    def handle(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> Response:
        path, _, query = path.partition("?")
        path = path.rstrip("/") or "/"
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if not self._authorized(headers):
            return 401, {"error": "segredo ausente ou inválido"}
        matched = [(m, rx.match(path), fn) for m, rx, fn in self._routes]
        matched = [(m, mo, fn) for m, mo, fn in matched if mo]
        if not matched:
            return 404, {"error": f"rota inexistente: {path}"}
        hit = next(((mo, fn) for m, mo, fn in matched if m == method), None)
        if hit is None:
            return 405, {"error": f"método {method} não aceito em {path}"}
        mo, fn = hit
        try:
            if method == "GET":  # GET não tem corpo: os parâmetros vêm da query string
                data = {k: v[-1] for k, v in parse_qs(query).items()}
            else:
                data = json.loads(body) if body.strip() else {}
            return 200, fn(data, **mo.groupdict())
        except json.JSONDecodeError:
            return 400, {"error": "corpo não é JSON válido"}
        except ValidationError as e:
            # via JSON: o erro de um validador próprio traz a exceção, que não serializa
            return 422, {"error": "corpo inválido", "detail": json.loads(e.json(include_url=False))}
        except NotFoundError as e:
            return 404, {"error": str(e)}
        except EditorialError as e:
            return 409, {"error": str(e)}
        except AgentFailed as e:
            return e.status, e.body

    def _authorized(self, headers: Mapping[str, str]) -> bool:
        got = next((v for k, v in headers.items() if k.lower() == TOKEN_HEADER.lower()), "")
        return hmac.compare_digest(got.encode(), self.token.encode())

    @contextmanager
    def _queue(self) -> Iterator[Queue]:
        with self._lock:
            q = Queue(self.db, self.policy)
            try:
                yield q
            finally:
                q.con.close()

    def _entry(self, e: Entry) -> dict:
        return {"entry": entry_json(e, self.policy)}

    # ---- decisão 1
    def _propose(self, data: dict) -> dict:
        b = ProposeBody.model_validate(data)
        now = self.clock()
        entries = [
            Entry(**c.model_dump(), batch=b.batch, proposed_at=now) for c in b.entries
        ]
        with self._queue() as q:
            q.propose(b.batch, entries, now)
        return {"proposed": [e.id for e in entries]}

    def _get(self, data: dict, id: str) -> dict:
        _Empty.model_validate(data)
        with self._queue() as q:
            return self._entry(q.get(id))

    def _transition(self, id: str, op: Callable[[Queue, datetime], Entry]) -> dict:
        with self._queue() as q:
            return self._entry(op(q, self.clock()))

    def _choose(self, data: dict, id: str) -> dict:
        when = WhenBody.model_validate(data).when
        return self._transition(id, lambda q, now: q.choose(id, now, when))

    def _bank(self, data: dict, id: str) -> dict:
        _Empty.model_validate(data)
        return self._transition(id, lambda q, now: q.bank(id, now))

    def _discard(self, data: dict, id: str) -> dict:
        _Empty.model_validate(data)
        return self._transition(id, lambda q, now: q.discard(id, now))

    def _none_today(self, data: dict, batch: str) -> dict:
        _Empty.model_validate(data)
        with self._queue() as q:
            q.none_today(batch, self.clock())
        return {"batch": batch, "answered": True}

    # ---- decisão 2
    def _drafted(self, data: dict, id: str) -> dict:
        post = Post.model_validate(data)
        return self._transition(id, lambda q, now: q.drafted(id, now, post))

    def _approve(self, data: dict, id: str) -> dict:
        when = WhenBody.model_validate(data).when
        return self._transition(id, lambda q, now: q.approve(id, now, when))

    def _reschedule(self, data: dict, id: str) -> dict:
        when = WhenBody.model_validate(data).when
        return self._transition(id, lambda q, now: q.reschedule(id, now, when))

    # ---- publicação
    def _due(self, data: dict) -> dict:
        _Empty.model_validate(data)
        with self._queue() as q:
            due = q.due(self.clock())
        items = []
        for e in due:
            assert e.post is not None  # approve recusa pauta sem post
            li = linkedin_post_json(e.post)
            email = (messages.shadow_publication_email(e, li, self.policy.tz)
                     if self.shadow else None)
            items.append({**entry_json(e, self.policy), "linkedin": li, "email": email})
        return {"shadow": self.shadow, "entries": items}

    def _publishing(self, data: dict, id: str) -> dict:
        _Empty.model_validate(data)
        return self._transition(id, lambda q, now: q.publishing(id, now))

    def _published(self, data: dict, id: str) -> dict:
        urn = PublishedBody.model_validate(data).urn
        return self._transition(id, lambda q, now: q.published(id, now, urn))

    def _failed(self, data: dict, id: str) -> dict:
        error = FailedBody.model_validate(data).error
        with self._queue() as q:
            e = q.failed(id, self.clock(), error)
        # Falha nunca reenvia (ADR 0004): Felipe precisa saber para decidir
        self.alerts.notify(
            "publish_failed", "publication",
            messages.publish_failed_message(e, error, self.policy.tz),
            key=f"publish_failed:{id}", title=e.title,
        )
        return self._entry(e)

    # ---- relógio e leitura
    def _tick(self, data: dict) -> dict:
        _Empty.model_validate(data)
        now = self.clock()
        with self._queue() as q:
            events = q.tick(now)
            entries = {ev.entry_id: q.get(ev.entry_id) for ev in events if ev.entry_id}
            stuck = q.stuck_publishing(now, STUCK_PUBLISHING_AFTER)
        self._watch(now, stuck)
        return {
            "shadow": self.shadow,
            "events": [ev.model_dump() for ev in events],
            "email": messages.tick_email(events, entries, self.shadow),
        }

    def _watch(self, now: datetime, stuck: list[tuple[Entry, datetime]]) -> None:
        """Alertas de operação vistos pelo relógio. Vão para a caixa de alertas (entregues
        pelo linkyLedgerAlerts), não para o e-mail do tick: a caixa é durável e deduplica."""
        for e, since in stuck:
            self.alerts.notify(
                "publishing_stuck", "publication",
                messages.publishing_stuck_message(e, since, self.policy.tz),
                key=f"publishing_stuck:{e.id}:{since.isoformat()}", title=e.title,
            )
        exp = self.alerts.linkedin_token_expires_on()
        if exp is None:  # sem a data, o aviso de 7 dias nunca sairia: avisa uma vez
            self.alerts.notify(
                "linkedin_token", "linkedin", messages.LINKEDIN_TOKEN_UNKNOWN,
                key="linkedin_token:unknown",
            )
            return
        days = self._token_days_left(exp, now)
        stage = next((s for s, limit in TOKEN_WARNINGS if days <= limit), None)
        if stage:
            self.alerts.notify(
                "linkedin_token", "linkedin", messages.linkedin_token_message(exp, days),
                key=f"linkedin_token:{exp.isoformat()}:{stage}",
            )

    # ---- token do LinkedIn
    def _token_days_left(self, expires_on: date, now: datetime) -> int:
        return (expires_on - now.astimezone(self.policy.tz).date()).days

    def _token_json(self) -> dict:
        exp = self.alerts.linkedin_token_expires_on()
        return {"expires_on": exp.isoformat() if exp else None,
                "days_left": self._token_days_left(exp, self.clock()) if exp else None}

    def _token(self, data: dict) -> dict:
        _Empty.model_validate(data)
        return self._token_json()

    def _set_token(self, data: dict) -> dict:
        """Registra a validade do token ao (re)conectar a credencial "LinkedIn account" no n8n
        (60 dias). O n8n não expõe essa data, então ela é informada aqui."""
        self.alerts.set_linkedin_token_expires_on(TokenBody.model_validate(data).expires_on)
        return self._token_json()

    def _proposal_plan(self, data: dict) -> dict:
        _Empty.model_validate(data)
        with self._queue() as q:
            return {"plan": q.proposal_plan(self.clock())}

    def _agenda(self, data: dict) -> dict:
        n = AgendaQuery.model_validate(data).n
        with self._queue() as q:
            slots = q.agenda(self.clock(), n)
        return {"slots": [
            {"slot": s.isoformat(),
             "entry": {"id": e.id, "title": e.title, "state": e.state.value} if e else None}
            for s, e in slots
        ]}

    def _inbox(self, data: dict) -> dict:
        limit = InboxQuery.model_validate(data).limit
        with self._queue() as q:
            return {"entries": [entry_json(e, self.policy)
                                for e in q.inbox(self.clock(), limit)]}

    # ---- alertas e gasto
    def _alerts(self, data: dict) -> dict:
        _Empty.model_validate(data)
        pending = self.alerts.pending()
        return {"shadow": self.shadow, "alerts": pending,
                "email": messages.alerts_email(pending, self.shadow)}

    def _ack(self, data: dict) -> dict:
        return {"acked": self.alerts.ack(AckBody.model_validate(data).ids)}

    def _spending(self, data: dict) -> dict:
        _Empty.model_validate(data)
        b = self.harness.config.budget
        return {
            **self.harness.spending(),
            "caps": {"run_usd": b.per_run_usd, "day_usd": b.per_day_usd,
                     "month_usd": b.per_month_usd},
            "warn_ratio": b.warn_ratio,
        }

    # ---- agentes
    def _agent(self, data: dict, name: str) -> dict:
        spec = self.agents.get(name)
        if spec is None:
            raise NotFoundError(f"agente {name} não está registrado no serviço")
        inp = spec.input.model_validate(data)
        with self._agent_lock:
            try:
                r = self.harness.run(spec, inp)
            except BudgetExceeded as e:
                raise AgentFailed(402, {"error": str(e), "scope": e.scope}) from e
            except RunFailed as e:
                raise AgentFailed(502, {"error": str(e)}) from e
        return {"run_id": r.run_id, "model": r.model, "cost_usd": r.cost_usd,
                "output": r.output.model_dump(mode="json")}

    # ---- esteira em produção (docs/ideas/producao-mvp.md)
    def _curate(self, data: dict) -> dict:
        """Antes do e-mail de pautas: itens da janela → triagem e curadoria → pautas na fila.
        Chamado pelo linkyProposals no horário de pautas; repetir não duplica o lote."""
        _Empty.model_validate(data)
        now = self.clock()
        with self._queue() as q:
            plan = q.proposal_plan(now)
            if plan is None:
                return {"proposed": [], "reason": "agora não é horário de pautas"}
            batch = plan["batch"]  # o horário agendado do envio: repetir não duplica o lote
            if q.has_batch(batch):
                return {"proposed": [], "reason": "as pautas deste horário já foram propostas"}
            exclude = pipeline.recent_exclusions(q.all(), now)
        start = datetime.fromisoformat(plan["coverage_start"])
        items = pipeline.load_items(self.items_dir, start, now)
        if not items:  # sintoma de coleta parada: avisa (uma vez por envio)
            self._pipeline_alert(now, f"curate-empty:{batch}",
                                 messages.curate_empty_message(start, now, self.policy.tz))
            return {"proposed": [], "reason": "nenhum item coletado na janela"}
        try:
            with self._agent_lock:
                cards = self.pipeline.curate(items, now=now, n_cards=plan["cards"],
                                             exclude=exclude)
        except BudgetExceeded as e:
            raise AgentFailed(402, {"error": str(e), "scope": e.scope}) from e
        except Exception as e:  # modelo, rede, saída inválida: o e-mail sai só com repescagem
            self._pipeline_alert(now, f"curate:{now.astimezone(self.policy.tz):%Y-%m-%d %H}",
                                 messages.curate_failed_message(e))
            raise AgentFailed(502, {"error": str(e)}) from e
        if not cards:
            return {"proposed": [], "reason": "nenhum fato coube num padrão do playbook"}
        body = ProposeBody(batch=batch, entries=[Card(**c.model_dump()) for c in cards])
        return {**self._propose(body.model_dump(mode="json")), "items": len(items)}

    def _draft_next(self, data: dict) -> dict:
        """Uma pauta escolhida (ou com ajuste pedido) por chamada: redação, checagem e arte →
        post aguardando aprovação. Chamado pelo linkyApprovalEmails a cada 15 minutos, antes
        de montar os e-mails. Falhou duas vezes na mesma versão? Para e avisa."""
        _Empty.model_validate(data)
        # Uma redação por vez, da escolha da pauta até a imagem gravada: uma chamada que chega
        # durante outra (ou durante a curadoria) volta sem fazer nada e a próxima tenta de novo
        if not self._agent_lock.acquire(blocking=False):
            return {"drafted": None, "reason": "outra execução dos agentes em curso"}
        try:
            return self._draft_one()
        finally:
            self._agent_lock.release()

    def _draft_one(self) -> dict:
        now = self.clock()
        fails = self._draft_failures()
        with self._queue() as q:
            todo = sorted(q.all(State.CHOSEN), key=lambda e: e.slot or e.proposed_at)
            everything = q.all()
            hooks = pipeline.recent_hooks(everything)
        pipeline.forget_dropped_art(self.data_dir, everything)
        todo = [e for e in todo if fails.get(_fail_key(e), 0) < MAX_DRAFT_FAILURES]
        if not todo:
            return {"drafted": None}
        e = todo[0]
        key = _fail_key(e)  # antes de gravar o post, que pode mudar a versão
        try:
            draft = self.pipeline.write(e, recent_hooks=hooks)
            img = self.pipeline.image(e, draft)
        except BudgetExceeded as err:
            raise AgentFailed(402, {"error": str(err), "scope": err.scope}) from err
        except Exception as err:  # registra e segue: a próxima chamada tenta de novo
            n = self._record_draft_failure(e)
            if n >= MAX_DRAFT_FAILURES:  # parou de tentar: a pauta volta ao banco
                with self._queue() as q, suppress(EditorialError):
                    q.release(e.id, self.clock())
            self._pipeline_alert(now, f"draft:{_fail_key(e)}:{n}",
                                 messages.draft_failed_message(e, err, n, MAX_DRAFT_FAILURES),
                                 title=e.title)
            return {"drafted": None, "failed": e.id, "error": str(err)}
        name = pipeline.image_name(e)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        if (self.images_dir / name).exists():  # nunca troca uma imagem já mostrada a Felipe
            name = f"{name.removesuffix('.png')}-{e.version}.png"
        with open(self.images_dir / name, "xb") as f:
            f.write(img.png)
        post = pipeline.post_from(draft, name, img.alt_text)
        with self._queue() as q:
            try:
                e = q.drafted(e.id, self.clock(), post)
            except EditorialError:  # Felipe descartou ou a pauta venceu durante a redação
                return {"drafted": None, "reason": f"a pauta {e.id} mudou durante a redação"}
        # Deu certo: um aviso de falha desta escolha que ainda não saiu só confundiria
        # (o e-mail de alertas sai de hora em hora, depois do e-mail de aprovação)
        self.alerts.withdraw(f"pipeline:draft:{key}:")
        return {"drafted": e.id, "image": name}

    def _image(self, data: dict, name: str) -> dict:
        """A imagem de um post, para o n8n anexar ao e-mail e enviar ao LinkedIn."""
        n = ImageName(name=name).name
        f = self.images_dir / n
        if not f.is_file():
            raise NotFoundError(f"imagem {n} não existe")
        return {"name": n, "mime": "image/png",
                "base64": base64.b64encode(f.read_bytes()).decode("ascii")}

    def _pipeline_alert(self, now: datetime, key: str, message: str,
                        title: str | None = None) -> None:
        self.alerts.notify("pipeline", "pipeline", message, key=f"pipeline:{key}", title=title)

    def _draft_failures(self) -> dict[str, int]:
        f = self.data_dir / "draft_failures.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def _record_draft_failure(self, e: Entry) -> int:
        fails = self._draft_failures()
        k = _fail_key(e)
        fails[k] = fails.get(k, 0) + 1
        (self.data_dir / "draft_failures.json").write_text(json.dumps(fails), encoding="utf-8")
        return fails[k]

    # ---- etapa D: e-mails de decisão e formulários (ADR 0005)
    def _proposal_email(self, data: dict) -> dict:
        """Decisão 1: monta o e-mail de pautas a partir do plano do horário (pautas novas,
        repescagem e agenda) e cria o formulário. Sem pauta para mostrar, sem e-mail."""
        _Empty.model_validate(data)
        now = self.clock()
        with self._queue() as q:
            plan = q.proposal_plan(now)
            if plan is None:
                return {"plan": None, "email": None}
            new = [q.get(i) for i in plan["new"]]
            carry = [q.get(i) for i in plan["carry_over"]]
            if not new and not carry:
                return {"plan": plan, "email": None}
            fid = self.forms.issue_pick([e.id for e in new + carry])
        email = messages.proposal_email(plan, new, carry, self.policy, self.forms.link(fid),
                                        now, self.shadow)
        return {"plan": plan, "form_id": fid, "email": email}

    def _approval_emails(self, data: dict) -> dict:
        """Decisão 2: um e-mail por post pronto cuja versão ainda não foi enviada. O n8n
        confirma cada envio em `POST /forms/{id}/sent`; sem confirmação, volta na próxima."""
        _Empty.model_validate(data)
        with self._queue() as q:
            pending = self.forms.approval_outbox(q)
        out = []
        for e, fid in pending:
            assert e.post is not None  # aguardando aprovação sempre tem post
            path = f"{N8N_IMAGE_DIR}/{e.post.image}"
            out.append({
                "entry_id": e.id, "form_id": fid, "image": e.post.image, "image_path": path,
                "image_url_path": f"/images/{e.post.image}",
                "email": messages.approval_email(e, self.policy, self.forms.link(fid),
                                                 e.post.image, self.shadow),
            })
        return {"shadow": self.shadow, "emails": out}

    def _form_page(self, data: dict, id: str) -> dict:
        # Só leitura (T4′): scanners de link podem abrir isto à vontade. A query string (o
        # próprio `f`, parâmetros de rastreio) é ignorada.
        with self._queue() as q:
            return self.forms.page(id, q, self.clock())

    def _form_submit(self, data: dict, id: str) -> dict:
        fields = FormSubmitBody.model_validate(data).fields
        with self._queue() as q:
            return self.forms.submit(id, fields, q, self.clock())

    def _form_sent(self, data: dict, id: str) -> dict:
        _Empty.model_validate(data)
        if not self.forms.mark_sent(id):
            raise NotFoundError(f"formulário {id} não existe")
        return {"form_id": id, "sent": True}
