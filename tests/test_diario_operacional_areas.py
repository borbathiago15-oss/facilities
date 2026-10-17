"""As áreas do contrato: um cliente, várias passagens, cada uma com a sua.

O caso que deu origem a isto são dois recados reais do mesmo dia, do mesmo
cliente e do mesmo turno:

    PASSAGEM DE TURNO – PEPSICO FÁBRICA RECIFE
    Setor: Expedição · 21/09/2026 · 1º Turno · Paulo Cezar

    PASSAGEM DE TURNO – PEPSICO FÁBRICA RECIFE
    Setor: Almoxarifado · 21/09/2026 · 1º Turno · Jefferson

E a escala que vem atrás: o Novo Atacarejo Moreno tem cerca de dez áreas e
vinte encarregados.

O que se prova aqui:

* dois encarregados de ÁREAS diferentes lançam o mesmo turno no mesmo dia —
  antes o segundo batia em 409 e simplesmente não conseguia lançar;
* área é CADASTRO e se SELECIONA: nome repetido no mesmo contrato é recusado,
  porque com vinte pessoas digitando "Expedição" e "expedicao" virariam duas;
* o painel e o relatório recortam por área, em vez de somar a Expedição com
  o Almoxarifado numa média que não diz nada;
* desativar uma área não apaga passagem nenhuma;
* a área de um contrato não encosta em outro contrato.
"""
import html
import json
import re

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import (DiarioArea, DiarioConfiguracao, DiarioTurno)
from facilities.passagem import analitico as an

EXPEDICAO = [{'nome': 'Retrabalho realizado', 'codigo': 'retrabalho',
              'obrigatorio': True}]
ALMOXARIFADO = [{'nome': 'Estoque organizado', 'codigo': 'estoque',
                 'obrigatorio': True}]


@pytest.fixture()
def recife(app_module):
    """PepsiCo Fábrica Recife: duas áreas, um modelo cada, um encarregado."""
    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != cliente.id).first())
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()

        ids = {}
        for nome_area, perguntas in [('Expedição', EXPEDICAO),
                                     ('Almoxarifado', ALMOXARIFADO)]:
            area = DiarioArea(client_id=cliente.id, nome=nome_area,
                              ativo=True, created_by=admin.id)
            app_module.db.session.add(area)
            app_module.db.session.flush()
            cfg = DiarioConfiguracao(
                client_id=cliente.id, area_id=area.id,
                nome=f'Passagem {nome_area}',
                turnos_json=json.dumps([{'nome': '1º Turno'}]),
                campos_json='[]',
                atividades_json=json.dumps(perguntas),
                tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id)
            app_module.db.session.add(cfg)
            app_module.db.session.flush()
            ids[nome_area] = {'area': area.id, 'cfg': cfg.id}

        enc = app_module.User.query.filter_by(
            email='enc.recife@teste.com').first()
        if enc is None:
            enc = app_module.User(name='Paulo Cezar',
                                  email='enc.recife@teste.com', is_active=True)
            app_module.db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = '[]'
        enc.set_password('senha12345')
        enc.clients = [cliente]
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'outro_id': outro.id, 'areas': ids,
                'email': enc.email}


@pytest.fixture()
def piso(client, recife):
    client.post('/login', data={'email': recife['email'],
                                'password': 'senha12345'})
    return client


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _lancar(cl, recife, area, dia=None, turno='1º Turno', **extra):
    corpo = {'client_id': recife['client_id'],
             'configuracao_id': recife['areas'][area]['cfg'],
             'data_turno': (dia or tempo.hoje()).isoformat(),
             'turno': turno, 'finalizar': True}
    corpo.update(extra)
    return cl.post('/passagem-de-turno/api/turnos', json=corpo)


# ── A colisão que travava o segundo setor ────────────────────────────────

def test_duas_areas_lancam_o_mesmo_turno_no_mesmo_dia(app_module, piso, recife):
    """Era o defeito: o Almoxarifado recebia 409 e não conseguia lançar."""
    assert _lancar(piso, recife, 'Expedição').status_code == 201
    assert _lancar(piso, recife, 'Almoxarifado').status_code == 201
    with app_module.app.app_context():
        assert DiarioTurno.query.filter_by(
            client_id=recife['client_id']).count() == 2


def test_reenviar_a_MESMA_area_continua_sendo_a_mesma_passagem(
        app_module, piso, recife):
    """Rascunho e encerramento são uma passagem só — isso não podia mudar."""
    piso.post('/passagem-de-turno/api/turnos', json={
        'client_id': recife['client_id'],
        'configuracao_id': recife['areas']['Expedição']['cfg'],
        'data_turno': tempo.hoje().isoformat(), 'turno': '1º Turno'})
    assert _lancar(piso, recife, 'Expedição').status_code == 201
    assert _lancar(piso, recife, 'Expedição').status_code == 409
    with app_module.app.app_context():
        assert DiarioTurno.query.filter_by(
            client_id=recife['client_id']).count() == 1


# ── Área é cadastro, não texto digitado ──────────────────────────────────

def test_area_repetida_no_mesmo_contrato_e_recusada(mestre, recife):
    """Com vinte pessoas lançando, "Expedição" e "expedicao" virariam duas."""
    r = mestre.post('/passagem-de-turno/api/areas',
                    json={'client_id': recife['client_id'], 'nome': 'expedição'})
    assert r.status_code == 409
    assert 'Expedição' in r.get_json()['error']


def test_area_sem_nome_e_recusada(mestre, recife):
    assert mestre.post('/passagem-de-turno/api/areas',
                       json={'client_id': recife['client_id'],
                             'nome': '  '}).status_code == 400


def test_o_mesmo_nome_de_area_pode_existir_em_contratos_diferentes(
        mestre, recife):
    """"Expedição" da PepsiCo e "Expedição" do Atacarejo são duas áreas."""
    r = mestre.post('/passagem-de-turno/api/areas',
                    json={'client_id': recife['outro_id'], 'nome': 'Expedição'})
    assert r.status_code == 201


def test_renomear_area_nao_cria_outra(app_module, mestre, recife):
    aid = recife['areas']['Expedição']['area']
    assert mestre.put(f'/passagem-de-turno/api/areas/{aid}',
                      json={'nome': 'Expedição Seca'}).status_code == 200
    with app_module.app.app_context():
        assert DiarioArea.query.filter_by(
            client_id=recife['client_id']).count() == 2
        assert DiarioArea.query.get(aid).nome == 'Expedição Seca'


def test_desativar_area_nao_apaga_a_passagem_lancada(app_module, piso, mestre,
                                                     recife):
    """Desativar esconde de quem lança; o histórico continua de pé."""
    _lancar(piso, recife, 'Expedição')
    aid = recife['areas']['Expedição']['area']
    assert mestre.put(f'/passagem-de-turno/api/areas/{aid}',
                      json={'ativo': False}).status_code == 200
    with app_module.app.app_context():
        assert DiarioArea.query.get(aid).ativo is False
        assert DiarioTurno.query.filter_by(
            client_id=recife['client_id']).count() == 1
        # E some do seletor de quem vai lançar.
        assert 'Expedição' not in [
            a.nome for a in an.areas_do_contrato(recife['client_id'])]


# ── O recorte por área ───────────────────────────────────────────────────

def test_o_painel_separa_expedicao_de_almoxarifado(app_module, piso, recife):
    _lancar(piso, recife, 'Expedição',
            dados={'atividade:retrabalho': {'concluido': True}})
    _lancar(piso, recife, 'Almoxarifado',
            dados={'atividade:estoque': {'concluido': False}})
    with app_module.app.app_context():
        exp = an.painel(recife['client_id'],
                        area_id=recife['areas']['Expedição']['area'])
        alm = an.painel(recife['client_id'],
                        area_id=recife['areas']['Almoxarifado']['area'])
        tudo = an.painel(recife['client_id'])
        assert exp['aderencia']['pct'] == 100.0
        assert alm['aderencia']['pct'] == 0.0
        # Sem recorte, as duas viram uma média que não descreve nenhuma.
        assert tudo['aderencia']['pct'] == 50.0


def test_o_filtro_de_area_do_painel_recusa_area_de_outro_contrato(
        app_module, mestre, piso, recife):
    """Id chutado não pode vazar a área de outro cliente nem esvaziar a tela."""
    with app_module.app.app_context():
        intrusa = DiarioArea(client_id=recife['outro_id'], nome='Doca',
                             ativo=True)
        app_module.db.session.add(intrusa)
        app_module.db.session.commit()
        alheia = intrusa.id
    _lancar(piso, recife, 'Expedição')
    _lancar(piso, recife, 'Almoxarifado')
    tela = piso.get('/passagem-de-turno/'
                    f'?client_id={recife["client_id"]}&area_id={alheia}')
    assert tela.status_code == 200
    # Cai em "todas": a tela continua mostrando as DUAS passagens do contrato
    # em vez de esvaziar por causa de um id que não é dele.
    corpo = tela.get_data(as_text=True)
    assert 'Expedição' in corpo and 'Almoxarifado' in corpo
    with app_module.app.app_context():
        # E a área alheia não empresta modelo nenhum a este contrato.
        assert an._configs_da_area(recife['client_id'], alheia) == []


def test_modelo_nao_aponta_para_area_de_outro_contrato(app_module, mestre,
                                                       recife):
    with app_module.app.app_context():
        alheia = DiarioArea(client_id=recife['outro_id'], nome='Doca',
                            ativo=True)
        app_module.db.session.add(alheia)
        app_module.db.session.commit()
        alheia_id = alheia.id
    r = mestre.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': recife['client_id'], 'nome': 'Tentativa',
        'area_id': alheia_id, 'perguntas': []})
    assert r.status_code == 201
    # A área alheia é descartada em silêncio — o modelo nasce sem área, e não
    # apontando para a operação de outro cliente.
    assert r.get_json()['area_id'] is None


def test_o_relatorio_mensal_sai_por_area(app_module, piso, mestre, recife):
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Expedição',
            dados={'atividade:retrabalho': {'concluido': True}})
    _lancar(piso, recife, 'Almoxarifado',
            dados={'atividade:estoque': {'concluido': False}})
    base = (f'/passagem-de-turno/relatorio-mensal?client_id={recife["client_id"]}'
            f'&mes={hoje.month}&ano={hoje.year}')
    aid = recife['areas']['Expedição']['area']
    tela = mestre.get(f'{base}&area_id={aid}').get_data(as_text=True)
    assert 'Expedição' in tela
    with app_module.app.app_context():
        rel = an.fechamento_mensal(recife['client_id'], hoje.year, hoje.month,
                                   area_id=aid)
        assert rel['turnos']['total'] == 1
        assert rel['aderencia']['pct'] == 100.0


def test_o_pdf_do_relatorio_por_area_continua_pdf(mestre, piso, recife):
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Expedição')
    aid = recife['areas']['Expedição']['area']
    r = mestre.get(f'/passagem-de-turno/relatorio-mensal'
                   f'?client_id={recife["client_id"]}&mes={hoje.month}'
                   f'&ano={hoje.year}&area_id={aid}&format=pdf')
    assert r.status_code == 200
    assert r.data[:4] == b'%PDF'
    assert 'Expedi' in r.headers.get('Content-Disposition', '')


# ── A tela de quem lança ─────────────────────────────────────────────────

def test_a_tela_de_passagem_oferece_as_areas(piso, recife):
    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'diario-area' in tela
    assert 'Expedição' in tela and 'Almoxarifado' in tela


def test_a_area_manda_TODOS_os_seus_modelos_para_a_tela(app_module, piso, recife):
    """Um modelo POR TURNO — e a tela precisa dos três para resolver o par.

    No CD de Simões Filho cada turno registra coisas diferentes: o T1 conta
    formulários Q e retrabalho, o T2 conta volumes de OT/PVV/DTS, o T3 conta
    carretas em fila e hora de fim de expediente. São três modelos na mesma
    área, e quem lança escolhe só ÁREA e TURNO — o modelo é consequência.

    Se a rota mandasse um modelo só (o primeiro, ou o "ativo"), o T2 e o T3
    cairiam nas perguntas do T1 sem que ninguém percebesse.
    """
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        area = recife['areas']['Expedição']['area']
        for turno in ('T2', 'T3'):
            app_module.db.session.add(DiarioConfiguracao(
                client_id=recife['client_id'], area_id=area,
                nome=f'Expedição — {turno}',
                turnos_json=json.dumps([{'nome': turno}]),
                campos_json='[]',
                atividades_json=json.dumps(
                    [{'nome': f'Rotina do {turno}', 'codigo': f'rot_{turno}'}]),
                tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id))
        app_module.db.session.commit()

    # Lê o payload que a tela recebe, em vez de procurar texto no HTML: o
    # `|tojson` escapa acento e travessão, e um assert de substring passaria
    # ou falharia pelo motivo errado.
    corpo = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    bruto = re.search(r"data-configs='([^']*)'", corpo).group(1)
    modelos = json.loads(html.unescape(bruto))
    da_area = {m['nome']: m for m in modelos
               if m['area_id'] == recife['areas']['Expedição']['area']}
    assert set(da_area) == {'Passagem Expedição', 'Expedição — T2',
                            'Expedição — T3'}
    # E cada um leva as SUAS perguntas, não as do primeiro da lista.
    for turno in ('T2', 'T3'):
        modelo = da_area[f'Expedição — {turno}']
        assert [p['nome'] for p in modelo['perguntas']] == [f'Rotina do {turno}']
        assert [t['nome'] for t in modelo['turnos']] == [turno]


def test_area_sem_modelo_nao_e_oferecida_a_quem_lanca(app_module, mestre, piso,
                                                      recife):
    """Oferecer uma área sem modelo levaria a pessoa a uma tela sem pergunta."""
    mestre.post('/passagem-de-turno/api/areas',
                json={'client_id': recife['client_id'], 'nome': 'Recebimento'})
    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'Recebimento' not in tela


def test_o_cadastro_lista_as_areas_com_quantos_modelos_amparam(mestre, recife):
    tela = mestre.get('/passagem-de-turno/configuracao'
                      f'?client_id={recife["client_id"]}').get_data(as_text=True)
    assert 'Áreas deste contrato' in tela
    assert 'Expedição' in tela and 'Almoxarifado' in tela


def test_o_piso_nao_cadastra_area(piso, recife):
    """Cadastro de área é do Master — senão cada turno inventaria a sua."""
    r = piso.post('/passagem-de-turno/api/areas',
                  json={'client_id': recife['client_id'], 'nome': 'Minha área'})
    assert r.status_code in (302, 403)


# ── O semáforo 🟢🟡🔴 ────────────────────────────────────────────────────

def test_escolha_guarda_as_opcoes_do_modelo(app_module, mestre, recife):
    """O status geral do recado de WhatsApp vira dado, não texto solto."""
    r = mestre.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': recife['client_id'], 'nome': 'Com semáforo',
        'perguntas': [{'nome': 'Status geral da operação', 'tipo': 'escolha',
                       'opcoes': ['NORMAL', 'ATENÇÃO', 'CRÍTICO']}]})
    assert r.status_code == 201
    pergunta = r.get_json()['perguntas'][0]
    assert pergunta['tipo'] == 'escolha'
    assert pergunta['opcoes'] == ['NORMAL', 'ATENÇÃO', 'CRÍTICO']


def test_escolha_sem_opcao_vira_texto(mestre, recife):
    """Seletor vazio na tela do piso é pior do que um campo de texto."""
    r = mestre.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': recife['client_id'], 'nome': 'Semáforo vazio',
        'perguntas': [{'nome': 'Status', 'tipo': 'escolha', 'opcoes': ['  ']}]})
    assert r.status_code == 201
    assert r.get_json()['perguntas'][0]['tipo'] == 'texto'


def test_a_resposta_da_escolha_e_gravada(app_module, piso, mestre, recife):
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=recife['client_id'],
            area_id=recife['areas']['Expedição']['area'],
            nome='Com semáforo',
            turnos_json=json.dumps([{'nome': '1º Turno'}]),
            campos_json=json.dumps([{'nome': 'Status', 'codigo': 'status',
                                     'tipo': 'escolha',
                                     'opcoes': ['NORMAL', 'ATENÇÃO']}]),
            atividades_json='[]', tipos_ocorrencia_json='[]',
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        cid = cfg.id
    r = piso.post('/passagem-de-turno/api/turnos', json={
        'client_id': recife['client_id'], 'configuracao_id': cid,
        'data_turno': tempo.hoje().isoformat(), 'turno': '1º Turno',
        'dados': {'status': 'ATENÇÃO'}, 'finalizar': True})
    assert r.status_code == 201
    assert r.get_json()['dados']['status'] == 'ATENÇÃO'


# ── Contrato que não se divide continua funcionando ──────────────────────

def test_contrato_sem_area_continua_lancando_normalmente(app_module, piso,
                                                         recife):
    """A área é divisão nova, não requisito retroativo."""
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=recife['client_id'], area_id=None, nome='Sem área',
            turnos_json=json.dumps([{'nome': 'Único'}]), campos_json='[]',
            atividades_json='[]', tipos_ocorrencia_json='[]',
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        cid = cfg.id
    r = piso.post('/passagem-de-turno/api/turnos', json={
        'client_id': recife['client_id'], 'configuracao_id': cid,
        'data_turno': tempo.hoje().isoformat(), 'turno': 'Único',
        'finalizar': True})
    assert r.status_code == 201
    with app_module.app.app_context():
        # O painel sem recorte continua vendo esse turno...
        assert an.painel(recife['client_id'])['n_turnos'] == 1
        # ...e o recorte por uma área qualquer NÃO o traz junto, porque ele
        # não é de área nenhuma.
        assert an.painel(recife['client_id'],
                         area_id=recife['areas']['Expedição']['area']
                         )['n_turnos'] == 0
