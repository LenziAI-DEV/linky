"""Orquestração da esteira no serviço (docs/ideas/producao-mvp.md), com agentes falsos.

Cobre: `POST /curate` (itens → pautas), `POST /draft_next` (pauta escolhida → post com
variantes e imagem), `GET /images/{nome}`, falha da redação e a escolha do hook e da leitura
no formulário de aprovação.
"""

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from html import unescape

import pytest

from linky_agents.agents.contracts import CardOut, Draft, Hook, ImageResult
from linky_agents.service import App

TOKEN = "segredo-de-teste"
AUTH = {"X-Linky-Token": TOKEN}
FORMS_URL = "https://n8n.exemplo/webhook/linky-form"
MON_7 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)  # seg 09/11, 07:00 em Brasília
PNG = b"\x89PNG\r\n\x1a\nfalso"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class FakeAgents:
    def __init__(self):
        self.curated: list[dict] = []
        self.written: list[str] = []
        self.fail_write = False

    def curate(self, items, *, now, n_cards, exclude):
        self.curated.append({"items": items, "n": n_cards, "exclude": exclude})
        return [
            CardOut(id=f"2026-11-08-{it['id']}", title=f"Pauta {it['id']}",
                    event_date="2026-11-08", score=28, sources=[it["url"]],
                    what="O fato.", why="Importa.", angle="A tese.", pattern="P2",
                    audience="gestor")
            for it in items[:n_cards]
        ]

    def write(self, entry, *, recent_hooks):
        if self.fail_write:
            raise RuntimeError("modelo fora do ar")
        self.written.append(entry.id)
        ajuste = f" Ajuste: {entry.adjustments[-1]}." if entry.adjustments else ""
        return Draft(
            structure="E1",
            hooks=[Hook(kind="H2", text="Quatro corridas."),
                   Hook(kind="H1", text="Agentes pediram 4 corridas. O app pediu milhões."),
                   Hook(kind="H5", text="Agente de IA ainda não é canal.")],
            body="O número saiu no balanço do trimestre." + ajuste,
            readings=["O ponto que importa: o cliente ainda não delegou.",
                      "O ponto que importa: canal novo pede métrica."],
            tail="Uma ressalva: são números da própria empresa.\n\nVocê delegaria? Sim ou não?",
            closing="escolha",
            headline="4 corridas",
            notes=["conferir o trimestre"],
        )

    def image(self, entry, draft):
        return ImageResult(png=PNG, alt_text="Arte: o número 4 em destaque.",
                           composition={}, theme="claro")


@pytest.fixture
def clock():
    return Clock(MON_7)


@pytest.fixture
def agents():
    return FakeAgents()


@pytest.fixture
def items_dir(tmp_path):
    d = tmp_path / "items"
    d.mkdir()
    rows = [
        {"id": f"i{n}", "source": "tecnoblog", "title": f"Notícia {n}", "url": f"https://x/{n}",
         "summary": "", "published_utc": f"2026-11-09T0{n + 1}:00:00+00:00",
         "published_brt_date": "2026-11-08"}
        for n in range(5)
    ]
    old = {**rows[0], "id": "velho", "published_utc": "2026-11-01T10:00:00+00:00"}
    (d / "2026-11-08.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [*rows, old]) + "\n", encoding="utf-8")
    return d  # a janela da seg 07:00 começa no e-mail de domingo, 21:00 (seg 00:00 UTC)


@pytest.fixture
def app(tmp_path, clock, agents, items_dir):
    return App(data_dir=tmp_path / "data", token=TOKEN, clock=clock, forms_url=FORMS_URL,
               items_dir=items_dir, pipeline_agents=agents)


def call(app, method, path, body=None):
    raw = json.dumps(body).encode() if body is not None else b""
    return app.handle(method, path, dict(AUTH), raw)


def form_link(email):
    return re.search(re.escape(FORMS_URL) + r"\?f=([\w-]+)", email["html"]).group(1)


def hidden(html, name):
    m = re.search(r'name="' + re.escape(name) + r'" value="([^"]*)"', html)
    return unescape(m.group(1)) if m else None


def chosen_entry(app, agents):
    """Cura, escolhe a primeira pauta pelo formulário e devolve o ID."""
    assert call(app, "POST", "/curate")[0] == 200
    email = call(app, "POST", "/proposal_email")[1]["email"]
    fid = form_link(email)
    eid = "2026-11-08-i0"
    html = call(app, "GET", f"/forms/{fid}")[1]["html"]
    fields = {"f": fid, f"a:{eid}": "next", f"t:{eid}": hidden(html, f"t:{eid}")}
    assert call(app, "POST", f"/forms/{fid}", {"fields": fields})[0] == 200
    return eid


# ------------------------------------------------------------------------- curadoria
def test_curate_propoe_as_pautas_da_janela_com_padrao_e_publico(app, agents):
    status, body = call(app, "POST", "/curate")
    assert status == 200
    assert body["proposed"] == ["2026-11-08-i0", "2026-11-08-i1", "2026-11-08-i2"]
    assert body["items"] == 5  # o item fora da janela ficou de fora
    entry = call(app, "GET", "/entries/2026-11-08-i0")[1]["entry"]
    assert (entry["pattern"], entry["audience"]) == ("P2", "gestor")
    # As pautas novas entram no e-mail das 07:00
    plan = call(app, "POST", "/proposal_email")[1]["plan"]
    assert plan["new"][:3] == body["proposed"]


def test_curate_nao_duplica_o_lote_do_mesmo_horario(app, agents):
    call(app, "POST", "/curate")
    status, body = call(app, "POST", "/curate")
    assert status == 200 and body["proposed"] == []
    assert "já foram propostas" in body["reason"]
    assert len(agents.curated) == 1


def test_curate_com_o_relogio_real_domingo_e_depois_segunda(app, agents, clock, items_dir):
    """O n8n chama segundos depois do horário: a janela e as pautas novas se ancoram no
    horário agendado, não no relógio (regressão achada na simulação de 16/11)."""
    sunday = [{"id": f"s{n}", "source": "tecnoblog", "title": f"Domingo {n}",
               "url": f"https://x/s{n}", "summary": "",
               "published_utc": f"2026-11-08T1{n}:00:00+00:00",
               "published_brt_date": "2026-11-08"} for n in range(3)]
    with (items_dir / "2026-11-08.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in sunday) + "\n")
    clock.now = datetime(2026, 11, 9, 0, 0, 20, tzinfo=UTC)  # dom 21:00:20 em Brasília
    sun = call(app, "POST", "/curate")[1]
    assert sun["proposed"] and all("-s" in i or "velho" in i for i in sun["proposed"])
    assert call(app, "POST", "/curate")[1]["proposed"] == []  # repetir não duplica
    clock.now = MON_7 + timedelta(seconds=35)  # seg 07:00:35
    mon = call(app, "POST", "/curate")[1]
    assert mon["proposed"] == ["2026-11-08-i0", "2026-11-08-i1", "2026-11-08-i2"]
    clock.now += timedelta(seconds=40)
    plan = call(app, "POST", "/proposal_email")[1]["plan"]
    assert plan["new"] == mon["proposed"]  # as de domingo vão para a repescagem
    assert not set(plan["carry_over"]) & set(mon["proposed"])


def test_curate_fora_do_horario_de_pautas_nao_faz_nada(app, agents, clock):
    clock.now = datetime(2026, 11, 14, 13, 0, tzinfo=UTC)  # sábado: sem pautas
    status, body = call(app, "POST", "/curate")
    assert status == 200 and body["proposed"] == []
    assert agents.curated == []


# ------------------------------------------------------------------------- redação
def test_draft_next_transforma_a_escolhida_em_post_com_variantes_e_imagem(app, agents, clock):
    eid = chosen_entry(app, agents)
    clock.now += timedelta(minutes=5)
    status, body = call(app, "POST", "/draft_next")
    assert status == 200 and body == {"drafted": eid, "image": f"{eid}-v1.png"}
    post = call(app, "GET", f"/entries/{eid}")[1]["entry"]["post"]
    assert post["commentary"].startswith("Quatro corridas.\n\nO número saiu")
    assert len(post["hooks"]) == 3 and len(post["readings"]) == 2
    status, img = call(app, "GET", f"/images/{eid}-v1.png")
    assert status == 200 and base64.b64decode(img["base64"]) == PNG
    # Nada mais a redigir
    assert call(app, "POST", "/draft_next")[1] == {"drafted": None}


def test_post_descartado_sai_do_registro_da_arte(app, agents, tmp_path):
    from linky_agents.render.compose import Composition
    from linky_agents.render.registry import CompositionRegistry

    eid = chosen_entry(app, agents)
    call(app, "POST", "/draft_next")
    el = {"kind": "rect", "x": 72, "y": 300, "w": 50, "h": 50, "fill": "ink"}
    comp = Composition.model_validate({"background": "paper",
                                       "pieces": [{"name": "manchete", "elements": [el]}]})
    reg = CompositionRegistry(tmp_path / "data" / "compositions.db")
    reg.record(eid, comp)
    reg.record("outro-post", comp)
    assert call(app, "POST", f"/entries/{eid}/discard", {})[0] == 200
    call(app, "POST", "/draft_next")
    assert [r.post for r in reg.recent()] == ["outro-post"]


def test_imagem_inexistente_ou_nome_invalido(app):
    assert call(app, "GET", "/images/nada.png")[0] == 404
    assert call(app, "GET", "/images/..%2Fforms.db")[0] == 422


def test_falha_na_redacao_avisa_e_para_depois_de_duas(app, agents, clock):
    eid = chosen_entry(app, agents)
    agents.fail_write = True
    for _ in (1, 2):
        status, body = call(app, "POST", "/draft_next")
        assert status == 200 and body["failed"] == eid
    assert call(app, "POST", "/draft_next")[1] == {"drafted": None}  # parou de tentar
    alerts = [a for a in call(app, "GET", "/alerts")[1]["alerts"] if a["kind"] == "pipeline"]
    assert len(alerts) == 2 and "Parei de tentar" in alerts[-1]["message"]
    # A pauta não fica presa ocupando o horário: volta ao banco, e escolhê-la de novo
    # recomeça a contagem de falhas
    entry = call(app, "GET", f"/entries/{eid}")[1]["entry"]
    assert entry["state"] == "banked" and entry["slot"] is None
    assert call(app, "POST", f"/entries/{eid}/choose", {})[0] == 200
    agents.fail_write = False
    assert call(app, "POST", "/draft_next")[1]["drafted"] == eid


def test_falha_resolvida_antes_do_envio_nao_vira_alerta(app, agents):
    """17/11: a 1ª tentativa da arte falhou às 17:35 UTC, a 2ª deu certo às 17:50 e o e-mail
    de aprovação saiu; o alerta de falha, enviado de hora em hora, chegou às 18:10, depois
    do sucesso. Se a redação dá certo, o aviso pendente daquela pauta perde o sentido."""
    eid = chosen_entry(app, agents)
    app.alerts.notify("pipeline", "pipeline", "outro aviso", key="pipeline:outro")
    agents.fail_write = True
    assert call(app, "POST", "/draft_next")[1]["failed"] == eid
    agents.fail_write = False
    assert call(app, "POST", "/draft_next")[1]["drafted"] == eid
    alerts = [a for a in call(app, "GET", "/alerts")[1]["alerts"] if a["kind"] == "pipeline"]
    assert [a["message"] for a in alerts] == ["outro aviso"]


def test_falha_ja_enviada_continua_registrada(app, agents):
    eid = chosen_entry(app, agents)
    agents.fail_write = True
    call(app, "POST", "/draft_next")
    ids = [a["id"] for a in call(app, "GET", "/alerts")[1]["alerts"]]
    assert call(app, "POST", "/alerts/ack", {"ids": ids})[0] == 200
    agents.fail_write = False
    assert call(app, "POST", "/draft_next")[1]["drafted"] == eid
    assert call(app, "GET", "/alerts")[1]["alerts"] == []


def test_draft_next_durante_outra_execucao_nao_redige(app, agents):
    chosen_entry(app, agents)
    app._agent_lock.acquire()
    try:
        assert call(app, "POST", "/draft_next")[1]["drafted"] is None
    finally:
        app._agent_lock.release()
    assert agents.written == []


def test_imagem_ja_mostrada_nunca_e_sobrescrita(app, agents, tmp_path):
    eid = chosen_entry(app, agents)
    images = tmp_path / "data" / "images"
    images.mkdir(parents=True)
    (images / f"{eid}-v1.png").write_bytes(b"a que Felipe viu")
    body = call(app, "POST", "/draft_next")[1]
    assert body["drafted"] == eid and body["image"] != f"{eid}-v1.png"
    assert (images / f"{eid}-v1.png").read_bytes() == b"a que Felipe viu"


# ------------------------------------------------------------------------- aprovação
def approval_form(app):
    out = call(app, "POST", "/approval_emails")[1]["emails"]
    assert len(out) == 1
    return out[0]


def test_aprovar_com_outro_hook_e_a_leitura_de_felipe(app, agents, clock):
    eid = chosen_entry(app, agents)
    call(app, "POST", "/draft_next")
    mail = approval_form(app)
    assert "Hooks (o 1 está no texto acima)" in mail["email"]["text"]
    assert mail["image_url_path"] == f"/images/{eid}-v1.png"
    fid = mail["form_id"]
    html = call(app, "GET", f"/forms/{fid}")[1]["html"]
    assert f"name='h:{eid}'" in html and "Escrever a minha" in html
    fields = {"f": fid, f"a:{eid}": "approve", f"t:{eid}": hidden(html, f"t:{eid}"),
              f"h:{eid}": "2", f"r:{eid}": "c", f"c:{eid}": "Minha leitura: canal sem métrica."}
    status, body = call(app, "POST", f"/forms/{fid}", {"fields": fields})
    assert status == 200 and "Aprovado" in body["html"]
    entry = call(app, "GET", f"/entries/{eid}")[1]["entry"]
    assert entry["state"] == "approved"
    assert entry["post"]["commentary"] == (
        "Agente de IA ainda não é canal.\n\nO número saiu no balanço do trimestre.\n\n"
        "Minha leitura: canal sem métrica.\n\nUma ressalva: são números da própria empresa."
        "\n\nVocê delegaria? Sim ou não?"
    )


def test_aprovacao_recusada_nao_troca_a_legenda(app, agents):
    """O texto escolhido só é gravado junto com a aprovação (Felipe aprova o texto exato)."""
    eid = chosen_entry(app, agents)
    call(app, "POST", "/draft_next")
    fid = approval_form(app)["form_id"]
    html = call(app, "GET", f"/forms/{fid}")[1]["html"]
    before = call(app, "GET", f"/entries/{eid}")[1]["entry"]
    fields = {"f": fid, f"a:{eid}": "approve", f"t:{eid}": hidden(html, f"t:{eid}"),
              f"h:{eid}": "2", f"w:{eid}": "2026-11-14"}  # sábado: sem horário de post
    call(app, "POST", f"/forms/{fid}", {"fields": fields})
    after = call(app, "GET", f"/entries/{eid}")[1]["entry"]
    assert after["state"] == "awaiting_approval"
    assert after["post"]["commentary"] == before["post"]["commentary"]
    assert after["version"] == before["version"]


def test_aprovar_sem_mexer_mantem_o_texto_mostrado(app, agents):
    eid = chosen_entry(app, agents)
    call(app, "POST", "/draft_next")
    fid = approval_form(app)["form_id"]
    html = call(app, "GET", f"/forms/{fid}")[1]["html"]
    shown = call(app, "GET", f"/entries/{eid}")[1]["entry"]["post"]["commentary"]
    fields = {"f": fid, f"a:{eid}": "approve", f"t:{eid}": hidden(html, f"t:{eid}")}
    assert call(app, "POST", f"/forms/{fid}", {"fields": fields})[0] == 200
    assert call(app, "GET", f"/entries/{eid}")[1]["entry"]["post"]["commentary"] == shown


def test_ajuste_pedido_refaz_o_post_com_imagem_nova(app, agents):
    eid = chosen_entry(app, agents)
    call(app, "POST", "/draft_next")
    fid = approval_form(app)["form_id"]
    html = call(app, "GET", f"/forms/{fid}")[1]["html"]
    fields = {"f": fid, f"a:{eid}": "adjust", f"t:{eid}": hidden(html, f"t:{eid}"),
              f"n:{eid}": "mais curto"}
    assert call(app, "POST", f"/forms/{fid}", {"fields": fields})[0] == 200
    status, body = call(app, "POST", "/draft_next")
    assert body == {"drafted": eid, "image": f"{eid}-v2.png"}
    post = call(app, "GET", f"/entries/{eid}")[1]["entry"]["post"]
    assert "Ajuste: mais curto." in post["commentary"]
