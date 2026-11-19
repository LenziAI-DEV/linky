"""Formulários das duas decisões de Felipe (etapa D, ADR 0005).

O e-mail leva só um link. O link abre a página do formulário (GET), que **nunca muda nada**:
scanners de link (pré-busca do Gmail, antivírus) podem abri-lo à vontade (T4′). Só o envio do
formulário (POST) decide, e cada pauta do formulário leva um token:

- o token é um HMAC de (formulário, pauta, versão da pauta), com chave derivada do segredo do
  serviço: não fica guardado em lugar nenhum, e só quem tem o e-mail chega à página;
- vale **uma vez**: o uso fica registrado (`used`), e toda decisão muda a versão da pauta,
  então um reenvio (botão voltar, duplo clique, robô) é recusado sem mudar nada;
- o padrão de cada pauta é "não decidir agora": um envio do formulário como veio não decide
  nada.

Interface: `Forms.issue_pick`, `Forms.approval_outbox`, `Forms.mark_sent`, `Forms.page` e
`Forms.submit`. As páginas voltam prontas (`{"status", "html"}`); o n8n só as entrega.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path

from ..editorial import MAX_ADJUSTMENTS, EditorialError, Entry, Policy, Queue, State
from .messages import card_parts, day, source_link, when
from .pipeline import recompose

OPINION_MAX = 280
NOTE_MAX = 1000
READING_MAX = 600  # leitura escrita por Felipe no formulário de aprovação
_CLOSED = {
    State.CHOSEN: "escolhida para {slot}",
    State.AWAITING_APPROVAL: "post pronto, aguardando aprovação para {slot}",
    State.APPROVED: "aprovada para {slot}",
    State.PUBLISHING: "em publicação",
    State.PUBLISHED: "publicada",
    State.FAILED: "a publicação falhou",
    State.EXPIRED: "venceu",
    State.DISCARDED: "descartada",
}
_STALE = ("Este formulário já foi usado para esta pauta, ou ela mudou desde que a página foi "
          "aberta. Nada foi alterado. Abra o link do e-mail de novo para ver como ela está.")


@dataclass(frozen=True)
class Form:
    id: str
    kind: str  # "pick" (decisão 1) ou "approve" (decisão 2)
    entries: list[str]
    round: int  # decisão 2: a versão do post (número de ajustes pedidos) que o e-mail mostra
    sent_at: str | None


class Forms:
    def __init__(self, db: Path, secret: str, url: str, policy: Policy, shadow: bool,
                 clock: Callable[[], datetime]):
        self.db, self.url, self.p, self.shadow, self.clock = Path(db), url, policy, shadow, clock
        self._key = hashlib.sha256(b"linky-forms|" + secret.encode()).digest()
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS forms (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, entries TEXT NOT NULL,
                    round INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, sent_at TEXT);
                CREATE TABLE IF NOT EXISTS used (
                    scope TEXT PRIMARY KEY, form_id TEXT NOT NULL, used_at TEXT NOT NULL,
                    action TEXT NOT NULL);
                """
            )

    # ---- guarda
    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        return con

    def _exec(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        con = self._con()
        try:
            with con:
                return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def get(self, form_id: str) -> Form | None:
        rows = self._exec("SELECT * FROM forms WHERE id=?", (form_id,))
        if not rows:
            return None
        r = rows[0]
        return Form(r["id"], r["kind"], json.loads(r["entries"]), r["round"], r["sent_at"])

    def _create(self, kind: str, entries: list[str], round_: int = 0) -> str:
        fid = secrets.token_urlsafe(16)
        self._exec("INSERT INTO forms(id, kind, entries, round, created_at) VALUES(?,?,?,?,?)",
                   (fid, kind, json.dumps(entries), round_, self.clock().isoformat()))
        return fid

    def link(self, form_id: str) -> str:
        return f"{self.url}?f={form_id}"

    def issue_pick(self, entry_ids: list[str]) -> str:
        """Formulário da decisão 1 para as pautas de um e-mail de pautas."""
        return self._create("pick", entry_ids)

    def approval_outbox(self, q: Queue) -> list[tuple[Entry, str]]:
        """Posts aguardando aprovação cujo e-mail desta versão ainda não saiu, com o
        formulário de cada um. Repetir a chamada devolve o mesmo formulário até `mark_sent`."""
        out = []
        for e in sorted(q.all(State.AWAITING_APPROVAL), key=lambda e: (e.slot is None, e.slot)):
            rnd = len(e.adjustments)
            since = q.awaiting_since(e.id)
            rows = [r for r in self._exec(
                "SELECT id, sent_at, created_at FROM forms WHERE kind='approve' AND entries=? "
                "AND round=?", (json.dumps([e.id]), rnd),
            ) if since is None or datetime.fromisoformat(r["created_at"]) >= since]
            # Só vale formulário criado depois que a pauta voltou a aguardar aprovação: um post
            # de data escolhida que perdeu o horário volta para Felipe com um e-mail novo
            if any(r["sent_at"] for r in rows):
                continue
            out.append((e, rows[0]["id"] if rows else self._create("approve", [e.id], rnd)))
        return out

    def mark_sent(self, form_id: str) -> bool:
        return bool(self._exec("UPDATE forms SET sent_at=? WHERE id=? RETURNING id",
                               (self.clock().isoformat(), form_id)))

    # ---- tokens
    def _token(self, form_id: str, subject: str) -> str:
        mac = hmac.new(self._key, f"{form_id}|{subject}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac[:18]).decode()

    def _scope(self, e: Entry) -> str:
        return f"{e.id}|{e.version}"

    def _accepts(self, form_id: str, scope: str, token: str) -> bool:
        """O token é deste formulário e desta versão da pauta, e ainda não foi usado."""
        ok = hmac.compare_digest(token.encode(), self._token(form_id, scope).encode())
        return ok and not self._exec("SELECT 1 FROM used WHERE scope=?", (scope,))

    def _use(self, form_id: str, scope: str, action: str) -> None:
        self._exec("INSERT INTO used(scope, form_id, used_at, action) VALUES(?,?,?,?)",
                   (scope, form_id, self.clock().isoformat(), action))

    # ---- páginas (GET: só leitura)
    def page(self, form_id: str, q: Queue, now: datetime) -> dict:
        form = self.get(form_id)
        if form is None:
            return self._page(404, "Formulário não encontrado",
                              "<p>Este link não corresponde a nenhum formulário.</p>")
        entries = [_get(q, eid) for eid in form.entries]
        if form.kind == "pick":
            body = self._pick_body(form, [e for e in entries if e], q, now)
            return self._page(200, "Escolher pautas", body)
        e = entries[0]
        if e is None:
            return self._page(404, "Pauta não encontrada", "<p>A pauta saiu da fila.</p>")
        return self._page(200, "Aprovar post", self._approve_body(form, e, q, now))

    def _pick_body(self, form: Form, entries: list[Entry], q: Queue, now: datetime) -> str:
        parts = [f"<form method=\"post\" action=\"{escape(self.link(form.id), quote=True)}\">",
                 _hidden("f", form.id)]
        for e in entries:
            parts.append(f"<fieldset><legend>{escape(e.title)}</legend>{_summary(e, self.p)}")
            open_ = e.state in (State.PROPOSED, State.BANKED) and now <= e.valid_until(self.p)
            if not open_:
                parts.append(f"<p class='st'>{escape(self._status(e, now))}</p></fieldset>")
                continue
            options = [("", "Não decidir agora"),
                       ("next", "Produzir para o próximo horário livre"),
                       ("date", "Produzir para a data abaixo")]
            if e.state == State.PROPOSED:
                options.append(("bank", "Guardar no banco"))
            options.append(("discard", "Descartar"))
            parts += [
                _select(f"a:{e.id}", "O que fazer", options),
                self._dates(f"w:{e.id}", "Data", q.free_slots(e, now), keep=None),
                f"<label>Opinião em uma linha (opcional)<input type='text' name='o:{escape(e.id)}'"
                f" maxlength='{OPINION_MAX}' value='{escape(e.opinion or '', quote=True)}'>"
                "</label>",
                _hidden(f"t:{e.id}", self._token(form.id, self._scope(e))),
                "</fieldset>",
            ]
        parts += [
            "<fieldset><label class='inline'><input type='checkbox' name='none' value='1'> "
            "Nenhuma me interessa hoje</label>"
            "<small>Conta como resposta. As pautas continuam valendo na repescagem.</small>",
            _hidden("t:none", self._token(form.id, f"none|{form.id}")),
            "</fieldset><button type='submit'>Enviar escolhas</button></form>",
        ]
        return "".join(parts)

    def _approve_body(self, form: Form, e: Entry, q: Queue, now: datetime) -> str:
        rounds = len(e.adjustments)
        if rounds > form.round:
            msg = ("Ajuste pedido: aguardando nova versão do post."
                   if e.state == State.CHOSEN and rounds == form.round + 1
                   else "Esta versão foi substituída: a nova versão está em outro e-mail.")
            return f"<h2>{escape(e.title)}</h2><p class='st'>{escape(msg)}</p>"
        head = f"<h2>{escape(e.title)}</h2>"
        if e.post is not None:
            head += (
                "<pre class='post'>" + escape(e.post.commentary) + "</pre>"
                f"<p><b>Texto alternativo:</b> {escape(e.post.alt_text)}<br>"
                f"<b>Imagem:</b> {escape(e.post.image)} (em anexo no e-mail)</p>"
            )
        if e.state not in (State.AWAITING_APPROVAL, State.APPROVED):
            return head + f"<p class='st'>{escape(self._status(e, now))}</p>"
        slot = when(e.slot, self.p.tz) if e.slot else "sem horário"
        head += f"<p><b>Horário:</b> {escape(slot)}</p>"
        if e.state == State.APPROVED:
            head += f"<p class='st'>Aprovado para {escape(slot)}.</p>"
            options = [("", "Manter como está"), ("reschedule", "Trocar o horário"),
                       ("discard", "Descartar")]
        else:
            options = [("", "Não decidir agora"), ("approve", "Aprovar"),
                       ("reschedule", "Só trocar o horário (sem aprovar)")]
            if rounds < MAX_ADJUSTMENTS:
                options.append(("adjust", f"Pedir ajuste ({rounds + 1} de {MAX_ADJUSTMENTS})"))
            options.append(("discard", "Descartar"))
        current = e.slot.astimezone(self.p.tz).date() if e.slot else None
        parts = [
            head,
            f"<form method=\"post\" action=\"{escape(self.link(form.id), quote=True)}\">",
            _hidden("f", form.id), "<fieldset>",
            _select(f"a:{e.id}", "O que fazer", options),
            self._dates(f"w:{e.id}", "Horário", q.free_slots(e, now), keep=current),
        ]
        if e.state == State.AWAITING_APPROVAL and e.post is not None and e.post.hooks:
            parts.append(_variants(e))
        if e.state == State.AWAITING_APPROVAL and rounds < MAX_ADJUSTMENTS:
            parts.append(f"<label>O que ajustar (para pedir ajuste)<textarea name='n:"
                         f"{escape(e.id)}' maxlength='{NOTE_MAX}' rows='3'></textarea></label>")
        parts += [_hidden(f"t:{e.id}", self._token(form.id, self._scope(e))), "</fieldset>",
                  "<button type='submit'>Enviar</button></form>"]
        return "".join(parts)

    def _dates(self, name: str, label: str, slots: list[datetime], keep: date | None) -> str:
        options = [("", f"Manter {day(keep)}" if keep else "—")]
        options += [(s.astimezone(self.p.tz).date().isoformat(), when(s, self.p.tz))
                    for s in slots if s.astimezone(self.p.tz).date() != keep]
        if keep is None and len(options) == 1:
            options = [("", "Nenhum horário livre antes de a pauta vencer")]
        return _select(name, label, options)

    def _status(self, e: Entry, now: datetime) -> str:
        if e.state in (State.PROPOSED, State.BANKED):  # aberta, mas passou da validade
            return f"Esta pauta venceu em {e.valid_until(self.p):%d/%m}."
        if e.state == State.EXPIRED:
            return "Esta pauta venceu."
        slot = when(e.slot, self.p.tz) if e.slot else "?"
        return "Esta pauta já foi respondida: " + _CLOSED[e.state].format(slot=slot) + "."

    def _page(self, status: int, title: str, body: str) -> dict:
        shadow = ("<p class='shadow'>Modo sombra: nada é publicado no LinkedIn. As escolhas "
                  "valem só para a fila.</p>") if self.shadow else ""
        html = (
            "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='robots' content='noindex,nofollow'>"
            f"<title>{escape(title)} · linky</title><style>{_CSS}</style></head><body>"
            f"<h1>{escape(title)}</h1>{shadow}{body}</body></html>"
        )
        return {"status": status, "html": html}

    # ---- envio (POST: decide)
    def submit(self, form_id: str, fields: Mapping[str, object], q: Queue,
               now: datetime) -> dict:
        form = self.get(form_id)
        if form is None:
            return self._page(404, "Formulário não encontrado",
                              "<p>Este link não corresponde a nenhum formulário.</p>")
        f = {k: _text(v) for k, v in fields.items()}
        chosen = [(eid, f.get(f"a:{eid}", "")) for eid in form.entries]
        chosen = [(eid, a) for eid, a in chosen if a]
        none = form.kind == "pick" and f.get("none") == "1"
        back = f"<p><a href='{escape(self.link(form.id), quote=True)}'>Voltar ao formulário</a></p>"
        if not chosen and not none:
            return self._page(400, "Nada foi marcado",
                              "<p>Nada foi marcado. Nada mudou.</p>" + back)
        results: list[tuple[str, str, str]] = []  # (ok | stale | error, título, mensagem)
        for eid, action in chosen:
            e = _get(q, eid)
            if e is None:
                results.append(("error", eid, "a pauta saiu da fila"))
                continue
            scope = self._scope(e)
            if not self._accepts(form.id, scope, f.get(f"t:{eid}", "")):
                results.append(("stale", e.title, _STALE))
                continue
            try:
                msg = self._apply(form, e, action, f, q, now)
            except (EditorialError, ValueError) as err:
                results.append(("error", e.title, str(err)))
                continue
            # Fila e registro de uso ficam em bancos separados: se este registro falhar, a
            # versão da pauta já subiu, e o reenvio é recusado do mesmo jeito
            self._use(form.id, scope, action)
            results.append(("ok", e.title, msg))
        if none:
            scope = f"none|{form.id}"
            if self._accepts(form.id, scope, f.get("t:none", "")):
                for batch in sorted({e.batch for e in map(lambda i: _get(q, i), form.entries)
                                     if e}):
                    with suppress(EditorialError):  # lote que saiu da fila: nada a marcar
                        q.none_today(batch, now)
                self._use(form.id, scope, "none")
                results.append(("ok", "Nenhuma hoje", "anotado como resposta do e-mail"))
            else:
                results.append(("stale", "Nenhuma hoje", "este formulário já registrou isso"))
        kinds = {r[0] for r in results}
        # 200 se alguma decisão valeu; senão 409 (token velho ou regra da fila, ADR 0003)
        status = 200 if "ok" in kinds else 409
        items = "".join(
            f"<li class='{k}'><b>{escape(t)}</b>: {escape(m)}</li>" for k, t, m in results
        )
        title = "Pronto" if status == 200 else "Nada mudou"
        return self._page(status, title, f"<ul class='res'>{items}</ul>{back}")

    def _apply(self, form: Form, e: Entry, action: str, f: dict[str, str], q: Queue,
               now: datetime) -> str:
        w = f.get(f"w:{e.id}", "")
        target = date.fromisoformat(w) if w else None
        if form.kind == "pick":
            opinion = " ".join(f.get(f"o:{e.id}", "").split())[:OPINION_MAX] or None
            if action == "next":
                e = q.choose(e.id, now, None, opinion)
            elif action == "date":
                if target is None:
                    raise EditorialError("escolha a data")
                e = q.choose(e.id, now, target, opinion)
            elif action == "bank":
                q.bank(e.id, now, opinion)
                return "guardada no banco"
            elif action == "discard":
                q.discard(e.id, now)
                return "descartada"
            else:
                raise EditorialError(f"ação desconhecida: {action}")
            return f"escolhida para {when(e.slot, self.p.tz)}"
        if len(e.adjustments) != form.round:
            raise EditorialError("esta versão do post foi substituída; use o e-mail mais novo")
        if action == "approve":
            e = q.approve(e.id, now, target, commentary=self._chosen_text(e, f))
            return f"Aprovado para {when(e.slot, self.p.tz)}"
        if action == "reschedule":
            if target is None:
                raise EditorialError("escolha o novo horário")
            e = q.reschedule(e.id, now, target)
            return f"horário trocado para {when(e.slot, self.p.tz)}"
        if action == "adjust":
            note = f.get(f"n:{e.id}", "").strip()[:NOTE_MAX]
            if not note:
                raise EditorialError("escreva o que ajustar")
            q.request_changes(e.id, now, note)
            return "ajuste pedido; a nova versão chega em outro e-mail"
        if action == "discard":
            q.discard(e.id, now)
            return "descartado"
        raise EditorialError(f"ação desconhecida: {action}")


    @staticmethod
    def _chosen_text(e: Entry, f: dict[str, str]) -> str | None:
        """A legenda com o hook e a leitura marcados (None: post sem variantes)."""
        if e.post is None or not e.post.hooks:
            return None
        try:
            hook = int(f.get(f"h:{e.id}", "0") or 0)
        except ValueError:
            hook = 0
        sel = f.get(f"r:{e.id}", "0") or "0"
        if sel == "c":
            own = f.get(f"c:{e.id}", "").strip()[:READING_MAX]
            if not own:
                raise EditorialError("escreva a sua leitura ou escolha uma das sugeridas")
            return recompose(e.post, hook, own)
        try:
            return recompose(e.post, hook, int(sel))
        except ValueError:
            return recompose(e.post, hook, 0)


# --------------------------------------------------------------------------- auxiliares
def _variants(e: Entry) -> str:
    """Escolha do hook e da leitura (playbook.md §3 e §4). O primeiro de cada já vem marcado:
    é a combinação mostrada acima."""
    assert e.post is not None
    eid = escape(e.id)
    hooks = "".join(
        f"<label class='inline'><input type='radio' name='h:{eid}' value='{i}'"
        f"{' checked' if i == 0 else ''}> {escape(h)}</label><br>"
        for i, h in enumerate(e.post.hooks)
    )
    who = "sua opinião" if e.post.reading_is_felipe else "voz neutra"
    readings = "".join(
        f"<label class='inline'><input type='radio' name='r:{eid}' value='{i}'"
        f"{' checked' if i == 0 else ''}> {escape(r)}</label><br>"
        for i, r in enumerate(e.post.readings)
    )
    readings += (
        f"<label class='inline'><input type='radio' name='r:{eid}' value='c'> Escrever a minha"
        f"</label><textarea name='c:{eid}' maxlength='{READING_MAX}' rows='3'></textarea>"
    )
    notes = (
        "<p class='st'>Avisos da checagem: " + escape("; ".join(e.post.notes)) + "</p>"
        if e.post.notes else ""
    )
    return (
        f"<fieldset><legend>Hook (vale ao aprovar)</legend>{hooks}</fieldset>"
        f"<fieldset><legend>Leitura ({who})</legend>{readings}</fieldset>{notes}"
    )
def _get(q: Queue, eid: str) -> Entry | None:
    try:
        return q.get(eid)
    except EditorialError:
        return None


def _text(v: object) -> str:
    if isinstance(v, list):
        v = v[-1] if v else ""
    return "" if v is None else str(v)


def _hidden(name: str, value: str) -> str:
    n, v = escape(name, quote=True), escape(value, quote=True)
    return f'<input type="hidden" name="{n}" value="{v}">'


def _select(name: str, label: str, options: list[tuple[str, str]]) -> str:
    opts = "".join(f'<option value="{escape(v, quote=True)}">{escape(t)}</option>'
                   for v, t in options)
    n = escape(name, quote=True)
    return f'<label>{escape(label)}<select name="{n}">{opts}</select></label>'


def _summary(e: Entry, p: Policy) -> str:
    html = "".join(f"<p><b>{label}:</b> {escape(t)}</p>" for label, t in card_parts(e))
    html += "".join(f"<p><small>{source_link(u)}</small></p>" for u in e.sources)
    return html + f"<p><small>Vale até {e.valid_until(p):%d/%m}</small></p>"


_CSS = (
    "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:640px;"
    "margin:0 auto;padding:16px;color:#111;background:#fff;line-height:1.45}"
    "fieldset{border:1px solid #ddd;border-radius:8px;margin:0 0 16px;padding:12px}"
    "legend{font-weight:bold;padding:0 6px}label{display:block;margin:8px 0}"
    "label.inline{display:inline}select,input[type=text],textarea{display:block;width:100%;"
    "box-sizing:border-box;padding:8px;margin-top:4px;font:inherit}"
    "button{padding:12px 20px;font:inherit;font-weight:bold;background:#111;color:#fff;"
    "border:0;border-radius:6px}pre.post{white-space:pre-wrap;font-family:inherit;"
    "border-left:3px solid #ccc;padding-left:12px}.st{color:#555;font-style:italic}"
    ".shadow{background:#fff6d6;padding:8px;border-radius:6px}.res li{margin:6px 0}"
    ".stale,.error{color:#a40000}"
)
