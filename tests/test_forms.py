"""Etapa D: e-mails de decisão e formulários, testados pela interface que o n8n usa.

O link do e-mail só abre a página (GET, sem efeito). Só o envio do formulário (POST, com o
token de uso único da pauta) muda a fila.
"""

import re
from datetime import UTC, datetime
from html import unescape

import pytest

from linky_agents.service import App

TOKEN = "segredo-de-teste"
AUTH = {"X-Linky-Token": TOKEN}
FORMS_URL = "https://n8n.exemplo/webhook/linky-form"
MON_7 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)  # seg 09/11, 07:00 em Brasília


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock(MON_7)


@pytest.fixture
def app(tmp_path, clock):
    return App(data_dir=tmp_path, token=TOKEN, clock=clock, forms_url=FORMS_URL)


def call(app, method, path, body=None):
    import json
    raw = json.dumps(body).encode() if body is not None else b""
    return app.handle(method, path, dict(AUTH), raw)


def card(eid, title=None, event="2026-11-08", **kw):
    return {"id": eid, "title": title or f"Pauta {eid}", "event_date": event,
            "perishable": True, "score": 28, "sources": [f"https://fonte.exemplo/{eid}"],
            "what": f"O que aconteceu em {eid}.", "why": f"Por que {eid} importa.",
            "angle": f"Abordagem de {eid}.", **kw}


def propose(app, *cards, batch="2026-11-09-0700"):
    status, body = call(app, "POST", "/propose", {"batch": batch, "entries": list(cards)})
    assert status == 200, body


def form_id_from(email):
    m = re.search(re.escape(FORMS_URL) + r"\?f=([\w-]+)", email["html"])
    assert m, "o e-mail precisa ter o link do formulário"
    assert f"{FORMS_URL}?f={m.group(1)}" in email["text"]
    return m.group(1)


def open_form(app, fid):
    status, body = call(app, "GET", f"/forms/{fid}")
    assert status == 200
    return body


def hidden(html, name):
    m = re.search(r'name="' + re.escape(name) + r'" value="([^"]*)"', html)
    return unescape(m.group(1)) if m else None


def submit(app, fid, fields):
    status, body = call(app, "POST", f"/forms/{fid}", {"fields": fields})
    assert status == 200
    return body


def state(app, eid):
    return call(app, "GET", f"/entries/{eid}")[1]["entry"]


# ------------------------------------------------------------------ decisão 1: e-mail de pautas
def test_email_de_pautas_traz_os_cards_a_agenda_e_o_link_do_formulario(app):
    propose(app, card("a", "Nubank <usa> IA"), card("b"))
    status, body = call(app, "POST", "/proposal_email")
    assert status == 200
    email = body["email"]
    assert email["subject"].startswith("[sombra] [linky] Pautas de seg 09/11")
    for txt in ("O que aconteceu em a.", "Por que a importa.", "Abordagem de a.",
                "https://fonte.exemplo/a", "vale até 12/11"):
        assert txt in email["text"]
        assert txt in unescape(email["html"])
    assert "Nubank &lt;usa&gt; IA" in email["html"]
    assert "seg 09/11 18:30" in email["text"]  # agenda: próximos horários
    form_id_from(email)


def test_sem_pauta_nova_nem_repescagem_nao_ha_email(app, clock):
    assert call(app, "POST", "/proposal_email")[1]["email"] is None
    clock.now = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)  # sábado: não tem e-mail
    propose(app, card("a", event="2026-11-13"), batch="sab")
    assert call(app, "POST", "/proposal_email")[1] == {"plan": None, "email": None}


def test_repescagem_repete_pautas_sem_resposta_de_emails_anteriores(app, clock):
    propose(app, card("velha1", event="2026-11-08"), card("velha2", event="2026-11-09"))
    clock.now = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)  # ter 07:00
    propose(app, card("nova"), batch="2026-11-10-0700")
    body = call(app, "POST", "/proposal_email")[1]
    assert body["plan"]["new"] == ["nova"]
    assert body["plan"]["carry_over"] == ["velha1", "velha2"]
    text = body["email"]["text"]
    assert text.index("Pauta nova") < text.index("Repescagem") < text.index("Pauta velha1")
    page = open_form(app, form_id_from(body["email"]))["html"]
    for eid in ("nova", "velha1", "velha2"):
        assert hidden(page, f"t:{eid}")


# ------------------------------------------------------------------ decisão 1: formulário
def test_formulario_aplica_varias_escolhas_de_uma_vez(app):
    propose(app, card("a"), card("b", event="2026-11-09"), card("c"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    page = open_form(app, fid)
    assert page["status"] == 200
    html = page["html"]
    assert f'action="{FORMS_URL}?f={fid}"' in html and 'method="post"' in html
    result = submit(app, fid, {
        "f": fid,
        "a:a": "next", "o:a": "O Brasil está atrasado nisso.", "t:a": hidden(html, "t:a"),
        "a:b": "date", "w:b": "2026-11-13", "t:b": hidden(html, "t:b"),
        "a:c": "bank", "t:c": hidden(html, "t:c"),
    })
    assert result["status"] == 200
    a, b, c = state(app, "a"), state(app, "b"), state(app, "c")
    assert (a["state"], a["slot"], a["opinion"]) == (
        "chosen", "2026-11-09T18:30:00-03:00", "O Brasil está atrasado nisso.")
    assert (b["state"], b["slot"], b["slot_mode"]) == (
        "chosen", "2026-11-13T18:30:00-03:00", "fixed")
    assert c["state"] == "banked"
    assert "seg 09/11" in result["html"] and "sex 13/11" in result["html"]


def test_abrir_o_formulario_nao_muda_nada(app, tmp_path):
    """T4′: scanners de link só fazem GET (e HEAD). Abrir o link quantas vezes for não muda
    a fila nem gasta o token."""
    propose(app, card("a"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    dbs = [tmp_path / "editorial.db", tmp_path / "forms.db"]
    before = [db.read_bytes() for db in dbs]
    pages = [open_form(app, fid)["html"] for _ in range(5)]
    assert len(set(pages)) == 1
    assert [db.read_bytes() for db in dbs] == before
    assert state(app, "a")["state"] == "proposed"


def test_envio_sem_nada_marcado_nao_muda_nada(app):
    """Um robô que envie o formulário como veio não decide nada: o padrão é 'nada'."""
    propose(app, card("a"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    result = submit(app, fid, {"f": fid, "a:a": "", "t:a": hidden(html, "t:a")})
    assert result["status"] == 400
    assert "Nada foi marcado" in result["html"]
    assert state(app, "a")["state"] == "proposed"


def test_token_vale_uma_vez_so(app):
    propose(app, card("a"), card("b"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    fields = {"f": fid, "a:a": "bank", "t:a": hidden(html, "t:a")}
    assert submit(app, fid, fields)["status"] == 200
    # o mesmo envio de novo (botão voltar, reenvio do navegador): recusado, nada muda
    again = submit(app, fid, {**fields, "a:a": "next"})
    assert again["status"] == 409
    assert state(app, "a")["state"] == "banked"
    # a página reaberta mostra a pauta no banco, com um token novo para escolher a data
    html2 = open_form(app, fid)["html"]
    assert hidden(html2, "t:a") not in (None, hidden(html, "t:a"))
    assert submit(app, fid, {"f": fid, "a:a": "next", "t:a": hidden(html2, "t:a")})[
        "status"] == 200
    assert state(app, "a")["state"] == "chosen"


def test_token_errado_ou_de_outro_formulario_e_recusado(app):
    propose(app, card("a"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    for t in ("", "inventado", None):
        fields = {"f": fid, "a:a": "next"}
        if t is not None:
            fields["t:a"] = t
        assert submit(app, fid, fields)["status"] == 409
    assert state(app, "a")["state"] == "proposed"
    status, body = call(app, "GET", "/forms/nao-existe")
    assert (status, body["status"]) == (200, 404)


def test_nenhuma_hoje_conta_como_resposta(app):
    propose(app, card("a"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    result = submit(app, fid, {"f": fid, "none": "1", "t:none": hidden(html, "t:none")})
    assert result["status"] == 200
    assert "Nenhuma hoje" in result["html"]
    assert state(app, "a")["state"] == "proposed"  # continua valendo para a repescagem


def test_erro_numa_pauta_nao_impede_as_outras(app):
    propose(app, card("a"), card("b"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    result = submit(app, fid, {
        "f": fid,
        "a:a": "date", "w:a": "2026-11-10", "t:a": hidden(html, "t:a"),  # terça não tem horário
        "a:b": "next", "t:b": hidden(html, "t:b"),
    })
    assert result["status"] == 200
    assert "não é dia de publicação" in result["html"]
    assert state(app, "a")["state"] == "proposed"
    assert state(app, "b")["state"] == "chosen"


def test_formulario_de_pauta_vencida_mostra_venceu(app, clock):
    propose(app, card("a", event="2026-11-08"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    clock.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    call(app, "POST", "/tick")
    html = open_form(app, fid)["html"]
    assert "venceu" in html
    assert hidden(html, "t:a") is None


def test_datas_oferecidas_sao_horarios_livres_dentro_da_validade(app):
    propose(app, card("a", event="2026-11-08"), card("b", event="2026-11-09"))
    call(app, "POST", "/entries/b/choose", {"when": "2026-11-11"})
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    dates = re.findall(r'<option value="(2026-\d\d-\d\d)"', html)
    assert dates == ["2026-11-09"]  # 11/11 ocupado; 13/11 depois da validade (12/11)


# ------------------------------------------------------------------ decisão 2: aprovação
POST = {
    "commentary": "Primeira linha.\n\nSegunda <linha> com (parênteses).",
    "alt_text": "Arte com a frase Primeira linha.",
    "image": "2026-11-09-a.png",
}


def drafted(app, eid="a", when=None):
    propose(app, card(eid, event="2026-11-09"), batch="lote-" + eid)
    call(app, "POST", f"/entries/{eid}/choose", {"when": when} if when else {})
    status, body = call(app, "POST", f"/entries/{eid}/drafted", POST)
    assert status == 200, body


def approval(app):
    status, body = call(app, "POST", "/approval_emails")
    assert status == 200
    return body["emails"]


def test_post_pronto_gera_email_de_aprovacao_ate_ser_enviado(app):
    drafted(app)
    [item] = approval(app)
    assert item["entry_id"] == "a"
    assert item["image_path"] == "/home/node/.n8n-files/linky/2026-11-09-a.png"
    email = item["email"]
    assert email["subject"] == "[sombra] [linky] Aprovar post: Pauta a (seg 09/11 18:30)"
    assert "Segunda <linha> com (parênteses)." in email["text"]  # sem escape do LinkedIn
    assert "Segunda &lt;linha&gt;" in email["html"]
    assert POST["alt_text"] in email["text"]
    assert "src='cid:linky-post'" in email["html"]  # a imagem anexada pelo n8n, no corpo
    fid = form_id_from(email)
    assert fid == item["form_id"]
    assert [i["form_id"] for i in approval(app)] == [fid]  # sem confirmação, volta igual
    assert call(app, "POST", f"/forms/{fid}/sent")[0] == 200
    assert approval(app) == []


def approval_form(app):
    [item] = approval(app)
    call(app, "POST", f"/forms/{item['form_id']}/sent")
    return item["form_id"]


def test_aprovar_pelo_formulario(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    assert "Segunda &lt;linha&gt;" in html
    result = submit(app, fid, {"f": fid, "a:a": "approve", "t:a": hidden(html, "t:a")})
    assert result["status"] == 200
    assert state(app, "a")["state"] == "approved"
    assert "Aprovado" in result["html"] and "seg 09/11 18:30" in result["html"]


def test_aprovar_trocando_o_horario(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    submit(app, fid, {"f": fid, "a:a": "approve", "w:a": "2026-11-13",
                      "t:a": hidden(html, "t:a")})
    e = state(app, "a")
    assert (e["state"], e["slot"]) == ("approved", "2026-11-13T18:30:00-03:00")


def test_so_trocar_o_horario_sem_aprovar(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    r = submit(app, fid, {"f": fid, "a:a": "reschedule", "w:a": "2026-11-11",
                          "t:a": hidden(html, "t:a")})
    assert r["status"] == 200
    e = state(app, "a")
    assert (e["state"], e["slot"]) == ("awaiting_approval", "2026-11-11T18:30:00-03:00")
    # o mesmo formulário, reaberto, ainda serve para aprovar
    html = open_form(app, fid)["html"]
    submit(app, fid, {"f": fid, "a:a": "approve", "t:a": hidden(html, "t:a")})
    assert state(app, "a")["state"] == "approved"


def test_pedir_ajuste_exige_o_que_mudar_e_gera_nova_versao(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    r = submit(app, fid, {"f": fid, "a:a": "adjust", "n:a": "", "t:a": hidden(html, "t:a")})
    assert "o que ajustar" in r["html"]
    assert state(app, "a")["state"] == "awaiting_approval"
    r = submit(app, fid, {"f": fid, "a:a": "adjust", "n:a": "Tire o segundo parágrafo.",
                          "t:a": hidden(html, "t:a")})
    assert r["status"] == 200
    e = state(app, "a")
    assert (e["state"], e["adjustments"]) == ("chosen", ["Tire o segundo parágrafo."])
    assert e["slot"] == "2026-11-09T18:30:00-03:00"  # o horário continua reservado
    assert "aguardando nova versão" in open_form(app, fid)["html"]
    # nova versão do post: novo e-mail, com outro formulário
    call(app, "POST", "/entries/a/drafted", {**POST, "commentary": "Só a primeira linha."})
    [item] = approval(app)
    assert item["form_id"] != fid
    assert "Versão 2 do post" in item["email"]["text"]
    assert "Tire o segundo parágrafo." in item["email"]["text"]  # o pedido, para conferir
    assert "a nova versão está em outro e-mail" in open_form(app, fid)["html"]


def test_descartar_pelo_formulario(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    submit(app, fid, {"f": fid, "a:a": "discard", "t:a": hidden(html, "t:a")})
    assert state(app, "a")["state"] == "discarded"


def test_aprovacao_tambem_vale_uma_vez(app):
    drafted(app)
    fid = approval_form(app)
    html = open_form(app, fid)["html"]
    fields = {"f": fid, "a:a": "approve", "t:a": hidden(html, "t:a")}
    submit(app, fid, fields)
    assert submit(app, fid, {**fields, "a:a": "discard"})["status"] == 409
    assert state(app, "a")["state"] == "approved"


def test_fora_da_sombra_o_assunto_nao_tem_prefixo(tmp_path, clock):
    live = App(data_dir=tmp_path, token=TOKEN, clock=clock, forms_url=FORMS_URL, shadow=False)
    drafted(live)
    assert approval(live)[0]["email"]["subject"].startswith("[linky] Aprovar post")


# ------------------------------------------------------------------ revisão de código
def test_fonte_com_esquema_perigoso_nao_vira_link(app):
    propose(app, card("a", sources=["javascript:alert(1)", "https://ok.exemplo/x"]))
    email = call(app, "POST", "/proposal_email")[1]["email"]
    html = open_form(app, form_id_from(email))["html"]
    for doc in (email["html"], html):
        assert "href='javascript" not in doc and 'href="javascript' not in doc
        assert "href='https://ok.exemplo/x'" in doc


def test_email_de_pautas_respeita_o_numero_de_cards_do_horario(app):
    propose(app, *[card(f"p{i}", score=20 + i) for i in range(5)])
    body = call(app, "POST", "/proposal_email")[1]
    assert body["plan"]["new"] == ["p4", "p3", "p2"]  # 3 cards de segunda, os de maior nota


def test_resposta_pela_repescagem_tira_do_modo_silencioso(app, clock):
    propose(app, card("velha", event="2026-11-09"), batch="b0")
    for i, day in enumerate((10, 11, 12), start=1):  # três e-mails seguidos sem resposta
        clock.now = datetime(2026, 11, day, 10, 0, tzinfo=UTC)
        propose(app, card(f"n{i}", event=f"2026-11-{day}"), batch=f"b{i}")
    assert call(app, "GET", "/proposal_plan")[1]["plan"] is None  # em silêncio, só domingo
    call(app, "POST", "/entries/velha/bank")  # responde a uma pauta do lote mais antigo
    assert call(app, "GET", "/proposal_plan")[1]["plan"]["silent_mode"] is False


def test_nenhuma_hoje_com_lote_sumido_volta_pagina_e_nao_json(app):
    propose(app, card("a"))
    fid = form_id_from(call(app, "POST", "/proposal_email")[1]["email"])
    html = open_form(app, fid)["html"]
    import sqlite3
    con = sqlite3.connect(app.db)
    with con:
        con.execute("DELETE FROM batches")
    con.close()
    status, body = call(app, "POST", f"/forms/{fid}",
                        {"fields": {"none": "1", "t:none": hidden(html, "t:none")}})
    assert status == 200 and "html" in body
