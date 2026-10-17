"""Fase 2 — a cadeia de pessoas e o acesso que sai dela.

    Gerente (cliente GL) → Coordenador → Supervisor → Encarregado
                          └ Coordenador 2 → Encarregado 2

* quem está acima vê os locais de quem está abaixo; o de baixo não vê o de cima;
* o gerente vê todos os locais dos clientes pelos quais responde;
* um coordenador não vê o local do outro coordenador;
* o superior precisa estar num nível acima; trocar perfil não deixa a
  cadeia de cabeça para baixo;
* o coordenador e o gerente agem como gestão; o supervisor faz a passagem.
"""
import pytest

from tests import fabrica


@pytest.fixture()
def cadeia(app_module):
    from app import Client, db
    from facilities.cadastros import servico
    with app_module.app.app_context():
        locais = {n: fabrica.local(n).id for n in ('Shopping Centro', 'Hospital Norte',
                                                    'Condomínio Sul')}
        ger = fabrica.pessoa(app_module, 'ger.cadeia@trino.com', 'gerente')
        emp = servico.salvar_empresa(None, {'nome': 'Trino Serviços'}, None)
        gl = servico.salvar_contratante(None, {'nome': 'Grupo GL', 'empresa_id': emp.id,
                                               'gerente_id': ger}, None)
        # O Shopping e o Hospital são do cliente GL; o Condomínio, de ninguém.
        for nome in ('Shopping Centro', 'Hospital Norte'):
            db.session.get(Client, locais[nome]).contratante_id = gl.id
        db.session.commit()
        coord = fabrica.pessoa(app_module, 'coord.cadeia@trino.com', 'pleno',
                               locais=['Shopping Centro'], superior_id=ger)
        coord2 = fabrica.pessoa(app_module, 'coord2.cadeia@trino.com', 'pleno',
                                locais=['Condomínio Sul'])
        sup = fabrica.pessoa(app_module, 'sup.cadeia@trino.com', 'supervisor',
                             superior_id=coord)
        enc = fabrica.pessoa(app_module, 'enc.cadeia@trino.com', 'encarregado',
                             locais=['Hospital Norte'], superior_id=sup)
        enc2 = fabrica.pessoa(app_module, 'enc2.cadeia@trino.com', 'encarregado',
                              locais=['Condomínio Sul'], superior_id=coord2)
    return {'locais': locais, 'ger': ger, 'coord': coord, 'coord2': coord2, 'sup': sup,
            'enc': enc, 'enc2': enc2}


def _carteira(app_module, uid):
    from app import User, db
    from facilities.core.hierarquia import carteira
    with app_module.app.app_context():
        return carteira(db.session.get(User, uid))


def test_quem_esta_acima_ve_os_locais_de_baixo(app_module, cadeia):
    L = cadeia['locais']
    assert _carteira(app_module, cadeia['enc']) == {L['Hospital Norte']}
    # O supervisor não tem local próprio: vê o do encarregado dele.
    assert _carteira(app_module, cadeia['sup']) == {L['Hospital Norte']}
    assert _carteira(app_module, cadeia['coord']) == {L['Shopping Centro'], L['Hospital Norte']}
    # O gerente: os locais dos clientes dele (Shopping e Hospital) e da equipe.
    assert _carteira(app_module, cadeia['ger']) == {L['Shopping Centro'], L['Hospital Norte']}


def test_um_coordenador_nao_ve_o_local_do_outro(app_module, cadeia):
    L = cadeia['locais']
    assert L['Condomínio Sul'] not in _carteira(app_module, cadeia['coord'])
    assert _carteira(app_module, cadeia['coord2']) == {L['Condomínio Sul']}
    assert L['Condomínio Sul'] not in _carteira(app_module, cadeia['ger'])


def test_o_de_baixo_nao_ve_o_de_cima(app_module, cadeia):
    L = cadeia['locais']
    assert L['Shopping Centro'] not in _carteira(app_module, cadeia['enc'])
    c = fabrica.entrar(app_module, 'enc.cadeia@trino.com')
    # A tela ignora o local fora da carteira e abre a do próprio encarregado.
    html = c.get(f"/passagem-de-turno/turno?client_id={L['Shopping Centro']}").get_data(
        as_text=True)
    assert 'Shopping Centro' not in html and 'Hospital Norte' in html
    assert c.get(f"/cadastros/locais/{L['Shopping Centro']}").status_code == 403


def test_pela_tela_o_gerente_abre_os_locais_da_equipe(app_module, cadeia):
    L = cadeia['locais']
    c = fabrica.entrar(app_module, 'ger.cadeia@trino.com')
    assert c.get(f"/cadastros/locais/{L['Hospital Norte']}").status_code == 200
    assert c.get(f"/cadastros/locais/{L['Condomínio Sul']}").status_code == 403
    c = fabrica.entrar(app_module, 'sup.cadeia@trino.com')
    assert c.get(f"/passagem-de-turno/turno?client_id={L['Hospital Norte']}").status_code == 200


def test_desligar_o_meio_da_cadeia_nao_corta_a_visao_de_cima(app_module, cadeia):
    from app import User, db
    with app_module.app.app_context():
        db.session.get(User, cadeia['sup']).is_active = False
        db.session.commit()
    assert cadeia['locais']['Hospital Norte'] in _carteira(app_module, cadeia['coord'])


def test_encarregado_que_sai_tira_o_local_da_equipe_de_cima(app_module, cadeia):
    from app import User, db
    with app_module.app.app_context():
        db.session.get(User, cadeia['enc']).is_active = False
        db.session.commit()
    assert _carteira(app_module, cadeia['sup']) == set()


def test_superior_precisa_estar_num_nivel_acima(app_module, cadeia, auth_client):
    from app import User, db
    # Encarregado não pode ser superior do supervisor.
    r = auth_client.post(f"/admin/usuarios/{cadeia['sup']}", data={
        'name': 'Sup', 'email': 'sup.cadeia@trino.com', 'role': 'supervisor',
        'superior_id': cadeia['enc'], 'is_active': '1'}, follow_redirects=True)
    assert 'nível acima' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert db.session.get(User, cadeia['sup']).superior_id == cadeia['coord']
    # Pular nível vale: encarregado direto sob o coordenador.
    r = auth_client.post(f"/admin/usuarios/{cadeia['enc2']}", data={
        'name': 'Enc2', 'email': 'enc2.cadeia@trino.com', 'role': 'encarregado',
        'superior_id': cadeia['coord'], 'clients': [cadeia['locais']['Condomínio Sul']],
        'is_active': '1'})
    with app_module.app.app_context():
        assert db.session.get(User, cadeia['enc2']).superior_id == cadeia['coord']


def test_trocar_perfil_nao_poe_a_cadeia_de_cabeca_para_baixo(app_module, cadeia, auth_client):
    from app import User, db
    r = auth_client.post(f"/admin/usuarios/{cadeia['sup']}", data={
        'name': 'Sup', 'email': 'sup.cadeia@trino.com', 'role': 'encarregado',
        'superior_id': cadeia['coord'], 'is_active': '1'}, follow_redirects=True)
    assert 'abaixo desta pessoa' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert db.session.get(User, cadeia['sup']).role == 'supervisor'


def test_administrador_e_diretoria_ficam_fora_da_cadeia(app_module, cadeia, auth_client):
    with app_module.app.app_context():
        dire = fabrica.pessoa(app_module, 'dir.cadeia@trino.com', 'visualizador',
                              all_clients=True)
    r = auth_client.post(f'/admin/usuarios/{dire}', data={
        'name': 'Dir', 'email': 'dir.cadeia@trino.com', 'role': 'visualizador',
        'superior_id': cadeia['ger'], 'all_clients': '1', 'is_active': '1'},
        follow_redirects=True)
    assert 'fora da cadeia' in r.get_data(as_text=True)
    assert _carteira(app_module, dire) is None


def test_gestao_e_piso_pelo_perfil(app_module):
    from app import User
    with app_module.app.app_context():
        for role, gestao in (('gerente', True), ('pleno', True), ('master', True),
                             ('supervisor', False), ('encarregado', False),
                             ('tecnico', False), ('visualizador', False), ('cliente', False)):
            u = User(name='x', email=f'{role}@perfil.test', role=role)
            assert u.e_gestao() is gestao, role
            assert u.sees_client_data() is gestao, role
        assert User(role='supervisor').can_access('diario_operacional')
        assert not User(role='cliente').can_view('diario_operacional')
        assert User(role='gerente').pode('diario_config')


def test_gerente_responsavel_pelo_cliente_e_so_perfil_gerente(app_module, cadeia):
    from facilities.cadastros import servico
    from facilities.cadastros.models import Contratante, Empresa
    with app_module.app.app_context():
        emp = Empresa.query.first()
        with pytest.raises(servico.CadastroInvalido, match='Gerente'):
            servico.salvar_contratante(None, {'nome': 'Outro', 'empresa_id': emp.id,
                                              'gerente_id': cadeia['coord']}, None)
        assert Contratante.query.filter_by(nome='Outro').first() is None
