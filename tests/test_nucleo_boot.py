"""A fábrica recusa subir com configuração que perde dado ou derruba sessão.

* sem ``SECRET_KEY`` fora do SQLite de desenvolvimento → não sobe (cada
  worker sorteava a sua e o login falhava ao acaso);
* com Postgres, anexos no disco local só com ``STORAGE_BACKEND=local``
  escrito (faltando uma R2_*, as fotos iam para o disco que some);
* a imagem de produção exige ``DATABASE_URL`` (sem ela subiria num SQLite
  dentro do contêiner);
* as chaves liga/desliga não falham abertas (``true`` não pode virar False);
* ``PROXY_HOPS`` faz o IP do cliente valer atrás de proxy;
* o boot não faz DDL — nem no SQLite;
* a suíte não zera banco que não seja de teste;
* a imagem Docker não leva ``.env``, ``instance/``, ``.venv`` nem ``.git``.
"""
import os

import pytest
import sqlalchemy as sa

from facilities import _atras_de_proxy, _flag, _saltos_de_proxy, create_app
from facilities.object_storage import LocalStorage, StorageError, get_storage

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTGRES_DE_MENTIRA = 'postgresql://u:p@127.0.0.1:1/facilities'
R2_VARS = ('R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')


@pytest.fixture()
def ambiente_limpo(monkeypatch, tmp_path):
    """Ambiente de produção sem nada: cada teste liga só o que precisa."""
    for nome in ('SECRET_KEY', 'STORAGE_BACKEND', 'PROXY_HOPS', 'EXIGIR_DATABASE_URL',
                 *R2_VARS):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv('UPLOAD_FOLDER', str(tmp_path / 'uploads'))
    return monkeypatch


def _sqlite(tmp_path, nome='boot.db'):
    return f'sqlite:///{tmp_path / nome}'


# ── SECRET_KEY ────────────────────────────────────────────────────────────

def test_sem_secret_key_fora_do_sqlite_o_boot_para(ambiente_limpo):
    ambiente_limpo.setenv('DATABASE_URL', POSTGRES_DE_MENTIRA)
    ambiente_limpo.setenv('STORAGE_BACKEND', 'local')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()


def test_imagem_de_producao_exige_secret_key_mesmo_com_sqlite(ambiente_limpo, tmp_path):
    ambiente_limpo.setenv('EXIGIR_DATABASE_URL', '1')
    ambiente_limpo.setenv('DATABASE_URL', _sqlite(tmp_path))
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()


def test_sem_secret_key_no_sqlite_de_desenvolvimento_sobe_com_chave_aleatoria(
        ambiente_limpo, tmp_path):
    ambiente_limpo.setenv('DATABASE_URL', _sqlite(tmp_path))
    app = create_app()
    assert app.config['SECRET_KEY'] and len(app.config['SECRET_KEY']) >= 32


# ── Destino dos anexos ────────────────────────────────────────────────────

def test_postgres_sem_r2_e_sem_storage_backend_o_boot_para(ambiente_limpo):
    ambiente_limpo.setenv('DATABASE_URL', POSTGRES_DE_MENTIRA)
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    with pytest.raises(StorageError, match='R2_BUCKET'):
        create_app()


def test_nome_de_variavel_r2_errado_tambem_para_o_boot(ambiente_limpo):
    ambiente_limpo.setenv('DATABASE_URL', POSTGRES_DE_MENTIRA)
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    for nome in R2_VARS[:3]:
        ambiente_limpo.setenv(nome, 'x')
    ambiente_limpo.setenv('R2_BUKET', 'fotos')          # o erro de digitação
    with pytest.raises(StorageError, match='R2_BUCKET'):
        create_app()


def test_disco_local_vale_quando_pedido_por_escrito(ambiente_limpo, tmp_path):
    ambiente_limpo.setenv('STORAGE_BACKEND', 'local')
    assert isinstance(get_storage(str(tmp_path), local_implicito=False), LocalStorage)
    ambiente_limpo.delenv('STORAGE_BACKEND')
    # No SQLite de desenvolvimento o disco local continua sendo o padrão.
    assert isinstance(get_storage(str(tmp_path)), LocalStorage)


def test_storage_backend_desconhecido_para_o_boot(ambiente_limpo, tmp_path):
    ambiente_limpo.setenv('STORAGE_BACKEND', 'r22')
    with pytest.raises(StorageError, match='desconhecido'):
        get_storage(str(tmp_path))


# ── DATABASE_URL na imagem de produção ────────────────────────────────────

def test_imagem_de_producao_sem_database_url_nao_sobe(ambiente_limpo):
    ambiente_limpo.setenv('EXIGIR_DATABASE_URL', '1')
    ambiente_limpo.setenv('DATABASE_URL', '')
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        create_app()


def test_dockerfile_liga_a_exigencia_de_database_url():
    with open(os.path.join(RAIZ, 'Dockerfile'), encoding='utf-8') as f:
        assert 'EXIGIR_DATABASE_URL=1' in f.read()


# ── Liga/desliga sem falhar aberto ────────────────────────────────────────

@pytest.mark.parametrize('valor', ['1', 'true', 'True', 'YES', 'on', ' sim '])
def test_flag_ligada(monkeypatch, valor):
    monkeypatch.setenv('FLAG_DE_TESTE', valor)
    assert _flag('FLAG_DE_TESTE', False) is True


@pytest.mark.parametrize('valor', ['0', 'false', 'False', 'no', 'OFF', 'não'])
def test_flag_desligada(monkeypatch, valor):
    monkeypatch.setenv('FLAG_DE_TESTE', valor)
    assert _flag('FLAG_DE_TESTE', True) is False


def test_flag_vazia_fica_no_padrao_e_valor_estranho_para_o_boot(monkeypatch):
    monkeypatch.delenv('FLAG_DE_TESTE', raising=False)
    assert _flag('FLAG_DE_TESTE', True) is True
    monkeypatch.setenv('FLAG_DE_TESTE', '  ')
    assert _flag('FLAG_DE_TESTE', True) is True
    monkeypatch.setenv('FLAG_DE_TESTE', 'verdadeiro')
    with pytest.raises(RuntimeError, match='FLAG_DE_TESTE'):
        _flag('FLAG_DE_TESTE', True)


def test_session_cookie_secure_true_liga_os_dois_cookies(ambiente_limpo, tmp_path):
    """``true`` virava False na leitura antiga (``== '1'``): falha aberta."""
    ambiente_limpo.setenv('DATABASE_URL', _sqlite(tmp_path))
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    ambiente_limpo.setenv('SESSION_COOKIE_SECURE', 'true')
    app = create_app()
    assert app.config['SESSION_COOKIE_SECURE'] is True
    assert app.config['REMEMBER_COOKIE_SECURE'] is True
    assert app.config['REMEMBER_COOKIE_SAMESITE'] == 'Lax'


# ── Proxy ─────────────────────────────────────────────────────────────────

def _app_que_diz_o_ip():
    from flask import Flask, request
    app = Flask('ip')

    @app.get('/ip')
    def ip():
        return request.remote_addr or ''
    return app


def test_sem_proxy_hops_o_cabecalho_do_cliente_e_ignorado(monkeypatch):
    monkeypatch.delenv('PROXY_HOPS', raising=False)
    app = _app_que_diz_o_ip()
    _atras_de_proxy(app, _saltos_de_proxy())
    r = app.test_client().get('/ip', headers={'X-Forwarded-For': '203.0.113.7'},
                              environ_base={'REMOTE_ADDR': '10.0.0.1'})
    assert r.get_data(as_text=True) == '10.0.0.1'


def test_proxy_hops_faz_valer_o_ip_do_cliente(monkeypatch):
    monkeypatch.setenv('PROXY_HOPS', '1')
    app = _app_que_diz_o_ip()
    _atras_de_proxy(app, _saltos_de_proxy())
    r = app.test_client().get('/ip', headers={'X-Forwarded-For': '203.0.113.7'},
                              environ_base={'REMOTE_ADDR': '10.0.0.1'})
    assert r.get_data(as_text=True) == '203.0.113.7'


def test_proxy_hops_invalido_para_o_boot(monkeypatch):
    monkeypatch.setenv('PROXY_HOPS', 'um')
    with pytest.raises(RuntimeError, match='PROXY_HOPS'):
        _saltos_de_proxy()


def test_a_fabrica_aplica_o_proxy_hops(ambiente_limpo, tmp_path):
    from werkzeug.middleware.proxy_fix import ProxyFix
    ambiente_limpo.setenv('DATABASE_URL', _sqlite(tmp_path))
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    ambiente_limpo.setenv('PROXY_HOPS', '2')
    app = create_app()
    assert isinstance(app.wsgi_app, ProxyFix) and app.wsgi_app.x_for == 2


# ── O boot não faz DDL ────────────────────────────────────────────────────

def test_o_boot_nao_cria_tabelas_nem_no_sqlite(ambiente_limpo, tmp_path):
    """O ``create_all`` no boot quebrava o ``flask db upgrade`` ("table users
    already exists") e escondia do autogenerate a coluna nova."""
    ambiente_limpo.setenv('DATABASE_URL', _sqlite(tmp_path, 'vazio.db'))
    ambiente_limpo.setenv('SECRET_KEY', 'segredo-de-teste')
    app = create_app()
    with app.app_context():
        from facilities.extensions import db
        assert sa.inspect(db.engine).get_table_names() == []
        db.engine.dispose()


# ── A suíte não zera banco que não é de teste ─────────────────────────────

@pytest.mark.parametrize('url', [
    'postgresql://u:p@db.exemplo.supabase.co:5432/postgres',
    'postgresql://u:p@localhost/facilities',
    'postgresql://u:p@localhost/producao',
])
def test_conftest_recusa_banco_sem_test_no_nome(url):
    from tests.conftest import recusar_banco_que_nao_e_de_teste
    with pytest.raises(pytest.exit.Exception):
        recusar_banco_que_nao_e_de_teste(url)


@pytest.mark.parametrize('url', [
    'postgresql://postgres:postgres@localhost:5432/facilities_testes',
    'postgresql://u:p@localhost/facilities_test',
])
def test_conftest_aceita_banco_de_teste(url):
    from tests.conftest import recusar_banco_que_nao_e_de_teste
    recusar_banco_que_nao_e_de_teste(url)


# ── Imagem Docker ─────────────────────────────────────────────────────────

def test_dockerignore_deixa_de_fora_segredo_dados_e_ambiente_local():
    with open(os.path.join(RAIZ, '.dockerignore'), encoding='utf-8') as f:
        linhas = {l.strip().rstrip('/') for l in f if l.strip() and not l.startswith('#')}
    for item in ('.env', 'instance', '.venv', 'venv', '.git', '*.db', 'tests'):
        assert item in linhas, item
    # As migrações TÊM de ir: o entrypoint roda ``flask db upgrade``.
    assert not any(l.startswith('migrations') for l in linhas)


def test_dockerfile_copia_ja_com_o_dono_certo():
    """``chown -R`` numa camada própria duplicava todos os bytes da imagem."""
    with open(os.path.join(RAIZ, 'Dockerfile'), encoding='utf-8') as f:
        texto = f.read()
    assert 'COPY --chown=facilities . .' in texto
    assert 'chown -R' not in texto
