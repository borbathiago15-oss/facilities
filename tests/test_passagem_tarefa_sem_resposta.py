"""A tarefa da gestão no ENCERRAMENTO da passagem — e a hora do aparelho.

O que estava solto, e o que se prova aqui (cada regra com o contraexemplo):

* **A tarefa que ninguém respondeu.** Encerrar sem "fiz" nem "não deu"
  deixava a tarefa "pendente" para sempre, numa passagem que não volta a
  abrir. Agora ela vira pendência de prioridade ALTA deste turno, a tarefa
  fica "virou pendência" com a resposta "Não respondida no turno", e quem
  pediu é avisado. Rascunho não converte nada; tarefa já respondida não é
  tocada; o reenvio da fila do aparelho não duplica.
* **A origem da pendência do "Não deu".** Respondida antes de a passagem
  existir, ela nascia sem turno — e caía na fila como se a gestão a tivesse
  aberto. Com rascunho já salvo, liga na hora; sem rascunho, o encerramento
  liga. Passagem de OUTRA área (outro modelo) não a adota.
* **Tarefa para turno encerrado** é recusada (409): ninguém a responderia.
* **O aviso ao piso** fala a língua do formulário: "prioridade alta", não
  "crítica" — e conta as pendências que nasceram das tarefas.
* **A hora do aparelho** é guardada só se for crível (com fuso, até 5 min à
  frente e até 72 h atrás da chegada), nunca recusa o encerramento, não muda
  o ``submitted_at`` e não pode ser forjada por dentro de ``dados``. A tela
  mostra as duas horas quando a fila as separou.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import json
import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import (
    DiarioConfiguracao, DiarioPendencia, DiarioPendenciaEvento,
    DiarioTarefaTurno, DiarioTurno, TAREFA_TURNO_FEITA, TAREFA_TURNO_PENDENTE,
    TAREFA_TURNO_VIROU_PENDENCIA)
from facilities.core.models import Notification

TAREFA = 'Conferir a temperatura da câmara'


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
    u.permissions_json = '[]'
    u.set_password('senha12345')
    db.session.flush()
    u.clients = clientes
    return u


@pytest.fixture()
def cena(app_module):
    """Um contrato com duas áreas (modelos) e dois encarregados."""
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()
        paulo = _usuario(app_module, 'paulo.semresposta@trino.com',
                         'Paulo do Piso', [cliente])
        rita = _usuario(app_module, 'rita.semresposta@trino.com',
                        'Rita do Piso', [cliente])

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
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        return {'cid': cliente.id, 'paulo': paulo.id, 'rita': rita.id,
                'admin': admin.id, 'exped': exped.id, 'almox': almox.id,
                'dia': date(2026, 9, 25)}


def _entrar(app_module, email, senha='senha12345'):
    c = app_module.app.test_client()
    c.post('/login', data={'email': email, 'password': senha})
    return c


@pytest.fixture()
def mestre(app_module):
    return _entrar(app_module, 'admin@grupotrino.com.br', TEST_ADMIN_PASSWORD)


@pytest.fixture()
def paulo(app_module, cena):
    return _entrar(app_module, 'paulo.semresposta@trino.com')


def _atribuir(mestre, cena, **kw):
    corpo = {'client_id': cena['cid'], 'configuracao_id': cena['exped'],
             'data_turno': cena['dia'].isoformat(), 'turno': '1º Turno',
             'titulo': TAREFA, 'forma_resposta': 'texto'}
    corpo.update(kw)
    return mestre.post('/passagem-de-turno/api/tarefas-turno', json=corpo)


def _salvar(cliente, cena, finalizar=True, **kw):
    corpo = {'client_id': cena['cid'], 'configuracao_id': cena['exped'],
             'data_turno': cena['dia'].isoformat(), 'turno': '1º Turno',
             'dados': {}, 'pendencias': [], 'finalizar': finalizar}
    corpo.update(kw)
    return cliente.post('/passagem-de-turno/api/turnos', json=corpo)


def _responder(cliente, tid, **corpo):
    return cliente.post(f'/passagem-de-turno/api/tarefas-turno/{tid}/responder',
                        json=corpo)


def _avisos(app_module, uid):
    with app_module.app.app_context():
        return [(n.title, n.message) for n in
                Notification.query.filter_by(user_id=uid,
                                             notification_type='passagem_turno')
                .order_by(Notification.id).all()]


def _avisos_de_encerramento(app_module, uid):
    return [a for a in _avisos(app_module, uid) if ' encerrado com ' in a[0]]


def _tarefa_id(app_module):
    with app_module.app.app_context():
        return DiarioTarefaTurno.query.order_by(DiarioTarefaTurno.id).first().id


def _iso(dt):
    """datetime UTC ingênuo → o que o navegador manda (``toISOString``)."""
    return dt.replace(microsecond=0).isoformat() + '.000Z'


# ── 1(b). A tarefa sem resposta vira pendência no encerramento ───────────

def test_tarefa_sem_resposta_vira_pendencia_alta_deste_turno(app_module, mestre,
                                                             paulo, cena):
    assert _atribuir(mestre, cena, descricao='Depois da manutenção').status_code == 201
    r = _salvar(paulo, cena)
    assert r.status_code == 201, r.get_data(as_text=True)
    turno_id = r.get_json()['id']

    with app_module.app.app_context():
        t = DiarioTarefaTurno.query.one()
        assert t.status == TAREFA_TURNO_VIROU_PENDENCIA
        assert t.resposta == 'Não respondida no turno'
        # Ninguém respondeu: quem encerrou está na pendência, não aqui.
        assert t.respondida_por is None
        p = DiarioPendencia.query.get(t.pendencia_id)
        assert p.turno_id == turno_id
        assert p.prioridade == 'alta'
        assert p.status == 'aberta'
        assert p.titulo == f'Tarefa não respondida: {TAREFA}'
        assert 'encerrado sem resposta' in p.descricao
        assert 'Depois da manutenção' in p.descricao
        assert p.created_by == cena['paulo']
        # A pendência é DESTE turno: ele a abriu, não a "recebeu".
        assert DiarioPendenciaEvento.query.filter_by(
            pendencia_id=p.id, turno_id=turno_id).count() == 0


def test_quem_pediu_e_avisado_da_tarefa_nao_respondida(app_module, mestre,
                                                       paulo, cena):
    _atribuir(mestre, cena)
    _salvar(paulo, cena)
    assert _avisos(app_module, cena['admin']) == [
        (f'Tarefa não respondida: {TAREFA}',
         '1º Turno de 25/09 encerrado sem resposta — virou pendência de '
         'prioridade alta.')]


def test_rascunho_nao_converte_a_tarefa(app_module, mestre, paulo, cena):
    """Salvar rascunho não é encerrar: ainda dá tempo de responder."""
    _atribuir(mestre, cena)
    assert _salvar(paulo, cena, finalizar=False).status_code == 201
    with app_module.app.app_context():
        assert DiarioTarefaTurno.query.one().status == TAREFA_TURNO_PENDENTE
        assert DiarioPendencia.query.count() == 0
    assert _avisos(app_module, cena['admin']) == []


def test_tarefa_respondida_nao_e_tocada_no_encerramento(app_module, mestre,
                                                        paulo, cena):
    _atribuir(mestre, cena)
    assert _responder(paulo, _tarefa_id(app_module),
                      resposta='-18,4 na sonda 2').status_code == 200
    _salvar(paulo, cena)
    with app_module.app.app_context():
        t = DiarioTarefaTurno.query.one()
        assert t.status == TAREFA_TURNO_FEITA
        assert t.resposta == '-18,4 na sonda 2'
        assert DiarioPendencia.query.count() == 0


def test_tarefa_de_outra_area_ou_turno_nao_e_convertida(app_module, mestre,
                                                        paulo, cena):
    """A chave é a da passagem: contrato, MODELO, dia e turno."""
    _atribuir(mestre, cena, configuracao_id=cena['almox'])
    _atribuir(mestre, cena, turno='2º Turno')
    _salvar(paulo, cena)
    with app_module.app.app_context():
        assert {t.status for t in DiarioTarefaTurno.query.all()} == {
            TAREFA_TURNO_PENDENTE}
        assert DiarioPendencia.query.count() == 0


def test_reenvio_da_fila_nao_duplica_a_conversao(app_module, mestre, paulo, cena):
    """O celular sem sinal reenvia o MESMO encerramento: nada se repete."""
    _atribuir(mestre, cena)
    assert _salvar(paulo, cena, envio_id='envio-fila-0001').status_code == 201
    r = _salvar(paulo, cena, envio_id='envio-fila-0001')
    assert r.status_code == 200 and r.get_json().get('repetido') is True
    with app_module.app.app_context():
        assert DiarioPendencia.query.count() == 1
    assert len(_avisos(app_module, cena['admin'])) == 1


# ── 1(a) e 2. A origem da pendência do "Não deu" ─────────────────────────

def test_nao_deu_antes_da_passagem_ganha_o_turno_no_encerramento(app_module,
                                                                 mestre, paulo,
                                                                 cena):
    _atribuir(mestre, cena)
    tid = _tarefa_id(app_module)
    assert _responder(paulo, tid, virou_pendencia=True,
                      resposta='câmara em manutenção').status_code == 200
    with app_module.app.app_context():
        pid = DiarioTarefaTurno.query.get(tid).pendencia_id
        # Ainda não há passagem: nasce sem turno.
        assert DiarioPendencia.query.get(pid).turno_id is None

    r = _salvar(paulo, cena)
    turno_id = r.get_json()['id']
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id == turno_id
        # Aberta por este turno: não ganha "recebida" do próprio turno.
        assert DiarioPendenciaEvento.query.filter_by(
            pendencia_id=pid, turno_id=turno_id).count() == 0

    # E aparece em "Pendências deixadas" da passagem.
    corpo = paulo.get(f'/passagem-de-turno/turno/{turno_id}').get_data(as_text=True)
    assert TAREFA in corpo
    assert 'Nenhuma pendência deixada' not in corpo


def test_nao_deu_com_rascunho_salvo_liga_na_hora(app_module, mestre, paulo, cena):
    _atribuir(mestre, cena)
    rascunho = _salvar(paulo, cena, finalizar=False).get_json()['id']
    tid = _tarefa_id(app_module)
    r = _responder(paulo, tid, virou_pendencia=True, resposta='sem sonda')
    assert r.status_code == 200
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(r.get_json()['pendencia_id']).turno_id == rascunho


def _pendencias(lista):
    return {(x['pendencia'] if isinstance(x, dict) else x).id for x in lista}


def test_nao_deu_antes_de_salvar_espera_a_passagem(app_module, mestre, paulo,
                                                   cena):
    """Sem turno, mas não é da gestão: é trabalho de uma passagem que ainda
    não saiu. Até ela encerrar, não conta no painel nem como P1 da Torre — a
    do mesmo "Não deu" respondido depois do rascunho já ficava de fora — e o
    outro modelo do contrato que encerra no meio não a "recebe"."""
    from facilities.passagem import analitico as an
    hoje = dict(cena, dia=tempo.hoje())
    _atribuir(mestre, hoje)
    pid = _responder(paulo, _tarefa_id(app_module), virou_pendencia=True,
                     resposta='câmara em manutenção').get_json()['pendencia_id']
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id is None
        assert pid not in _pendencias(an.pendencias_da_janela(cena['cid'], hoje['dia'],
                                                              hoje['dia']))
        assert pid not in _pendencias(an.criticas_e_vencidas(cena['cid']))

    # O Almoxarifado (modelo sem área: a mesma área do contrato) encerra o
    # mesmo turno antes da Expedição — e não carrega o que ela não entregou.
    _salvar(paulo, hoje, configuracao_id=cena['almox'])
    with app_module.app.app_context():
        assert DiarioPendenciaEvento.query.filter_by(pendencia_id=pid).count() == 0

    # A Expedição encerra: a pendência ganha o turno e passa a contar.
    exped = _salvar(paulo, hoje).get_json()['id']
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id == exped
        assert pid in _pendencias(an.pendencias_da_janela(cena['cid'], hoje['dia'],
                                                          hoje['dia']))
        assert pid in _pendencias(an.criticas_e_vencidas(cena['cid']))
    # E o turno seguinte a recebe.
    t2 = _salvar(paulo, hoje, turno='2º Turno').get_json()['id']
    with app_module.app.app_context():
        assert [(e.tipo, e.turno_id) for e in DiarioPendenciaEvento.query
                .filter_by(pendencia_id=pid)] == [('recebida', t2)]


def test_nao_deu_sem_passagem_vale_como_do_contrato_depois_da_espera(
        app_module, mestre, paulo, cena):
    """Se ninguém encerrar a passagem daquele turno, a pendência não pode
    sumir para sempre: passados os dias de espera, vale como a da gestão —
    conta, e qualquer passagem do contrato a recebe."""
    from app import db
    from facilities.passagem import analitico as an
    espera = an.DIAS_DE_ESPERA_DA_TAREFA
    velho = dict(cena, dia=tempo.hoje() - timedelta(days=espera + 1))
    _atribuir(mestre, velho)
    pid = _responder(paulo, _tarefa_id(app_module), virou_pendencia=True,
                     resposta='sem sonda').get_json()['pendencia_id']
    with app_module.app.app_context():
        def esperando(hoje):
            return pid in set(db.session.execute(
                an.pendencias_aguardando_passagem(cena['cid'], hoje=hoje)).scalars())
        # As bordas da espera, contadas do dia do turno da tarefa.
        assert esperando(velho['dia'] + timedelta(days=espera))
        assert not esperando(velho['dia'] + timedelta(days=espera + 1))
        assert pid in _pendencias(an.criticas_e_vencidas(cena['cid']))
    t = _salvar(paulo, dict(cena, dia=tempo.hoje()),
                configuracao_id=cena['almox']).get_json()['id']
    with app_module.app.app_context():
        assert [(e.tipo, e.turno_id) for e in DiarioPendenciaEvento.query
                .filter_by(pendencia_id=pid)] == [('recebida', t)]


def test_nao_deu_preso_a_rascunho_abandonado_volta_depois_da_espera(
        app_module, mestre, paulo, cena):
    """O "Não deu" respondido DEPOIS de "Salvar rascunho" nasce preso ao
    rascunho. Se o rascunho nunca encerra, a pendência ficava fora de todo
    indicador para sempre — enquanto o mesmo "Não deu" respondido antes do
    rascunho voltava a contar em dois dias. Agora as duas esperam o mesmo
    prazo."""
    from facilities.passagem import analitico as an
    espera = an.DIAS_DE_ESPERA_DA_TAREFA
    hoje = dict(cena, dia=tempo.hoje())
    velho = dict(cena, dia=tempo.hoje() - timedelta(days=espera + 1))
    pids = {}
    for nome, quando in (('hoje', hoje), ('velho', velho)):
        _atribuir(mestre, quando, titulo=f'{TAREFA} ({nome})')
        rascunho = _salvar(paulo, quando, finalizar=False).get_json()['id']
        with app_module.app.app_context():
            tid = DiarioTarefaTurno.query.filter_by(
                titulo=f'{TAREFA} ({nome})').one().id
        r = _responder(paulo, tid, virou_pendencia=True, resposta='sem sonda')
        pids[nome] = r.get_json()['pendencia_id']
        with app_module.app.app_context():
            assert DiarioPendencia.query.get(pids[nome]).turno_id == rascunho
    with app_module.app.app_context():
        criticas = _pendencias(an.criticas_e_vencidas(cena['cid']))
        # A de hoje ainda é trabalho de um rascunho em andamento.
        assert pids['hoje'] not in criticas
        # A de dias atrás, presa a um rascunho que ninguém encerrou, conta.
        assert pids['velho'] in criticas
    # E a passagem encerrada hoje carrega a velha, não a de hoje.
    t = _salvar(paulo, hoje, turno='2º Turno').get_json()['id']
    with app_module.app.app_context():
        recebidas = {e.pendencia_id for e in DiarioPendenciaEvento.query
                     .filter_by(turno_id=t, tipo='recebida')}
        assert pids['velho'] in recebidas
        assert pids['hoje'] not in recebidas


def test_corrigir_o_turno_liga_o_nao_deu_e_acerta_a_tarefa(app_module, mestre,
                                                           paulo, cena):
    """Encerrou como 2º Turno, corrigiu para o 1º: a passagem passa a ser a
    do 1º, e o que a gestão pediu para o 1º é acertado como no encerramento
    — o "Não deu" sem turno ganha a origem e a tarefa sem resposta vira
    pendência. Antes a correção só reescrevia o dia e o turno."""
    from facilities.passagem.models import (
        TAREFA_TURNO_VIROU_PENDENCIA)
    hoje = dict(cena, dia=tempo.hoje())
    _atribuir(mestre, hoje, titulo='Conferir a doca 5')
    _atribuir(mestre, hoje, titulo='Contar os pallets vazios')
    with app_module.app.app_context():
        nao_deu = DiarioTarefaTurno.query.filter_by(titulo='Conferir a doca 5').one().id
        muda = DiarioTarefaTurno.query.filter_by(
            titulo='Contar os pallets vazios').one().id
    pid = _responder(paulo, nao_deu, virou_pendencia=True,
                     resposta='doca interditada').get_json()['pendencia_id']
    turno = _salvar(paulo, hoje, turno='2º Turno').get_json()['id']
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id is None
        assert DiarioTarefaTurno.query.get(muda).status == TAREFA_TURNO_PENDENTE
    r = paulo.post(f'/passagem-de-turno/api/turnos/{turno}/corrigir',
                   json={'turno': '1º Turno', 'motivo': 'Era o 1º Turno.'})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id == turno
        tarefa = DiarioTarefaTurno.query.get(muda)
        assert tarefa.status == TAREFA_TURNO_VIROU_PENDENCIA
        assert DiarioPendencia.query.get(tarefa.pendencia_id).turno_id == turno
    # Corrigir só a observação não mexe em tarefa nenhuma.
    r = paulo.post(f'/passagem-de-turno/api/turnos/{turno}/corrigir',
                   json={'observacao': 'Doca 5 interditada.',
                         'motivo': 'Faltou a observação.'})
    assert r.status_code == 200


def test_correcao_que_da_a_origem_nao_conta_o_proprio_turno(app_module, mestre,
                                                           paulo, cena):
    """A passagem esquecida de dias atrás é lançada como 2º Turno: o "Não
    deu" do 1º, sem turno e já fora da espera, vale como do contrato e é
    "recebido" por ela. Corrigida para o 1º, ela passa a ser a ORIGEM da
    pendência — e quem abre não carrega: "passou por" não conta o próprio
    turno, e a trilha não diz que ele a recebeu."""
    from facilities.passagem import analitico as an
    velho = dict(cena, dia=tempo.hoje() - timedelta(days=an.DIAS_DE_ESPERA_DA_TAREFA + 1))
    _atribuir(mestre, velho)
    pid = _responder(paulo, _tarefa_id(app_module), virou_pendencia=True,
                     resposta='doca interditada').get_json()['pendencia_id']
    turno = _salvar(paulo, velho, turno='2º Turno').get_json()['id']
    with app_module.app.app_context():
        assert [(e.tipo, e.turno_id) for e in DiarioPendenciaEvento.query
                .filter_by(pendencia_id=pid)] == [('recebida', turno)]
    r = paulo.post(f'/passagem-de-turno/api/turnos/{turno}/corrigir',
                   json={'turno': '1º Turno', 'motivo': 'Era o 1º Turno.'})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        p = DiarioPendencia.query.get(pid)
        assert p.turno_id == turno
        assert an.passagens_das_pendencias([p]).get(pid, 0) == 0
        assert an._resumo_das_trilhas([pid]).get(pid, {}).get('passagens', 0) == 0
        assert [e['tipo'] for e in an.trilha_da_pendencia(pid)] == []


def test_passagem_de_outra_area_nao_adota_a_pendencia(app_module, mestre, paulo,
                                                      cena):
    """Mesmo dia e turno, outro modelo: a Expedição não é o Almoxarifado."""
    _atribuir(mestre, cena)
    _salvar(paulo, cena, finalizar=False, configuracao_id=cena['almox'])
    tid = _tarefa_id(app_module)
    r = _responder(paulo, tid, virou_pendencia=True, resposta='sem sonda')
    pid = r.get_json()['pendencia_id']
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id is None
    _salvar(paulo, cena, configuracao_id=cena['almox'])
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id is None


def test_origem_ja_gravada_nao_muda_de_dono(app_module, mestre, paulo, cena):
    """Só a pendência SEM turno é adotada no encerramento."""
    _atribuir(mestre, cena)
    tid = _tarefa_id(app_module)
    pid = _responder(paulo, tid, virou_pendencia=True,
                     resposta='sem sonda').get_json()['pendencia_id']
    with app_module.app.app_context():
        from app import db
        outro = DiarioTurno(client_id=cena['cid'], configuracao_id=cena['exped'],
                            data_turno=date(2026, 9, 24), turno='2º Turno',
                            status='encerrado', dados_json='{}',
                            created_by=cena['rita'])
        db.session.add(outro)
        db.session.flush()
        DiarioPendencia.query.get(pid).turno_id = outro.id
        db.session.commit()
        outro_id = outro.id
    _salvar(paulo, cena)
    with app_module.app.app_context():
        assert DiarioPendencia.query.get(pid).turno_id == outro_id


# ── 3. Tarefa para turno já encerrado ────────────────────────────────────

def test_tarefa_para_turno_encerrado_e_recusada(app_module, mestre, paulo, cena):
    assert _salvar(paulo, cena).status_code == 201
    r = _atribuir(mestre, cena)
    assert r.status_code == 409
    assert r.get_json()['error'] == 'Esse turno já foi encerrado — escolha outro.'
    with app_module.app.app_context():
        assert DiarioTarefaTurno.query.count() == 0
    # Recusada não avisa o piso de uma tarefa que não existe.
    assert _avisos(app_module, cena['rita']) == []


@pytest.mark.parametrize('mudanca', [
    {'configuracao_id': 'almox'},          # outra área
    {'turno': '2º Turno'},                 # outro turno
    {'data_turno': '2026-09-26'},          # outro dia
])
def test_turno_encerrado_nao_trava_outra_chave(app_module, mestre, paulo, cena,
                                               mudanca):
    _salvar(paulo, cena)
    if 'configuracao_id' in mudanca:
        mudanca = dict(mudanca, configuracao_id=cena[mudanca['configuracao_id']])
    assert _atribuir(mestre, cena, **mudanca).status_code == 201


def test_rascunho_ainda_aceita_tarefa(app_module, mestre, paulo, cena):
    """Rascunho não é encerramento: o turno ainda está acontecendo."""
    _salvar(paulo, cena, finalizar=False)
    assert _atribuir(mestre, cena).status_code == 201


# ── 4. O aviso ao piso fala "prioridade alta" ────────────────────────────

def test_aviso_ao_piso_diz_prioridade_alta_e_conta_a_tarefa(app_module, mestre,
                                                            paulo, cena):
    _atribuir(mestre, cena)
    _salvar(paulo, cena, pendencias=[
        {'titulo': 'Doca 3 sem empilhadeira', 'prioridade': 'alta'},
        {'titulo': 'Etiqueta faltando', 'prioridade': 'media'}])
    # 1 lançada + 1 da tarefa não respondida. (O outro aviso da Rita é o
    # da tarefa nova, de quando a gestão atribuiu.)
    assert _avisos_de_encerramento(app_module, cena['rita']) == [
        ('1º Turno de 25/09 encerrado com 2 pendências de prioridade alta',
         'Abra a passagem para ver o que ficou para o seu turno.')]


def test_aviso_conta_o_nao_deu_que_ficou_sem_turno(app_module, mestre, paulo, cena):
    _atribuir(mestre, cena)
    _responder(paulo, _tarefa_id(app_module), virou_pendencia=True,
               resposta='sem sonda')
    _salvar(paulo, cena)
    titulos = [a[0] for a in _avisos_de_encerramento(app_module, cena['rita'])]
    assert titulos == ['1º Turno de 25/09 encerrado com 1 pendência de prioridade alta']
    assert not any('crítica' in t for t in titulos)


# ── 6. A hora do aparelho ────────────────────────────────────────────────

def _dados(app_module, turno_id):
    with app_module.app.app_context():
        t = DiarioTurno.query.get(turno_id)
        return json.loads(t.dados_json), t.submitted_at


def test_hora_do_aparelho_e_guardada_sem_mexer_na_chegada(app_module, paulo, cena):
    tocado = datetime.utcnow() - timedelta(hours=3)
    antes = datetime.utcnow()
    r = _salvar(paulo, cena, encerrado_no_aparelho=_iso(tocado))
    assert r.status_code == 201
    dados, chegada = _dados(app_module, r.get_json()['id'])
    guardada = datetime.fromisoformat(dados['_encerrado_no_aparelho'])
    assert guardada.tzinfo is not None
    assert guardada.astimezone(timezone.utc).replace(tzinfo=None) == \
        tocado.replace(microsecond=0)
    # `submitted_at` continua sendo a hora de CHEGADA — a da auditoria.
    assert chegada >= antes.replace(microsecond=0) - timedelta(seconds=1)


@pytest.mark.parametrize('bruto', [
    'ontem de tarde',                           # não é data
    '2026-09-25T10:00:00',                      # sem fuso
    12345,                                      # nem texto é
    'FUTURO',                                   # relógio adiantado demais
    'PASSADO',                                  # relógio parado
    '0001-01-01T00:00:00+05:00',                # estoura na conversão p/ UTC
    '9999-12-31T23:59:59-05:00',                # idem, do outro lado
])
def test_hora_do_aparelho_incrivel_nao_e_guardada_e_nao_recusa(app_module, paulo,
                                                               cena, bruto):
    if bruto == 'FUTURO':
        bruto = _iso(datetime.utcnow() + timedelta(minutes=30))
    elif bruto == 'PASSADO':
        bruto = _iso(datetime.utcnow() - timedelta(hours=80))
    r = _salvar(paulo, cena, encerrado_no_aparelho=bruto)
    # O encerramento entra de qualquer jeito: relógio errado não pode
    # impedir a passagem de existir.
    assert r.status_code == 201
    dados, _ = _dados(app_module, r.get_json()['id'])
    assert '_encerrado_no_aparelho' not in dados
    assert r.get_json()['status'] == 'encerrado'


def test_hora_do_aparelho_nao_se_forja_por_dentro_dos_dados(app_module, paulo, cena):
    forjada = _iso(datetime.utcnow() - timedelta(hours=1))
    r = _salvar(paulo, cena, dados={'_encerrado_no_aparelho': forjada})
    dados, _ = _dados(app_module, r.get_json()['id'])
    assert '_encerrado_no_aparelho' not in dados


def test_rascunho_nao_guarda_hora_do_aparelho(app_module, paulo, cena):
    r = _salvar(paulo, cena, finalizar=False,
                encerrado_no_aparelho=_iso(datetime.utcnow()))
    dados, _ = _dados(app_module, r.get_json()['id'])
    assert '_encerrado_no_aparelho' not in dados


def test_a_janela_da_hora_do_aparelho():
    """As bordas: 5 min à frente e 72 h atrás da chegada; fuso é convertido."""
    from facilities.passagem.rotas import hora_do_aparelho
    chegada = datetime(2026, 9, 25, 15, 0, 0)          # UTC
    assert hora_do_aparelho('2026-09-25T15:04:00Z', chegada) == \
        '2026-09-25T15:04:00+00:00'
    assert hora_do_aparelho('2026-09-25T15:06:00Z', chegada) is None
    assert hora_do_aparelho('2026-09-22T16:00:00Z', chegada) is not None  # 71 h
    assert hora_do_aparelho('2026-09-22T14:00:00Z', chegada) is None      # 73 h
    # 09h10 em Brasília = 12h10 UTC.
    assert hora_do_aparelho('2026-09-25T09:10:00-03:00', chegada) == \
        '2026-09-25T12:10:00+00:00'
    assert hora_do_aparelho('', chegada) is None
    assert hora_do_aparelho(None, chegada) is None


def _turno_com_horas(app_module, cena, aparelho, chegada):
    """Passagem encerrada com as duas horas fixas (UTC ingênuo)."""
    with app_module.app.app_context():
        from app import db
        t = DiarioTurno(client_id=cena['cid'], configuracao_id=cena['exped'],
                        data_turno=cena['dia'], turno='1º Turno',
                        status='encerrado', created_by=cena['paulo'],
                        submitted_at=chegada,
                        dados_json=json.dumps({'_encerrado_no_aparelho':
                                               aparelho.replace(tzinfo=timezone.utc)
                                               .isoformat()}))
        db.session.add(t)
        db.session.commit()
        return t.id


def test_ver_turno_mostra_as_duas_horas_quando_a_fila_separou(app_module, paulo,
                                                              cena):
    # 06h10 e 08h42 em Brasília.
    tid = _turno_com_horas(app_module, cena, datetime(2026, 9, 25, 9, 10),
                           datetime(2026, 9, 25, 11, 42))
    corpo = paulo.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'encerrado no aparelho às 06:10' in corpo
    assert 'chegou ao sistema às 08:42' in corpo


def test_ver_turno_com_diferenca_pequena_mostra_a_linha_de_sempre(app_module,
                                                                  paulo, cena):
    chegada = datetime(2026, 9, 25, 11, 42)
    tid = _turno_com_horas(app_module, cena, chegada - timedelta(minutes=2),
                           chegada)
    corpo = paulo.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'encerrado no aparelho' not in corpo
    assert f'encerrado em {tempo.fmt(chegada)}' in corpo


def test_ver_turno_fila_que_virou_o_dia_mostra_a_data(app_module, paulo, cena):
    """22h10 de um dia e 07h05 do outro: só a hora leria ao contrário."""
    tid = _turno_com_horas(app_module, cena, datetime(2026, 9, 26, 1, 10),
                           datetime(2026, 9, 26, 10, 5))
    corpo = paulo.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'encerrado no aparelho em 25/09 às 22:10' in corpo
    assert 'chegou ao sistema em 26/09 às 07:05' in corpo


def test_encerramento_no_aparelho_sem_hora_guardada():
    from facilities.passagem.rotas import encerramento_no_aparelho
    assert encerramento_no_aparelho(SimpleNamespace(
        submitted_at=datetime(2026, 9, 25, 11, 42), dados_json='{}')) is None
    assert encerramento_no_aparelho(SimpleNamespace(
        submitted_at=None, dados_json='{}')) is None
    assert encerramento_no_aparelho(SimpleNamespace(
        submitted_at=datetime(2026, 9, 25, 11, 42),
        dados_json='{"_encerrado_no_aparelho": "lixo"}')) is None
