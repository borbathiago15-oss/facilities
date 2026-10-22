"""Diretoria (perfil ``visualizador``) só lê a Passagem de Turno.

Visto na gravação dos vídeos (22/10/2026): o painel mostrava "+ Nova passagem"
para a diretoria, e a tela de lançar o turno abria com formulário e botões
"Resolver". Quem só consulta não pode chegar a um botão que grava.
"""
import json
import uuid

import pytest

from facilities import tempo
from tests.conftest import TEST_ADMIN_PASSWORD


@pytest.fixture()
def cena(app_module):
    from facilities.passagem.models import DiarioConfiguracao, DiarioPendencia
    with app_module.app.app_context():
        cliente = app_module.Client.query.order_by(app_module.Client.id).first()
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Portaria — livro do turno',
            turnos_json=json.dumps([{'nome': 'Diurno'}]), campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Rondas', 'codigo': 'rondas',
                                         'obrigatorio': True}]),
            tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id)
        pend = DiarioPendencia(client_id=cliente.id, titulo='Portão lateral travado',
                               created_by=admin.id)
        app_module.db.session.add_all([cfg, pend])
        app_module.db.session.commit()
        return {'cid': cliente.id, 'cfg': cfg.id, 'pend': pend.id}


@pytest.fixture()
def pessoas(app_module):
    criadas = []

    def criar(nome, role, client_ids=()):
        with app_module.app.app_context():
            from app import Client, db
            u = app_module.User(name=nome, email=f'{uuid.uuid4().hex[:10]}@leitura.test',
                                role=role, must_change_password=False)
            u.set_password('senha12345')
            u.clients = [db.session.get(Client, cid) for cid in client_ids]
            db.session.add(u)
            db.session.commit()
            criadas.append(u.id)
            c = app_module.app.test_client()
            c.post('/login', data={'email': u.email, 'password': 'senha12345'})
            return c

    yield criar
    with app_module.app.app_context():
        from app import db
        for uid in criadas:
            u = db.session.get(app_module.User, uid)
            u.is_active, u.is_deleted, u.clients = False, True, []
        db.session.commit()


def _corpo_do_turno(cena, finalizar):
    return {'client_id': cena['cid'], 'configuracao_id': cena['cfg'],
            'data_turno': tempo.hoje().isoformat(), 'turno': 'Diurno',
            'dados': {'atividade:rondas': {'concluido': True}},
            'ocorrencias': [], 'finalizar': finalizar}


def test_diretoria_nao_ve_o_botao_de_nova_passagem(cena, pessoas):
    diretora = pessoas('Diretora', 'visualizador', [cena['cid']])
    r = diretora.get(f"/passagem-de-turno/?client_id={cena['cid']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Nova passagem' not in html
    assert 'Passagem de Turno' in html          # o painel continua abrindo


def test_diretoria_nao_abre_a_tela_de_lancar_o_turno(cena, pessoas):
    diretora = pessoas('Diretora', 'visualizador', [cena['cid']])
    r = diretora.get(f"/passagem-de-turno/turno?client_id={cena['cid']}")
    assert r.status_code == 403
    assert 'Portão lateral travado' not in r.get_data(as_text=True)


def test_diretoria_recebe_403_ao_salvar_encerrar_e_resolver(cena, pessoas):
    diretora = pessoas('Diretora', 'visualizador', [cena['cid']])
    for finalizar in (False, True):
        r = diretora.post('/passagem-de-turno/api/turnos',
                          json=_corpo_do_turno(cena, finalizar))
        assert r.status_code == 403, r.get_data(as_text=True)
        assert r.is_json and r.get_json()['error']
    r = diretora.post(f"/passagem-de-turno/api/pendencias/{cena['pend']}/resolver",
                      json={'resolucao': 'Trocaram o motor'})
    assert r.status_code == 403
    assert r.is_json and r.get_json()['error']
    # E o mesmo padrão em Chamados › novo.
    assert diretora.get('/chamados/novo').status_code == 403


def test_gestor_continua_lancando_e_resolvendo(cena, pessoas):
    gestor = pessoas('Gestor', 'pleno', [cena['cid']])
    html = gestor.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(as_text=True)
    assert 'Nova passagem' in html
    assert gestor.get(f"/passagem-de-turno/turno?client_id={cena['cid']}").status_code == 200
    r = gestor.post('/passagem-de-turno/api/turnos', json=_corpo_do_turno(cena, True))
    assert r.status_code == 201, r.get_data(as_text=True)
    r = gestor.post(f"/passagem-de-turno/api/pendencias/{cena['pend']}/resolver",
                    json={'resolucao': 'Trocaram o motor'})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_administrador_continua_vendo_o_botao(cena, app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br', 'password': TEST_ADMIN_PASSWORD})
    assert 'Nova passagem' in c.get(f"/passagem-de-turno/?client_id={cena['cid']}"
                                    ).get_data(as_text=True)
