"""Primeiro administrador sem terminal (ADMIN_INICIAL_EMAIL): cria só quando
não há administrador ativo; senha temporária com troca obrigatória."""
import pytest

from tests import fabrica


@pytest.fixture()
def sem_admin(app_module):
    """Tira (só durante o teste) os administradores ativos semeados."""
    from app import User, db
    with app_module.app.app_context():
        ids = [u.id for u in User.query.filter_by(role='master', is_active=True)]
        User.query.filter(User.id.in_(ids)).update({'is_active': False})
        db.session.commit()
    yield
    with app_module.app.app_context():
        User.query.filter(User.id.in_(ids)).update({'is_active': True})
        User.query.filter_by(email='dono.inicial@trino.com').delete()
        db.session.commit()


def _rodar(app_module, monkeypatch, **env):
    for k in ('ADMIN_INICIAL_EMAIL', 'ADMIN_INICIAL_NOME', 'ADMIN_INICIAL_SENHA'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return app_module.app.test_cli_runner().invoke(args=['admin-inicial'])


def test_sem_variavel_nao_faz_nada(app_module, monkeypatch, sem_admin):
    from app import User
    r = _rodar(app_module, monkeypatch)
    assert r.exit_code == 0 and r.output == ''
    with app_module.app.app_context():
        assert User.query.filter_by(role='master', is_active=True).count() == 0


def test_cria_com_senha_sorteada_e_troca_obrigatoria(app_module, monkeypatch, sem_admin):
    r = _rodar(app_module, monkeypatch, ADMIN_INICIAL_EMAIL='Dono.Inicial@trino.com',
               ADMIN_INICIAL_NOME='Thiago Borba')
    assert 'Senha temporária: ' in r.output
    senha = r.output.split('Senha temporária: ')[1].split(' ')[0]
    c = app_module.app.test_client()
    resp = c.post('/login', data={'email': 'dono.inicial@trino.com', 'password': senha})
    assert resp.status_code == 302 and '/trocar-senha' in resp.headers['Location']
    # Rodar de novo (a cada deploy) não troca a senha nem cria outro.
    r2 = _rodar(app_module, monkeypatch, ADMIN_INICIAL_EMAIL='dono.inicial@trino.com')
    assert 'nada a fazer' in r2.output


def test_senha_informada_na_variavel(app_module, monkeypatch, sem_admin):
    r = _rodar(app_module, monkeypatch, ADMIN_INICIAL_EMAIL='dono.inicial@trino.com',
               ADMIN_INICIAL_SENHA='inicial-123')
    assert 'Senha temporária' not in r.output and 'inicial-123' not in r.output
    c = app_module.app.test_client()
    resp = c.post('/login', data={'email': 'dono.inicial@trino.com', 'password': 'inicial-123'})
    assert resp.status_code == 302 and '/trocar-senha' in resp.headers['Location']


def test_com_administrador_ativo_nao_mexe(app_module, monkeypatch):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'existente@trino.com', 'pleno')
    r = _rodar(app_module, monkeypatch, ADMIN_INICIAL_EMAIL='existente@trino.com')
    assert 'nada a fazer' in r.output
    from app import User
    with app_module.app.app_context():
        assert User.query.filter_by(email='existente@trino.com').one().role == 'pleno'
