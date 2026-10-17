"""Fase 1 — os cadastros pela tela, e quem pode o quê.

* empresa, cliente e estado: só o administrador;
* estrutura do local: administrador e gestor (só nos locais da carteira); a
  diretoria consulta; encarregado e técnico não abrem;
* o formulário de locais liga cliente e estado;
* as etiquetas saem em PDF; o endereço do QR exige login e carteira.
"""
from tests import fabrica


def _ids(app_module):
    with app_module.app.app_context():
        return fabrica.estrutura(app_module)


def test_admin_cadastra_empresa_cliente_estado_e_liga_o_local(app_module, auth_client):
    r = auth_client.post('/cadastros/empresas', data={'nome': 'Trino Serviços', 'cnpj': ''})
    assert r.status_code == 302
    with app_module.app.app_context():
        from facilities.cadastros.models import Empresa, Estado
        emp = Empresa.query.filter_by(nome='Trino Serviços').one().id
        mg = Estado.query.filter_by(sigla='MG').one().id
    auth_client.post('/cadastros/clientes', data={'nome': 'Grupo GL', 'empresa_id': emp,
                                                  'centro_custo': 'GL'})
    auth_client.post(f'/cadastros/estados/{mg}/ativo', data={'ativo': '1'})
    with app_module.app.app_context():
        from facilities.cadastros.models import Contratante
        cli = Contratante.query.filter_by(nome='Grupo GL').one().id
    r = auth_client.post('/admin/contratos', data={
        'name': 'GL — Armazém 2', 'cost_center': 'GL-02', 'contratante_id': cli,
        'estado_id': mg})
    assert r.status_code == 302
    with app_module.app.app_context():
        from app import Client
        loc = Client.query.filter_by(name='GL — Armazém 2').one()
        assert loc.contratante.nome == 'Grupo GL' and loc.estado.sigla == 'MG'
        assert loc.cost_center == 'GL-02'
    html = auth_client.get('/admin/contratos').get_data(as_text=True)
    assert 'Grupo GL' in html and 'Locais' in html


def test_local_nao_aceita_estado_desativado(app_module, auth_client):
    with app_module.app.app_context():
        from facilities.cadastros.models import Estado
        rj = Estado.query.filter_by(sigla='RJ').one().id
    auth_client.post('/admin/contratos', data={'name': 'Local no RJ', 'estado_id': rj})
    with app_module.app.app_context():
        from app import Client
        assert Client.query.filter_by(name='Local no RJ').first() is None


def test_local_sem_cliente_continua_valendo(app_module, auth_client):
    r = auth_client.post('/admin/contratos', data={'name': 'Local antigo sem cliente'})
    assert r.status_code == 302
    with app_module.app.app_context():
        from app import Client
        loc = Client.query.filter_by(name='Local antigo sem cliente').one()
        assert loc.contratante_id is None and loc.estado_id is None


def test_admin_monta_a_arvore_pela_tela(app_module, auth_client):
    with app_module.app.app_context():
        cid = fabrica.local('Condomínio Sul').id
    base = f'/cadastros/locais/{cid}'
    auth_client.post(f'{base}/setor', data={'nome': 'Área comum'})
    with app_module.app.app_context():
        from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
        sid = Setor.query.filter_by(client_id=cid, nome='Área comum').one().id
    auth_client.post(f'{base}/ambiente', data={'nome': 'Hall', 'setor_id': sid})
    with app_module.app.app_context():
        aid = Ambiente.query.filter_by(nome='Hall').one().id
    auth_client.post(f'{base}/equipamento', data={'nome': 'Elevador', 'ambiente_id': aid})
    auth_client.post(f'{base}/ponto', data={'nome': 'Porta do hall', 'ambiente_id': aid})
    html = auth_client.get(base).get_data(as_text=True)
    for texto in ('Área comum', 'Hall', 'Elevador', 'Porta do hall'):
        assert texto in html
    with app_module.app.app_context():
        pid = PontoInspecao.query.filter_by(nome='Porta do hall').one().id
    auth_client.post(f'{base}/ponto/{pid}/ativo', data={'ativo': '0'})
    assert 'Porta do hall' not in auth_client.get(base).get_data(as_text=True)
    assert 'Porta do hall' in auth_client.get(base + '?inativos=1').get_data(as_text=True)


def test_erro_de_cadastro_volta_com_a_mensagem(app_module, auth_client):
    ids = _ids(app_module)
    r = auth_client.post(f"/cadastros/locais/{ids['local']}/setor",
                         data={'nome': 'administrativo'}, follow_redirects=True)
    assert 'Já existe' in r.get_data(as_text=True)


def test_item_de_outro_local_da_404(app_module, auth_client):
    ids = _ids(app_module)
    with app_module.app.app_context():
        outro = fabrica.local('Hospital Norte').id
    r = auth_client.post(f"/cadastros/locais/{outro}/setor/{ids['setor']}",
                         data={'nome': 'Sequestro'})
    assert r.status_code == 404
    r = auth_client.post(f"/cadastros/locais/{outro}/ponto/{ids['ponto']}/ativo",
                         data={'ativo': '0'})
    assert r.status_code == 404


def test_gestor_estrutura_so_os_locais_dele(app_module):
    ids = _ids(app_module)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'gestor.estrutura@trino.com', 'pleno',
                       locais=['Shopping Centro'])
        outro = fabrica.local('Hospital Norte').id
    c = fabrica.entrar(app_module, 'gestor.estrutura@trino.com')
    assert c.get(f"/cadastros/locais/{ids['local']}").status_code == 200
    assert c.post(f"/cadastros/locais/{ids['local']}/setor",
                  data={'nome': 'Novo do gestor'}).status_code == 302
    assert c.get(f'/cadastros/locais/{outro}').status_code == 403
    assert c.post(f'/cadastros/locais/{outro}/setor', data={'nome': 'X'}).status_code == 403
    # Empresa, cliente e estado são do administrador.
    assert c.post('/cadastros/empresas', data={'nome': 'Pirata'}).status_code in (302, 403)
    with app_module.app.app_context():
        from facilities.cadastros.models import Empresa, Setor
        assert Empresa.query.filter_by(nome='Pirata').first() is None
        assert Setor.query.filter_by(nome='Novo do gestor').count() == 1
        assert Setor.query.filter_by(nome='X').count() == 0


def test_diretoria_consulta_e_nao_altera(app_module):
    ids = _ids(app_module)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'diretoria.cad@trino.com', 'visualizador', all_clients=True)
    c = fabrica.entrar(app_module, 'diretoria.cad@trino.com')
    assert c.get(f"/cadastros/locais/{ids['local']}").status_code == 200
    assert c.post(f"/cadastros/locais/{ids['local']}/setor",
                  data={'nome': 'Da diretoria'}).status_code == 403


def test_encarregado_e_tecnico_nao_abrem_cadastros(app_module):
    ids = _ids(app_module)
    for papel in ('encarregado', 'tecnico'):
        email = f'{papel}.cad@trino.com'
        with app_module.app.app_context():
            fabrica.pessoa(app_module, email, papel, locais=['Shopping Centro'])
        c = fabrica.entrar(app_module, email)
        assert c.get('/cadastros/').status_code == 403
        assert c.get(f"/cadastros/locais/{ids['local']}").status_code == 403
        assert c.post(f"/cadastros/locais/{ids['local']}/setor",
                      data={'nome': 'Do piso'}).status_code == 403


def test_etiquetas_saem_em_pdf(app_module, auth_client):
    ids = _ids(app_module)
    r = auth_client.get(f"/cadastros/locais/{ids['local']}/etiquetas.pdf")
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.data[:4] == b'%PDF'
    r = auth_client.get(f"/cadastros/locais/{ids['local']}/etiquetas.pdf?ponto={ids['ponto']}")
    assert r.data[:4] == b'%PDF'


def test_qr_exige_login_e_carteira(app_module, auth_client):
    ids = _ids(app_module)
    anonimo = app_module.app.test_client()
    r = anonimo.get(f"/q/{ids['qr']}")
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert 'Porta do banheiro' in auth_client.get(f"/q/{ids['qr']}").get_data(as_text=True)
    assert auth_client.get('/q/codigo-que-nao-existe').status_code == 404
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'enc.fora@trino.com', 'encarregado', locais=['Hospital Norte'])
        fabrica.pessoa(app_module, 'enc.dentro@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
    assert fabrica.entrar(app_module, 'enc.fora@trino.com').get(
        f"/q/{ids['qr']}").status_code == 403
    assert fabrica.entrar(app_module, 'enc.dentro@trino.com').get(
        f"/q/{ids['qr']}").status_code == 200


def test_menu_mostra_cadastros_para_a_gestao(app_module, auth_client):
    html = auth_client.get('/cadastros/').get_data(as_text=True)
    assert 'Empresas do grupo' in html and 'Estrutura dos locais' in html
