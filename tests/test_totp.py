"""Fase 2 — a segunda etapa do login (código do aplicativo autenticador).

* certo entra; errado e reutilizado são recusados;
* entre a senha e o código a pessoa NÃO está logada;
* 5 códigos errados mandam de volta à senha;
* ativar exige um código válido; desativar exige a senha;
* o administrador desliga para quem perdeu o celular, e as sessões caem.
"""
import re

from facilities.core import totp
from tests import fabrica


def _com_codigo(app_module, email, papel='pleno'):
    from app import User, db
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, email, papel, locais=['Shopping Centro'])
        u = db.session.get(User, uid)
        u.totp_segredo = totp.novo_segredo()
        u.totp_ativo = True
        db.session.commit()
        return uid, u.totp_segredo


def _senha(app_module, email):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': email, 'password': fabrica.SENHA})
    return c, r


def test_codigo_certo_entra_e_errado_nao(app_module):
    _, segredo = _com_codigo(app_module, 'totp1@trino.com')
    c, r = _senha(app_module, 'totp1@trino.com')
    assert r.status_code == 302 and r.headers['Location'].endswith('/login/codigo')
    assert c.get('/').status_code == 302                       # ainda não entrou
    assert c.post('/login/codigo', data={'codigo': '000000'}).status_code == 401
    r = c.post('/login/codigo', data={'codigo': totp.codigo(segredo)})
    assert r.status_code == 302
    assert c.get('/').status_code == 200


def test_codigo_reutilizado_e_recusado(app_module):
    _, segredo = _com_codigo(app_module, 'totp2@trino.com')
    cod = totp.codigo(segredo)
    c, _ = _senha(app_module, 'totp2@trino.com')
    assert c.post('/login/codigo', data={'codigo': cod}).status_code == 302
    outro, _ = _senha(app_module, 'totp2@trino.com')
    assert outro.post('/login/codigo', data={'codigo': cod}).status_code == 401


def test_cinco_erros_voltam_para_a_senha(app_module):
    _com_codigo(app_module, 'totp3@trino.com')
    c, _ = _senha(app_module, 'totp3@trino.com')
    for _ in range(4):
        assert c.post('/login/codigo', data={'codigo': '000000'}).status_code == 401
    r = c.post('/login/codigo', data={'codigo': '000000'})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert c.get('/login/codigo').status_code == 302


def test_codigo_sem_ter_passado_pela_senha_nao_abre(app_module):
    _, segredo = _com_codigo(app_module, 'totp4@trino.com')
    c = app_module.app.test_client()
    r = c.post('/login/codigo', data={'codigo': totp.codigo(segredo)})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert c.get('/').status_code == 302


def test_ativar_e_desativar_pela_propria_pessoa(app_module):
    from app import User, db
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'totp5@trino.com', 'encarregado',
                             locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'totp5@trino.com')
    html = c.get('/conta/seguranca').get_data(as_text=True)
    segredo = re.search(r'<code class="user-select-all">([A-Z2-7]+)</code>', html).group(1)
    assert '<svg' in html
    c.post('/conta/seguranca/ativar', data={'codigo': '123456'})
    with app_module.app.app_context():
        assert db.session.get(User, uid).totp_ativo is False
    c.post('/conta/seguranca/ativar', data={'codigo': totp.codigo(segredo)})
    with app_module.app.app_context():
        assert db.session.get(User, uid).totp_ativo is True
    c.post('/conta/seguranca/desativar', data={'senha': 'errada'})
    with app_module.app.app_context():
        assert db.session.get(User, uid).totp_ativo is True
    c.post('/conta/seguranca/desativar', data={'senha': fabrica.SENHA})
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        assert u.totp_ativo is False and u.totp_segredo is None


def test_administrador_desliga_para_quem_perdeu_o_celular(app_module, auth_client):
    from app import User, db
    uid, segredo = _com_codigo(app_module, 'totp6@trino.com')
    c, _ = _senha(app_module, 'totp6@trino.com')
    c.post('/login/codigo', data={'codigo': totp.codigo(segredo)})
    assert c.get('/').status_code == 200
    auth_client.post(f'/admin/usuarios/{uid}/desligar-codigo')
    with app_module.app.app_context():
        assert db.session.get(User, uid).totp_ativo is False
    assert c.get('/').status_code == 302                       # a sessão aberta caiu
    fabrica.entrar(app_module, 'totp6@trino.com')               # só a senha basta


def test_verificar_tolera_um_passo_e_recusa_lixo():
    s = totp.novo_segredo()
    agora = 1_800_000_000
    assert totp.verificar(s, totp.codigo(s, agora - 30), instante=agora) is not None
    assert totp.verificar(s, totp.codigo(s, agora - 90), instante=agora) is None
    for lixo in ('', 'abcdef', '12345', '1234567', None):
        assert totp.verificar(s, lixo, instante=agora) is None
