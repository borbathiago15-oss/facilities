"""Corrigir a passagem lançada errada — sem deixar de poder provar nada.

O dilema, nas palavras do problema: "digamos que lancei a passagem de turno
errado, esse usuário poderá fazer a edição" — e, logo em seguida, "o usuário
x pode fazer sua edição mas não pode fazer no do usuário y".

As duas frases, juntas, descrevem o que o sistema NÃO fazia, nas duas
pontas ao mesmo tempo:

* passagem ENCERRADA recusava qualquer escrita, inclusive de quem a lançou —
  o engano honesto virava permanente;
* RASCUNHO aceitava escrita de qualquer um com acesso ao contrato, inclusive
  por cima do rascunho de outra pessoa, que perdia o digitado sem saber.

O que se prova aqui, com o contraexemplo de cada regra:

* o autor corrige, e a correção fica registrada com motivo — não é
  sobrescrita silenciosa;
* quem não é o autor NÃO corrige, nem sendo master (foi decisão explícita,
  tomada sabendo que o erro de quem sair da empresa fica);
* correção sem motivo é recusada;
* a janela fecha quando o turno seguinte encerra;
* a janela de um MODELO não fecha por causa de outro — Expedição e
  Almoxarifado passam turno em paralelo;
* mover a passagem para cima de outra que já existe é recusado;
* a régua congelada não se corrige: ela registra o que era exigido no dia;
* o rascunho é de quem o abriu.
"""
from datetime import date, datetime, timedelta

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities.passagem.models import (
    DiarioConfiguracao, DiarioTurno, DiarioTurnoCorrecao)


@pytest.fixture()
def cena(app_module):
    """Um contrato, dois modelos (duas áreas) e dois encarregados."""
    with app_module.app.app_context():
        from app import Client, db
        cliente = Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()

        def _pessoa(email, nome):
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
            return u

        ana = _pessoa('ana.turno@trino.com', 'Ana da Manhã')
        bento = _pessoa('bento.turno@trino.com', 'Bento da Tarde')
        db.session.flush()
        # A carteira do encarregado é a relação `clients`, como no resto da
        # casa — não um JSON solto.
        for u in (ana, bento):
            u.clients = [cliente]

        def _modelo(nome):
            c = DiarioConfiguracao.query.filter_by(
                client_id=cliente.id, nome=nome).first()
            if c is None:
                c = DiarioConfiguracao(client_id=cliente.id, nome=nome,
                                       atividades_json='[]', campos_json='[]',
                                       ativo=True)
                db.session.add(c)
            return c

        exped = _modelo('Expedição')
        almox = _modelo('Almoxarifado')
        db.session.commit()
        return {'cid': cliente.id, 'admin': admin.id, 'ana': ana.id,
                'bento': bento.id, 'exped': exped.id, 'almox': almox.id,
                'hoje': date(2026, 9, 21)}


def _passagem(app_module, cena, autor, config_id=None, turno='1º Turno',
              dia=None, quando=None, dados=None, obs='tudo certo'):
    """Uma passagem JÁ ENCERRADA — é sobre elas que a correção age."""
    import json
    from app import db
    t = DiarioTurno(client_id=cena['cid'],
                    configuracao_id=config_id or cena['exped'],
                    data_turno=dia or cena['hoje'], turno=turno,
                    status='encerrado', observacao=obs,
                    dados_json=json.dumps(dados or {'atv_dts': True}),
                    created_by=autor,
                    submitted_at=quando or datetime(2026, 9, 21, 14, 0))
    db.session.add(t)
    db.session.commit()
    return t


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


# ── O autor corrige, e fica o rastro ─────────────────────────────────────

def test_o_autor_corrige_o_turno_que_lancou_errado(app_module, cena):
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id

    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'turno': '2º Turno', 'motivo': 'lancei no turno errado'})
    assert r.status_code == 200, r.get_data(as_text=True)

    with app_module.app.app_context():
        t = DiarioTurno.query.get(tid)
        assert t.turno == '2º Turno'
        # E NÃO é sobrescrita silenciosa: o que havia antes fica guardado.
        trilha = DiarioTurnoCorrecao.query.filter_by(turno_id=tid).all()
        assert len(trilha) == 1
        assert trilha[0].motivo == 'lancei no turno errado'
        assert trilha[0].created_by == cena['ana']
        assert 'turno' in trilha[0].campos
        assert '1º Turno' in trilha[0].antes_json


def test_correcao_sem_motivo_e_recusada(app_module, cena):
    """Correção que não custa uma frase vira botão de reescrever o passado."""
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'turno': '2º Turno', 'motivo': '   '})
    assert r.status_code == 400
    with app_module.app.app_context():
        assert DiarioTurno.query.get(tid).turno == '1º Turno'


def test_correcao_que_nao_muda_nada_e_recusada(app_module, cena):
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'turno': '1º Turno', 'motivo': 'sem querer'})
    assert r.status_code == 400
    with app_module.app.app_context():
        assert DiarioTurnoCorrecao.query.filter_by(turno_id=tid).count() == 0


# ── Quem não lançou não corrige — nem o master ───────────────────────────

def test_o_colega_nao_corrige_a_passagem_de_outro(app_module, cena):
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id
    c = _cliente(app_module, 'bento.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'turno': '2º Turno', 'motivo': 'acho que está errado'})
    assert r.status_code == 403
    with app_module.app.app_context():
        assert DiarioTurno.query.get(tid).turno == '1º Turno'


def test_nem_o_master_corrige_a_passagem_de_outro(app_module, mestre, cena):
    """Decisão explícita, tomada sabendo o preço.

    O preço: se a Ana sair da empresa, o erro dela fica. O que se compra com
    ele é que o escrito na passagem foi escrito por quem a assina — e é isso
    que faz o documento valer numa discussão com o cliente.
    """
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id
    r = mestre.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
                    json={'turno': '2º Turno', 'motivo': 'arrumando'})
    assert r.status_code == 403
    with app_module.app.app_context():
        assert DiarioTurno.query.get(tid).turno == '1º Turno'


# ── A janela ─────────────────────────────────────────────────────────────

def test_a_janela_fecha_quando_o_turno_seguinte_encerra(app_module, cena):
    """Os números já alimentaram o painel; alguém já agiu em cima deles."""
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana']).id
        _passagem(app_module, cena, cena['bento'], turno='2º Turno',
                  quando=datetime(2026, 9, 21, 22, 0))
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'observacao': 'tarde demais', 'motivo': 'tarde demais'})
    assert r.status_code == 409
    assert 'turno seguinte' in r.get_json()['error']


def test_a_janela_de_um_modelo_nao_fecha_por_causa_de_outro(app_module, cena):
    """Expedição e Almoxarifado passam turno em paralelo.

    Este é o contraponto do teste acima, e nasceu do mesmo defeito que já
    mordeu o 409 do lançamento: sem o modelo na conta, o fechamento de uma
    área trancava a outra.
    """
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana'],
                        config_id=cena['exped']).id
        _passagem(app_module, cena, cena['bento'], config_id=cena['almox'],
                  quando=datetime(2026, 9, 21, 22, 0))
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'observacao': 'ainda dá', 'motivo': 'corrigindo a nota'})
    assert r.status_code == 200


# ── O que a correção não pode fazer ──────────────────────────────────────

def test_nao_da_para_mover_para_cima_de_uma_passagem_que_ja_existe(app_module,
                                                                   cena):
    """Fundir duas passagens numa linha só perderia uma delas."""
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana'], turno='1º Turno').id
        _passagem(app_module, cena, cena['ana'], turno='2º Turno',
                  dia=cena['hoje'] - timedelta(days=1))
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'turno': '2º Turno',
                     'data_turno': (cena['hoje'] - timedelta(days=1)).isoformat(),
                     'motivo': 'era esse dia'})
    assert r.status_code == 409
    assert 'Já existe passagem' in r.get_json()['error']


def test_a_regua_congelada_nao_se_corrige(app_module, cena):
    """Ela registra o que era EXIGIDO no dia.

    Reescrevê-la mudaria a nota de aderência do turno sem que ninguém
    tivesse feito nada diferente — seria corrigir a prova, não o registro.
    """
    import json
    from facilities.passagem import analitico as an
    with app_module.app.app_context():
        tid = _passagem(app_module, cena, cena['ana'],
                        dados={an.CHAVE_EXIGIDAS: ['dts', 'cinco_s'],
                               'atv_dts': True}).id
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'dados': {an.CHAVE_EXIGIDAS: [], 'atv_dts': False},
                     'motivo': 'marquei errado o DTS'})
    assert r.status_code == 200
    with app_module.app.app_context():
        dados = json.loads(DiarioTurno.query.get(tid).dados_json)
        # A resposta mudou…
        assert dados['atv_dts'] is False
        # …e a régua, não.
        assert dados[an.CHAVE_EXIGIDAS] == ['dts', 'cinco_s']


def test_rascunho_nao_entra_pela_correcao(app_module, cena):
    """Rascunho se edita normalmente — a correção é para o que fechou."""
    with app_module.app.app_context():
        from app import db
        t = DiarioTurno(client_id=cena['cid'], configuracao_id=cena['exped'],
                        data_turno=cena['hoje'], turno='3º Turno',
                        status='aberto', dados_json='{}',
                        created_by=cena['ana'])
        db.session.add(t)
        db.session.commit()
        tid = t.id
    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post(f'/passagem-de-turno/api/turnos/{tid}/corrigir',
               json={'observacao': 'x', 'motivo': 'y'})
    assert r.status_code == 409
    assert 'rascunho' in r.get_json()['error']


# ── O rascunho é de quem o abriu ─────────────────────────────────────────

def test_ninguem_salva_por_cima_do_rascunho_alheio(app_module, cena):
    """Antes disto o dono perdia o digitado sem nunca saber por quê."""
    with app_module.app.app_context():
        from app import db
        t = DiarioTurno(client_id=cena['cid'], configuracao_id=cena['exped'],
                        data_turno=cena['hoje'], turno='1º Turno',
                        status='aberto', dados_json='{"atv_dts": true}',
                        observacao='a Ana estava escrevendo',
                        created_by=cena['ana'])
        db.session.add(t)
        db.session.commit()
        tid = t.id

    c = _cliente(app_module, 'bento.turno@trino.com')
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['cid'], 'configuracao_id': cena['exped'],
        'data_turno': cena['hoje'].isoformat(), 'turno': '1º Turno',
        'dados': {}, 'observacao': 'apaguei tudo'})
    assert r.status_code == 403
    assert 'Ana' in r.get_json()['error']
    with app_module.app.app_context():
        assert DiarioTurno.query.get(tid).observacao == 'a Ana estava escrevendo'


def test_o_dono_continua_salvando_o_proprio_rascunho(app_module, cena):
    """O contraponto: a regra não pode travar quem está trabalhando."""
    with app_module.app.app_context():
        from app import db
        t = DiarioTurno(client_id=cena['cid'], configuracao_id=cena['exped'],
                        data_turno=cena['hoje'], turno='1º Turno',
                        status='aberto', dados_json='{}',
                        created_by=cena['ana'])
        db.session.add(t)
        db.session.commit()
        tid = t.id

    c = _cliente(app_module, 'ana.turno@trino.com')
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['cid'], 'configuracao_id': cena['exped'],
        'data_turno': cena['hoje'].isoformat(), 'turno': '1º Turno',
        'dados': {'atv_dts': True}, 'observacao': 'continuando'})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    with app_module.app.app_context():
        assert DiarioTurno.query.get(tid).observacao == 'continuando'
