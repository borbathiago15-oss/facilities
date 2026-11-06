"""Banco fora do ar ou pendurado (auditoria, Fase 3 → Leva L1).

* erro de banco (``OperationalError``, pool sem conexão livre, consulta
  cortada pelo ``statement_timeout``) vira **503** com ``Retry-After: 5`` e
  "tente de novo em instantes" — JSON para quem chama a API, página para quem
  navega — e a página sai sem consultar o banco de novo;
* ``/healthz`` não carrega a pessoa logada nem toca no banco;
* ``/readyz`` faz ``SELECT 1``: 200 com o banco de pé, 503 sem ele.

Pool e tempos limite da conexão: ``test_banco_conexao.py``.
"""
import os

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from facilities.core.erros import MENSAGENS
from tests import fabrica

MSG = 'O sistema está com dificuldade para falar com o banco. Tente de novo em instantes.'
NO_POSTGRES = bool(os.environ.get('TEST_DATABASE_URL', '').strip())


def _op():
    return sa_exc.OperationalError('SELECT 1', {}, Exception('server closed the connection'))


def _pool():
    return sa_exc.TimeoutError('QueuePool limit of size 8 overflow 2 reached, '
                               'connection timed out, timeout 5.00')


def _que_levanta(erro):
    def view(*_a, **_k):
        raise erro()
    return view


class _Contador:
    """Conta as consultas que chegam ao banco enquanto está ligado."""

    def __init__(self, engine):
        self.engine, self.n = engine, 0

    def _conta(self, *_a, **_k):
        self.n += 1

    def __enter__(self):
        sa.event.listen(self.engine, 'before_cursor_execute', self._conta)
        return self

    def __exit__(self, *_):
        sa.event.remove(self.engine, 'before_cursor_execute', self._conta)


@pytest.fixture()
def logado(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'banco.fora@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
    return fabrica.entrar(app_module, 'banco.fora@trino.com')


# ── 503 ───────────────────────────────────────────────────────────────────

def test_mensagem_do_503_e_a_combinada():
    assert MENSAGENS[503] == MSG


@pytest.mark.parametrize('erro', [_op, _pool], ids=['operational', 'pool'])
def test_erro_de_banco_na_api_e_503_em_json(app_module, logado, monkeypatch, erro):
    monkeypatch.setitem(app_module.app.view_functions, 'api_v1.eu', _que_levanta(erro))
    r = logado.get('/api/v1/eu')
    assert r.status_code == 503
    assert r.headers['Retry-After'] == '5'
    assert r.get_json() == {'error': MSG}
    assert r.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('erro', [_op, _pool], ids=['operational', 'pool'])
def test_erro_de_banco_na_tela_e_503_em_pagina(app_module, logado, monkeypatch, erro):
    monkeypatch.setitem(app_module.app.view_functions, 'core.inicio', _que_levanta(erro))
    r = logado.get('/', headers={'Sec-Fetch-Mode': 'navigate', 'Accept': 'text/html'})
    assert r.status_code == 503
    assert r.headers['Retry-After'] == '5'
    assert r.mimetype == 'text/html'
    html = r.get_data(as_text=True)
    assert MSG in html and 'Tentar de novo' in html
    # Nem um 500 genérico disfarçado.
    assert MENSAGENS[500] not in html


def test_envio_que_falha_no_banco_nao_oferece_reenviar(app_module, logado, monkeypatch):
    """Era um POST: recarregar mandaria de novo — a página só leva de volta."""
    monkeypatch.setitem(app_module.app.view_functions, 'auth.logout', _que_levanta(_op))
    r = logado.post('/logout', headers={'Sec-Fetch-Mode': 'navigate', 'Accept': 'text/html'})
    assert r.status_code == 503
    html = r.get_data(as_text=True)
    assert 'data-recarregar' not in html and 'data-voltar' in html


def test_a_pagina_do_503_nao_consulta_o_banco(app_module, logado, monkeypatch):
    """A página normal monta o menu e o sino (consultas): com o banco
    pendurado ela esperaria de novo. A do 503 não pergunta nada ao banco."""
    from facilities.core import erros
    monkeypatch.setitem(app_module.app.view_functions, 'core.inicio', _que_levanta(_op))
    with app_module.app.app_context():
        engine = app_module.db.engine
    visto = {}

    def medido(e):
        with _Contador(engine) as cont:
            resposta = erros._erro_de_banco(e)
        visto['consultas'] = cont.n
        return resposta

    # O handler é registrado por referência: troca no mapa do app.
    for classe in erros.ERROS_DE_BANCO:
        monkeypatch.setitem(app_module.app.error_handler_spec[None][None], classe, medido)
    r = logado.get('/', headers={'Sec-Fetch-Mode': 'navigate'})
    assert r.status_code == 503
    assert visto['consultas'] == 0


def test_o_log_do_503_nao_traz_host_usuario_nem_parametros(app_module, logado, monkeypatch,
                                                           caplog):
    """A mensagem do psycopg2 diz host, usuário e banco; a do SQLAlchemy, a
    consulta com os parâmetros. No log vai só a classe e um motivo curto."""
    import logging

    class _Driver(Exception):
        pgcode = None

    def erro():
        return sa_exc.OperationalError(
            'SELECT * FROM users WHERE email_index = %(e)s', {'e': 'joana.silva@trino.com'},
            _Driver('connection to server at "db-producao.exemplo.net" (10.1.2.3), port 5432 '
                    'failed: FATAL:  password authentication failed for user "facilities_app"'))

    monkeypatch.setitem(app_module.app.view_functions, 'api_v1.eu', _que_levanta(erro))
    # No Postgres a suíte roda as migrações, e o fileConfig do Alembic
    # desliga os loggers que já existiam (o do app entre eles).
    monkeypatch.setattr(app_module.app.logger, 'disabled', False)
    with caplog.at_level(logging.WARNING):
        r = logado.get('/api/v1/eu')
    assert r.status_code == 503
    texto = caplog.text
    assert 'banco indisponível (503)' in texto and 'OperationalError' in texto
    assert 'usuário ou senha do banco recusados' in texto
    for vazado in ('db-producao.exemplo.net', '10.1.2.3', 'facilities_app',
                   'joana.silva', 'email_index'):
        assert vazado not in texto


def test_resumo_de_erro_comum_apaga_url_com_senha_e_email():
    from facilities.core.log_seguro import resumo
    texto = resumo(ValueError('falhou em postgresql://u:segredo@h/db para ana@trino.com '
                              'user "fac"\nsegunda linha'))
    assert texto.startswith('ValueError: falhou em')
    for vazado in ('segredo', 'ana@trino.com', '"fac"', 'segunda linha'):
        assert vazado not in texto


def test_banco_fora_ao_carregar_a_pessoa_logada_tambem_e_503(app_module, logado,
                                                              monkeypatch):
    """O primeiro toque no banco costuma ser o ``user_loader`` (antes da tela)."""
    from facilities.extensions import login_manager

    def fora(_ident):
        raise _op()

    monkeypatch.setattr(login_manager, '_user_callback', fora)
    r = logado.get('/api/v1/eu')
    assert r.status_code == 503 and r.get_json() == {'error': MSG}
    r = logado.get('/', headers={'Sec-Fetch-Mode': 'navigate'})
    assert r.status_code == 503 and MSG in r.get_data(as_text=True)


@pytest.mark.skipif(not NO_POSTGRES, reason='QueryCanceled real só no Postgres')
def test_consulta_cortada_pelo_statement_timeout_e_503(app_module, logado, monkeypatch):
    """``QueryCanceled`` (statement_timeout) chega embrulhado no
    ``OperationalError`` do SQLAlchemy — de verdade, no Postgres."""
    from sqlalchemy import text

    def lenta():
        app_module.db.session.execute(text("SET LOCAL statement_timeout = '50ms'"))
        app_module.db.session.execute(text('SELECT pg_sleep(2)'))
        return 'não chega aqui'

    monkeypatch.setitem(app_module.app.view_functions, 'api_v1.eu', lenta)
    r = logado.get('/api/v1/eu')
    assert r.status_code == 503 and r.get_json() == {'error': MSG}
    # A sessão voltou ao normal (rollback no handler): o próximo pedido passa.
    monkeypatch.undo()
    assert logado.get('/api/v1/eu').status_code == 200


def test_outro_erro_continua_500(app_module, logado, monkeypatch):
    def quebra():
        raise ValueError('defeito de verdade')
    monkeypatch.setitem(app_module.app.view_functions, 'api_v1.eu', quebra)
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = False
    try:
        r = logado.get('/api/v1/eu')
    finally:
        app_module.app.config['PROPAGATE_EXCEPTIONS'] = None
    assert r.status_code == 500 and 'Retry-After' not in r.headers


# ── /healthz e /readyz ────────────────────────────────────────────────────

def _engine(app_module):
    with app_module.app.app_context():
        return app_module.db.engine


def test_healthz_logado_nao_toca_no_banco(app_module, logado):
    with _Contador(_engine(app_module)) as cont:
        r = logado.get('/healthz')
    assert r.status_code == 200 and r.get_json() == {'status': 'ok'}
    assert cont.n == 0


def test_healthz_responde_mesmo_com_o_banco_fora(app_module, logado, monkeypatch):
    """Com o banco fora, o ``user_loader`` falharia — o /healthz nem chama."""
    from facilities.extensions import login_manager

    def fora(_ident):
        raise AssertionError('o /healthz não pode carregar a pessoa logada')

    monkeypatch.setattr(login_manager, '_user_callback', fora)
    r = logado.get('/healthz')
    assert r.status_code == 200 and r.get_json() == {'status': 'ok'}
    assert r.headers['Cache-Control'] == 'no-store'


def test_readyz_com_o_banco_de_pe(client):
    r = client.get('/readyz')
    assert r.status_code == 200 and r.get_json() == {'status': 'ok'}


def test_readyz_sem_o_banco_e_503(app_module, client, monkeypatch):
    engine = _engine(app_module)

    def fora(*_a, **_k):
        raise _op()

    monkeypatch.setattr(type(engine), 'connect', fora)
    r = client.get('/readyz')
    assert r.status_code == 503
    assert r.headers['Retry-After'] == '5'
    assert r.get_json()['status'] == 'indisponivel'
    assert r.get_json()['error'] == MSG


def test_readyz_logado_so_faz_o_select_1(app_module, logado):
    with _Contador(_engine(app_module)) as cont:
        r = logado.get('/readyz')
    assert r.status_code == 200
    # SELECT 1 (+ o SET LOCAL no Postgres; + o ping do pool): nada da pessoa.
    assert cont.n <= 3


def test_falha_de_banco_no_agendador_vai_sem_o_rastro(caplog):
    """O rastro (``logger.exception``) repetiria a mensagem do driver."""
    import logging

    from facilities.core.log_seguro import registrar_falha
    log = logging.getLogger('teste.agendador')
    erro = sa_exc.OperationalError('SELECT 1', {}, Exception('user "facilities_app" timed out'))
    with caplog.at_level(logging.WARNING):
        registrar_falha(log, erro, 'agendador: etapa %s falhou', 'tarefas')
    assert 'etapa tarefas falhou' in caplog.text and 'tempo esgotado' in caplog.text
    assert 'facilities_app' not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)
