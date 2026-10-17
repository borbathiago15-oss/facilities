"""Costuras entre as correções da Passagem de Turno (área, rascunho, tarefa).

Cada frente acertou a sua regra; aqui ficam as três arestas que só aparecem
quando as regras se encontram:

* pendência de passagem em RASCUNHO não é "recebida" por outro turno — ela
  ainda não foi entregue a ninguém, e já fica fora dos indicadores pelo mesmo
  motivo; ao encerrar a passagem de origem, ela passa a ser carregada;
* a baixa ("Resolver") e a nota ("Continua") feitas na tela da Expedição se
  amarram à passagem da Expedição, não à do Almoxarifado que tem o mesmo
  nome de turno no mesmo dia;
* uma correção pela API não apaga nem forja a hora do aparelho.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from facilities.passagem.models import (
    DiarioArea, DiarioConfiguracao, DiarioPendencia, DiarioPendenciaEvento,
    DiarioTurno)
from facilities.passagem.rotas import CHAVE_ENCERRADO_NO_APARELHO

DIA = date(2026, 8, 3)


def _usuario(app_module, email, nome, clientes):
    from app import db
    u = app_module.User.query.filter_by(email=email).first()
    if u is None:
        u = app_module.User(name=nome, email=email)
        db.session.add(u)
    u.role = 'encarregado'
    u.is_active = True
    u.is_deleted = False
    u.must_change_password = False
    u.permissions_json = '["diario_operacional"]'
    u.set_password('senha12345')
    db.session.flush()
    u.clients = clientes
    return u


@pytest.fixture()
def contrato(app_module):
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()
        _usuario(app_module, 'enc.costura@trino.com', 'Encarregada da costura', [cliente])
        expedicao = DiarioArea(client_id=cliente.id, nome='Expedição costura', ativo=True)
        almox = DiarioArea(client_id=cliente.id, nome='Almoxarifado costura', ativo=True)
        db.session.add_all([expedicao, almox])
        db.session.flush()

        def modelo(nome, area_id):
            cfg = DiarioConfiguracao(client_id=cliente.id, area_id=area_id, nome=nome,
                                     atividades_json='[]', campos_json='[]',
                                     turnos_json='["T1","T2"]', ativo=True)
            db.session.add(cfg)
            db.session.flush()
            return cfg.id

        ids = {'cid': cliente.id, 'A': modelo('Expedição costura', expedicao.id),
               'B': modelo('Almoxarifado costura', almox.id)}
        db.session.commit()
    return ids


@pytest.fixture()
def piso(app_module, contrato):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'enc.costura@trino.com', 'password': 'senha12345'})
    return c


def _salva(cl, contrato, modelo, dia, turno, finalizar, pendencias=(), extra=None):
    corpo = {'client_id': contrato['cid'], 'configuracao_id': contrato[modelo],
             'data_turno': (DIA + timedelta(days=dia)).isoformat(), 'turno': turno,
             'dados': {}, 'pendencias': list(pendencias), 'ocorrencias': [],
             'finalizar': finalizar}
    corpo.update(extra or {})
    r = cl.post('/passagem-de-turno/api/turnos', json=corpo)
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    return r.get_json()['id']


def _recebidas(pid):
    return [e.turno_id for e in DiarioPendenciaEvento.query
            .filter_by(pendencia_id=pid, tipo='recebida').all()]


def test_pendencia_de_rascunho_nao_e_recebida_ate_o_encerramento(app_module, piso, contrato):
    titulo = 'Palete quebrado na rua 4 (costura)'
    rascunho = _salva(piso, contrato, 'A', 0, 'T1', finalizar=False,
                      pendencias=[{'titulo': titulo, 'prioridade': 'media'}])
    # Outro modelo da mesma área? Não há; o T2 da própria Expedição encerra
    # enquanto o T1 ainda é rascunho: não pode "receber" o que não lhe foi passado.
    t2 = _salva(piso, contrato, 'A', 0, 'T2', finalizar=True)
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(titulo=titulo).one().id
        assert _recebidas(pid) == []
    # O T1 encerra (a pendência foi entregue); o próximo turno da área recebe.
    _salva(piso, contrato, 'A', 0, 'T1', finalizar=True,
           pendencias=[{'titulo': titulo, 'prioridade': 'media'}])
    t3 = _salva(piso, contrato, 'A', 1, 'T1', finalizar=True)
    with app_module.app.app_context():
        assert _recebidas(pid) == [t3]
        assert t2 not in _recebidas(pid) and rascunho not in _recebidas(pid)


def test_baixa_feita_na_tela_da_expedicao_amarra_na_passagem_da_expedicao(app_module, piso, contrato):
    titulo = 'Etiquetas acabando (costura)'
    _salva(piso, contrato, 'A', 2, 'T1', finalizar=True,
           pendencias=[{'titulo': titulo, 'prioridade': 'media'}])
    # No dia seguinte, as DUAS áreas têm rascunho do "T1" — mesmo nome, mesmo dia.
    exp = _salva(piso, contrato, 'A', 3, 'T1', finalizar=False)
    alm = _salva(piso, contrato, 'B', 3, 'T1', finalizar=False)
    assert exp != alm
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(titulo=titulo).one().id
    dia = (DIA + timedelta(days=3)).isoformat()
    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota', json={
        'texto': 'Pedi ao almoxarifado.', 'data_turno': dia, 'turno': 'T1',
        'configuracao_id': contrato['A']})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver', json={
        'resolucao': 'Chegaram 4 rolos.', 'data_turno': dia, 'turno': 'T1',
        'configuracao_id': contrato['A']})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        turnos = {e.tipo: e.turno_id for e in DiarioPendenciaEvento.query
                  .filter_by(pendencia_id=pid).all() if e.tipo in ('tentativa', 'resolvida')}
        assert turnos == {'tentativa': exp, 'resolvida': exp}


def test_correcao_pela_api_nao_apaga_nem_forja_a_hora_do_aparelho(app_module, piso, contrato):
    tocou = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    tid = _salva(piso, contrato, 'A', 5, 'T1', finalizar=True,
                 extra={'encerrado_no_aparelho': tocou})
    with app_module.app.app_context():
        antes = json.loads(DiarioTurno.query.get(tid).dados_json)
    assert antes.get(CHAVE_ENCERRADO_NO_APARELHO), 'o encerramento devia guardar a hora do toque'
    forjada = '2020-01-01T00:00:00+00:00'
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir', json={
        'motivo': 'Ajuste de resposta', 'dados': {'campo_x': '7', CHAVE_ENCERRADO_NO_APARELHO: forjada}})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        depois = json.loads(DiarioTurno.query.get(tid).dados_json)
    assert depois[CHAVE_ENCERRADO_NO_APARELHO] == antes[CHAVE_ENCERRADO_NO_APARELHO]
    assert depois['campo_x'] == '7'


