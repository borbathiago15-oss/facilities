"""Login forte (auditoria de segurança, bloco A, 19/10/2026).

* SEC-001: gestão e diretoria só usam o sistema com a segunda etapa.
* SEC-002: o erro de senha é contado no banco (rajada em paralelo não escapa).
* SEC-003: os erros de código ficam no servidor (repetir o cookie não zera).
* SEC-007: conta bloqueada avisa o administrador.
* SEC-011: errar a senha atual em "trocar a senha" conta como erro de login.
"""
import threading

import pytest

from facilities.core import totp
from tests import fabrica


def _pessoa(app_module, email, papel='pleno'):
    with app_module.app.app_context():
        return fabrica.pessoa(app_module, email, papel, locais=['Shopping Centro'])


def _com_codigo(app_module, email, papel='pleno'):
    from app import User, db
    uid = _pessoa(app_module, email, papel)
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        u.totp_segredo = totp.novo_segredo()
        u.totp_ativo = True
        u.totp_ultimo_passo = None
        db.session.commit()
        return uid, u.totp_segredo


def _usuario(app_module, uid):
    from app import User, db
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        db.session.refresh(u)
        return u


@pytest.fixture()
def mfa_ligado(app_module):
    app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = True
    yield
    app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = False


# ── SEC-001: segunda etapa obrigatória para a gestão ──────────────────────

@pytest.mark.parametrize('papel', ['master', 'gerente', 'pleno', 'visualizador'])
def test_gestao_sem_codigo_so_abre_a_tela_de_seguranca(app_module, mfa_ligado, papel):
    _pessoa(app_module, f'mfa.{papel}@trino.com', papel)
    c = fabrica.entrar(app_module, f'mfa.{papel}@trino.com')
    r = c.get('/')
    assert r.status_code == 302 and '/conta/seguranca' in r.headers['Location']
    assert c.get('/conta/seguranca').status_code == 200
    assert c.get('/trocar-senha').status_code == 200
    # Pela API (JSON) também não passa.
    assert c.post('/app/api/leitura', json={}).status_code == 403


@pytest.mark.parametrize('papel', ['supervisor', 'encarregado', 'tecnico'])
def test_pessoal_de_campo_segue_sem_codigo(app_module, mfa_ligado, papel):
    _pessoa(app_module, f'campo.{papel}@trino.com', papel)
    c = fabrica.entrar(app_module, f'campo.{papel}@trino.com')
    r = c.get('/')
    assert '/conta/seguranca' not in (r.headers.get('Location') or '')


def test_ativar_o_codigo_libera_e_derruba_as_outras_sessoes(app_module, mfa_ligado):
    _pessoa(app_module, 'mfa.ativa@trino.com')
    outra = fabrica.entrar(app_module, 'mfa.ativa@trino.com')
    c = fabrica.entrar(app_module, 'mfa.ativa@trino.com')
    c.get('/conta/seguranca')
    with c.session_transaction() as s:
        segredo = s['_totp_novo']
    r = c.post('/conta/seguranca/ativar', data={'codigo': totp.codigo(segredo)})
    assert r.status_code == 302
    assert c.get('/').status_code in (200, 302)
    assert '/conta/seguranca' not in (c.get('/').headers.get('Location') or '')
    # A sessão aberta só com a senha caiu.
    r = outra.get('/conta/seguranca')
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_gestao_nao_desliga_o_codigo_obrigatorio(app_module, mfa_ligado):
    uid, segredo = _com_codigo(app_module, 'mfa.desliga@trino.com')
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'mfa.desliga@trino.com', 'password': fabrica.SENHA})
    c.post('/login/codigo', data={'codigo': totp.codigo(segredo)})
    c.post('/conta/seguranca/desativar', data={'senha': fabrica.SENHA})
    assert _usuario(app_module, uid).totp_ativo is True


# ── SEC-002: contagem atômica dos erros de senha ──────────────────────────

def test_rajada_em_paralelo_nao_escapa_do_bloqueio(app_module):
    uid = _pessoa(app_module, 'rajada@trino.com')
    barreira = threading.Barrier(12)

    def tentar(i):
        c = app_module.app.test_client()
        barreira.wait()
        c.post('/login', data={'email': 'rajada@trino.com', 'password': f'errada{i}xx'})

    linhas = [threading.Thread(target=tentar, args=(i,)) for i in range(12)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join()
    assert _usuario(app_module, uid).lockout_until is not None
    # Bloqueada: nem a senha certa entra.
    r = app_module.app.test_client().post('/login', data={'email': 'rajada@trino.com',
                                                           'password': fabrica.SENHA})
    assert r.status_code == 401


def test_conta_com_objeto_velho_na_sessao_ainda_conta_certo(app_module):
    """O contador soma no banco, não no valor que o Python leu antes."""
    from app import User, db
    from facilities.core.auth import _contar_erro_de_senha
    from datetime import datetime
    uid = _pessoa(app_module, 'velho@trino.com')
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        _ = u.failed_login_count                      # lido: 0
        db.session.execute(db.update(User).where(User.id == uid)
                           .values(failed_login_count=3))
        db.session.commit()
        assert _contar_erro_de_senha(u, datetime.utcnow()) is False
        assert u.failed_login_count == 4


# ── SEC-003: erros de código no servidor ──────────────────────────────────

def test_repetir_o_cookie_nao_zera_os_erros_de_codigo(app_module):
    uid, segredo = _com_codigo(app_module, 'cookie@trino.com')
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': 'cookie@trino.com', 'password': fabrica.SENHA})
    assert '/login/codigo' in r.headers['Location']
    guardado = c.get_cookie('session').value
    for _ in range(5):
        c.set_cookie('session', guardado)
        c.post('/login/codigo', data={'codigo': '000000'})
    assert _usuario(app_module, uid).totp_bloqueio_ate is not None
    # Travado: nem o código certo entra, nem logando de novo com a senha.
    c2 = app_module.app.test_client()
    c2.post('/login', data={'email': 'cookie@trino.com', 'password': fabrica.SENHA})
    r = c2.post('/login/codigo', data={'codigo': totp.codigo(segredo)})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    r = c2.get('/')
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_senha_certa_nao_zera_os_erros_de_codigo(app_module):
    uid, _segredo = _com_codigo(app_module, 'zera@trino.com')
    for _ in range(2):
        c = app_module.app.test_client()
        c.post('/login', data={'email': 'zera@trino.com', 'password': fabrica.SENHA})
        for _ in range(2):
            c.post('/login/codigo', data={'codigo': '000000'})
    # 4 erros em duas entradas com a senha certa: a conta continua somando.
    assert _usuario(app_module, uid).totp_falhas == 4


def test_codigo_certo_zera_e_nao_vale_duas_vezes(app_module):
    uid, segredo = _com_codigo(app_module, 'certo@trino.com')
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'certo@trino.com', 'password': fabrica.SENHA})
    c.post('/login/codigo', data={'codigo': '000000'})
    codigo = totp.codigo(segredo)
    assert c.post('/login/codigo', data={'codigo': codigo}).status_code == 302
    assert _usuario(app_module, uid).totp_falhas == 0
    # O mesmo código, em outro aparelho, não entra de novo.
    c2 = app_module.app.test_client()
    c2.post('/login', data={'email': 'certo@trino.com', 'password': fabrica.SENHA})
    assert c2.post('/login/codigo', data={'codigo': codigo}).status_code == 401


# ── SEC-007: o administrador fica sabendo do bloqueio ─────────────────────

def test_bloqueio_avisa_o_administrador(app_module):
    from app import db
    from facilities.core.models import Notification
    _pessoa(app_module, 'alvo@trino.com')
    admin = _pessoa(app_module, 'adm.aviso@trino.com', 'master')
    c = app_module.app.test_client()
    for i in range(5):
        c.post('/login', data={'email': 'alvo@trino.com', 'password': f'errada{i}xx'})
    with app_module.app.app_context():
        avisos = Notification.query.filter_by(user_id=admin).all()
        assert any('alvo@trino.com' in a.title for a in avisos)
        db.session.rollback()


# ── SEC-011: a senha atual também tem limite ──────────────────────────────

def test_errar_a_senha_atual_bloqueia_e_derruba_a_sessao(app_module):
    uid = _pessoa(app_module, 'troca@trino.com')
    c = fabrica.entrar(app_module, 'troca@trino.com')
    for i in range(5):
        r = c.post('/trocar-senha', data={'atual': f'errada{i}xx', 'nova': 'novasenha123',
                                          'confirma': 'novasenha123'})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert _usuario(app_module, uid).lockout_until is not None
    r = c.get('/')
    assert r.status_code == 302 and '/login' in r.headers['Location']
