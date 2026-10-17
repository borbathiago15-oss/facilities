"""A trilha da pendência: o que um turno tentou chega ao turno seguinte.

O caso que deu origem a tudo isto, nas palavras de quem pediu:

    "Uma devolução recebida do T02 que o T01 não conseguiu achar o processo,
     essa fica pendente até a resolução."

A primeira metade já funcionava — pendência aberta não morre com o turno nem
com o dia. A segunda metade não existia: o T01 passava o turno inteiro atrás
do processo, não achava, encerrava, e a linha no banco terminava o dia
IDÊNTICA. O esforço sumia, e o T02 do dia seguinte recomeçava do zero,
ligando de novo para o mesmo CD que o T01 já havia ligado.

O que se prova aqui:

* a pendência atravessa turno e dia enquanto estiver aberta;
* o turno que a recebe e não resolve deixa registro DISSO sem que se peça
  digitação a ninguém;
* "resolver" exige dizer o que foi feito, e grava quem foi;
* a contagem de passagens conta TURNOS, não eventos;
* a idade conta desde o dia do turno que a abriu, não desde a digitação.
"""
import json
from datetime import timedelta

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import (DiarioConfiguracao, DiarioPendencia,
                          DiarioPendenciaEvento, DiarioTurno)
from facilities.passagem import analitico as an

ATIVIDADES = [{'nome': 'Conferência de série', 'codigo': 'serie',
               'obrigatorio': True}]


@pytest.fixture()
def operacao(app_module):
    """Um contrato de dois turnos com um encarregado ligado a ele."""
    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='CD Whirlpool',
            turnos_json=json.dumps([{'nome': 'T01'}, {'nome': 'T02'}]),
            campos_json=json.dumps([]),
            atividades_json=json.dumps(ATIVIDADES),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)

        enc = app_module.User.query.filter_by(
            email='encarregado.trilha@teste.com').first()
        if enc is None:
            enc = app_module.User(name='Encarregado da trilha',
                                  email='encarregado.trilha@teste.com',
                                  is_active=True)
            app_module.db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = json.dumps([])
        enc.set_password('senha12345')
        enc.clients = [cliente]
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'config_id': cfg.id,
                'email': enc.email, 'senha': 'senha12345', 'enc_id': enc.id}


@pytest.fixture()
def piso(client, operacao):
    client.post('/login', data={'email': operacao['email'],
                                'password': operacao['senha']})
    return client


@pytest.fixture()
def mestre(app_module):
    """O Master em test_client PRÓPRIO — ``/login`` redireciona quem já entrou."""
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _passagem(cl, operacao, dia, turno, **extra):
    corpo = {'client_id': operacao['client_id'],
             'configuracao_id': operacao['config_id'],
             'data_turno': dia.isoformat(), 'turno': turno, 'finalizar': True}
    corpo.update(extra)
    return cl.post('/passagem-de-turno/api/turnos', json=corpo)


def _devolucao(cl, operacao, dia, titulo='Devolução sem processo',
               referencia='445.221'):
    """O T02 recebe a devolução e a deixa para o turno seguinte."""
    return _passagem(cl, operacao, dia, 'T02', pendencias=[
        {'titulo': titulo, 'referencia': referencia,
         'descricao': 'Nota na portaria, sem processo no sistema.',
         'prioridade': 'media'}])


# ── A travessia ──────────────────────────────────────────────────────────

def test_a_devolucao_atravessa_turno_e_dia_ate_alguem_resolver(
        app_module, piso, operacao):
    hoje = tempo.hoje()
    assert _devolucao(piso, operacao, hoje - timedelta(days=3)).status_code == 201

    # Dois dias e três turnos depois, ela continua na tela de quem entra.
    for dia, turno in [(hoje - timedelta(days=2), 'T01'),
                       (hoje - timedelta(days=2), 'T02'),
                       (hoje - timedelta(days=1), 'T01')]:
        tela = piso.get('/passagem-de-turno/turno')
        assert 'Devolução sem processo' in tela.get_data(as_text=True)
        _passagem(piso, operacao, dia, turno)

    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'Devolução sem processo' in tela
    # E o número dela é procurável, porque ganhou campo próprio.
    assert '445.221' in tela


def test_o_turno_que_recebeu_e_nao_resolveu_deixa_registro_disso(
        app_module, piso, operacao):
    """Sem pedir digitação a ninguém — senão o piso simplesmente não faria."""
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=1))
    _passagem(piso, operacao, hoje, 'T01')          # recebeu, não resolveu

    with app_module.app.app_context():
        p = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first()
        eventos = DiarioPendenciaEvento.query.filter_by(pendencia_id=p.id).all()
        assert [e.tipo for e in eventos] == ['recebida']
        t01 = DiarioTurno.query.filter_by(turno='T01').first()
        assert eventos[0].turno_id == t01.id
        assert eventos[0].created_by == operacao['enc_id']


def test_quem_abriu_a_pendencia_nao_conta_como_quem_a_carregou(
        app_module, piso, operacao):
    """O turno que entrega não está carregando nada — está entregando."""
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        p = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first()
        assert DiarioPendenciaEvento.query.filter_by(pendencia_id=p.id).count() == 0


def test_reencerrar_o_mesmo_turno_nao_infla_a_trilha(app_module, piso, operacao):
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=1))
    _passagem(piso, operacao, hoje, 'T01')
    # O segundo envio do mesmo turno é recusado (já encerrado), e mesmo que
    # não fosse, a trilha não pode ganhar um evento repetido.
    _passagem(piso, operacao, hoje, 'T01')
    with app_module.app.app_context():
        p = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first()
        assert DiarioPendenciaEvento.query.filter_by(pendencia_id=p.id).count() == 1


# ── Resolver exige dizer o que foi feito ─────────────────────────────────

def test_resolver_sem_dizer_o_que_foi_feito_e_recusado(app_module, piso, operacao):
    """Um "resolver" que não custa nada vira botão de limpar a tela."""
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id

    for corpo in ({}, {'resolucao': ''}, {'resolucao': '   '}):
        r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
                      json=corpo)
        assert r.status_code == 400, corpo

    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).status == 'aberta'


def test_resolver_grava_o_que_foi_feito_e_quem_fez(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id

    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
                  json={'resolucao': 'Fiscal abriu o processo 77.402.'})
    assert r.status_code == 200

    with app_module.app.app_context():
        p = DiarioPendencia.query.get(pid)
        assert p.status == 'resolvida'
        assert p.resolucao == 'Fiscal abriu o processo 77.402.'
        assert p.resolved_by == operacao['enc_id']
        assert p.resolved_at is not None
        ev = DiarioPendenciaEvento.query.filter_by(
            pendencia_id=pid, tipo='resolvida').one()
        assert ev.texto == 'Fiscal abriu o processo 77.402.'


def test_resolver_duas_vezes_nao_reescreve_a_primeira_resolucao(
        app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
              json={'resolucao': 'Processo localizado.'})
    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
                  json={'resolucao': 'outra coisa qualquer'})
    assert r.status_code == 409
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).resolucao == 'Processo localizado.'


def test_o_gestor_tambem_deve_a_frase(app_module, mestre, piso, operacao):
    """Se o caminho curto sobrevivesse no dashboard, ele viraria O caminho."""
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    assert mestre.post(
        f'/passagem-de-turno/api/pendencias/{pid}/resolver').status_code == 400


# ── "Continua": o que se tentou ──────────────────────────────────────────

def test_a_tentativa_de_um_turno_chega_ao_turno_seguinte(
        app_module, piso, operacao):
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=1))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id

    r = piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
                  json={'texto': 'Liguei para o CD de origem, sem retorno.',
                        'data_turno': hoje.isoformat(), 'turno': 'T01'})
    assert r.status_code == 200

    with app_module.app.app_context():
        p = DiarioPendencia.query.get(pid)
        assert p.status == 'aberta'          # anotar não baixa
        ev = DiarioPendenciaEvento.query.filter_by(
            pendencia_id=pid, tipo='tentativa').one()
        assert 'CD de origem' in ev.texto
        # O relatório mostra a última tentativa ao lado da pendência parada.
        resumo = an._resumo_das_trilhas([pid])
        assert 'CD de origem' in resumo[pid]['ultima']

    # E, o que importa mais, ela chega ao CARTÃO de quem entra depois.
    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'Já se tentou' in tela
    assert 'CD de origem' in tela


def test_a_ultima_tentativa_e_a_mais_recente(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje() - timedelta(days=1))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    for texto in ('liguei para o CD', 'abri chamado no fiscal'):
        piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
                  json={'texto': texto})
    with app_module.app.app_context():
        linha = an.fila_de_pendencias(operacao['client_id'])[0]
        assert linha['ultima_tentativa']['texto'] == 'abri chamado no fiscal'
        assert linha['ultima_tentativa']['quem'] == 'Encarregado da trilha'


def test_pendencia_sem_tentativa_nao_inventa_texto(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        assert an.fila_de_pendencias(
            operacao['client_id'])[0]['ultima_tentativa'] is None


def test_anotar_sem_texto_e_recusado(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    assert piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
                     json={'texto': '  '}).status_code == 400


def test_nao_se_anota_em_pendencia_ja_resolvida(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
              json={'resolucao': 'Resolvido.'})
    assert piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
                     json={'texto': 'tardio'}).status_code == 409


def test_o_evento_so_se_amarra_a_um_turno_que_existe(app_module, piso, operacao):
    """Antes de a passagem ser salva não há turno — e inventar um seria pior."""
    _devolucao(piso, operacao, tempo.hoje() - timedelta(days=1))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'tentei', 'data_turno': tempo.hoje().isoformat(),
                    'turno': 'T01'})
    with app_module.app.app_context():
        ev = DiarioPendenciaEvento.query.filter_by(
            pendencia_id=pid, tipo='tentativa').one()
        assert ev.turno_id is None          # o T01 de hoje ainda não existe
        assert ev.created_by == operacao['enc_id']


# ── As contas da tela ────────────────────────────────────────────────────

def test_o_turno_que_ja_disse_o_que_tentou_nao_ganha_evento_mudo(
        app_module, piso, operacao):
    """Quem anotou já se declarou; o "recebeu e não resolveu" seria ruído.

    E o que a tela mostra é TURNO, não evento: um turno que anota e depois
    encerra continua sendo um turno na conta de "passou por N".
    """
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=1))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    # Rascunho primeiro: o turno passa a existir, e a anotação se amarra nele.
    piso.post('/passagem-de-turno/api/turnos', json={
        'client_id': operacao['client_id'], 'configuracao_id': operacao['config_id'],
        'data_turno': hoje.isoformat(), 'turno': 'T01'})
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'liguei', 'data_turno': hoje.isoformat(),
                    'turno': 'T01'})
    _passagem(piso, operacao, hoje, 'T01')          # encerra

    with app_module.app.app_context():
        eventos = DiarioPendenciaEvento.query.filter_by(pendencia_id=pid).all()
        assert [e.tipo for e in eventos] == ['tentativa']
        assert eventos[0].texto == 'liguei'
        fila = an.fila_de_pendencias(operacao['client_id'])
        linha = next(x for x in fila if x['id'] == pid)
        assert linha['passagens'] == 1


def test_a_idade_conta_do_dia_do_turno_e_nao_da_digitacao(
        app_module, piso, operacao):
    """Lançar atrasado é rotina; a pendência não pode nascer mais nova por isso."""
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=4))
    with app_module.app.app_context():
        fila = an.fila_de_pendencias(operacao['client_id'])
        assert len(fila) == 1
        # O carimbo do banco é de agora (o teste acabou de lançar), mas o
        # turno é de quatro dias atrás: a âncora é o turno.
        assert fila[0]['dias'] >= 3
        assert fila[0]['vencida'] is True


def test_lancamento_no_proprio_dia_continua_usando_o_carimbo(
        app_module, piso, operacao):
    """Sem retroatividade não há o que corrigir — e nada pode envelhecer sozinho."""
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        fila = an.fila_de_pendencias(operacao['client_id'])
        assert fila[0]['dias'] == 0
        assert fila[0]['vencida'] is False


def test_a_fila_traz_origem_e_referencia_para_a_tela(app_module, piso, operacao):
    ontem = tempo.hoje() - timedelta(days=1)
    _devolucao(piso, operacao, ontem)
    with app_module.app.app_context():
        linha = an.fila_de_pendencias(operacao['client_id'])[0]
        assert linha['origem_turno'] == 'T02'
        assert linha['origem_data'] == ontem
        assert linha['referencia'] == '445.221'


def test_pendencia_resolvida_sai_da_fila(app_module, piso, operacao):
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
              json={'resolucao': 'Processo achado.'})
    with app_module.app.app_context():
        assert an.fila_de_pendencias(operacao['client_id']) == []


# ── O que o turno anterior deixou ────────────────────────────────────────

def test_a_tela_mostra_as_ocorrencias_do_turno_anterior(piso, operacao):
    """Antes só as pendências apareciam — o que JÁ aconteceu ficava escondido."""
    hoje = tempo.hoje()
    _passagem(piso, operacao, hoje - timedelta(days=1), 'T02',
              observacao='Doca 3 travada a tarde inteira.',
              ocorrencias=[{'tipo': 'Avaria', 'referencia': 'NF 9912',
                            'descricao': 'Pallet amassado na rua 12.'}])
    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'O turno anterior deixou' in tela
    assert 'Doca 3 travada' in tela
    assert 'Pallet amassado na rua 12' in tela
    assert 'NF 9912' in tela


def test_sem_passagem_anterior_o_bloco_nao_aparece(piso, operacao):
    tela = piso.get('/passagem-de-turno/turno').get_data(as_text=True)
    assert 'O turno anterior deixou' not in tela


# ── A trilha no relatório e na leitura do turno ──────────────────────────

def test_o_relatorio_mostra_o_que_foi_feito_e_o_que_se_tentou(
        app_module, piso, operacao):
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje)
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'Liguei para o CD, sem retorno.'})

    with app_module.app.app_context():
        rel = an.fechamento_mensal(operacao['client_id'], hoje.year, hoje.month)
        aberta = next(x for x in rel['pendencias']['lista_em_aberto']
                      if x['p'].id == pid)
        assert 'sem retorno' in aberta['ultima_tentativa']

    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
              json={'resolucao': 'Processo 77.402 aberto pelo fiscal.'})
    with app_module.app.app_context():
        rel = an.fechamento_mensal(operacao['client_id'], hoje.year, hoje.month)
        baixada = next(x for x in rel['pendencias']['lista_resolvidas']
                       if x['p'].id == pid)
        assert baixada['resolucao'] == 'Processo 77.402 aberto pelo fiscal.'
        assert baixada['resolvida_por'] == 'Encarregado da trilha'


def test_a_tela_e_o_relatorio_contam_a_MESMA_idade(app_module, piso, operacao):
    """Dois lugares refazendo a conta cada um do seu jeito é o defeito
    clássico do relatório — e este módulo já tinha as duas contas divergindo
    para a pendência lançada com atraso."""
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=3))
    with app_module.app.app_context():
        linha = an.fila_de_pendencias(operacao['client_id'])[0]
        rel = an.fechamento_mensal(operacao['client_id'], hoje.year, hoje.month)
        aberta = next(x for x in rel['pendencias']['lista_em_aberto']
                      if x['p'].id == linha['id'])
        assert aberta['dias'] == linha['dias'] >= 2


def test_o_pdf_do_relatorio_sai_com_a_trilha_dentro(app_module, piso, mestre,
                                                    operacao):
    """A tela e o PDF leem do mesmo dicionário — e o PDF tem de continuar PDF.

    O PDF é montado com ReportLab a partir de ``fechamento_mensal``; campo
    novo no dicionário que o construtor não saiba tratar derruba o download
    inteiro, e isso só aparece aqui.
    """
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje)
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'Liguei para o CD, sem retorno.'})

    r = mestre.get('/passagem-de-turno/relatorio-mensal'
                   f'?client_id={operacao["client_id"]}'
                   f'&mes={hoje.month}&ano={hoje.year}&format=pdf')
    assert r.status_code == 200
    assert r.data[:4] == b'%PDF'
    assert r.headers['Content-Type'].startswith('application/pdf')


def test_a_trilha_aparece_na_leitura_do_turno(app_module, piso, mestre, operacao):
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=1))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
        turno_id = DiarioTurno.query.filter_by(turno='T02').first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'Chamado 8891 aberto no fiscal.'})

    tela = mestre.get(f'/passagem-de-turno/turno/{turno_id}').get_data(as_text=True)
    assert 'Chamado 8891' in tela
    assert 'Encarregado da trilha' in tela


def test_a_trilha_sai_em_ordem_de_acontecimento(app_module, piso, operacao):
    hoje = tempo.hoje()
    _devolucao(piso, operacao, hoje - timedelta(days=2))
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/nota',
              json={'texto': 'primeira tentativa'})
    _passagem(piso, operacao, hoje - timedelta(days=1), 'T01')
    piso.post(f'/passagem-de-turno/api/pendencias/{pid}/resolver',
              json={'resolucao': 'fim'})
    with app_module.app.app_context():
        trilha = an.trilha_da_pendencia(pid)
        assert [e['tipo'] for e in trilha] == ['tentativa', 'recebida', 'resolvida']
        assert all(e['quem'] == 'Encarregado da trilha' for e in trilha)


# ── A porta ──────────────────────────────────────────────────────────────

def test_encarregado_de_outra_carteira_nao_mexe_na_pendencia(
        app_module, piso, operacao):
    """A trilha não pode virar uma porta lateral para outro contrato."""
    from tests.test_authz import _make_user
    _devolucao(piso, operacao, tempo.hoje())
    with app_module.app.app_context():
        pid = DiarioPendencia.query.filter_by(
            client_id=operacao['client_id']).order_by(DiarioPendencia.id).first().id
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != operacao['client_id']).first())
        _uid, email = _make_user(app_module, role='encarregado',
                                 client_ids=[outro.id])
    intruso = app_module.app.test_client()
    intruso.post('/login', data={'email': email, 'password': 'senha12345'})
    for rota, corpo in (('resolver', {'resolucao': 'tomei posse'}),
                        ('nota', {'texto': 'tomei posse'})):
        r = intruso.post(f'/passagem-de-turno/api/pendencias/{pid}/{rota}',
                         json=corpo)
        assert r.status_code in (403, 404), rota
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).status == 'aberta'
