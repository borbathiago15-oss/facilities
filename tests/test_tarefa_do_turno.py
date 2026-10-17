"""A tarefa que a gestão manda para um turno, e o que volta dela.

O que faltava: o gestor do contrato sabia pedir a ROTINA — o checklist do
modelo, que vale todo dia em todo turno — e não sabia pedir a EXCEÇÃO: "no
2º turno de quinta, confira a temperatura da câmara depois da manutenção".
Isso viajava por WhatsApp e voltava "ok", que não entra em série nenhuma.

O que se prova aqui, com o contraexemplo de cada regra:

* a gestão atribui, e a tarefa aparece na passagem DAQUELE turno — e só
  daquele: outra área, outro dia ou outro turno não a enxergam;
* o piso NÃO atribui tarefa a turno (a assimetria é o recurso);
* a forma de resposta é do PEDIDO e é cobrada: "ok" não passa onde se pediu
  número, e "mais ou menos" não passa onde se pediu sim ou não;
* "não deu" cria uma PENDÊNCIA de verdade — que atravessa turnos e sobe para
  a Torre — e não um estado morto na tabela da tarefa;
* responder duas vezes é recusado;
* o recorte de carteira vale aqui como no resto da casa.
"""
from datetime import date

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities.passagem.models import (
    DiarioConfiguracao, DiarioPendencia, DiarioTarefaTurno,
    TAREFA_TURNO_FEITA, TAREFA_TURNO_PENDENTE, TAREFA_TURNO_VIROU_PENDENCIA)


@pytest.fixture()
def cena(app_module):
    """Um contrato com duas áreas e um encarregado."""
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()
        outro = Client.query.filter(Client.id != cliente.id).first()

        enc = app_module.User.query.filter_by(
            email='piso.tarefa@trino.com').first()
        if enc is None:
            enc = app_module.User(name='Paulo do Piso',
                                  email='piso.tarefa@trino.com')
            db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = '[]'
        enc.set_password('senha12345')
        db.session.flush()
        enc.clients = [cliente]

        def _modelo(nome):
            c = DiarioConfiguracao.query.filter_by(
                client_id=cliente.id, nome=nome).first()
            if c is None:
                c = DiarioConfiguracao(client_id=cliente.id, nome=nome,
                                       atividades_json='[]', campos_json='[]',
                                       turnos_json='["1º Turno","2º Turno"]',
                                       ativo=True)
                db.session.add(c)
            return c

        exped, almox = _modelo('Expedição'), _modelo('Almoxarifado')
        db.session.commit()
        return {'cid': cliente.id, 'outro': outro.id, 'enc': enc.id,
                'exped': exped.id, 'almox': almox.id, 'dia': date(2026, 9, 25)}


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


@pytest.fixture()
def piso(app_module, cena):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'piso.tarefa@trino.com',
                           'password': 'senha12345'})
    return c


def _atribuir(mestre, cena, **kw):
    corpo = {'client_id': cena['cid'], 'configuracao_id': cena['exped'],
             'data_turno': cena['dia'].isoformat(), 'turno': '2º Turno',
             'titulo': 'Conferir a temperatura da câmara',
             'forma_resposta': 'numero'}
    corpo.update(kw)
    return mestre.post('/passagem-de-turno/api/tarefas-turno', json=corpo)


# ── A gestão atribui ─────────────────────────────────────────────────────

def test_a_gestao_atribui_e_a_tarefa_cai_no_turno(mestre, piso, cena):
    assert _atribuir(mestre, cena).status_code == 201

    r = piso.get(f"/passagem-de-turno/api/tarefas-turno"
                 f"?client_id={cena['cid']}&configuracao_id={cena['exped']}"
                 f"&data_turno={cena['dia'].isoformat()}&turno=2º Turno")
    tarefas = r.get_json()['tarefas']
    assert len(tarefas) == 1
    assert tarefas[0]['titulo'] == 'Conferir a temperatura da câmara'
    assert tarefas[0]['forma_resposta'] == 'numero'
    assert tarefas[0]['status'] == TAREFA_TURNO_PENDENTE


@pytest.mark.parametrize('mudanca', [
    {'configuracao_id': 'almox'},          # outra área
    {'turno': '1º Turno'},                 # outro turno
    {'data_turno': '2026-09-26'},          # outro dia
])
def test_a_tarefa_nao_vaza_para_o_turno_errado(mestre, piso, cena, mudanca):
    """O contraponto: pedir para o 2º turno de quinta é pedir só para ele."""
    assert _atribuir(mestre, cena).status_code == 201
    consulta = {'configuracao_id': cena['exped'],
                'data_turno': cena['dia'].isoformat(), 'turno': '2º Turno'}
    if 'configuracao_id' in mudanca:
        consulta['configuracao_id'] = cena[mudanca['configuracao_id']]
    consulta.update({k: v for k, v in mudanca.items()
                     if k != 'configuracao_id'})
    r = piso.get(f"/passagem-de-turno/api/tarefas-turno"
                 f"?client_id={cena['cid']}"
                 f"&configuracao_id={consulta['configuracao_id']}"
                 f"&data_turno={consulta['data_turno']}"
                 f"&turno={consulta['turno']}")
    assert r.get_json()['tarefas'] == []


def test_o_piso_nao_atribui_tarefa_a_turno(piso, cena):
    """A assimetria é o recurso: o encarregado não se manda tarefa."""
    r = piso.post('/passagem-de-turno/api/tarefas-turno', json={
        'client_id': cena['cid'], 'configuracao_id': cena['exped'],
        'data_turno': cena['dia'].isoformat(), 'turno': '2º Turno',
        'titulo': 'me dando serviço'})
    assert r.status_code == 403


def test_area_de_outro_contrato_e_recusada(app_module, mestre, cena):
    """Carteira e contrato mandam aqui como no resto da casa."""
    with app_module.app.app_context():
        from app import db
        alheia = DiarioConfiguracao(client_id=cena['outro'], nome='De outro',
                                    atividades_json='[]', campos_json='[]',
                                    turnos_json='[]', ativo=True)
        db.session.add(alheia)
        db.session.commit()
        aid = alheia.id
    r = _atribuir(mestre, cena, configuracao_id=aid)
    assert r.status_code == 400


# ── A forma de resposta é do pedido, e é cobrada ─────────────────────────

def test_onde_se_pediu_numero_ok_nao_passa(app_module, mestre, piso, cena):
    """"Ok" e "-18,4" custam o mesmo para digitar e valem coisas diferentes."""
    _atribuir(mestre, cena)
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'resposta': 'ok'})
    assert r.status_code == 400
    assert 'número' in r.get_json()['error']


def test_o_numero_com_contexto_passa(app_module, mestre, piso, cena):
    """"-18,4 na sonda 2" é o que a operação escreve de verdade.

    Recusar isso faria a pessoa apagar o contexto para o campo aceitar — e o
    contexto é metade do valor da resposta.
    """
    _atribuir(mestre, cena)
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'resposta': '-18,4 na sonda 2'})
    assert r.status_code == 200
    with app_module.app.app_context():
        t = DiarioTarefaTurno.query.get(tid)
        assert t.status == TAREFA_TURNO_FEITA
        assert t.resposta == '-18,4 na sonda 2'
        assert t.respondida_por == cena['enc']


def test_onde_se_pediu_sim_ou_nao_so_sim_ou_nao_passa(app_module, mestre,
                                                      piso, cena):
    _atribuir(mestre, cena, forma_resposta='sim_nao')
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    ruim = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                     json={'resposta': 'mais ou menos'})
    assert ruim.status_code == 400
    bom = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                    json={'resposta': 'Não'})
    assert bom.status_code == 200


def test_resposta_vazia_nao_marca_como_feita(app_module, mestre, piso, cena):
    _atribuir(mestre, cena, forma_resposta='texto')
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'resposta': '   '})
    assert r.status_code == 400
    with app_module.app.app_context():
        assert DiarioTarefaTurno.query.get(tid).status == TAREFA_TURNO_PENDENTE


# ── "Não deu" vira pendência DE VERDADE ──────────────────────────────────

def test_nao_deu_cria_pendencia_que_atravessa_turnos(app_module, mestre,
                                                     piso, cena):
    """Não é um estado morto na tabela da tarefa.

    Sem esta saída, quem não conseguiu fazer só teria a opção de mentir ou
    deixar em branco — e é justamente esse caso que a gestão mais precisa
    enxergar.
    """
    _atribuir(mestre, cena)
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
        antes = DiarioPendencia.query.filter_by(client_id=cena['cid']).count()

    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'virou_pendencia': True,
                        'resposta': 'a câmara estava em manutenção ainda'})
    assert r.status_code == 200

    with app_module.app.app_context():
        t = DiarioTarefaTurno.query.get(tid)
        assert t.status == TAREFA_TURNO_VIROU_PENDENCIA
        assert t.pendencia_id is not None
        depois = DiarioPendencia.query.filter_by(client_id=cena['cid']).count()
        assert depois == antes + 1
        p = DiarioPendencia.query.get(t.pendencia_id)
        assert p.status == 'aberta'
        assert p.prioridade == 'alta'
        assert 'manutenção ainda' in p.descricao


def test_nao_deu_sem_motivo_e_recusado(app_module, mestre, piso, cena):
    """"Não deu" sem dizer o que houve não ajuda o turno seguinte em nada."""
    _atribuir(mestre, cena)
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'virou_pendencia': True, 'resposta': ''})
    assert r.status_code == 400
    with app_module.app.app_context():
        assert DiarioTarefaTurno.query.get(tid).status == TAREFA_TURNO_PENDENTE


def test_nao_se_responde_duas_vezes(app_module, mestre, piso, cena):
    _atribuir(mestre, cena, forma_resposta='texto')
    with app_module.app.app_context():
        tid = DiarioTarefaTurno.query.first().id
    assert piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                     json={'resposta': 'feito'}).status_code == 200
    r = piso.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                  json={'resposta': 'feito de novo'})
    assert r.status_code == 409
    with app_module.app.app_context():
        assert DiarioTarefaTurno.query.get(tid).resposta == 'feito'


def test_a_tela_do_gestor_oferece_atribuir(mestre, cena):
    corpo = mestre.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(
        as_text=True)
    assert 'Tarefa para um turno' in corpo
    assert 'modalTarefaTurno' in corpo


def test_a_tela_do_piso_nao_oferece_atribuir(piso, cena):
    corpo = piso.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(
        as_text=True)
    assert 'modalTarefaTurno' not in corpo


# ── As ações têm de estar ALCANÇÁVEIS, não só existir ────────────────────

def test_o_master_alcanca_o_configurar_no_painel(mestre, cena):
    """A regressão que um Master relatou: "não consigo configurar".

    A tela tinha o botão — e ele estava a duas telas de rolagem horizontal,
    porque a fileira de ações virou carrossel e a "Tarefa para um turno" foi
    posta na frente dele. Medido no navegador: 757px de conteúdo numa faixa
    de 374px, com o "Configurar" em x=598.

    O teste guarda a REGRA, não o CSS: as ações do painel cabem na largura
    da tela, e o caminho para o cadastro das perguntas existe e responde.
    Um dia alguém vai querer o carrossel de volta; que seja com este teste
    na frente.
    """
    corpo = mestre.get(f"/passagem-de-turno/?client_id={cena['cid']}").get_data(
        as_text=True)
    assert 'Configurar' in corpo
    assert '/passagem-de-turno/configuracao' in corpo
    # E a fileira não pode voltar a rolar na horizontal escondendo o que
    # está no fim dela.
    import pathlib
    css = (pathlib.Path(__file__).resolve().parent.parent
           / 'facilities' / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    bloco = css[css.index('@media (max-width: 768px) {', css.index('.pg-acoes')):]
    bloco = bloco[:bloco.index('\n}')]
    assert 'flex-wrap: wrap' in bloco, 'as ações do celular precisam quebrar linha'
    assert 'overflow-x: auto' not in bloco, (
        'a fileira de ações voltou a rolar na horizontal — foi assim que o '
        '"Configurar" do master sumiu')


def test_o_cadastro_das_perguntas_abre_para_o_master(mestre, cena):
    """O destino do botão, e não só o botão: a tela tem de abrir de verdade."""
    r = mestre.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}")
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert 'Modelo de passagem de turno' in corpo


def test_o_piso_nao_abre_o_cadastro(piso, cena):
    """O contraponto: configurar a régua é do master."""
    r = piso.get(f"/passagem-de-turno/configuracao?client_id={cena['cid']}",
                 follow_redirects=False)
    assert r.status_code in (302, 403)
