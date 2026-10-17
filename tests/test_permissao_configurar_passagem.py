"""Quem configura o modelo de passagem de turno.

No Trino Intelligence a configuração era uma permissão FINA, concedida pessoa
a pessoa. No Facilities a regra parte do perfil: o GESTOR configura os
contratos dele sem precisar de marcação (é ele quem conhece a rotina do
posto), e o administrador pode conceder a mesma permissão a um encarregado
ou técnico pelo cadastro de pessoas.

O que se prova aqui:

* administrador e gestor entram, sem marcação;
* encarregado e técnico SEM a permissão são barrados, e COM ela entram;
* a barreira vale para ESCREVER, não só para abrir a tela;
* o cadastro de pessoas concede, e descarta permissão inventada;
* quem é barrado recebe instrução do que fazer, não um "acesso negado" seco.
"""
import json

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities.passagem.models import (
    DiarioConfiguracao)


@pytest.fixture()
def cena(app_module):
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()

        def _pessoa(email, nome, papel, perms):
            u = app_module.User.query.filter_by(email=email).first()
            if u is None:
                u = app_module.User(name=nome, email=email)
                db.session.add(u)
            u.role = papel
            u.is_active = True
            u.is_deleted = False
            u.must_change_password = False
            u.permissions_json = json.dumps(perms)
            u.set_password('senha12345')
            db.session.flush()
            u.clients = [cliente]
            return u

        # O encarregado do posto: faz a passagem, mas NÃO configura.
        sem = _pessoa('coord.sem@trino.com', 'Encarregado sem permissão',
                      'encarregado', [])
        # O gestor do contrato: configura sem marcação nenhuma.
        com = _pessoa('coord.com@trino.com', 'Gestor do contrato',
                      'pleno', [])
        _pessoa('tecnico.sem@trino.com', 'Técnico sem permissão', 'tecnico', [])
        # O piso, também com a permissão — é o caso que motivou o recurso.
        piso = _pessoa('piso.cfg@trino.com', 'Encarregado com permissão',
                       'encarregado', ['diario_config'])
        db.session.commit()
        return {'cid': cliente.id, 'sem': sem.id, 'com': com.id,
                'piso': piso.id}


def _cliente(app_module, email):
    c = app_module.app.test_client()
    c.post('/login', data={'email': email, 'password': 'senha12345'})
    return c


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


# ── Abrir a tela ─────────────────────────────────────────────────────────

def test_o_master_continua_entrando_sem_marcacao(mestre, cena):
    r = mestre.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}")
    assert r.status_code == 200
    assert 'Modelo de passagem de turno' in r.get_data(as_text=True)


@pytest.mark.parametrize('email', ['coord.sem@trino.com', 'tecnico.sem@trino.com'])
def test_encarregado_e_tecnico_sem_a_permissao_sao_barrados(app_module, cena, email):
    """O contraexemplo: alcançar o módulo não é poder configurá-lo."""
    c = _cliente(app_module, email)
    r = c.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}",
              follow_redirects=False)
    assert r.status_code == 302


def test_o_gestor_entra_sem_marcacao(app_module, cena):
    c = _cliente(app_module, 'coord.com@trino.com')
    r = c.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}")
    assert r.status_code == 200
    assert 'Modelo de passagem de turno' in r.get_data(as_text=True)


def test_o_encarregado_tambem_pode_receber(app_module, cena):
    """O caso que motivou o recurso: quem conhece a rotina é o piso."""
    c = _cliente(app_module, 'piso.cfg@trino.com')
    r = c.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}")
    assert r.status_code == 200


def test_quem_e_barrado_recebe_instrucao_do_que_fazer(app_module, cena):
    """"Acesso negado" seco deixa a pessoa sem próximo passo."""
    c = _cliente(app_module, 'coord.sem@trino.com')
    corpo = c.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}",
                  follow_redirects=True).get_data(as_text=True)
    assert 'permissão do administrador' in corpo


# ── Escrever, que é o que de fato importa ────────────────────────────────

def test_sem_permissao_nao_cria_modelo(app_module, cena):
    """A barreira é de ESCRITA, não só de tela — senão seria enfeite."""
    c = _cliente(app_module, 'coord.sem@trino.com')
    r = c.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': cena['cid'], 'nome': 'Modelo de fora',
        'turnos': [{'nome': 'T1'}], 'perguntas': [], 'tipos_ocorrencia': []})
    assert r.status_code == 403
    with app_module.app.app_context():
        assert DiarioConfiguracao.query.filter_by(
            nome='Modelo de fora').first() is None


def test_sem_permissao_nao_cria_area(app_module, cena):
    c = _cliente(app_module, 'coord.sem@trino.com')
    r = c.post('/passagem-de-turno/api/areas',
               json={'client_id': cena['cid'], 'nome': 'Área de fora'})
    assert r.status_code == 403


def test_com_permissao_cria_modelo(app_module, cena):
    c = _cliente(app_module, 'coord.com@trino.com')
    r = c.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': cena['cid'], 'nome': 'Modelo do coordenador',
        'turnos': [{'nome': 'T1'}], 'perguntas': [], 'tipos_ocorrencia': []})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    with app_module.app.app_context():
        assert DiarioConfiguracao.query.filter_by(
            nome='Modelo do coordenador').first() is not None


# ── O cadastro que concede ───────────────────────────────────────────────

def _form_de(app_module, uid, **extra):
    with app_module.app.app_context():
        u = app_module.User.query.get(uid)
        dados = {'name': u.name, 'email': u.email, 'role': u.role,
                 'clients': [str(c.id) for c in u.clients], 'is_active': '1'}
    dados.update(extra)
    return dados


def test_o_administrador_concede_a_permissao_pelo_cadastro(app_module, mestre, cena):
    """O caminho de verdade: o administrador marca a caixa e a pessoa passa a poder."""
    r = mestre.post(f"/admin/usuarios/{cena['sem']}",
                    data=_form_de(app_module, cena['sem'], permissoes=['diario_config']))
    assert r.status_code == 302, r.get_data(as_text=True)
    with app_module.app.app_context():
        u = app_module.User.query.get(cena['sem'])
        assert 'diario_config' in u.permissions
        assert u.pode('diario_config') is True

    c = _cliente(app_module, 'coord.sem@trino.com')
    assert c.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}"
                 ).status_code == 200


def test_permissao_inventada_pelo_navegador_e_descartada(app_module, mestre,
                                                         cena):
    """O contraexemplo do cadastro: a lista é livre, a validação não."""
    r = mestre.post(f"/admin/usuarios/{cena['sem']}",
                    data=_form_de(app_module, cena['sem'],
                                  permissoes=['diario_config', 'virar_master']))
    assert r.status_code == 302
    with app_module.app.app_context():
        u = app_module.User.query.get(cena['sem'])
        assert u.permissions == ['diario_config']


def test_a_tela_de_usuarios_oferece_a_caixa(mestre):
    corpo = mestre.get('/admin/usuarios').get_data(as_text=True)
    assert 'name="permissoes" value="diario_config"' in corpo
    assert 'Configurar o modelo de passagem de turno' in corpo


def test_a_permissao_fina_nao_abre_modulo(app_module, cena):
    """Ela libera uma AÇÃO, e não uma porta: não vira acesso a módulo.

    Sem esta garantia, uma chave nova na mesma lista poderia, sem querer,
    passar a valer como permissão de módulo em `can_access`.
    """
    with app_module.app.app_context():
        u = app_module.User.query.get(cena['piso'])
        assert u.pode('diario_config') is True
        # 'diario_config' não é módulo, e não deve se comportar como um.
        assert u.can_access('diario_config') is False
        from app import User
        assert 'diario_config' not in User.MODULES


def test_o_botao_acompanha_a_permissao_e_nao_o_perfil(app_module, cena):
    """Acesso sem caminho é acesso que ninguém usa.

    Enquanto o botão perguntava "é master", quem recebia a concessão no
    cadastro ganhava a rota e não ganhava a porta: a tela não oferecia lugar
    nenhum para clicar, e a pessoa concluía que não tinha permissão.
    """
    com = _cliente(app_module, 'coord.com@trino.com')
    corpo = com.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(
        as_text=True)
    assert '/passagem-de-turno/configuracao' in corpo

    sem = _cliente(app_module, 'coord.sem@trino.com')
    corpo = sem.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(
        as_text=True)
    assert '/passagem-de-turno/configuracao' not in corpo
