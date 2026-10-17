"""'Passou por N turnos' conta POR ÁREA — a de onde a pendência veio.

O defeito, como apareceu na demo: "aberta há 5 dias · passou por 25 turnos".
Toda passagem encerrada, de QUALQUER área do contrato, gravava "recebida" em
todas as pendências abertas; a conta e o aviso de pendência parada somavam
as passagens de todas as áreas. O Almoxarifado nunca viu a devolução da
Expedição, mas a trilha dizia que sim — e o responsável do contrato era
avisado de uma "pendência parada" que nenhum turno da Expedição deixou parar.

O que se prova, com o contraexemplo de cada regra:

* a área de um turno é a área do modelo; os modelos sem área são, juntos,
  a área do contrato (o CD com um modelo por turno: o T2 recebe o que o T1
  deixou), e a área 5 não colide com ela por número;
* encerrar a passagem da área B não grava "recebida" na pendência da área A
  — e a da área A grava; outro modelo da MESMA área também carrega;
* a pendência aberta pela gestão (sem turno) é do contrato: qualquer área a
  carrega;
* "passou por N turnos" (fila do piso, tela e relatório) e o aviso de
  pendência parada contam só os turnos da área de origem;
* dados antigos: a "recebida" que o defeito gravou por turno de outra área
  não conta nem aparece na trilha — mas a TENTATIVA de outra área conta.
"""
from datetime import date, datetime, timedelta

import pytest

from facilities.passagem.models import (
    DiarioArea, DiarioConfiguracao, DiarioPendencia, DiarioPendenciaEvento,
    DiarioTurno)
from facilities.core.models import Notification
from facilities.passagem import analitico as an
from facilities.passagem.rotas import TURNOS_PARA_AVISAR_PARADA

TITULO = 'Devolução 9917 sem processo'


def _usuario(app_module, email, nome, role, clientes):
    from app import db
    u = app_module.User.query.filter_by(email=email).first()
    if u is None:
        u = app_module.User(name=nome, email=email)
        db.session.add(u)
    u.role = role
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
    """Um contrato com duas áreas, um segundo modelo da área A e dois modelos
    sem área — o retrato da PepsiCo Fábrica Recife, mais o contrato antigo
    que ainda não se dividiu."""
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()
        enc = _usuario(app_module, 'enc.porarea@trino.com', 'Encarregado das áreas',
                       'encarregado', [cliente])
        gestora = _usuario(app_module, 'gestora.porarea@trino.com', 'Gestora das áreas',
                           'pleno', [cliente])
        expedicao = DiarioArea(client_id=cliente.id, nome='Expedição', ativo=True)
        almox = DiarioArea(client_id=cliente.id, nome='Almoxarifado', ativo=True)
        db.session.add_all([expedicao, almox])
        db.session.flush()

        def modelo(nome, area_id):
            cfg = DiarioConfiguracao(client_id=cliente.id, area_id=area_id, nome=nome,
                                     atividades_json='[]', campos_json='[]',
                                     turnos_json='["T1","T2","T3"]', ativo=True)
            db.session.add(cfg)
            db.session.flush()
            return cfg.id

        ids = {'cid': cliente.id, 'enc': enc.id, 'gestora': gestora.id,
               'area_a': expedicao.id, 'area_b': almox.id,
               'A': modelo('Expedição', expedicao.id),
               'A2': modelo('Expedição — conferência', expedicao.id),
               'B': modelo('Almoxarifado', almox.id),
               'S1': modelo('Portaria', None),
               'S2': modelo('Pátio', None)}
        cliente.responsible_user_id = gestora.id
        db.session.commit()
    yield ids
    with app_module.app.app_context():
        from app import Client, db
        Client.query.get(ids['cid']).responsible_user_id = None
        db.session.commit()


@pytest.fixture()
def piso(app_module, contrato):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'enc.porarea@trino.com', 'password': 'senha12345'})
    return c


@pytest.fixture()
def gestao(app_module, contrato):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'gestora.porarea@trino.com', 'password': 'senha12345'})
    return c


DIA0 = date(2026, 9, 1)


def _encerra(cl, contrato, modelo, dia, turno='T1', pendencias=()):
    """Encerra a passagem do ``modelo`` no dia ``DIA0 + dia``; devolve o id do turno."""
    r = cl.post('/passagem-de-turno/api/turnos', json={
        'client_id': contrato['cid'], 'configuracao_id': contrato[modelo],
        'data_turno': (DIA0 + timedelta(days=dia)).isoformat(), 'turno': turno,
        'dados': {}, 'pendencias': list(pendencias), 'ocorrencias': [],
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['id']


def _abre(app_module, cl, contrato, modelo, dia=0):
    """A pendência nasce na passagem do ``modelo``; devolve (id da pendência, id do turno)."""
    tid = _encerra(cl, contrato, modelo, dia,
                   pendencias=[{'titulo': TITULO, 'prioridade': 'media'}])
    with app_module.app.app_context():
        return _pid(), tid


def _pid(titulo=TITULO):
    return DiarioPendencia.query.filter_by(titulo=titulo).one().id


def _eventos(pid):
    return [(e.tipo, e.turno_id) for e in DiarioPendenciaEvento.query
            .filter_by(pendencia_id=pid).order_by(DiarioPendenciaEvento.id).all()]


def _passagens_na_fila(cid, pid):
    return next(x for x in an.fila_de_pendencias(cid) if x['id'] == pid)['passagens']


def _avisos(uid):
    return [n.title for n in Notification.query.filter(
        Notification.user_id == uid, Notification.title.like('Pendência parada%')).all()]


def _evento_antigo(pid, turno_id, tipo, quando, uid, texto=None):
    """Grava direto no banco, como o defeito antigo gravava."""
    from app import db
    db.session.add(DiarioPendenciaEvento(pendencia_id=pid, turno_id=turno_id,
                                         tipo=tipo, texto=texto, created_by=uid,
                                         created_at=quando))
    db.session.commit()


# ── A área de um turno ───────────────────────────────────────────────────

def test_a_chave_da_area_separa_area_do_contrato():
    assert an.chave_da_area(5, 9) == ('area', 5)
    # Modelo sem área é da área do contrato — qualquer que seja o modelo.
    assert an.chave_da_area(None, 9) == ('contrato', 0)
    assert an.chave_da_area(None, 9) == an.chave_da_area(None, 4)
    # Uma área cadastrada não vira "do contrato" por coincidência de número.
    assert an.chave_da_area(5, 1) != an.chave_da_area(None, 5)


def test_a_area_do_turno_vem_do_modelo(app_module, piso, contrato):
    ids = {m: _encerra(piso, contrato, m, 0) for m in ('A', 'A2', 'B', 'S1', 'S2')}
    with app_module.app.app_context():
        areas = an.areas_dos_turnos(ids.values())
        # Dois modelos da Expedição são a mesma área.
        assert areas[ids['A']] == areas[ids['A2']] == ('area', contrato['area_a'])
        assert areas[ids['B']] == ('area', contrato['area_b'])
        # Os modelos sem área são, juntos, a área do contrato.
        assert areas[ids['S1']] == areas[ids['S2']] == ('contrato', 0)
        assert areas[ids['S1']] != areas[ids['A']]
        # A versão de um turno só dá a mesma resposta.
        for tid in ids.values():
            assert an.area_do_turno(DiarioTurno.query.get(tid)) == areas[tid]
        assert an.areas_dos_turnos([]) == {}


# ── O registro no encerramento ───────────────────────────────────────────

def test_a_passagem_da_outra_area_nao_registra_recebida(app_module, piso, contrato):
    pid, _ = _abre(app_module, piso, contrato, 'A')
    for dia in (1, 2, 3):
        _encerra(piso, contrato, 'B', dia)
    with app_module.app.app_context():
        assert _eventos(pid) == []
        assert _passagens_na_fila(contrato['cid'], pid) == 0

    # O contraponto: o turno seguinte da PRÓPRIA área registra.
    t_a = _encerra(piso, contrato, 'A', 1)
    with app_module.app.app_context():
        assert _eventos(pid) == [('recebida', t_a)]
        assert _passagens_na_fila(contrato['cid'], pid) == 1


def test_outro_modelo_da_mesma_area_carrega(app_module, piso, contrato):
    """A área é o cadastro, não o modelo: a conferência da Expedição recebe
    o que a Expedição deixou."""
    pid, _ = _abre(app_module, piso, contrato, 'A')
    t = _encerra(piso, contrato, 'A2', 1)
    with app_module.app.app_context():
        assert _eventos(pid) == [('recebida', t)]


def test_modelos_sem_area_carregam_entre_si(app_module, piso, contrato):
    """O CD que nunca cadastrou áreas e tem um modelo por turno: a
    pendência que o modelo do T1 abriu é recebida pelo modelo do T2. Com
    cada modelo como área própria, o T2 nunca recebia — "passou por N"
    subia uma vez por dia e o aviso de parada atrasava três dias."""
    pid, _ = _abre(app_module, piso, contrato, 'S1')
    t2 = _encerra(piso, contrato, 'S2', 0, turno='T2')
    t3 = _encerra(piso, contrato, 'S1', 0, turno='T3')
    with app_module.app.app_context():
        assert _eventos(pid) == [('recebida', t2), ('recebida', t3)]
        assert _passagens_na_fila(contrato['cid'], pid) == 2


def test_pendencia_de_modelo_sem_area_e_do_contrato(app_module, piso, contrato):
    """No contrato que já se dividiu em áreas, a pendência do modelo antigo
    (sem área) não tem área de origem: é do contrato, como a da gestão, e
    qualquer área a carrega. Presa à "área do contrato", nenhuma passagem
    das áreas a recebia — "passou por 0" para sempre e nenhum aviso de
    parada, com a pendência parada há dias."""
    pid, _ = _abre(app_module, piso, contrato, 'S1')
    ta = _encerra(piso, contrato, 'A', 0, turno='T2')
    tb = _encerra(piso, contrato, 'B', 0, turno='T2')
    with app_module.app.app_context():
        assert _eventos(pid) == [('recebida', ta), ('recebida', tb)]
        assert _passagens_na_fila(contrato['cid'], pid) == 2
        assert _avisos(contrato['gestora']) == []
    # O terceiro turno que a deixa parada avisa o responsável do contrato.
    _encerra(piso, contrato, 'A', 0, turno='T3')
    with app_module.app.app_context():
        assert _avisos(contrato['gestora']) == [
            f'Pendência parada há 3 turnos: {TITULO}']


def test_modelo_sem_area_nao_carrega_a_pendencia_de_uma_area(app_module, piso,
                                                            contrato):
    """O contrário não vale: a pendência da Expedição é da Expedição — o
    modelo sem área não a carrega."""
    pid, _ = _abre(app_module, piso, contrato, 'A')
    _encerra(piso, contrato, 'S1', 1)
    _encerra(piso, contrato, 'S2', 1, turno='T2')
    with app_module.app.app_context():
        assert _eventos(pid) == []


def test_pendencia_da_gestao_e_recebida_por_qualquer_area(app_module, piso, gestao,
                                                          contrato):
    r = gestao.post('/passagem-de-turno/api/pendencias', json={
        'client_id': contrato['cid'], 'titulo': 'Inventário rotativo atrasado',
        'prioridade': 'media'})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    turnos = [_encerra(piso, contrato, m, 1) for m in ('A', 'B', 'S1')]
    with app_module.app.app_context():
        pid = _pid('Inventário rotativo atrasado')
        assert DiarioPendencia.query.get(pid).turno_id is None
        assert sorted(_eventos(pid)) == sorted(('recebida', t) for t in turnos)
        assert _passagens_na_fila(contrato['cid'], pid) == 3
        assert an._resumo_das_trilhas([pid])[pid]['passagens'] == 3
        assert [e['tipo'] for e in an.trilha_da_pendencia(pid)] == ['recebida'] * 3


# ── A conta: fila, tela, relatório ───────────────────────────────────────

def test_passou_por_conta_so_os_turnos_da_area_de_origem(app_module, piso, contrato):
    pid, _ = _abre(app_module, piso, contrato, 'A')
    for dia in (1, 2):
        _encerra(piso, contrato, 'B', dia)
        _encerra(piso, contrato, 'A', dia)
    with app_module.app.app_context():
        assert _passagens_na_fila(contrato['cid'], pid) == 2
        # O relatório mensal lê a mesma conta.
        assert an._resumo_das_trilhas([pid])[pid]['passagens'] == 2
        assert an.passagens_das_pendencias([DiarioPendencia.query.get(pid)]) == {pid: 2}
    tela = piso.get(f"/passagem-de-turno/turno?client_id={contrato['cid']}")
    corpo = tela.get_data(as_text=True)
    assert 'passou por 2 turnos' in corpo
    assert 'passou por 4 turnos' not in corpo


def test_o_aviso_de_parada_conta_por_area(app_module, piso, contrato):
    pid, _ = _abre(app_module, piso, contrato, 'A')
    # Três passagens do Almoxarifado: antes isso bastava para o alarme.
    for dia in (1, 2, 3):
        _encerra(piso, contrato, 'B', dia)
    with app_module.app.app_context():
        assert _avisos(contrato['gestora']) == []
    _encerra(piso, contrato, 'A', 1)
    _encerra(piso, contrato, 'A', 2)
    with app_module.app.app_context():
        assert _avisos(contrato['gestora']) == []
    # O terceiro turno da Expedição que a deixa parada — esse sim avisa.
    _encerra(piso, contrato, 'A', 3)
    with app_module.app.app_context():
        assert TURNOS_PARA_AVISAR_PARADA == 3
        assert _avisos(contrato['gestora']) == [f'Pendência parada há 3 turnos: {TITULO}']


# ── Dados antigos: o que o defeito já gravou ─────────────────────────────

def test_recebida_antiga_de_outra_area_nao_conta_nem_aparece(app_module, piso,
                                                             contrato):
    pid, _ = _abre(app_module, piso, contrato, 'A')
    turnos_b = [_encerra(piso, contrato, 'B', dia) for dia in (1, 2, 3, 4)]
    with app_module.app.app_context():
        assert _eventos(pid) == []               # o código novo não grava
        # O que o código antigo gravou: "recebida" em cada turno do Almoxarifado...
        for i, tid in enumerate(turnos_b):
            _evento_antigo(pid, tid, 'recebida', datetime(2026, 9, 2 + i, 12),
                           contrato['enc'])
        # ...e uma TENTATIVA de verdade, de quem do Almoxarifado ajudou.
        _evento_antigo(pid, turnos_b[0], 'tentativa', datetime(2026, 9, 2, 13),
                       contrato['enc'], texto='Almoxarifado ligou para o CD de origem')

    # O turno seguinte da Expedição: a conta antiga daria 5 e dispararia o aviso.
    t_a = _encerra(piso, contrato, 'A', 5)
    with app_module.app.app_context():
        # Contam: o turno da tentativa (de qualquer área) e o da Expedição.
        assert _passagens_na_fila(contrato['cid'], pid) == 2
        assert an._resumo_das_trilhas([pid])[pid] == {
            'passagens': 2, 'ultima': 'Almoxarifado ligou para o CD de origem'}
        trilha = an.trilha_da_pendencia(pid)
        assert [e['tipo'] for e in trilha] == ['tentativa', 'recebida']
        assert trilha[1]['data_turno'] == DIA0 + timedelta(days=5)
        assert DiarioTurno.query.get(t_a).configuracao_id == contrato['A']
        assert _avisos(contrato['gestora']) == []


def test_recebida_antiga_na_pendencia_da_gestao_continua_contando(app_module, piso,
                                                                  contrato):
    """Sem turno de origem a pendência é do contrato — o histórico dela vale todo."""
    turnos = [_encerra(piso, contrato, m, 1) for m in ('A', 'B')]
    with app_module.app.app_context():
        from app import db
        p = DiarioPendencia(client_id=contrato['cid'], titulo='Pendência da gestão',
                            prioridade='media', created_by=contrato['gestora'])
        db.session.add(p)
        db.session.commit()
        pid = p.id
        for i, tid in enumerate(turnos):
            _evento_antigo(pid, tid, 'recebida', datetime(2026, 9, 2, 10 + i),
                           contrato['enc'])
        assert _passagens_na_fila(contrato['cid'], pid) == 2
        assert an._resumo_das_trilhas([pid])[pid]['passagens'] == 2
        assert len(an.trilha_da_pendencia(pid)) == 2


def test_resolvida_de_outra_area_aparece_na_trilha(app_module, piso, contrato):
    """Quem resolveu, resolveu — de qualquer área."""
    pid, _ = _abre(app_module, piso, contrato, 'A')
    t_b = _encerra(piso, contrato, 'B', 1)
    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver', json={
        'resolucao': 'Almoxarifado achou o processo', 'turno_id': t_b})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        trilha = an.trilha_da_pendencia(pid)
        assert [e['tipo'] for e in trilha] == ['resolvida']
        assert an._resumo_das_trilhas([pid])[pid]['passagens'] == 1


# ── O contrato misto e a área desativada ─────────────────────────────────

def _configs_da_tela(corpo):
    import html
    import json
    import re
    bruto = re.search(r"data-configs='([^']*)'", corpo).group(1)
    return {c['nome']: c for c in json.loads(html.unescape(bruto))}


def test_contrato_misto_oferece_os_modelos_sem_area(app_module, piso, contrato):
    """Contrato que se dividiu em áreas e manteve modelos ativos sem área: o
    seletor só oferecia as áreas, e ninguém conseguia lançar a passagem
    desses modelos. Agora eles têm a opção "Geral (sem área)"."""
    import os
    corpo = piso.get(f"/passagem-de-turno/turno?client_id={contrato['cid']}"
                     ).get_data(as_text=True)
    assert '<option value="sem-area">Geral (sem área)</option>' in corpo
    configs = _configs_da_tela(corpo)
    assert configs['Portaria']['area_id'] is None
    assert configs['Expedição']['area_id'] == contrato['area_a']
    # O bloco "o turno anterior deixou" dessa opção é o da área do contrato.
    _encerra(piso, contrato, 'S1', 0)
    corpo = piso.get(f"/passagem-de-turno/turno?client_id={contrato['cid']}"
                     ).get_data(as_text=True)
    assert 'data-area="contrato-0"' in corpo
    # E o JS sabe o que fazer com a opção.
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'facilities', 'static', 'js', 'diario_operacional.js'),
              encoding='utf-8') as f:
        js = f.read()
    from facilities.passagem.rotas import AREA_SEM_CADASTRO
    assert f"area === '{AREA_SEM_CADASTRO}'" in js


def test_contrato_sem_modelo_sem_area_nao_ganha_a_opcao(app_module, piso, contrato):
    with app_module.app.app_context():
        from app import db
        for m in ('S1', 'S2'):
            DiarioConfiguracao.query.get(contrato[m]).ativo = False
        db.session.commit()
    corpo = piso.get(f"/passagem-de-turno/turno?client_id={contrato['cid']}"
                     ).get_data(as_text=True)
    assert 'sem-area' not in corpo.split('id="diario-area"')[1].split('</select>')[0]


def test_area_desativada_vira_area_do_contrato(app_module, piso, contrato):
    """Desativar a área não mexe nos modelos dela. A tela passa a oferecê-los
    junto com os sem área — e a conta precisa dizer o mesmo: o que a área
    desativada deixou é do contrato, e o modelo sem área recebe."""
    pid, t_b = _abre(app_module, piso, contrato, 'B')
    with app_module.app.app_context():
        from app import db
        DiarioArea.query.get(contrato['area_b']).ativo = False
        db.session.commit()
        assert an.areas_dos_turnos([t_b])[t_b] == an.AREA_DO_CONTRATO
        assert an.area_do_turno(DiarioTurno.query.get(t_b)) == an.AREA_DO_CONTRATO
        assert an.chaves_dos_modelos(contrato['cid'])[contrato['B']] == \
            an.AREA_DO_CONTRATO
    corpo = piso.get(f"/passagem-de-turno/turno?client_id={contrato['cid']}"
                     ).get_data(as_text=True)
    assert _configs_da_tela(corpo)['Almoxarifado']['area_id'] is None
    assert '>Almoxarifado</option>' not in corpo
    t = _encerra(piso, contrato, 'S1', 1)
    with app_module.app.app_context():
        assert _eventos(pid) == [('recebida', t)]


def test_aviso_ao_piso_alcanca_quem_lanca_na_mesma_area(app_module, piso, contrato):
    """O aviso de prioridade alta vai para quem lança passagem DESTA área —
    no CD de um modelo por turno, quem lança o T2 noutro modelo herda o que
    o T1 deixou. Antes o filtro era o modelo."""
    from facilities.passagem import rotas
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.get(contrato['cid'])
        sup = _usuario(app_module, 'sup.porarea@trino.com', 'Supervisora da área',
                       'pleno', [cliente])
        db.session.add(DiarioTurno(client_id=contrato['cid'],
                                   configuracao_id=contrato['A2'],
                                   data_turno=DIA0, turno='T2', status='encerrado',
                                   dados_json='{}', created_by=sup.id))
        db.session.commit()
        assert sup.id in rotas._time_do_piso(contrato['cid'], contrato['A'])
        assert sup.id not in rotas._time_do_piso(contrato['cid'], contrato['B'])
        # O que o modelo sem área deixa é do contrato — todas as áreas o
        # carregam, e o aviso alcança quem lança em qualquer uma.
        assert sup.id in rotas._time_do_piso(contrato['cid'], contrato['S1'])
