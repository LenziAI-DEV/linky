"""E-mails que o n8n entrega: assunto, HTML e texto redigidos aqui, onde há teste.

O n8n só transporta (Resend). Em modo sombra, todo assunto ganha o prefixo `[sombra]`,
para Felipe saber que nada daquilo mudou o mundo real. Texto vindo da web (títulos de
pauta) é escapado no HTML.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, tzinfo
from html import escape
from zoneinfo import ZoneInfo

from ..editorial import Entry, Event, Policy, State

SHADOW_PREFIX = "[sombra] "

# Eventos do relógio que pedem ação (ou atenção) de Felipe: tipo -> (rótulo, o que fazer).
# "pulled_forward" fica de fora: só antecipa um post já aprovado e aparece na agenda do
# próximo e-mail de pautas.
ACTIONABLE = {
    "reminder": ("Lembrete de aprovação",
                 "Sem aprovação até o prazo, o post é adiado para o próximo horário livre."),
    "postponed": ("Post adiado", "Faltou a aprovação no prazo. Nada foi publicado."),
    "expired": ("Pauta vencida", "A pauta passou da validade e saiu da fila."),
    "missed_rescheduled": (
        "Post remarcado",
        "Nada foi publicado no horário original (n8n fora do ar ou, em sombra, porque nada é "
        "publicado). O post continua aprovado; se a aprovação tiver mais de 48 horas no novo "
        "horário, você recebe a revalidação no dia.",
    ),
    "missed_reapproval": (
        "Post perdeu a data escolhida",
        "Nada foi publicado. Como a data era sua, o post só sai se você aprovar de novo (pode "
        "trocar o horário) pelo e-mail de aprovação; sem aprovação no prazo, é adiado ou vence.",
    ),
    "recheck": ("Revalidar post aprovado",
                "Foi aprovado há mais de 48 horas e sai hoje. Confira se ainda faz sentido; "
                "para segurar, descarte ou remarque antes das 18:30."),
}


def _email(subject: str, lines: list[str], html_blocks: list[str], shadow: bool) -> dict:
    prefix = SHADOW_PREFIX if shadow else ""
    note_txt = ["", "(Modo sombra: nada foi publicado nem alterado no LinkedIn.)"] if shadow else []
    note_html = (
        ["<p style='color:#777'><i>Modo sombra: nada foi publicado nem alterado no "
         "LinkedIn.</i></p>"] if shadow else []
    )
    return {
        "subject": f"{prefix}[linky] {subject}",
        "text": "\n".join(lines + note_txt),
        "html": "".join(html_blocks + note_html),
    }


def tick_email(events: Iterable[Event], entries: dict[str, Entry], shadow: bool) -> dict | None:
    """Um e-mail com todos os eventos do relógio que pedem ação, ou None."""
    todo = [ev for ev in events if ev.kind in ACTIONABLE]
    if not todo:
        return None
    if len(todo) == 1:
        subject = f"{ACTIONABLE[todo[0].kind][0]}: {_title(todo[0], entries)}"
    else:
        subject = f"{len(todo)} avisos da fila editorial"
    lines, blocks = [], ["<p>Olá, Felipe.</p><ul>"]
    for ev in todo:
        label, hint = ACTIONABLE[ev.kind]
        lines.append(f"- {label}: {ev.detail}\n  {hint}")
        blocks.append(
            f"<li><b>{escape(label)}</b>: {escape(ev.detail)}<br>"
            f"<small>{escape(hint)}</small></li>"
        )
    blocks.append("</ul>")
    return _email(subject, lines, blocks, shadow)


def _title(ev: Event, entries: dict[str, Entry]) -> str:
    e = entries.get(ev.entry_id or "")
    return e.title if e else ev.detail


def shadow_publication_email(e: Entry, linkedin: dict, tz: ZoneInfo) -> dict:
    """Em modo sombra, o registro do que a publicação faria (nada vai ao LinkedIn).
    `linkedin` é o post no formato do LinkedIn (legenda já escapada)."""
    slot = f"{e.slot.astimezone(tz):%d/%m %H:%M}" if e.slot else "?"
    commentary, n = linkedin["commentary"], len(linkedin["commentary"])
    lines = [
        f"Pauta: {e.id} (horário {slot})",
        f"Imagem: {linkedin['image_path']}",
        f"Texto alternativo: {linkedin['alt_text']}",
        f"Legenda ({n} caracteres, já escapada):",
        "",
        commentary,
    ]
    blocks = [
        f"<p>Esta publicação <b>sairia agora</b> no LinkedIn ({escape(slot)}).</p>",
        f"<p><b>Pauta:</b> {escape(e.id)}<br><b>Imagem:</b> "
        f"{escape(linkedin['image_path'])}<br><b>Texto alternativo:</b> "
        f"{escape(linkedin['alt_text'])}</p>",
        f"<p><b>Legenda</b> ({n} caracteres, já escapada):</p>",
        "<pre style='white-space:pre-wrap;font-family:inherit'>"
        f"{escape(commentary)}</pre>",
    ]
    return _email(f"Publicaria agora: {e.title}", lines, blocks, shadow=True)


COST_KINDS = {"budget_warning", "budget_blocked"}
# Alertas de operação (etapa E): tipo -> rótulo do assunto
ALERT_LABELS = {
    "publish_failed": "Publicação com falha",
    "publishing_stuck": "Publicação sem confirmação",
    "linkedin_token": "Token do LinkedIn",
    "linkedin_session": "Coletor de métricas parado",
    "pipeline": "Esteira com falha",
    "metrics_stale": "Coletor de métricas sem leitura",
}


def curate_failed_message(err: Exception) -> str:
    return (
        "A curadoria das pautas falhou e o e-mail deste horário sai só com a repescagem "
        f"(se houver). Erro: {err}"
    )


def curate_empty_message(start: datetime, end: datetime, tz: ZoneInfo) -> str:
    return (
        "A curadoria não achou nenhum item coletado entre "
        f"{start.astimezone(tz):%d/%m %H:%M} e {end.astimezone(tz):%d/%m %H:%M}: a coleta "
        "(cron a cada 3 horas na VPS, ops/collect.sh) pode estar parada. O e-mail deste "
        "horário sai só com a repescagem."
    )


def draft_failed_message(e: Entry, err: Exception, n: int, limit: int) -> str:
    then = (
        "A próxima chamada (em até 15 minutos) tenta de novo."
        if n < limit
        else "Parei de tentar: a pauta voltou ao banco e o horário ficou livre. Ela aparece na "
        "repescagem do próximo e-mail de pautas, se você quiser escolhê-la de novo."
    )
    return f"A redação do post da pauta \"{e.title}\" falhou ({n} de {limit}). {then} Erro: {err}"


def publish_failed_message(e: Entry, error: str, tz: ZoneInfo) -> str:
    slot = f"{e.slot.astimezone(tz):%d/%m %H:%M}" if e.slot else "sem horário"
    hint = (
        " O erro parece de autorização: confira se o token do LinkedIn venceu."
        if re.search(r"\b401\b", error) else ""
    )
    return (
        f"A publicação de \"{e.title}\" (horário {slot}) falhou: {error}.{hint} "
        "O post não é reenviado sozinho: confira no LinkedIn se algo saiu e decida "
        "o que fazer com a pauta."
    )


def publishing_stuck_message(e: Entry, since: datetime, tz: ZoneInfo) -> str:
    return (
        f"O post \"{e.title}\" está em publicação desde {since.astimezone(tz):%d/%m %H:%M} "
        "e o n8n não confirmou o resultado. Confira no LinkedIn se ele saiu e registre o "
        "resultado na fila (ops/README.md, \"Post preso em publicação\")."
    )


LINKEDIN_TOKEN_UNKNOWN = (
    "A validade do token do LinkedIn (credencial \"LinkedIn account\" no n8n) não está "
    "registrada no linky-agents, então o aviso de 7 dias antes de vencer não pode sair. "
    "Registre a data (POST /linkedin/token, ver ops/README.md)."
)


def linkedin_token_message(expires_on: date, days_left: int) -> str:
    when = (
        f"venceu em {expires_on:%d/%m/%Y}" if days_left < 0
        else f"vence hoje ({expires_on:%d/%m/%Y})" if days_left == 0
        else f"vence em {expires_on:%d/%m/%Y}, daqui a {days_left} "
             f"dia{'s' if days_left > 1 else ''}"
    )
    return (
        f"O token do LinkedIn (credencial \"LinkedIn account\" no n8n) {when}. "
        "Sem ele, a publicação falha. Reconecte a credencial no n8n e registre a nova "
        "validade no linky-agents (POST /linkedin/token, ver ops/README.md)."
    )


def _alerts_subject(alerts: list[dict]) -> str:
    if all(a["kind"] in COST_KINDS for a in alerts):
        return (
            f"Alerta de custo ({alerts[0]['scope']})" if len(alerts) == 1
            else f"Alerta de custo: {len(alerts)} avisos"
        )
    if len(alerts) > 1:
        return f"{len(alerts)} alertas"
    a = alerts[0]
    label = ALERT_LABELS.get(a["kind"], "Alerta")
    return f"{label}: {a['title']}" if a.get("title") else label


def alerts_email(alerts: list[dict], shadow: bool) -> dict | None:
    if not alerts:
        return None
    subject = _alerts_subject(alerts)
    lines = [f"- {a['message']}" for a in alerts]
    blocks = ["<ul>", *(f"<li>{escape(a['message'])}</li>" for a in alerts), "</ul>"]
    return _email(subject, lines, blocks, shadow)


# --------------------------------------------------------------------------- etapa D
# Os dois e-mails de decisão só levam um link para o formulário. O link abre a página
# (GET, sem efeito); só o envio do formulário (POST, com token de uso único) decide algo.
_DAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_BUTTON = ("display:inline-block;padding:12px 20px;background:#111;color:#fff;"
           "text-decoration:none;border-radius:6px;font-weight:bold")
_LINK_NOTE = "O link só abre o formulário: nada muda até você marcar e enviar."
# A imagem do post vai anexada pelo n8n com este Content-ID e aparece no corpo do e-mail
IMAGE_CID = "linky-post"


def when(dt: datetime, tz: tzinfo) -> str:
    """'seg 09/11 18:30' no fuso da política."""
    local = dt.astimezone(tz)
    return f"{_DAYS[local.weekday()]} {local:%d/%m %H:%M}"


def day(d: date) -> str:
    return f"{_DAYS[d.weekday()]} {d:%d/%m}"


def card_parts(e: Entry) -> list[tuple[str, str]]:
    """O card como Felipe lê (no e-mail e no formulário): só as partes preenchidas."""
    parts = [("O que aconteceu", e.what), ("Por que importa", e.why), ("Abordagem", e.angle)]
    return [(label, txt) for label, txt in parts if txt]


def source_link(url: str) -> str:
    """Link para a fonte. Fontes vêm da web: só http(s) vira link (nada de `javascript:`)."""
    if url.lower().startswith(("https://", "http://")):
        return f"<a href='{escape(url, quote=True)}' rel='noreferrer'>{escape(url)}</a>"
    return escape(url)


def _card(e: Entry, policy: Policy, n: int) -> tuple[list[str], str]:
    valid = f"vale até {e.valid_until(policy):%d/%m}"
    kind = "perecível" if e.perishable else "duradoura"
    meta = f"nota {e.score} · {kind} · {valid}"
    if e.state == State.BANKED:
        meta += " · no banco"
    lines = [f"{n}. {e.title}", f"   {meta}"]
    lines += [f"   {label}: {txt}" for label, txt in card_parts(e)]
    lines += [f"   Fonte: {u}" for u in e.sources]
    html = [f"<div style='margin:0 0 18px'><b>{n}. {escape(e.title)}</b><br>"
            f"<small style='color:#666'>{escape(meta)}</small>"]
    html += [f"<br><b>{label}:</b> {escape(txt)}" for label, txt in card_parts(e)]
    html += [f"<br><small>Fonte: {source_link(u)}</small>" for u in e.sources]
    html.append("</div>")
    return lines, "".join(html)


def proposal_email(
    plan: dict, new: list[Entry], carry: list[Entry], policy: Policy, link: str,
    now: datetime, shadow: bool,
) -> dict:
    """Decisão 1: as pautas novas, a repescagem, a agenda e o link do formulário."""
    today = now.astimezone(policy.tz).date()
    lines = [f"Pautas de {day(today)}.", ""]
    blocks = [f"<p>Pautas de {escape(day(today))}.</p>"]
    if plan.get("silent_mode"):
        note = ("Modo silencioso: os e-mails diários pararam porque os últimos ficaram sem "
                "resposta. Qualquer resposta reativa tudo.")
        lines += [note, ""]
        blocks.append(f"<p><i>{escape(note)}</i></p>")
    n = 0
    for title, group in (("Pautas novas", new), ("Repescagem (ainda valem)", carry)):
        if not group:
            continue
        lines += [f"== {title} ==", ""]
        blocks.append(f"<h3>{escape(title)}</h3>")
        for e in group:
            n += 1
            txt, html = _card(e, policy, n)
            lines += [*txt, ""]
            blocks.append(html)
    lines.append("== Agenda ==")
    blocks.append("<h3>Agenda</h3><ul>")
    for s in plan["agenda"]:
        slot = when(datetime.fromisoformat(s["slot"]), policy.tz)
        what = s["entry"] or "(livre)"
        lines.append(f"- {slot}: {what}")
        blocks.append(f"<li>{escape(slot)}: {escape(what)}</li>")
    blocks.append("</ul>")
    lines += ["", f"Escolher pautas: {link}", _LINK_NOTE]
    blocks.append(f"<p><a href='{escape(link, quote=True)}' style='{_BUTTON}'>Escolher pautas"
                  f"</a></p><p><small>{escape(_LINK_NOTE)}</small></p>")
    subject = f"Pautas de {day(today)} ({n} {'pauta' if n == 1 else 'pautas'})"
    return _email(subject, lines, blocks, shadow)


def approval_email(e: Entry, policy: Policy, link: str, image: str, shadow: bool) -> dict:
    """Decisão 2: o post exato (legenda sem escape, como Felipe aprova), o horário e o link."""
    assert e.post is not None
    slot = when(e.slot, policy.tz) if e.slot else "sem horário"
    version = len(e.adjustments) + 1
    head = f"Aprovar post{f' (versão {version})' if version > 1 else ''}"
    lines = [f"Pauta: {e.title}", f"Horário reservado: {slot}"]
    blocks = [f"<p><b>Pauta:</b> {escape(e.title)}<br><b>Horário reservado:</b> "
              f"{escape(slot)}</p>"]
    if version > 1:
        asked = e.adjustments[-1]
        lines.append(f"Versão {version} do post. Ajuste pedido: {asked}")
        blocks.append(f"<p>Versão {version} do post. <b>Ajuste pedido:</b> "
                      f"{escape(asked)}</p>")
    lines += ["", "Legenda:", "", e.post.commentary, "",
              f"Texto alternativo: {e.post.alt_text}", f"Imagem: {image} (em anexo)"]
    blocks += [
        "<p><b>Legenda:</b></p>",
        "<pre style='white-space:pre-wrap;font-family:inherit;border-left:3px solid #ccc;"
        f"padding-left:12px'>{escape(e.post.commentary)}</pre>",
        f"<p><img src='cid:{IMAGE_CID}' alt='{escape(e.post.alt_text, quote=True)}' "
        "style='max-width:100%;border:1px solid #ddd'></p>",
        f"<p><b>Texto alternativo:</b> {escape(e.post.alt_text)}<br>"
        f"<b>Imagem:</b> {escape(image)} (em anexo)</p>",
    ]
    if e.post.hooks and (len(e.post.hooks) > 1 or len(e.post.readings) > 1):
        alt_h = [f"{i}) {h}" for i, h in enumerate(e.post.hooks, 1)]
        alt_r = [f"{chr(64 + i)}) {r}" for i, r in enumerate(e.post.readings, 1)]
        lines += ["", "Hooks (o 1 está no texto acima):", *alt_h,
                  "", "Leituras (a A está no texto acima):", *alt_r,
                  "Escolha o hook e a leitura no formulário, ou escreva a sua leitura."]
        blocks += [
            "<p><b>Hooks</b> (o 1 está no texto acima):<br>"
            + "<br>".join(escape(x) for x in alt_h) + "</p>",
            "<p><b>Leituras</b> (a A está no texto acima):<br>"
            + "<br>".join(escape(x) for x in alt_r) + "</p>",
            "<p>Escolha o hook e a leitura no formulário, ou escreva a sua leitura.</p>",
        ]
    if e.post.notes:
        lines += ["", "Avisos da checagem: " + "; ".join(e.post.notes)]
        blocks.append("<p><b>Avisos da checagem:</b> " + escape("; ".join(e.post.notes))
                      + "</p>")
    deadline = when(policy.deadline(e.slot), policy.tz) if e.slot else None
    tail = f"Aprovar (com o hook e a leitura), ajustar, descartar ou trocar o horário: {link}"
    lines += ["", tail, _LINK_NOTE]
    if deadline:
        lines.append(f"Prazo para aprovar: {deadline}.")
    blocks.append(f"<p><a href='{escape(link, quote=True)}' style='{_BUTTON}'>Abrir formulário"
                  f"</a></p><p><small>{escape(_LINK_NOTE)}"
                  f"{f' Prazo para aprovar: {escape(deadline)}.' if deadline else ''}"
                  "</small></p>")
    return _email(f"{head}: {e.title} ({slot})", lines, blocks, shadow)
