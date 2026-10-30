"""Ambiente de teste: SQLite temporário, CSRF desligado e o seed mínimo.

O ``app_module`` é o módulo ``app`` (como no Trino Intelligence, de onde os
testes da Passagem vieram): ``app_module.app``, ``app_module.db``,
``app_module.User``, ``app_module.Client``.
"""
import os
import tempfile

import pytest
from sqlalchemy.engine import make_url

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-pass')
# Chave FIXA dos campos cifrados (core/cifra.py), só da suíte.
os.environ['FIELD_ENCRYPTION_KEY'] = 'dGVzdGUtZGEtc3VpdGUtY2hhdmUtY2lmcmEtMzJieXQ='
os.environ.pop('FIELD_ENCRYPTION_OLD_KEYS', None)
os.environ['SESSION_COOKIE_SECURE'] = '0'
os.environ['RATELIMIT_ENABLED'] = '0'
# A segunda etapa obrigatória da gestão (auditoria SEC-001) fica desligada na
# suíte; tests/test_seguranca_login.py liga e confere.
os.environ['MFA_OBRIGATORIO_GESTAO'] = '0'
# Anexos de teste no disco temporário, SEMPRE: com as R2_* no ambiente de
# quem roda, a suíte gravaria no bucket de verdade; e com Postgres a fábrica
# exige o destino dos anexos declarado.
os.environ['STORAGE_BACKEND'] = 'local'
os.environ.pop('PROXY_HOPS', None)
os.environ.pop('EXIGIR_DATABASE_URL', None)
TEST_ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
ADMIN_EMAIL = 'admin@grupotrino.com.br'
CONTRATOS_SEMEADOS = ('Shopping Centro', 'Hospital Norte', 'Condomínio Sul')


def recusar_banco_que_nao_e_de_teste(url):
    """Para a suíte se o banco de TEST_DATABASE_URL não for claramente de teste.

    A fixture abaixo faz ``downgrade base`` — o downgrade da migração inicial
    apaga TODAS as tabelas. Com a URL da produção copiada por engano (o
    próprio CI usa a mesma para DATABASE_URL e TEST_DATABASE_URL), a suíte
    zerava a produção sem perguntar. Exige "test" no nome do banco
    (``facilities_testes``, ``facilities_test``...).
    """
    try:
        nome = make_url(url).database or ''
    except Exception:
        pytest.exit(f'TEST_DATABASE_URL não é uma URL de banco válida: {url!r}.',
                    returncode=4)
    if 'test' not in nome.lower():
        pytest.exit(f'TEST_DATABASE_URL aponta para o banco {nome!r}, cujo nome não '
                    'tem "test". A suíte APAGA todas as tabelas do banco de teste; '
                    'use um banco só para isso (ex.: facilities_testes).',
                    returncode=4)


@pytest.fixture(scope='session')
def app_module():
    # TEST_DATABASE_URL=postgresql://... roda a suíte contra um Postgres de
    # verdade (o MESMO tipo de banco da produção — nunca o banco dela), com o
    # schema vindo das MIGRAÇÕES. O banco é zerado no começo: só banco de teste.
    pg = os.environ.get('TEST_DATABASE_URL', '').strip()
    path = None
    if pg:
        recusar_banco_que_nao_e_de_teste(pg)
        os.environ['DATABASE_URL'] = pg
    else:
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.environ['DATABASE_URL'] = f'sqlite:///{path}'
    os.environ['UPLOAD_FOLDER'] = tempfile.mkdtemp(prefix='facilities-uploads-')
    import app as app_mod
    app_mod.app.config['WTF_CSRF_ENABLED'] = False
    app_mod.app.config['RATELIMIT_ENABLED'] = False
    app_mod.app.config['TESTING'] = True
    with app_mod.app.app_context():
        db = app_mod.db
        if pg:
            from flask_migrate import downgrade, upgrade
            raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            pasta = os.path.join(raiz, 'migrations')
            db.session.remove()
            downgrade(directory=pasta, revision='base')
            # A volta das migrações guarda os cadastros em _quarentena_* e a
            # ida seguinte os devolve (é o que protege a produção). No banco
            # de TESTE isso traria de volta o lixo da rodada anterior: aqui,
            # e só aqui, a quarentena é descartada.
            from sqlalchemy import inspect, text
            for nome in inspect(db.engine).get_table_names():
                if nome.startswith('_quarentena_'):
                    with db.engine.begin() as con:
                        con.execute(text(f'DROP TABLE "{nome}"'))
            upgrade(directory=pasta)
        else:
            # O boot não faz DDL em banco nenhum: no SQLite temporário o
            # schema sai direto dos modelos — e as 27 UFs, que no Postgres
            # vêm da migração, entram aqui.
            db.create_all()
            from facilities.cadastros.models import UFS, Estado
            for sigla, nome in UFS:
                db.session.add(Estado(sigla=sigla, nome=nome, is_active=False))
        for nome in CONTRATOS_SEMEADOS:
            if not app_mod.Client.query.filter_by(name=nome).first():
                db.session.add(app_mod.Client(name=nome, cost_center='CC-' + nome[:3].upper(),
                                              is_active=True))
        admin = app_mod.User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin is None:
            admin = app_mod.User(name='Administrador', email=ADMIN_EMAIL, role='master')
            db.session.add(admin)
        admin.set_password(TEST_ADMIN_PASSWORD)
        admin.must_change_password = False
        db.session.commit()
    yield app_mod
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def clean_transactional_data(app_module):
    """Isola cada teste: apaga o que é lançado (mantém contratos e pessoas)."""
    yield
    with app_module.app.app_context():
        from tests.fabrica import desligar_criadas
        desligar_criadas()
        from facilities.core.models import Notification
        from facilities.passagem.models import (
            DiarioAnexo, DiarioArea, DiarioConfiguracao, DiarioOcorrencia,
            DiarioPendencia, DiarioPendenciaEvento, DiarioTarefaTurno,
            DiarioTurno, DiarioTurnoCorrecao)
        from facilities.chamados import models as chamados_models
        from facilities.cadastros import models as cadastros_models
        from facilities.core.models import Client
        # Os cadastros da estrutura: desliga os locais dos clientes e apaga
        # do filho para o pai. Os estados ficam (são a lista fixa), desativados.
        from facilities.rotas import models as rotas_models
        from facilities.core.models import PushInscricao
        # A preventiva aponta para pontos, checklists e chamados: sai antes.
        from facilities.preventiva import models as preventiva_models
        # Fase 6: equipe e visitas apontam para rotas, checklists e chamados.
        from facilities.equipes import models as equipes_models
        from facilities.visitas import models as visitas_models
        from facilities.materiais import models as materiais_models
        from facilities.integracao import models as integracao_models
        from facilities.portal import models as portal_models
        from facilities.relatorios import models as relatorios_models
        app_module.db.session.execute(integracao_models.chave_locais.delete())
        app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False
        app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = False
        # A área aponta para o checklist dela (cadastro simplificado): solta
        # antes de apagar os checklists.
        cadastros_models.PontoInspecao.query.update({'checklist_id': None})
        for model in (relatorios_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + portal_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + integracao_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + materiais_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + equipes_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + visitas_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + preventiva_models.MODELOS_EM_ORDEM_DE_LIMPEZA
                      + rotas_models.MODELOS_EM_ORDEM_DE_LIMPEZA + (PushInscricao,)):
            model.query.delete()
        app_module.app.extensions.pop('facilities_push', None)
        Client.query.update({'contratante_id': None, 'estado_id': None, 'latitude': None,
                             'longitude': None, 'raio_gps_m': None,
                             'posicao_marcada_em': None, 'posicao_marcada_por': None})
        # A cadeia e o perfil cliente (Fase 2) também apontam para cadastros.
        app_module.User.query.update({'cliente_id': None, 'superior_id': None})
        for model in cadastros_models.MODELOS_EM_ORDEM_DE_LIMPEZA:
            model.query.delete()
        cadastros_models.Estado.query.update({'is_active': False})
        modelos = list(getattr(chamados_models, 'MODELOS_EM_ORDEM_DE_LIMPEZA', ()))
        modelos += [Notification, DiarioAnexo, DiarioPendenciaEvento, DiarioTurnoCorrecao,
                    DiarioTarefaTurno, DiarioOcorrencia, DiarioPendencia, DiarioTurno,
                    DiarioConfiguracao, DiarioArea]
        for model in modelos:
            model.query.delete()
        app_module.db.session.commit()


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture()
def auth_client(client):
    client.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
    return client
