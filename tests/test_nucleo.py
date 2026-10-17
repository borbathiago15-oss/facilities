"""O núcleo: login próprio, troca de senha, sessões, cadastros e app instalável.

* senha errada cinco vezes bloqueia a conta; a resposta (mensagem e status)
  não diz se o e-mail existe nem se a conta está bloqueada;
* quem precisa trocar a senha não abre nada antes de trocar;
* trocar a senha (ou ser desativado) derruba as sessões abertas;
* cadastros são do administrador; o gestor não cadastra;
* ``/healthz``, ``/sw.js`` e ``/app/sessao`` respondem sem login.
"""
import pytest

from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD


def _pessoa(app_module, email, papel='encarregado', trocar=False):
    from app import User, db
    u = User.query.filter_by(email=email).first()
    if u is None:
        u = User(name='Pessoa Teste', email=email)
        db.session.add(u)
    u.role = papel
    u.is_active = True
    u.is_deleted = False
    u.must_change_password = trocar
    u.failed_login_count = 0
    u.lockout_until = None
    u.set_password('senha12345')
    db.session.commit()
    return u.id


def _entrar(app_module, email, senha='senha12345'):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': email, 'password': senha})
    return c, r


def test_login_certo_entra_e_errado_nao_diz_por_que(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'login.ok@trino.com')
    c, r = _entrar(app_module, 'login.ok@trino.com')
    assert r.status_code == 302
    assert c.get('/').status_code == 200
    _, errado = _entrar(app_module, 'login.ok@trino.com', 'outra-senha')
    _, inexistente = _entrar(app_module, 'ninguem@trino.com', 'outra-senha')
    assert errado.status_code == inexistente.status_code == 401
    assert 'E-mail ou senha incorretos.' in errado.get_data(as_text=True)
    assert 'E-mail ou senha incorretos.' in inexistente.get_data(as_text=True)


def test_cinco_erros_bloqueiam_a_conta(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'bloqueio@trino.com')
    for _ in range(5):
        _entrar(app_module, 'bloqueio@trino.com', 'errada')
    # Agora nem a senha certa entra — e a recusa é a MESMA de um e-mail que
    # não existe (antes era 429 "Conta bloqueada", que confirmava a conta).
    _, r = _entrar(app_module, 'bloqueio@trino.com')
    assert r.status_code == 401
    assert 'E-mail ou senha incorretos.' in r.get_data(as_text=True)
    with app_module.app.app_context():
        from datetime import datetime
        from app import User
        u = User.query.filter_by(email='bloqueio@trino.com').one()
        assert u.lockout_until and u.lockout_until > datetime.utcnow()


def test_quem_precisa_trocar_a_senha_nao_abre_nada_antes(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'troca@trino.com', trocar=True)
    c, r = _entrar(app_module, 'troca@trino.com')
    assert r.headers['Location'].endswith('/trocar-senha')
    assert c.get('/passagem-de-turno/').headers['Location'].endswith('/trocar-senha')
    assert c.post('/chamados/', data={}).status_code == 403
    r = c.post('/trocar-senha', data={'atual': 'senha12345', 'nova': 'nova-senha-123',
                                      'confirma': 'nova-senha-123'})
    assert r.status_code == 302
    assert c.get('/').status_code == 200


def test_trocar_a_senha_derruba_a_sessao_do_outro_aparelho(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'dois.aparelhos@trino.com')
    celular, _ = _entrar(app_module, 'dois.aparelhos@trino.com')
    computador, _ = _entrar(app_module, 'dois.aparelhos@trino.com')
    computador.post('/trocar-senha', data={'atual': 'senha12345', 'nova': 'nova-senha-123',
                                           'confirma': 'nova-senha-123'})
    assert computador.get('/').status_code == 200          # este aparelho continua
    assert celular.get('/').status_code == 302              # o outro cai no login


def test_senha_curta_ou_diferente_e_recusada(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'senha.ruim@trino.com')
    c, _ = _entrar(app_module, 'senha.ruim@trino.com')
    assert c.post('/trocar-senha', data={'atual': 'senha12345', 'nova': 'curta',
                                         'confirma': 'curta'}).status_code == 400
    assert c.post('/trocar-senha', data={'atual': 'senha12345', 'nova': 'nova-senha-123',
                                         'confirma': 'outra-senha-123'}).status_code == 400


def test_o_administrador_cadastra_com_senha_temporaria(app_module, auth_client):
    with app_module.app.app_context():
        from app import Client
        cid = Client.query.first().id
    r = auth_client.post('/admin/usuarios', data={
        'name': 'Rita Portaria', 'email': 'rita.portaria@trino.com', 'role': 'encarregado',
        'clients': [str(cid)]}, follow_redirects=True)
    corpo = r.get_data(as_text=True)
    assert 'Senha temporária:' in corpo
    senha = corpo.split('Senha temporária: ')[1].split(' ')[0]
    with app_module.app.app_context():
        from app import User
        u = User.query.filter_by(email='rita.portaria@trino.com').one()
        assert u.must_change_password and u.client_ids == [cid]
    _, r = _entrar(app_module, 'rita.portaria@trino.com', senha)
    assert r.headers['Location'].endswith('/trocar-senha')


def test_email_repetido_nao_cadastra(app_module, auth_client):
    r = auth_client.post('/admin/usuarios', data={
        'name': 'Outro Admin', 'email': ADMIN_EMAIL, 'role': 'pleno'}, follow_redirects=True)
    assert 'Já existe uma pessoa com este e-mail.' in r.get_data(as_text=True)


def test_desativar_derruba_a_sessao(app_module, auth_client):
    with app_module.app.app_context():
        uid = _pessoa(app_module, 'desativa@trino.com')
    c, _ = _entrar(app_module, 'desativa@trino.com')
    assert c.get('/').status_code == 200
    auth_client.post(f'/admin/usuarios/{uid}', data={
        'name': 'Pessoa Teste', 'email': 'desativa@trino.com', 'role': 'encarregado'})
    assert c.get('/').status_code == 302
    _, r = _entrar(app_module, 'desativa@trino.com')
    assert r.status_code == 401


def test_o_administrador_nao_tira_o_proprio_acesso(app_module, auth_client):
    with app_module.app.app_context():
        from app import User
        uid = User.query.filter_by(email=ADMIN_EMAIL).one().id
    r = auth_client.post(f'/admin/usuarios/{uid}', data={
        'name': 'Administrador', 'email': ADMIN_EMAIL, 'role': 'pleno', 'is_active': '1'},
        follow_redirects=True)
    assert 'Você não pode tirar o seu próprio acesso de administrador.' in r.get_data(as_text=True)
    with app_module.app.app_context():
        from app import User
        assert User.query.get(uid).role == 'master'


@pytest.mark.parametrize('papel', ['pleno', 'encarregado', 'tecnico', 'visualizador'])
def test_cadastros_sao_so_do_administrador(app_module, papel):
    with app_module.app.app_context():
        _pessoa(app_module, f'sem.cadastro.{papel}@trino.com', papel)
    c, _ = _entrar(app_module, f'sem.cadastro.{papel}@trino.com')
    assert c.get('/admin/usuarios').status_code == 302
    assert c.post('/admin/contratos', data={'name': 'Contrato pirata'}).status_code == 403
    with app_module.app.app_context():
        from app import Client
        assert Client.query.filter_by(name='Contrato pirata').first() is None


def test_o_administrador_cadastra_contrato(app_module, auth_client):
    auth_client.post('/admin/contratos', data={'name': 'Escola Leste — Limpeza',
                                               'cost_center': 'CC-ESC'})
    with app_module.app.app_context():
        from app import Client
        c = Client.query.filter_by(name='Escola Leste — Limpeza').one()
        assert c.is_active and c.cost_center == 'CC-ESC'


def test_publicos_sem_login(app_module):
    c = app_module.app.test_client()
    assert c.get('/healthz').get_json() == {'status': 'ok'}
    sw = c.get('/sw.js')
    assert sw.status_code == 200 and sw.headers['Service-Worker-Allowed'] == '/'
    assert c.get('/manifest.webmanifest').get_json()['name'] == 'Trino Facilities'
    assert c.get('/app/sessao').status_code == 401
    assert 'versao' in c.get('/app/versao').get_json()
    # O resto pede login: a tela vai para o login, a API recebe 401 em JSON.
    assert c.get('/chamados/').status_code == 302
    assert c.post('/passagem-de-turno/api/turnos', json={}).status_code == 401


def test_sessao_do_app_diz_quem_esta_logado(app_module, auth_client):
    r = auth_client.get('/app/sessao')
    assert r.status_code == 200 and r.get_json()['autenticado'] is True


def test_avisos_abrem_e_marcam_como_lidos(app_module, auth_client):
    with app_module.app.app_context():
        from app import User, db
        from facilities.core.models import Notification
        uid = User.query.filter_by(email=ADMIN_EMAIL).one().id
        n = Notification(user_id=uid, title='Teste', message='m', link='/chamados/',
                         status='unread')
        db.session.add(n)
        db.session.commit()
        nid = n.id
    assert '>1<' in auth_client.get('/').get_data(as_text=True).replace('</span>', '<')
    r = auth_client.post(f'/avisos/{nid}/abrir')
    assert r.headers['Location'].endswith('/chamados/')
    with app_module.app.app_context():
        from facilities.core.models import Notification
        assert Notification.query.get(nid).status == 'read'


def test_responsavel_do_contrato_tem_de_ser_gestor_ativo(app_module, auth_client):
    """A lista da tela só traz gestores, mas um POST montado à mão aceitava
    qualquer pessoa — e ela passava a receber os avisos de gestor."""
    with app_module.app.app_context():
        enc_id = _pessoa(app_module, 'enc.responsavel@trino.com', 'encarregado')
        gestor_id = _pessoa(app_module, 'gestor.responsavel@trino.com', 'pleno')
    r = auth_client.post('/admin/contratos', data={
        'name': 'Contrato com encarregado responsável', 'responsible_user_id': str(enc_id)},
        follow_redirects=True)
    assert 'precisa ser um gestor ou administrador ativo' in r.get_data(as_text=True)
    auth_client.post('/admin/contratos', data={
        'name': 'Contrato com gestor responsável', 'responsible_user_id': str(gestor_id)})
    with app_module.app.app_context():
        from app import Client
        assert Client.query.filter_by(name='Contrato com encarregado responsável').first() is None
        c = Client.query.filter_by(name='Contrato com gestor responsável').one()
        assert c.responsible_user_id == gestor_id
        cid = c.id
    r = auth_client.post(f'/admin/contratos/{cid}', data={
        'name': 'Contrato com gestor responsável', 'is_active': '1',
        'responsible_user_id': str(enc_id)}, follow_redirects=True)
    assert 'precisa ser um gestor ou administrador ativo' in r.get_data(as_text=True)
    with app_module.app.app_context():
        from app import Client
        assert Client.query.get(cid).responsible_user_id == gestor_id
