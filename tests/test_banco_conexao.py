"""Conexão com o Postgres: pool e tempos limite (auditoria, Fase 3 → Leva L1).

* o Postgres ganha pool do tamanho das threads e tempos limite curtos
  (``core/banco.py``); o SQLite dos testes e do desenvolvimento fica como era;
* agendador e comandos usam a ``DIRECT_DATABASE_URL`` (sem pooler), com
  limites de sessão maiores; o site, a ``DATABASE_URL``;
* o gunicorn lê processos, threads e tempos do ambiente.
"""
import os

import pytest
import sqlalchemy as sa

from facilities.core import banco

NO_POSTGRES = bool(os.environ.get('TEST_DATABASE_URL', '').strip())


# ── Pool e tempos limite ──────────────────────────────────────────────────

PG = 'postgresql://u:p@db.exemplo.com:5432/facilities'


def test_sqlite_fica_so_com_pre_ping():
    assert banco.opcoes_do_engine('sqlite:///x.db', env={}) == {'pool_pre_ping': True}


def test_postgres_do_site_ganha_pool_e_tempos_limite():
    o = banco.opcoes_do_engine(PG, banco.WEB, env={})
    assert o['pool_pre_ping'] is True
    assert (o['pool_size'], o['max_overflow'], o['pool_timeout'], o['pool_recycle']) \
        == (8, 2, 5, 300)
    assert o['connect_args'] == {
        'connect_timeout': 5, 'keepalives': 1, 'keepalives_idle': 30,
        'keepalives_interval': 10, 'keepalives_count': 3, 'tcp_user_timeout': 15000,
        'application_name': 'facilities-web'}
    # Nada de options=-c ... (o pooler em modo transação recusa).
    assert 'options' not in o['connect_args']


def test_pool_segue_as_threads_e_as_variaveis():
    o = banco.opcoes_do_engine(PG, banco.WEB, env={'GUNICORN_THREADS': '12'})
    assert o['pool_size'] == 12
    o = banco.opcoes_do_engine(PG, banco.WEB, env={
        'GUNICORN_THREADS': '12', 'DB_POOL_SIZE': '20', 'DB_MAX_OVERFLOW': '0',
        'DB_POOL_TIMEOUT': '3', 'DB_POOL_RECYCLE': '120', 'DB_CONNECT_TIMEOUT': '4',
        'DB_TCP_USER_TIMEOUT_MS': '9000'})
    assert (o['pool_size'], o['max_overflow'], o['pool_timeout'], o['pool_recycle']) \
        == (20, 0, 3, 120)
    assert o['connect_args']['connect_timeout'] == 4
    assert o['connect_args']['tcp_user_timeout'] == 9000


def test_valor_que_nao_e_numero_para_o_boot():
    with pytest.raises(RuntimeError, match='DB_POOL_SIZE'):
        banco.opcoes_do_engine(PG, env={'DB_POOL_SIZE': 'muitas'})
    with pytest.raises(RuntimeError, match='GUNICORN_THREADS'):
        banco.opcoes_do_engine(PG, env={'GUNICORN_THREADS': '0'})


def test_agendador_e_comandos_tem_pool_pequeno_e_nome_proprio():
    o = banco.opcoes_do_engine(PG, banco.AGENDADOR, env={})
    assert o['pool_size'] == 2 and o['connect_args']['application_name'] == 'facilities-agendador'
    o = banco.opcoes_do_engine(PG, banco.CLI, env={})
    assert o['connect_args']['application_name'] == 'facilities-cli'


@pytest.mark.parametrize('argv, esperado', [
    (['/usr/local/bin/gunicorn', 'app:app'], 'web'),
    (['/venv/bin/pytest', '-q'], 'web'),
    (['/venv/bin/flask', '--app', 'facilities', 'agendador', 'rodar'], 'agendador'),
    (['/venv/bin/flask', '--app', 'facilities', 'db', 'upgrade'], 'cli'),
    (['/venv/lib/python3.12/site-packages/flask/__main__.py', 'anexos', 'arquivar'], 'cli'),
    (['/venv/bin/flask', '--app', 'facilities', 'run'], 'web'),
])
def test_quem_e_o_processo(argv, esperado):
    assert banco.processo(argv=argv, env={}) == esperado


def test_processo_pela_variavel():
    assert banco.processo(argv=['gunicorn'], env={'FACILITIES_PROCESSO': 'agendador'}) \
        == 'agendador'
    with pytest.raises(RuntimeError, match='FACILITIES_PROCESSO'):
        banco.processo(argv=['gunicorn'], env={'FACILITIES_PROCESSO': 'outro'})


def test_url_direta_so_para_agendador_e_comandos():
    env = {'DATABASE_URL': 'postgresql://a@pooler/x', 'DIRECT_DATABASE_URL': 'postgresql://a@direto/x'}
    assert banco.url_do_processo(banco.WEB, env) == 'postgresql://a@pooler/x'
    assert banco.url_do_processo(banco.AGENDADOR, env) == 'postgresql://a@direto/x'
    assert banco.url_do_processo(banco.CLI, env) == 'postgresql://a@direto/x'
    # Sem a direta, todo mundo usa a DATABASE_URL.
    assert banco.url_do_processo(banco.AGENDADOR, {'DATABASE_URL': 'postgresql://a@db/x'}) \
        == 'postgresql://a@db/x'


def test_a_fabrica_aplica_no_postgres_e_nao_no_sqlite(monkeypatch, tmp_path):
    from facilities import create_app
    from facilities.extensions import db
    monkeypatch.setenv('SECRET_KEY', 'segredo-de-teste')
    monkeypatch.setenv('STORAGE_BACKEND', 'local')
    monkeypatch.setenv('UPLOAD_FOLDER', str(tmp_path / 'up'))
    for nome in ('DIRECT_DATABASE_URL', 'FACILITIES_PROCESSO', 'GUNICORN_THREADS',
                 'DB_POOL_SIZE', 'EXIGIR_DATABASE_URL'):
        monkeypatch.delenv(nome, raising=False)
    # Porta 1: nada atende; criar o engine não conecta.
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@127.0.0.1:1/facilities')
    app = create_app()
    assert app.config['SQLALCHEMY_ENGINE_OPTIONS']['pool_size'] == 8
    with app.app_context():
        pool = db.engine.pool
        assert (pool.size(), pool._max_overflow, pool._timeout, pool._recycle) == (8, 2, 5, 300)
        db.engine.dispose()
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "x.db"}')
    app = create_app()
    assert app.config['SQLALCHEMY_ENGINE_OPTIONS'] == {'pool_pre_ping': True}
    with app.app_context():
        db.engine.dispose()


def test_entrypoint_le_processos_threads_e_tempos_do_ambiente():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'docker-entrypoint.sh'), encoding='utf-8') as f:
        sh = f.read()
    for trecho in ('WEB_CONCURRENCY:-4', 'GUNICORN_THREADS:-8', '--threads "$GUNICORN_THREADS"',
                   'GUNICORN_TIMEOUT:-30', 'GUNICORN_GRACEFUL_TIMEOUT:-25',
                   'GUNICORN_KEEPALIVE:-5'):
        assert trecho in sh, trecho


# ── Limites do agendador e dos comandos (URL direta) ─────────────────────

def test_agendador_na_url_direta_ganha_limites_maiores():
    env = {'DIRECT_DATABASE_URL': 'postgresql://a@direto/x'}
    assert banco.limites_das_tarefas(banco.AGENDADOR, env) == [
        "SET statement_timeout = '5min'", "SET lock_timeout = '1min'",
        "SET idle_in_transaction_session_timeout = '10min'"]
    env['DB_TAREFAS_STATEMENT_TIMEOUT'] = '0'
    assert banco.limites_das_tarefas(banco.CLI, env)[0] == "SET statement_timeout = '0'"


def test_sem_url_direta_ou_no_site_nao_ha_set_de_sessao():
    """SET de sessão por pooler em modo transação vazaria para outra pessoa."""
    assert banco.limites_das_tarefas(banco.AGENDADOR, {}) == []
    assert banco.limites_das_tarefas(banco.WEB, {'DIRECT_DATABASE_URL': 'postgresql://d/x'}) == []


def test_limite_mal_escrito_para_o_boot():
    with pytest.raises(RuntimeError, match='DB_TAREFAS_LOCK_TIMEOUT'):
        banco.limites_das_tarefas(banco.AGENDADOR, {
            'DIRECT_DATABASE_URL': 'postgresql://d/x',
            'DB_TAREFAS_LOCK_TIMEOUT': "1min'; DROP TABLE users; --"})


@pytest.mark.skipif(not NO_POSTGRES, reason='SET de sessão só no Postgres')
def test_conexao_do_agendador_nasce_com_os_limites():
    url = os.environ['TEST_DATABASE_URL']
    proc = banco.AGENDADOR
    env = {'DIRECT_DATABASE_URL': url}
    engine = sa.create_engine(url, **banco.opcoes_do_engine(url, proc, env={}))
    try:
        banco.aplicar_limites_das_tarefas(engine, proc, env)
        with engine.connect() as con:
            assert con.execute(sa.text('SHOW statement_timeout')).scalar() == '5min'
            assert con.execute(sa.text('SHOW lock_timeout')).scalar() == '1min'
            assert con.execute(sa.text("SELECT current_setting('application_name')")) \
                .scalar() == 'facilities-agendador'
            con.rollback()
        # A devolução ao pool (rollback) não desfaz os SET.
        with engine.connect() as con:
            assert con.execute(sa.text('SHOW statement_timeout')).scalar() == '5min'
    finally:
        engine.dispose()
