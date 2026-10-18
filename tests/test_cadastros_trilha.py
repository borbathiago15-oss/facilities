"""Fase 1 — a trilha dos cadastros: toda mudança deixa evento com antes e
depois, e nenhuma rota apaga ou edita evento."""
import json

from tests import fabrica


def test_toda_mudanca_gera_evento_com_antes_e_depois(app_module, auth_client):
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        from facilities.cadastros.models import CadastroEvento
        criados = {(e.entidade, e.acao) for e in CadastroEvento.query}
    assert {('empresa', 'criado'), ('contratante', 'criado'), ('setor', 'criado'),
            ('ambiente', 'criado'), ('equipamento', 'criado'), ('ponto', 'criado')} <= criados
    auth_client.post(f"/cadastros/locais/{ids['local']}/setor/{ids['setor']}",
                     data={'nome': 'Administração'})
    auth_client.post(f"/cadastros/locais/{ids['local']}/setor/{ids['setor']}/ativo",
                     data={'ativo': '0'})
    with app_module.app.app_context():
        from facilities.cadastros.models import CadastroEvento
        from app import User
        renomeio = CadastroEvento.query.filter_by(entidade='setor', acao='alterado').one()
        assert json.loads(renomeio.antes_json)['nome'] == 'Administrativo'
        assert json.loads(renomeio.depois_json)['nome'] == 'Administração'
        assert renomeio.autor.email == User.query.filter_by(role='master').first().email
        # A cascata também deixa rastro: setor, ambiente, equipamento e ponto.
        desativados = {e.entidade for e in CadastroEvento.query.filter_by(acao='desativado')}
        assert desativados == {'setor', 'ambiente', 'equipamento', 'ponto'}


def test_edicao_do_local_entra_na_trilha(app_module, auth_client):
    with app_module.app.app_context():
        loc = fabrica.local('Condomínio Sul')
        cid, nome = loc.id, loc.name
    auth_client.post(f'/admin/contratos/{cid}', data={'name': nome, 'cost_center': 'CS-9',
                                                      'is_active': '1'})
    with app_module.app.app_context():
        from facilities.cadastros.models import CadastroEvento
        ev = CadastroEvento.query.filter_by(entidade='local', entidade_id=cid).one()
        assert json.loads(ev.depois_json)['cost_center'] == 'CS-9'
    html = auth_client.get(f'/cadastros/locais/{cid}/trilha').get_data(as_text=True)
    assert 'CS-9' in html


def test_trilha_aparece_e_nao_tem_rota_de_apagar(app_module, auth_client):
    with app_module.app.app_context():
        fabrica.estrutura(app_module)
    html = auth_client.get('/cadastros/trilha').get_data(as_text=True)
    assert 'Cadastrado' in html and 'Porta do banheiro' in html
    regras = [r for r in app_module.app.url_map.iter_rules() if 'trilha' in r.rule]
    assert regras and all(r.methods <= {'GET', 'HEAD', 'OPTIONS'} for r in regras)


def test_trilha_geral_e_so_do_administrador(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'gestor.trilha@trino.com', 'pleno', locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'gestor.trilha@trino.com')
    assert c.get('/cadastros/trilha').status_code in (302, 403)
