"""Ambiente de teste: SQLite temporário, CSRF desligado e o seed mínimo.

O ``app_module`` é o módulo ``app`` (como no Trino Intelligence, de onde os
testes da Passagem vieram): ``app_module.app``, ``app_module.db``,
``app_module.User``, ``app_module.Client``.
"""
import os
import tempfile

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-pass')
os.environ['SESSION_COOKIE_SECURE'] = '0'
os.environ['RATELIMIT_ENABLED'] = '0'
TEST_ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
ADMIN_EMAIL = 'admin@grupotrino.com.br'
CONTRATOS_SEMEADOS = ('Shopping Centro', 'Hospital Norte', 'Condomínio Sul')


@pytest.fixture(scope='session')
def app_module():
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
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def clean_transactional_data(app_module):
    """Isola cada teste: apaga o que é lançado (mantém contratos e pessoas)."""
    yield
    with app_module.app.app_context():
        from facilities.core.models import Notification
        from facilities.passagem.models import (
            DiarioAnexo, DiarioArea, DiarioConfiguracao, DiarioOcorrencia,
            DiarioPendencia, DiarioPendenciaEvento, DiarioTarefaTurno,
            DiarioTurno, DiarioTurnoCorrecao)
        from facilities.chamados import models as chamados_models
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
