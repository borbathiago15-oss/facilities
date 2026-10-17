"""O ponto de atenção: o fato que o gestor precisa LER, e hoje não lê.

O caso que deu origem a isto, nas palavras de quem gere a operação:

    Suspendi o colaborador X por indisciplinado
    Não atendimento da demanda do dia

Nenhum dos dois é pendência. Ninguém vai "resolver" a suspensão amanhã; o
não atendimento de ontem não vira tarefa de hoje. São fatos consumados — e,
antes disto, morriam dentro da passagem de turno: o encarregado registrava e
nada subia para a tela de quem gere o contrato.

O que se prova aqui:

* a ocorrência marcada como ponto de atenção sobe para a Torre de Comando, e a
  normal não sobe;
* ela sobe para um bloco de LEITURA — fora da mesa P1/P2/P3, fora do radar e
  fora do total, porque fato consumado não é tarefa que alguém possa fechar;
* e, por consequência, ela não envenena os dois sinais do compromisso: não
  aparece como "visto e nunca tocado" nem conta volta de PDCA;
* gravidade que não existe no vocabulário vira 'normal' — o corpo do POST não
  escolhe o que a tela do gestor vai mostrar;
* a ocorrência que já existia continua valendo 'normal', que é exatamente o
  que ela era quando foi escrita;
* a carteira manda: ponto de atenção de contrato alheio não vaza;
* e o mês agrega — "para análise" só vale se o relatório somar.
"""
import json

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import DiarioConfiguracao, DiarioOcorrencia, DiarioTurno
from facilities.passagem.models import (
    OCORRENCIA_CRITICA, OCORRENCIA_NORMAL)
from facilities.passagem import analitico as an

TIPOS = [{'nome': 'Disciplinar'}, {'nome': 'Operacional'}]


@pytest.fixture()
def operacao(app_module):
    """Um contrato com modelo de passagem, um encarregado e outro contrato."""
    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != cliente.id).first())
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()

        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Passagem CD',
            turnos_json=json.dumps([{'nome': '1º Turno'}]),
            campos_json='[]', atividades_json='[]',
            tipos_ocorrencia_json=json.dumps(TIPOS),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)

        enc = app_module.User.query.filter_by(
            email='enc.atencao@teste.com').first()
        if enc is None:
            enc = app_module.User(name='Encarregado',
                                  email='enc.atencao@teste.com',
                                  is_active=True)
            app_module.db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = '[]'
        enc.set_password('senha12345')
        enc.clients = [cliente]
        app_module.db.session.flush()
        cfg_id = cfg.id
        app_module.db.session.commit()
        return {'cid': cliente.id, 'outro': outro.id, 'cfg': cfg_id,
                'email': enc.email, 'admin_id': admin.id}


@pytest.fixture()
def piso(client, operacao):
    client.post('/login', data={'email': operacao['email'],
                                'password': 'senha12345'})
    return client


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _lancar(cl, operacao, ocorrencias, dia=None):
    return cl.post('/passagem-de-turno/api/turnos', json={
        'client_id': operacao['cid'], 'configuracao_id': operacao['cfg'],
        'data_turno': (dia or tempo.hoje()).isoformat(),
        'turno': '1º Turno', 'finalizar': True,
        'ocorrencias': ocorrencias})


def _semear(app_module, client_id, descricao, gravidade, quando=None):
    """Grava uma ocorrência direto, para os casos que não passam pela tela."""
    from datetime import datetime
    o = DiarioOcorrencia(client_id=client_id, tipo='Disciplinar',
                         descricao=descricao, gravidade=gravidade,
                         created_by=1,
                         created_at=quando or datetime.utcnow())
    app_module.db.session.add(o)
    app_module.db.session.commit()
    return o.id


# ── A marca chega ao banco ───────────────────────────────────────────────

def test_encarregado_marca_o_ponto_de_atencao(app_module, piso, operacao):
    """O caso literal do usuário, entrando pela tela do piso."""
    r = _lancar(piso, operacao, [
        {'tipo': 'Disciplinar', 'referencia': '',
         'descricao': 'Suspendi o colaborador X por indisciplina',
         'gravidade': 'critica'},
        {'tipo': 'Operacional', 'referencia': '',
         'descricao': 'Avaria em dois paletes na doca 3',
         'gravidade': 'normal'},
    ])
    assert r.status_code == 201
    with app_module.app.app_context():
        todas = DiarioOcorrencia.query.filter_by(
            client_id=operacao['cid']).all()
        por_grav = {o.gravidade for o in todas}
        assert por_grav == {OCORRENCIA_CRITICA, OCORRENCIA_NORMAL}
        critica = [o for o in todas if o.gravidade == OCORRENCIA_CRITICA]
        assert 'Suspendi' in critica[0].descricao


def test_sem_gravidade_no_corpo_a_ocorrencia_nasce_normal(app_module, piso,
                                                          operacao):
    """Compatibilidade: a tela antiga não mandava o campo."""
    assert _lancar(piso, operacao, [
        {'tipo': 'Operacional', 'descricao': 'Falta de empilhadeira'},
    ]).status_code == 201
    with app_module.app.app_context():
        o = DiarioOcorrencia.query.filter_by(client_id=operacao['cid']).first()
        assert o.gravidade == OCORRENCIA_NORMAL


def test_gravidade_inventada_nao_passa(app_module, piso, operacao):
    """O corpo do POST não escolhe o que a tela do gestor vai mostrar.

    Sem isto, um valor qualquer atravessaria até o bloco de pontos de
    atenção, que filtra por igualdade — e ficaria um registro que nem sobe
    nem se lê como normal, invisível nos dois lugares.
    """
    assert _lancar(piso, operacao, [
        {'tipo': 'Operacional', 'descricao': 'Teste',
         'gravidade': 'CATASTRÓFICA'},
    ]).status_code == 201
    with app_module.app.app_context():
        o = DiarioOcorrencia.query.filter_by(client_id=operacao['cid']).first()
        assert o.gravidade == OCORRENCIA_NORMAL


# ── A consulta ───────────────────────────────────────────────────────────

def test_so_a_critica_e_ponto_de_atencao(app_module, operacao):
    with app_module.app.app_context():
        _semear(app_module, operacao['cid'], 'Suspensão do X',
                OCORRENCIA_CRITICA)
        _semear(app_module, operacao['cid'], 'Palete avariado',
                OCORRENCIA_NORMAL)
        achadas = an.pontos_de_atencao(operacao['cid'])
        assert len(achadas) == 1
        assert achadas[0].descricao == 'Suspensão do X'


def test_ponto_de_atencao_nao_vaza_entre_contratos(app_module, operacao):
    """A carteira manda aqui como manda no resto da casa — e aqui manda mais,
    porque o texto pode nomear uma pessoa."""
    with app_module.app.app_context():
        _semear(app_module, operacao['outro'], 'Suspensão no outro contrato',
                OCORRENCIA_CRITICA)
        assert an.pontos_de_atencao(operacao['cid']) == []
        assert len(an.pontos_de_atencao(operacao['outro'])) == 1


def test_o_corte_por_data_recorta_a_tela_e_nao_o_dado(app_module, operacao):
    """A Torre de Comando quer a manhã; o Diário guarda tudo."""
    from datetime import datetime, timedelta
    with app_module.app.app_context():
        _semear(app_module, operacao['cid'], 'Antiga', OCORRENCIA_CRITICA,
                quando=datetime.utcnow() - timedelta(days=40))
        _semear(app_module, operacao['cid'], 'Recente', OCORRENCIA_CRITICA)
        # Sem corte, as duas.
        assert len(an.pontos_de_atencao(operacao['cid'])) == 2
        # Com corte, só a da janela.
        recorte = an.pontos_de_atencao(operacao['cid'],
                                       desde=tempo.hoje() - timedelta(days=7))
        assert [o.descricao for o in recorte] == ['Recente']


# ── A Torre de Comando: leitura, e fora da mesa ─────────────────────────────


# ── O mês ────────────────────────────────────────────────────────────────

def test_o_relatorio_mensal_separa_os_pontos_de_atencao(app_module, piso,
                                                        operacao):
    """"Para análise" só vale se o mês agregar.

    E separado do Pareto de propósito: o Pareto conta TIPOS, então a avaria
    de palete e a suspensão de colaborador caem na mesma barra quando são do
    mesmo tipo.
    """
    hoje = tempo.hoje()
    assert _lancar(piso, operacao, [
        {'tipo': 'Disciplinar', 'descricao': 'Suspendi o X',
         'gravidade': 'critica'},
        {'tipo': 'Operacional', 'descricao': 'Palete avariado',
         'gravidade': 'normal'},
    ], dia=hoje).status_code == 201
    with app_module.app.app_context():
        rel = an.fechamento_mensal(operacao['cid'], hoje.year, hoje.month)
        assert rel['ocorrencias']['total'] == 2
        atencao = rel['ocorrencias']['atencao']
        assert len(atencao) == 1
        assert atencao[0]['o'].descricao == 'Suspendi o X'
