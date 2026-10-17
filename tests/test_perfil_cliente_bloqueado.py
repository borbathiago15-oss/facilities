"""Fase 2 — o perfil cliente existe, mas não entra até a liberação (Fase 9)."""
from tests import fabrica


def test_conta_de_cliente_nao_faz_login(app_module):
    from facilities.cadastros import servico
    with app_module.app.app_context():
        emp = servico.salvar_empresa(None, {'nome': 'Trino Serviços'}, None)
        gl = servico.salvar_contratante(None, {'nome': 'Grupo GL', 'empresa_id': emp.id}, None)
        from app import db
        db.session.commit()
        fabrica.pessoa(app_module, 'cliente.gl@cliente.com', 'cliente', cliente_id=gl.id)
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': 'cliente.gl@cliente.com', 'password': fabrica.SENHA})
    assert r.status_code == 403
    assert 'ainda não foi liberado' in r.get_data(as_text=True)
    assert c.get('/').status_code == 302


def test_cliente_precisa_de_um_cliente_no_cadastro(app_module, auth_client):
    r = auth_client.post('/admin/usuarios', data={'name': 'Cli', 'email': 'cli.sem@x.com',
                                                  'role': 'cliente'}, follow_redirects=True)
    assert 'de qual cliente' in r.get_data(as_text=True)
    with app_module.app.app_context():
        from app import User
        assert User.query.filter_by(email='cli.sem@x.com').first() is None


def test_cliente_nao_age_em_modulo_nenhum(app_module):
    from app import User
    u = User(role='cliente')
    for modulo in ('diario_operacional', 'chamados'):
        assert not u.can_access(modulo) and not u.can_view(modulo)
    assert not u.e_gestao()
