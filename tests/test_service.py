"""Serviço HTTP do harness, testado pela interface `App.handle` (sem socket).

O relógio é fixo e o banco fica num diretório temporário. Nada chama API real.
"""

import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from linky_agents.harness import (
    AgentSpec,
    FakeProvider,
    Harness,
    ModelsConfig,
    PriceTable,
    Reply,
)
from linky_agents.service import App

TOKEN = "segredo-de-teste"
AUTH = {"X-Linky-Token": TOKEN}
# Segunda-feira, 09/11/2026, 08:00 em Brasília (11:00 UTC)
MON_8 = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock(MON_8)


@pytest.fixture
def app(tmp_path, clock):
    return App(data_dir=tmp_path, token=TOKEN, clock=clock)


def call(app, method, path, body=None, headers=AUTH):
    raw = json.dumps(body).encode() if body is not None else b""
    return app.handle(method, path, dict(headers), raw)


def test_health_responde_sem_token(app):
    status, body = call(app, "GET", "/health", headers={})
    assert status == 200
    assert body["status"] == "ok"


def test_rota_protegida_exige_token(app):
    assert call(app, "GET", "/agenda", headers={})[0] == 401
    assert call(app, "GET", "/agenda", headers={"X-Linky-Token": "errado"})[0] == 401
    assert call(app, "GET", "/agenda")[0] == 200


CARD = {
    "id": "nubank-fraude",
    "title": "Nubank usa IA na fila de fraude",
    "event_date": "2026-11-08",
    "perishable": True,
    "score": 31,
    "sources": ["https://example.com/nubank"],
}


POST = {
    "commentary": "A fila caiu 80% (segundo a Folha). @Nubank\n\n#IA",
    "alt_text": "Arte com a frase A fila caiu 80%.",
    "image": "2026-11-06-nubank-v2.png",
}


def propose(app, *cards, batch="2026-11-09-0700"):
    return call(app, "POST", "/propose", {"batch": batch, "entries": list(cards) or [CARD]})


def test_pauta_percorre_a_fila_ate_publicar(app, clock):
    assert propose(app) == (200, {"proposed": ["nubank-fraude"]})

    status, body = call(app, "POST", "/entries/nubank-fraude/choose", {})
    assert status == 200
    assert body["entry"]["state"] == "chosen"
    assert body["entry"]["slot"] == "2026-11-09T18:30:00-03:00"

    body = call(app, "POST", "/entries/nubank-fraude/drafted", POST)[1]
    assert body["entry"]["state"] == "awaiting_approval"
    saved = body["entry"]["post"]
    assert {k: saved[k] for k in POST} == POST  # guardado como Felipe aprova, sem escape
    body = call(app, "POST", "/entries/nubank-fraude/approve", {})[1]
    assert body["entry"]["state"] == "approved"
    assert call(app, "GET", "/due")[1]["entries"] == []

    clock.now = datetime(2026, 11, 9, 21, 31, tzinfo=UTC)  # 18:31 em Brasília
    due = call(app, "GET", "/due")[1]["entries"]
    assert [e["id"] for e in due] == ["nubank-fraude"]
    assert due[0]["linkedin"] == {
        "commentary": r"A fila caiu 80% \(segundo a Folha\). \@Nubank" + "\n\n#IA",
        "alt_text": POST["alt_text"],
        "image_path": "/home/node/.n8n-files/linky/2026-11-06-nubank-v2.png",
        "image_url_path": "/images/2026-11-06-nubank-v2.png",
    }

    status, body = call(
        app, "POST", "/entries/nubank-fraude/published", {"urn": "urn:li:share:1"}
    )
    assert status == 200
    assert body["entry"]["state"] == "published"
    entry = call(app, "GET", "/entries/nubank-fraude")[1]["entry"]
    assert entry["linkedin_urn"] == "urn:li:share:1"


def test_agenda_mostra_os_proximos_horarios(app):
    propose(app)
    call(app, "POST", "/entries/nubank-fraude/choose", {"when": "2026-11-11"})
    status, body = call(app, "GET", "/agenda?n=3")
    assert status == 200
    assert body["slots"] == [
        {"slot": "2026-11-09T18:30:00-03:00", "entry": None},
        {"slot": "2026-11-11T18:30:00-03:00",
         "entry": {"id": "nubank-fraude", "title": CARD["title"], "state": "chosen"}},
        {"slot": "2026-11-13T18:30:00-03:00", "entry": None},
    ]


def test_inbox_lista_pautas_sem_resposta(app):
    other = {**CARD, "id": "ramp", "title": "Ramp", "event_date": "2026-11-07"}
    propose(app, CARD, other)
    call(app, "POST", "/entries/nubank-fraude/bank")
    ids = [e["id"] for e in call(app, "GET", "/inbox")[1]["entries"]]
    assert ids == ["ramp", "nubank-fraude"]  # vence antes primeiro
    assert len(call(app, "GET", "/inbox?limit=1")[1]["entries"]) == 1


def test_proposal_plan_de_segunda_e_de_sabado(app, clock):
    plan = call(app, "GET", "/proposal_plan")[1]["plan"]
    assert plan["cards"] == 3
    assert plan["silent_mode"] is False
    clock.now = datetime(2026, 11, 14, 11, 0, tzinfo=UTC)  # sábado
    assert call(app, "GET", "/proposal_plan") == (200, {"plan": None})


def test_tick_vence_pauta_e_devolve_eventos(app, clock):
    propose(app)
    clock.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)  # validade: 08/11 + 4 dias
    status, body = call(app, "POST", "/tick")
    assert status == 200
    assert body["events"] == [
        {"kind": "expired", "entry_id": "nubank-fraude", "detail": CARD["title"]}
    ]
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["state"] == "expired"


def test_nenhuma_hoje_marca_o_lote_como_respondido(app):
    propose(app)
    assert call(app, "POST", "/batches/2026-11-09-0700/none_today") == (
        200, {"batch": "2026-11-09-0700", "answered": True},
    )
    assert call(app, "POST", "/batches/nao-existe/none_today")[0] == 404


def test_erros_viram_status_http(app):
    propose(app)
    # transição fora de ordem
    status, body = call(app, "POST", "/entries/nubank-fraude/published", {"urn": "x"})
    assert status == 409
    assert "esperado: approved" in body["error"]
    # pauta inexistente
    assert call(app, "POST", "/entries/fantasma/choose", {})[0] == 404
    # corpo fora do contrato
    assert call(app, "POST", "/entries/nubank-fraude/choose", {"quando": "amanhã"})[0] == 422
    assert app.handle("POST", "/propose", AUTH, b"{nao e json")[0] == 400
    # rota e método
    assert call(app, "GET", "/nada")[0] == 404
    assert call(app, "GET", "/propose")[0] == 405


def test_lote_repetido_nao_reabre_pautas(app):
    propose(app)
    call(app, "POST", "/entries/nubank-fraude/choose", {})
    assert propose(app)[0] == 409  # mesmo lote (n8n repetiu a chamada)
    assert propose(app, batch="outro-lote")[0] == 409  # mesma pauta noutro lote
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["state"] == "chosen"


# ------------------------------------------------------------------ agentes, gasto e alertas
class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    summary: str


ECHO = AgentSpec(name="eco", version="v1", input=EchoIn, output=EchoOut)
REPLY = Reply(text='{"summary": "ok"}', input_tokens=1000, output_tokens=100)  # US$ 0,12


@pytest.fixture
def agent_app(tmp_path, clock):
    prompts = tmp_path / "prompts" / "eco"
    prompts.mkdir(parents=True)
    (prompts / "v1.md").write_text("Resuma.\n", encoding="utf-8")
    config = ModelsConfig.model_validate({
        "providers": {"fake": {"kind": "fake"}},
        "budget": {"per_run_usd": 0.15, "per_day_usd": 0.14, "per_month_usd": 3.0,
                   "warn_ratio": 0.8, "timezone": "America/Sao_Paulo"},
        "agents": {"eco": {"max_input_tokens": 2000, "max_output_tokens": 500,
                           "chain": [{"provider": "fake", "model": "m"}]}},
    })
    prices = PriceTable.model_validate(
        {"version": "teste", "models": {"fake/m": {"input": 100.0, "output": 200.0}}}
    )
    fake = FakeProvider({"m": [REPLY, REPLY]})

    def harness(alert):
        return Harness(config, prices, tmp_path / "prompts", {"fake": fake},
                       tmp_path / "data", alert=alert, clock=clock)

    return App(data_dir=tmp_path / "data", token=TOKEN, clock=clock,
               harness_factory=harness, agents={"eco": ECHO})


def test_spending_comeca_zerado_com_os_tetos(app):
    status, body = call(app, "GET", "/spending")
    assert status == 200
    assert body["day_usd"] == 0 and body["month_usd"] == 0
    assert body["caps"] == {"run_usd": 0.15, "day_usd": 0.30, "month_usd": 3.0}


def test_agente_roda_registra_gasto_e_alerta_ao_cruzar_80_por_cento(agent_app):
    status, body = call(agent_app, "POST", "/agents/eco", {"text": "notícia"})
    assert status == 200
    assert body["output"] == {"summary": "ok"}
    assert body["cost_usd"] == pytest.approx(0.12)
    assert call(agent_app, "GET", "/spending")[1]["day_usd"] == pytest.approx(0.12)

    alerts = call(agent_app, "GET", "/alerts")[1]["alerts"]
    assert [(a["kind"], a["scope"]) for a in alerts] == [("budget_warning", "day")]
    assert alerts[0]["created_at"] == MON_8.isoformat()

    # a próxima chamada estouraria o teto do dia: não acontece e vira alerta de bloqueio
    status, body = call(agent_app, "POST", "/agents/eco", {"text": "outra"})
    assert status == 402
    assert body["scope"] == "day"
    kinds = [a["kind"] for a in call(agent_app, "GET", "/alerts")[1]["alerts"]]
    assert kinds == ["budget_warning", "budget_blocked"]


def test_alertas_saem_da_fila_so_depois_da_confirmacao(agent_app):
    call(agent_app, "POST", "/agents/eco", {"text": "notícia"})
    first = call(agent_app, "GET", "/alerts")[1]["alerts"]
    assert len(call(agent_app, "GET", "/alerts")[1]["alerts"]) == 1  # ler não consome
    status, body = call(agent_app, "POST", "/alerts/ack", {"ids": [first[0]["id"], 999]})
    assert (status, body) == (200, {"acked": [first[0]["id"]]})
    assert call(agent_app, "GET", "/alerts")[1]["alerts"] == []


def test_agente_desconhecido_ou_entrada_invalida(agent_app):
    assert call(agent_app, "POST", "/agents/nenhum", {})[0] == 404
    assert call(agent_app, "POST", "/agents/eco", {"texto": 1})[0] == 422


def test_servico_sobe_com_a_configuracao_real_e_sem_chaves_de_api(tmp_path, clock):
    def harness(alert):
        return Harness.from_repo(data_dir=tmp_path, env={}, alert=alert)

    a = App(data_dir=tmp_path, token=TOKEN, clock=clock, harness_factory=harness)
    assert call(a, "GET", "/health", headers={})[0] == 200
    assert call(a, "GET", "/spending")[1]["caps"]["month_usd"] == 3.0
    propose(a)
    assert call(a, "POST", "/entries/nubank-fraude/choose", {})[0] == 200


# ------------------------------------------------------------------ adaptador de socket
def test_servidor_http_de_verdade_responde_e_exige_o_segredo(tmp_path):
    import threading
    import urllib.error
    import urllib.request

    from linky_agents.service.server import make_server

    srv = make_server(App(data_dir=tmp_path, token=TOKEN, clock=lambda: MON_8), "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/health") as r:
            assert json.load(r)["status"] == "ok"
        req = urllib.request.Request(
            base + "/propose", method="POST", headers=AUTH,
            data=json.dumps({"batch": "b", "entries": [CARD]}).encode(),
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
            assert r.headers["Content-Type"] == "application/json; charset=utf-8"
            assert json.load(r) == {"proposed": ["nubank-fraude"]}
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/agenda")
        assert err.value.code == 401
    finally:
        srv.shutdown()
        srv.server_close()


def test_get_ignora_corpo(app):
    assert app.handle("GET", "/agenda", AUTH, b"lixo que nao e json")[0] == 200


def test_content_length_invalido_vira_400(tmp_path):
    import socket
    import threading

    from linky_agents.service.server import make_server

    srv = make_server(App(data_dir=tmp_path, token=TOKEN, clock=lambda: MON_8), "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for length in ("abc", "-5"):
            with socket.create_connection(srv.server_address, timeout=5) as s:
                s.sendall(f"POST /tick HTTP/1.1\r\nHost: x\r\nContent-Length: {length}\r\n"
                          f"X-Linky-Token: {TOKEN}\r\nConnection: close\r\n\r\n".encode())
                assert s.recv(100).startswith(b"HTTP/1.0 400")
    finally:
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------------ etapa C: e-mails e sombra
def approved_entry(app, clock, card=CARD, post=POST, when=None):
    propose(app, card, batch="lote-" + card["id"])
    call(app, "POST", f"/entries/{card['id']}/choose", {"when": when} if when else {})
    call(app, "POST", f"/entries/{card['id']}/drafted", post)
    return call(app, "POST", f"/entries/{card['id']}/approve", {})


def test_servico_comeca_em_modo_sombra(tmp_path, clock):
    app = App(data_dir=tmp_path, token=TOKEN, clock=clock)
    assert call(app, "GET", "/due")[1]["shadow"] is True
    live = App(data_dir=tmp_path, token=TOKEN, clock=clock, shadow=False)
    assert call(live, "GET", "/due")[1]["shadow"] is False


def test_lembrete_vira_email_com_prefixo_sombra(app, clock):
    propose(app)
    call(app, "POST", "/entries/nubank-fraude/choose", {})
    clock.now = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)  # 12:00 em Brasília
    status, body = call(app, "POST", "/tick")
    assert status == 200
    assert [ev["kind"] for ev in body["events"]] == ["reminder"]
    email = body["email"]
    assert email["subject"].startswith("[sombra] [linky] ")
    assert "Lembrete" in email["subject"]
    assert "aprovar até 16:30" in email["text"]
    assert "Nubank usa IA na fila de fraude" in email["html"]


def test_fora_do_modo_sombra_o_assunto_nao_tem_prefixo(tmp_path, clock):
    live = App(data_dir=tmp_path, token=TOKEN, clock=clock, shadow=False)
    propose(live)
    clock.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    email = call(live, "POST", "/tick")[1]["email"]
    assert email["subject"].startswith("[linky] ")
    assert "venc" in email["subject"].lower()


def test_tick_sem_evento_que_peca_acao_nao_gera_email(app, clock):
    assert call(app, "POST", "/tick")[1] == {"shadow": True, "events": [], "email": None}


def test_varios_eventos_num_so_email_e_titulo_escapado_no_html(app, clock):
    a = {**CARD, "id": "a", "title": "IA <script> & cia", "event_date": "2026-11-01"}
    b = {**CARD, "id": "b", "title": "Outra", "event_date": "2026-11-02"}
    propose(app, a, b)
    body = call(app, "POST", "/tick")[1]
    assert [ev["kind"] for ev in body["events"]] == ["expired", "expired"]
    assert "2 avisos" in body["email"]["subject"]
    assert "IA &lt;script&gt; &amp; cia" in body["email"]["html"]
    assert "<script>" not in body["email"]["html"]


def test_publicacao_em_sombra_traz_email_com_o_que_sairia(app, clock):
    approved_entry(app, clock)
    clock.now = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)
    body = call(app, "GET", "/due")[1]
    assert body["shadow"] is True
    email = body["entries"][0]["email"]
    assert email["subject"] == "[sombra] [linky] Publicaria agora: Nubank usa IA na fila de fraude"
    assert r"\(segundo a Folha\)" in email["text"]  # o texto exato que iria ao LinkedIn
    assert "2026-11-06-nubank-v2.png" in email["text"]
    assert POST["alt_text"] in email["html"]


def test_fora_do_modo_sombra_a_publicacao_nao_traz_email(tmp_path, clock):
    live = App(data_dir=tmp_path, token=TOKEN, clock=clock, shadow=False)
    approved_entry(live, clock)
    clock.now = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)
    assert call(live, "GET", "/due")[1]["entries"][0]["email"] is None


def test_post_em_publicacao_sai_do_due_e_nao_e_reenviado(app, clock):
    approved_entry(app, clock)
    clock.now = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)
    status, body = call(app, "POST", "/entries/nubank-fraude/publishing")
    assert status == 200
    assert body["entry"]["state"] == "publishing"
    assert call(app, "GET", "/due")[1]["entries"] == []  # n8n repetido não publica de novo
    assert call(app, "POST", "/entries/nubank-fraude/publishing")[0] == 409
    status, body = call(app, "POST", "/entries/nubank-fraude/failed", {"error": "HTTP 500"})
    assert body["entry"]["state"] == "failed"


def test_due_so_traz_o_post_do_dia_e_o_que_perdeu_o_horario_nao_passa_a_frente(app, clock):
    # ADR 0004, "post atrasado passa à frente": o de segunda perdeu o horário (sombra ou
    # n8n fora do ar) e não pode tomar o lugar do post de quarta
    other = {**CARD, "id": "ramp", "title": "Ramp", "event_date": "2026-11-09"}
    approved_entry(app, clock, card=other, when="2026-11-11")
    approved_entry(app, clock)
    clock.now = datetime(2026, 11, 11, 21, 30, tzinfo=UTC)  # qua 18:30, sem tick no meio
    assert [e["id"] for e in call(app, "GET", "/due")[1]["entries"]] == ["ramp"]


def test_post_do_dia_continua_no_due_ate_o_fim_do_dia(app, clock):
    approved_entry(app, clock)
    clock.now = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)  # seg 22:00: o n8n atrasou
    assert [e["id"] for e in call(app, "GET", "/due")[1]["entries"]] == ["nubank-fraude"]
    call(app, "POST", "/tick")
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["state"] == "approved"


def test_alertas_vem_com_email_pronto(agent_app):
    assert call(agent_app, "GET", "/alerts")[1] == {"shadow": True, "alerts": [], "email": None}
    call(agent_app, "POST", "/agents/eco", {"text": "a"})
    body = call(agent_app, "GET", "/alerts")[1]
    assert body["alerts"]
    assert body["email"]["subject"].startswith("[sombra] [linky] Alerta de custo")
    assert body["alerts"][0]["message"] in body["email"]["text"]


@pytest.mark.parametrize(("raw", "expected"), [
    (None, True), ("", True), ("on", True), ("true", True), ("1", True),
    ("off", False), ("false", False), ("0", False), (" OFF ", False),
])
def test_flag_de_modo_sombra_no_ambiente(raw, expected):
    from linky_agents.service.server import shadow_from_env
    assert shadow_from_env(raw) is expected


def test_flag_de_modo_sombra_com_valor_estranho_e_recusada():
    from linky_agents.service.server import shadow_from_env
    with pytest.raises(ValueError):
        shadow_from_env("talvez")


def test_legenda_que_passa_do_limite_do_linkedin_depois_do_escape_e_recusada(app):
    propose(app)
    call(app, "POST", "/entries/nubank-fraude/choose", {})
    longa = {**POST, "commentary": "(" * 1600}  # 1.600 caracteres, 3.200 depois do escape
    status, body = call(app, "POST", "/entries/nubank-fraude/drafted", longa)
    assert status == 422
    assert "3000" in json.dumps(body, ensure_ascii=False)
    assert call(app, "POST", "/entries/nubank-fraude/drafted", POST)[0] == 200


# ------------------------------------------------------------------ etapa E: alertas restantes
MON_1830 = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # seg 09/11 18:30 em Brasília


def test_publicacao_com_falha_vira_alerta_com_email(app, clock):
    approved_entry(app, clock)
    clock.now = MON_1830
    call(app, "POST", "/entries/nubank-fraude/publishing")
    call(app, "POST", "/entries/nubank-fraude/failed", {"error": "HTTP 500 no /rest/posts"})

    body = call(app, "GET", "/alerts")[1]
    assert [(a["kind"], a["scope"]) for a in body["alerts"]] == [("publish_failed", "publication")]
    email = body["email"]
    assert email["subject"] == (
        "[sombra] [linky] Publicação com falha: Nubank usa IA na fila de fraude"
    )
    assert "HTTP 500 no /rest/posts" in email["text"]
    assert "09/11 18:30" in email["text"]
    assert "não é reenviado" in email["text"]


def test_alerts_db_da_etapa_c_e_migrado_sem_perder_alertas(tmp_path, clock):
    import sqlite3
    con = sqlite3.connect(tmp_path / "alerts.db")  # esquema da etapa B/C, como na VPS
    con.execute(
        """CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            kind TEXT NOT NULL, scope TEXT NOT NULL, spent_usd REAL NOT NULL,
            cap_usd REAL NOT NULL, message TEXT NOT NULL, acked_at TEXT)"""
    )
    con.executemany(
        "INSERT INTO alerts(created_at, kind, scope, spent_usd, cap_usd, message, acked_at) "
        "VALUES(?,?,?,?,?,?,?)",
        [("2026-11-07T21:00:00+00:00", "budget_warning", "day", 0.25, 0.3, "lido", "x"),
         ("2026-11-07T22:00:00+00:00", "budget_warning", "month", 2.5, 3.0, "pendente", None)],
    )
    con.commit()
    con.close()

    app = App(data_dir=tmp_path, token=TOKEN, clock=clock)
    approved_entry(app, clock)
    clock.now = MON_1830
    call(app, "POST", "/entries/nubank-fraude/failed", {"error": "HTTP 401"})
    alerts = call(app, "GET", "/alerts")[1]["alerts"]
    assert [(a["id"], a["kind"]) for a in alerts] == [(2, "budget_warning"), (3, "publish_failed")]
    assert alerts[0]["spent_usd"] == 2.5
    assert "token do LinkedIn" in alerts[1]["message"]  # 401 sugere o token vencido
    App(data_dir=tmp_path, token=TOKEN, clock=clock)  # subir de novo não migra outra vez
    assert len(call(app, "GET", "/alerts")[1]["alerts"]) == 2


def test_post_preso_em_publicacao_vira_alerta_uma_vez(app, clock):
    call(app, "POST", "/linkedin/token", {"expires_on": "2027-01-05"})
    approved_entry(app, clock)
    clock.now = MON_1830
    call(app, "POST", "/entries/nubank-fraude/publishing")  # e o n8n cai no meio
    clock.now = datetime(2026, 11, 9, 21, 45, tzinfo=UTC)  # 18:45: ainda pode estar saindo
    call(app, "POST", "/tick")
    assert call(app, "GET", "/alerts")[1]["alerts"] == []

    clock.now = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)  # 19:00
    call(app, "POST", "/tick")
    body = call(app, "GET", "/alerts")[1]
    assert [a["kind"] for a in body["alerts"]] == ["publishing_stuck"]
    assert body["email"]["subject"] == (
        "[sombra] [linky] Publicação sem confirmação: Nubank usa IA na fila de fraude"
    )
    assert "desde 09/11 18:30" in body["email"]["text"]

    clock.now = datetime(2026, 11, 9, 23, 0, tzinfo=UTC)  # 20:00: não repete
    call(app, "POST", "/tick")
    assert len(call(app, "GET", "/alerts")[1]["alerts"]) == 1


def brt_noon(d: str) -> datetime:
    return datetime.fromisoformat(f"{d}T15:00:00+00:00")  # 12:00 em Brasília


def test_token_do_linkedin_avisa_a_7_dias_a_1_dia_e_vencido(app, clock):
    assert call(app, "GET", "/linkedin/token")[1] == {"expires_on": None, "days_left": None}
    status, body = call(app, "POST", "/linkedin/token", {"expires_on": "2027-01-05"})
    assert (status, body) == (200, {"expires_on": "2027-01-05", "days_left": 57})

    def tick_on(d):
        clock.now = brt_noon(d)
        call(app, "POST", "/tick")
        return [a["message"] for a in call(app, "GET", "/alerts")[1]["alerts"]]

    assert tick_on("2026-12-28") == []  # faltam 8 dias
    [msg] = tick_on("2026-12-29")
    assert "vence em 05/01/2027, daqui a 7 dias" in msg
    assert "LinkedIn account" in msg
    email = call(app, "GET", "/alerts")[1]["email"]
    assert email["subject"] == "[sombra] [linky] Token do LinkedIn"
    assert len(tick_on("2026-12-30")) == 1  # não repete a cada hora nem a cada dia
    assert "daqui a 1 dia." in tick_on("2027-01-04")[-1]
    assert "venceu em 05/01/2027" in tick_on("2027-01-06")[-1]
    assert len(tick_on("2027-01-07")) == 3


def test_token_renovado_volta_a_avisar_so_perto_da_nova_validade(app, clock):
    call(app, "POST", "/linkedin/token", {"expires_on": "2027-01-05"})
    clock.now = brt_noon("2027-01-02")
    call(app, "POST", "/tick")
    ids = [a["id"] for a in call(app, "GET", "/alerts")[1]["alerts"]]
    call(app, "POST", "/alerts/ack", {"ids": ids})
    call(app, "POST", "/linkedin/token", {"expires_on": "2027-03-03"})  # reconectado
    call(app, "POST", "/tick")
    assert call(app, "GET", "/alerts")[1]["alerts"] == []
    assert call(app, "POST", "/linkedin/token", {"expires_on": "amanhã"})[0] == 422


def test_lembrete_das_12h_sai_uma_vez_pelo_tick_de_hora_em_hora(app, clock):
    propose(app)
    call(app, "POST", "/entries/nubank-fraude/choose", {})
    call(app, "POST", "/entries/nubank-fraude/drafted", POST)  # aguardando aprovação

    def tick_at(hour_utc):
        clock.now = datetime(2026, 11, 9, hour_utc, 0, tzinfo=UTC)
        return call(app, "POST", "/tick")[1]["email"]

    assert tick_at(14) is None  # 11:00 em Brasília
    email = tick_at(15)  # 12:00
    assert email["subject"] == (
        "[sombra] [linky] Lembrete de aprovação: Nubank usa IA na fila de fraude"
    )
    assert "aprovar até 16:30" in email["text"]
    assert tick_at(16) is None  # 13:00: não repete
    call(app, "POST", "/entries/nubank-fraude/approve", {})
    assert tick_at(17) is None


def test_sem_validade_do_token_registrada_avisa_uma_vez(app, clock):
    call(app, "POST", "/tick")
    clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    call(app, "POST", "/tick")
    [alert] = call(app, "GET", "/alerts")[1]["alerts"]
    assert alert["kind"] == "linkedin_token"
    assert "não está registrada" in alert["message"]


# ------------------------------------------------- etapa H: post aprovado que perdeu o horário
TUE_0 = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)  # ter 10/11 00:00 em Brasília


def test_post_flexivel_que_perdeu_o_horario_vai_para_o_proximo_livre_e_e_revalidado(
    app, clock,
):
    approved_entry(app, clock)  # seg 09/11, "próximo horário livre"
    clock.now = TUE_0
    body = call(app, "POST", "/tick")[1]
    assert [ev["kind"] for ev in body["events"]] == ["missed_rescheduled"]
    entry = call(app, "GET", "/entries/nubank-fraude")[1]["entry"]
    assert entry["state"] == "approved"
    assert entry["slot"] == "2026-11-11T18:30:00-03:00"
    email = body["email"]
    assert email["subject"] == "[sombra] [linky] Post remarcado: Nubank usa IA na fila de fraude"
    assert "seg 09/11" in email["text"] and "qua 11/11 18:30" in email["text"]
    assert "Nada foi publicado" in email["text"]
    assert call(app, "POST", "/tick")[1]["events"] == []  # não repete

    # aprovado há mais de 48 h antes do novo horário: a revalidação de sempre (PRD §7.6)
    clock.now = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)  # qua 13:00
    assert [ev["kind"] for ev in call(app, "POST", "/tick")[1]["events"]] == ["recheck"]
    clock.now = datetime(2026, 11, 11, 21, 30, tzinfo=UTC)
    assert [e["id"] for e in call(app, "GET", "/due")[1]["entries"]] == ["nubank-fraude"]


def test_post_que_perdeu_o_horario_nunca_tira_o_horario_de_outro(app, clock):
    durable = {**CARD, "perishable": False}
    other = {**CARD, "id": "ramp", "title": "Ramp", "event_date": "2026-11-09"}
    approved_entry(app, clock, card=durable)  # seg 09/11
    approved_entry(app, clock, card=other, when="2026-11-11")
    clock.now = TUE_0
    call(app, "POST", "/tick")
    assert call(app, "GET", "/entries/ramp")[1]["entry"]["slot"] == "2026-11-11T18:30:00-03:00"
    entry = call(app, "GET", "/entries/nubank-fraude")[1]["entry"]
    assert entry["slot"] == "2026-11-13T18:30:00-03:00"


def test_post_que_perdeu_o_horario_sem_horario_antes_de_vencer_vence(app, clock):
    other = {**CARD, "id": "ramp", "title": "Ramp", "event_date": "2026-11-09"}
    approved_entry(app, clock)  # vale até 12/11
    approved_entry(app, clock, card=other, when="2026-11-11")
    clock.now = TUE_0
    body = call(app, "POST", "/tick")[1]
    assert [ev["kind"] for ev in body["events"]] == ["expired"]
    entry = call(app, "GET", "/entries/nubank-fraude")[1]["entry"]
    assert (entry["state"], entry["slot"]) == ("expired", None)
    assert "perdeu o horário de seg 09/11" in body["email"]["text"]


def test_post_com_data_escolhida_que_perdeu_o_horario_volta_para_felipe(app, clock):
    durable = {**CARD, "perishable": False}
    propose(app, durable, batch="lote-fixo")
    call(app, "POST", "/entries/nubank-fraude/choose", {"when": "2026-11-09"})
    call(app, "POST", "/entries/nubank-fraude/drafted", POST)
    [first] = call(app, "POST", "/approval_emails")[1]["emails"]
    call(app, "POST", f"/forms/{first['form_id']}/sent")  # o e-mail original saiu
    call(app, "POST", "/entries/nubank-fraude/approve", {})
    clock.now = TUE_0
    body = call(app, "POST", "/tick")[1]
    assert [ev["kind"] for ev in body["events"]] == ["missed_reapproval"]
    entry = call(app, "GET", "/entries/nubank-fraude")[1]["entry"]
    # a data era de Felipe: nada sai sem ele aprovar de novo; o horário sugerido é o próximo
    # livre, e sem aprovação no prazo vale a regra de sempre (adia ou vence)
    assert entry["state"] == "awaiting_approval"
    assert entry["slot"] == "2026-11-11T18:30:00-03:00"
    assert entry["approved_at"] is None
    assert call(app, "GET", "/due")[1]["entries"] == []
    assert "Post perdeu a data escolhida" in body["email"]["subject"]
    assert "aprovar de novo" in body["email"]["text"]
    [again] = call(app, "POST", "/approval_emails")[1]["emails"]  # novo e-mail de aprovação
    assert again["entry_id"] == "nubank-fraude" and again["form_id"] != first["form_id"]
    assert "qua 11/11 18:30" in again["email"]["subject"]
    call(app, "POST", f"/forms/{again['form_id']}/sent")
    assert call(app, "POST", "/approval_emails")[1]["emails"] == []
    # aprovar o horário sugerido é aceitar uma nova data fixa: continua "data escolhida"
    assert entry["slot_mode"] == "fixed"
    status, body = call(app, "POST", "/entries/nubank-fraude/approve", {})
    assert (status, body["entry"]["state"]) == (200, "approved")
    assert body["entry"]["slot_mode"] == "fixed"
    # só vira flexível se Felipe escolher "próximo horário livre"
    body = call(app, "POST", "/entries/nubank-fraude/reschedule", {})[1]
    assert body["entry"]["slot_mode"] == "next_free"


def test_post_publicado_ou_em_publicacao_nao_e_tocado_pela_regra(app, clock):
    approved_entry(app, clock)
    clock.now = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)
    call(app, "POST", "/entries/nubank-fraude/publishing")
    clock.now = TUE_0
    events = call(app, "POST", "/tick")[1]["events"]
    assert "missed_rescheduled" not in [ev["kind"] for ev in events]
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["state"] == "publishing"


def test_post_aprovado_que_perdeu_o_horario_tem_preferencia_sobre_post_sem_aprovacao(app, clock):
    # relógio parado de seg a qui: na mesma passagem, o aprovado (seg) e o sem aprovação (qua)
    # disputam sex 13/11; quem já foi aprovado fica com ele
    approved = {**CARD, "perishable": False}
    pending = {**CARD, "id": "ramp", "title": "Ramp", "perishable": False}
    approved_entry(app, clock, card=approved)
    propose(app, pending, batch="lote-ramp")
    call(app, "POST", "/entries/ramp/choose", {"when": "2026-11-11"})
    clock.now = datetime(2026, 11, 12, 3, 0, tzinfo=UTC)  # qui 00:00
    call(app, "POST", "/tick")
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["slot"] == (
        "2026-11-13T18:30:00-03:00")
    assert call(app, "GET", "/entries/ramp")[1]["entry"]["slot"] == "2026-11-16T18:30:00-03:00"


def test_post_aprovado_nao_precisa_do_prazo_de_aprovacao_para_pegar_o_horario(app, clock):
    approved_entry(app, clock, card={**CARD, "perishable": False})  # seg 09/11
    clock.now = datetime(2026, 11, 13, 20, 0, tzinfo=UTC)  # sex 17:00: o relógio voltou agora
    body = call(app, "POST", "/tick")[1]
    # sai hoje mesmo, aprovado há mais de 48 h: a revalidação vem na mesma passagem
    assert [ev["kind"] for ev in body["events"]] == ["missed_rescheduled", "recheck"]
    assert "sai em sex 13/11 18:30" in body["email"]["text"]
    assert call(app, "GET", "/entries/nubank-fraude")[1]["entry"]["slot"] == (
        "2026-11-13T18:30:00-03:00")
