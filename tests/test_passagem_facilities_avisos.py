"""Avisos da Passagem (sino): quem é o piso, e quem ainda tem o contrato.

Três defeitos do porte, uma régua só:

* **O técnico é piso.** No Trino o encarregado era o único perfil que fazia
  passagem; no Facilities o técnico de manutenção também passa o turno da
  equipe dele — e não recebia a "Tarefa para o turno" nem a "Pendência
  crítica". Num contrato atendido só por técnicos, ninguém recebia.
* **A carteira é a do ``require_client``.** Ela honra "todos os contratos";
  os avisos não honravam: o gestor regional responsável pelo contrato não
  recebia a pendência parada, e o volante que lança em qualquer contrato
  ficava fora do piso.
* **Quem saiu do contrato não lê mais o contrato.** Quem lançou passagem no
  último mês continuava recebendo título de tarefa e de pendência depois de
  perder o contrato (ou de ser desativado) — e o gestor que pediu uma tarefa
  e saiu do contrato continuava lendo a resposta do turno.

E o responsável de uma pendência é gente DESTE contrato: o id de qualquer
pessoa (ou de ninguém) era aceito e gravado.
"""
import json
import uuid
from datetime import datetime

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.core.models import Notification
from facilities.passagem.models import DiarioConfiguracao, DiarioPendencia, DiarioTurno
from facilities.passagem import rotas


@pytest.fixture()
def cena(app_module):
    """Dois contratos (A e B) e um modelo de passagem em A."""
    with app_module.app.app_context():
        clientes = app_module.Client.query.order_by(app_module.Client.id).all()
        a, b = clientes[0], clientes[1]
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=a.id, nome='Manutenção predial — rotina do turno',
            turnos_json=json.dumps([{'nome': 'Manhã'}, {'nome': 'Tarde'}]),
            campos_json='[]', atividades_json='[]', tipos_ocorrencia_json='[]',
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'A': a.id, 'B': b.id, 'cfg': cfg.id, 'admin': admin.id}


@pytest.fixture()
def pessoas(app_module):
    """Cria gente sob medida; ao fim, desativa — sem isto um volante com
    "todos os contratos" esquecido ativo entraria no piso dos outros testes."""
    criadas = []

    def criar(nome, role, client_ids=(), todos=False, ativo=True):
        with app_module.app.app_context():
            from app import Client, db
            u = app_module.User(name=nome, email=f'{uuid.uuid4().hex[:10]}@avisos.test',
                                role=role, must_change_password=False,
                                all_clients=todos, is_active=ativo)
            u.set_password('senha12345')
            u.clients = [db.session.get(Client, cid) for cid in client_ids]
            db.session.add(u)
            db.session.commit()
            criadas.append(u.id)
            return u.id

    yield criar
    with app_module.app.app_context():
        from app import db
        for uid in criadas:
            u = db.session.get(app_module.User, uid)
            u.is_active, u.is_deleted, u.all_clients, u.clients = False, True, False, []
        db.session.commit()


def _entrar(app_module, user_id):
    with app_module.app.app_context():
        email = app_module.User.query.get(user_id).email
    c = app_module.app.test_client()
    c.post('/login', data={'email': email, 'password': 'senha12345'})
    return c


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _avisos(app_module, user_id):
    with app_module.app.app_context():
        return [n.title for n in Notification.query.filter_by(user_id=user_id)
                .order_by(Notification.id)]


def _tarefa(cliente_http, cena, titulo='Conferir a bomba da caixa d’água'):
    return cliente_http.post('/passagem-de-turno/api/tarefas-turno', json={
        'client_id': cena['A'], 'configuracao_id': cena['cfg'],
        'data_turno': tempo.hoje().isoformat(), 'turno': 'Tarde', 'titulo': titulo})


def _lancou_passagem(app_module, cena, user_id):
    """Uma passagem lançada por ``user_id`` em A — é o que o põe no piso."""
    with app_module.app.app_context():
        app_module.db.session.add(DiarioTurno(
            client_id=cena['A'], configuracao_id=cena['cfg'], data_turno=tempo.hoje(),
            turno=f'Manhã {uuid.uuid4().hex[:4]}', status='encerrado', dados_json='{}',
            created_by=user_id, submitted_at=datetime.utcnow()))
        app_module.db.session.commit()


# ── O técnico é piso ─────────────────────────────────────────────────────

def test_o_tecnico_do_contrato_recebe_a_tarefa_do_turno(app_module, mestre, cena, pessoas):
    enc = pessoas('Encarregada de A', 'encarregado', [cena['A']])
    tec = pessoas('Técnico de A', 'tecnico', [cena['A']])
    tec_b = pessoas('Técnico de B', 'tecnico', [cena['B']])
    assert _tarefa(mestre, cena).status_code == 201
    titulo = f'Tarefa para o Tarde de {tempo.hoje().strftime("%d/%m")}'
    assert _avisos(app_module, enc) == [titulo]
    assert _avisos(app_module, tec) == [titulo]
    assert _avisos(app_module, tec_b) == []


def test_a_pendencia_critica_sem_responsavel_chega_ao_tecnico(app_module, mestre, cena,
                                                              pessoas):
    tec = pessoas('Técnico de A', 'tecnico', [cena['A']])
    r = mestre.post('/passagem-de-turno/api/pendencias', json={
        'client_id': cena['A'], 'titulo': 'Quadro elétrico do 3º andar desarmando',
        'prioridade': 'alta'})
    assert r.status_code == 201
    assert _avisos(app_module, tec) == ['Pendência crítica']


def test_contrato_atendido_so_por_tecnicos_tem_piso(app_module, cena, pessoas):
    tec = pessoas('Técnico do Condomínio', 'tecnico', [cena['B']])
    with app_module.app.app_context():
        assert tec in rotas._time_do_piso(cena['B'])


# ── "Todos os contratos" vale como no require_client ─────────────────────

def test_o_volante_com_todos_os_contratos_e_piso_de_qualquer_contrato(
        app_module, mestre, cena, pessoas):
    volante = pessoas('Encarregado volante', 'encarregado', todos=True)
    with app_module.app.app_context():
        assert volante in rotas._time_do_piso(cena['A'])
        assert volante in rotas._time_do_piso(cena['B'])
    assert _tarefa(mestre, cena).status_code == 201
    assert len(_avisos(app_module, volante)) == 1


def test_o_gestor_regional_responsavel_recebe_a_pendencia_parada(app_module, cena,
                                                                  pessoas):
    regional = pessoas('Gestor regional', 'pleno', todos=True)
    vinculado = pessoas('Gestora do contrato', 'pleno', [cena['A']])
    with app_module.app.app_context():
        assert rotas._ve_o_contrato(regional, cena['A']) is True
        cliente = app_module.Client.query.get(cena['A'])
        antes = cliente.responsible_user_id
        cliente.responsible_user_id = regional
        app_module.db.session.commit()
        try:
            assert rotas._gestores_do_contrato(cena['A']) == [regional]
            # Sem responsável, entram os VINCULADOS — o regional não recebe
            # o aviso de todos os contratos da casa.
            cliente.responsible_user_id = None
            app_module.db.session.commit()
            gestores = rotas._gestores_do_contrato(cena['A'])
            assert vinculado in gestores and regional not in gestores
        finally:
            cliente.responsible_user_id = antes
            app_module.db.session.commit()


# ── Quem saiu do contrato não recebe ─────────────────────────────────────

def test_quem_lancou_e_saiu_do_contrato_nao_recebe_mais(app_module, mestre, cena, pessoas):
    ex = pessoas('Ex-encarregado de A', 'encarregado', [cena['A']])
    _lancou_passagem(app_module, cena, ex)
    gestor_que_lancou = pessoas('Gestor que cobriu um turno', 'pleno', [cena['A']])
    _lancou_passagem(app_module, cena, gestor_que_lancou)
    with app_module.app.app_context():
        assert ex in rotas._time_do_piso(cena['A'], cena['cfg'])
        # Saiu de A (foi para B).
        from app import Client
        u = app_module.User.query.get(ex)
        u.clients = [app_module.db.session.get(Client, cena['B'])]
        app_module.db.session.commit()
        piso = rotas._time_do_piso(cena['A'], cena['cfg'])
        assert ex not in piso
        assert gestor_que_lancou in piso      # quem lançou e continua, fica
    assert _tarefa(mestre, cena, 'SEGREDO-DO-CONTRATO-A').status_code == 201
    r = mestre.post('/passagem-de-turno/api/pendencias', json={
        'client_id': cena['A'], 'titulo': 'PENDENCIA-SIGILOSA-A', 'prioridade': 'alta'})
    assert r.status_code == 201
    assert _avisos(app_module, ex) == []
    with app_module.app.app_context():
        assert Notification.query.filter(
            Notification.user_id == ex).count() == 0


def test_quem_foi_desativado_nao_recebe(app_module, mestre, cena, pessoas):
    inativo = pessoas('Encarregado desligado', 'encarregado', [cena['A']], ativo=False)
    _lancou_passagem(app_module, cena, inativo)
    assert _tarefa(mestre, cena).status_code == 201
    assert _avisos(app_module, inativo) == []


def test_a_diretoria_que_so_le_nao_recebe_aviso_de_piso(app_module, mestre, cena, pessoas):
    leitora = pessoas('Diretora', 'visualizador', [cena['A']])
    _lancou_passagem(app_module, cena, leitora)
    assert _tarefa(mestre, cena).status_code == 201
    assert _avisos(app_module, leitora) == []


def test_a_resposta_da_tarefa_nao_chega_a_quem_pediu_e_saiu_do_contrato(
        app_module, cena, pessoas):
    gestor = pessoas('Gestor que pediu', 'pleno', [cena['A']])
    enc = pessoas('Encarregada de A', 'encarregado', [cena['A']])
    r = _tarefa(_entrar(app_module, gestor), cena, 'Conferir o gerador')
    assert r.status_code == 201
    tarefa_id = r.get_json()['id']
    with app_module.app.app_context():
        from app import Client
        app_module.User.query.get(gestor).clients = [
            app_module.db.session.get(Client, cena['B'])]
        app_module.db.session.commit()
    r = _entrar(app_module, enc).post(
        f'/passagem-de-turno/api/tarefas-turno/{tarefa_id}/responder',
        json={'resposta': 'sim'})
    assert r.status_code == 200
    assert _avisos(app_module, gestor) == []


# ── O responsável da pendência é gente do contrato ───────────────────────

def _pendencia(cliente_http, cena, responsavel, prioridade='alta'):
    return cliente_http.post('/passagem-de-turno/api/pendencias', json={
        'client_id': cena['A'], 'titulo': 'Trocar a lâmpada da garagem',
        'prioridade': prioridade, 'assigned_to': responsavel})


def test_responsavel_de_outro_contrato_e_recusado(app_module, mestre, cena, pessoas):
    de_b = pessoas('Gestor só de B', 'pleno', [cena['B']])
    for prioridade in ('media', 'alta'):
        r = _pendencia(mestre, cena, de_b, prioridade)
        assert r.status_code == 400
        assert r.is_json and 'não trabalha neste contrato' in r.get_json()['error']
    with app_module.app.app_context():
        assert DiarioPendencia.query.count() == 0
    assert _avisos(app_module, de_b) == []


def test_responsavel_que_nao_existe_ou_desativado_e_recusado(app_module, mestre, cena,
                                                             pessoas):
    inativo = pessoas('Técnico desligado', 'tecnico', [cena['A']], ativo=False)
    leitora = pessoas('Diretora', 'visualizador', [cena['A']])
    for responsavel in (999999, 'abc', inativo, leitora):
        assert _pendencia(mestre, cena, responsavel).status_code == 400, responsavel
    with app_module.app.app_context():
        assert DiarioPendencia.query.count() == 0


def test_responsavel_do_contrato_e_aceito_e_avisado(app_module, mestre, cena, pessoas):
    tec = pessoas('Técnico de A', 'tecnico', [cena['A']])
    volante = pessoas('Técnico volante', 'tecnico', todos=True)
    for responsavel in (tec, volante):
        r = _pendencia(mestre, cena, responsavel)
        assert r.status_code == 201
        with app_module.app.app_context():
            assert DiarioPendencia.query.get(r.get_json()['id']).assigned_to == responsavel
        assert _avisos(app_module, responsavel) == ['Pendência crítica']


def test_prazo_invalido_e_400_e_nao_500(mestre, cena):
    r = mestre.post('/passagem-de-turno/api/pendencias', json={
        'client_id': cena['A'], 'titulo': 'Vistoria', 'due_date': '31/02/2026'})
    assert r.status_code == 400
