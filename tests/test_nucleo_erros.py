"""Erros em português: página com o menu para quem navega, JSON para o JS.

A página padrão do Werkzeug era em inglês e sem o menu. E as telas e a fila
sem internet leem a resposta como JSON: um 403 em HTML virava "sem conexão"
na tela e "sessão vencida" na fila, que travava naquele item para sempre.
"""
import re

import pytest

from tests.test_nucleo import _entrar, _pessoa

NAVEGANDO = {'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
             'Sec-Fetch-Mode': 'navigate'}
FETCH = {'Accept': '*/*', 'Sec-Fetch-Mode': 'cors'}


def _encarregado_de_um_contrato(app_module, email):
    """Encarregado cuja carteira tem só o primeiro contrato; devolve
    (cliente, id de um contrato FORA da carteira)."""
    with app_module.app.app_context():
        from app import Client, User, db
        uid = _pessoa(app_module, email)
        dentro, fora = Client.query.order_by(Client.id).limit(2).all()
        u = db.session.get(User, uid)
        u.clients = [dentro]
        db.session.commit()
        fora_id = fora.id
    c, _ = _entrar(app_module, email)
    return c, fora_id


def _sem_ingles(html):
    for termo in ('Not Found', 'Forbidden', 'Request Entity Too Large',
                  'Too Many Requests', 'requested URL'):
        assert termo not in html, termo


# ── 404 ───────────────────────────────────────────────────────────────────

def test_404_navegando_e_pagina_em_portugues_com_o_menu(auth_client):
    r = auth_client.get('/pagina-que-nao-existe', headers=NAVEGANDO)
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and r.mimetype == 'text/html'
    assert 'Página não encontrada' in html and 'Voltar ao início' in html
    assert 'class="fc-lateral"' in html                # o menu do sistema
    _sem_ingles(html)


def test_404_de_api_e_json(auth_client):
    r = auth_client.get('/passagem-de-turno/api/nao-existe', headers=NAVEGANDO)
    assert r.status_code == 404 and r.is_json
    assert 'Não encontramos' in r.get_json()['error']


def test_404_pedido_por_fetch_e_json_mesmo_fora_de_api(auth_client):
    r = auth_client.get('/chamados/99999999', headers=FETCH)
    assert r.status_code == 404 and r.is_json and r.get_json()['error']


def test_arquivo_estatico_que_falta_nao_monta_a_tela(auth_client):
    r = auth_client.get('/static/nao-existe.js', headers=NAVEGANDO)
    assert r.status_code == 404 and 'fc-lateral' not in r.get_data(as_text=True)


# ── 403 ───────────────────────────────────────────────────────────────────

def test_403_de_contrato_alheio_na_api_e_json_com_o_motivo(app_module):
    """O caso da fila: a API recusa o contrato e a fila precisa LER isso."""
    from facilities.core.acesso import FORA_DOS_CONTRATOS
    c, fora = _encarregado_de_um_contrato(app_module, 'erros.api@trino.com')
    r = c.get(f'/passagem-de-turno/api/tarefas-turno?client_id={fora}'
              '&data_turno=2026-10-01', headers=FETCH)
    assert r.status_code == 403 and r.is_json
    assert r.get_json() == {'error': FORA_DOS_CONTRATOS}
    assert 'carteira' not in FORA_DOS_CONTRATOS.lower()


def test_403_navegando_e_pagina_em_portugues_com_o_motivo(app_module):
    from facilities.core.acesso import FORA_DOS_CONTRATOS
    c, fora = _encarregado_de_um_contrato(app_module, 'erros.tela@trino.com')
    r = c.get(f'/passagem-de-turno/relatorio-mensal?client_id={fora}', headers=NAVEGANDO)
    html = r.get_data(as_text=True)
    assert r.status_code == 403 and r.mimetype == 'text/html'
    assert 'Sem acesso' in html and FORA_DOS_CONTRATOS in html
    assert 'class="fc-lateral"' in html
    _sem_ingles(html)


# ── 413 ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def limite_de_1_mb(app_module):
    antes = app_module.app.config['MAX_CONTENT_LENGTH']
    app_module.app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    yield
    app_module.app.config['MAX_CONTENT_LENGTH'] = antes


def test_413_pedido_por_fetch_e_json_em_portugues(client, limite_de_1_mb):
    """A fila trata 413 em JSON como "recusado" e segue para o próximo item;
    em HTML virava "sessão vencida" e parava a fila."""
    r = client.post('/login', data={'email': 'x@trino.com', 'password': 'y' * (2 << 20)},
                    headers=FETCH)
    assert r.status_code == 413 and r.is_json
    assert '1 MB' in r.get_json()['error'] and 'não foi gravado' in r.get_json()['error']


def test_413_navegando_e_pagina_em_portugues(client, limite_de_1_mb):
    r = client.post('/login', data={'email': 'x@trino.com', 'password': 'y' * (2 << 20)},
                    headers=NAVEGANDO)
    html = r.get_data(as_text=True)
    assert r.status_code == 413 and r.mimetype == 'text/html'
    assert 'Envio grande demais' in html and '1 MB' in html
    _sem_ingles(html)


# ── 405 e 500 ─────────────────────────────────────────────────────────────

def test_405_navegando_e_pagina_em_portugues(auth_client):
    r = auth_client.get('/logout', headers=NAVEGANDO)
    assert r.status_code == 405 and 'botão da tela' in r.get_data(as_text=True)
    # O HTTP pede que o 405 diga o método que vale ali.
    assert 'POST' in r.headers.get('Allow', '')


def test_500_desfaz_a_transacao_e_responde_em_portugues(app_module):
    from werkzeug.exceptions import InternalServerError
    from facilities.core import erros
    with app_module.app.test_request_context('/qualquer', headers=NAVEGANDO):
        corpo, codigo = erros._erro_interno(InternalServerError())
    assert codigo == 500 and 'Erro no sistema' in corpo
    with app_module.app.test_request_context('/passagem-de-turno/api/x'):
        resp, codigo = erros._erro_interno(InternalServerError())
    assert codigo == 500 and 'deu errado' in resp.get_json()['error']


# ── Quem decide entre página e JSON ───────────────────────────────────────

@pytest.mark.parametrize('caminho, cabecalhos, esperado', [
    ('/chamados/', NAVEGANDO, False),
    ('/chamados/', FETCH, True),
    ('/chamados/', {'X-Requested-With': 'XMLHttpRequest'}, True),
    ('/passagem-de-turno/api/turnos', NAVEGANDO, True),
    ('/chamados/', {'Accept': 'text/html'}, False),     # navegador sem Sec-Fetch
    ('/chamados/', {'Accept': '*/*'}, True),            # fetch sem Sec-Fetch
])
def test_pede_json(app_module, caminho, cabecalhos, esperado):
    from facilities.core.erros import pede_json
    with app_module.app.test_request_context(caminho, headers=cabecalhos):
        assert pede_json() is esperado


def test_a_pagina_de_erro_nao_cita_o_sistema_antigo(auth_client):
    html = auth_client.get('/pagina-que-nao-existe', headers=NAVEGANDO).get_data(as_text=True)
    assert not re.search(r'Trino Intelligence|Torre de Comando|PDCA|Master|carteira', html)
