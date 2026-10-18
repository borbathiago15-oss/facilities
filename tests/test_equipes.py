"""Fase 6 — equipe do posto: funcionários, escala sem sobreposição, presença
lançada pelo supervisor e cobertura de falta que reescala a rota.

O caso: no Shopping Centro, a Ana (com login) e a Mariana (sem login) são
ASG do posto "Limpeza 2º andar — manhã", que executa a rota da manhã. A Ana
falta; a Mariana cobre por atestado; as tarefas da rota passam para ela.
"""
from datetime import time, timedelta

import pytest

from facilities import tempo
from tests import fabrica

TODOS = '1234567'


@pytest.fixture()
def cena(app_module):
    from app import User, db
    from facilities.equipes import servico as eq
    from facilities.rotas import servico as rotas
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['ana_u'] = fabrica.pessoa(app_module, 'ana.eq@trino.com', 'encarregado',
                                      locais=['Shopping Centro'], nome='Ana')
        ids['bia_u'] = fabrica.pessoa(app_module, 'bia.eq@trino.com', 'encarregado',
                                      locais=['Shopping Centro'], nome='Bia')
        ids['sup'] = fabrica.pessoa(app_module, 'sup.eq@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.eq@trino.com', 'pleno',
                                      locais=['Shopping Centro'])
        ids['sup_fora'] = fabrica.pessoa(app_module, 'sup.fora.eq@trino.com', 'supervisor',
                                         locais=['Hospital Norte'])
        coord = db.session.get(User, ids['coord'])
        m = rotas.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        rotas.publicar(m, rotas.normalizar_itens([{'texto': 'Limpo?', 'tipo': 'sim_nao'}]),
                       {}, None)
        rota = rotas.salvar_rota(loc, None, {'nome': 'Manhã', 'turno': '1º Turno',
                                             'hora_inicio': '00:00', 'hora_fim': '23:59',
                                             'tolerancia_min': '60', 'dias_semana': TODOS,
                                             'presencas_por_turno': '2'})
        rotas.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                       'horarios': '08:00, 12:00, 20:00'})
        rotas.salvar_escala(rota, {'user_id': ids['ana_u'], 'dias_semana': TODOS,
                                   'data_inicio': (tempo.hoje() - timedelta(days=30))
                                   .isoformat()})
        ana = eq.salvar_funcionario(loc, None, {'nome': 'Ana', 'funcao': 'ASG',
                                                'user_id': str(ids['ana_u'])}, coord)
        mariana = eq.salvar_funcionario(loc, None, {'nome': 'Mariana', 'funcao': 'ASG'}, coord)
        bia = eq.salvar_funcionario(loc, None, {'nome': 'Bia', 'user_id': str(ids['bia_u'])},
                                    coord)
        posto = eq.salvar_posto(loc, None, {'nome': 'Limpeza 2º andar — manhã',
                                            'hora_inicio': '07:00', 'hora_fim': '15:00',
                                            'rota_id': str(rota.id)})
        esc = eq.salvar_escala(loc, {'funcionario_id': ana.id, 'posto_id': posto.id,
                                     'dias_semana': TODOS,
                                     'data_inicio': (tempo.hoje() - timedelta(days=30))
                                     .isoformat()}, coord)
        db.session.commit()
        ids.update(rota=rota.id, ana=ana.id, mariana=mariana.id, bia=bia.id, posto=posto.id,
                   escala=esc.id)
    return ids


def _u(uid):
    from app import User, db
    return db.session.get(User, uid)


# ── Sobreposição (regra pura) ─────────────────────────────────────────────

@pytest.mark.parametrize('a, b, cruza', [
    (('12345', '07:00', '15:00'), ('12345', '14:00', '22:00'), True),
    (('12345', '07:00', '15:00'), ('12345', '15:00', '23:00'), False),   # encosta, não cruza
    (('1', '07:00', '15:00'), ('2', '07:00', '15:00'), False),
    (('1', '22:00', '06:00'), ('2', '05:00', '12:00'), True),            # noite invade a terça
    (('7', '22:00', '06:00'), ('1', '05:00', '12:00'), True),            # domingo → segunda
    (('7', '22:00', '06:00'), ('1', '06:00', '12:00'), False),
])
def test_sobreposicao_semanal(a, b, cruza):
    from facilities.equipes.servico import se_sobrepoem

    def h(x):
        return time(*map(int, x.split(':')))
    assert se_sobrepoem(a[0], h(a[1]), h(a[2]), b[0], h(b[1]), h(b[2])) is cruza


# ── Cadastro e escala ─────────────────────────────────────────────────────

def test_login_do_funcionario_e_unico_e_do_local(app_module, cena):
    from facilities.equipes import servico as eq
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        loc = fabrica.local()
        with pytest.raises(RegraDaEquipe, match='já está ligado'):
            eq.salvar_funcionario(loc, None, {'nome': 'Outra', 'user_id': str(cena['ana_u'])},
                                  None)
        with pytest.raises(RegraDaEquipe, match='não atende'):
            eq.salvar_funcionario(loc, None, {'nome': 'Outra', 'user_id': str(cena['sup_fora'])},
                                  None)
        with pytest.raises(RegraDaEquipe, match='nome'):
            eq.salvar_funcionario(loc, None, {'nome': ' '}, None)


def test_escala_nao_poe_a_pessoa_em_dois_postos_ao_mesmo_tempo(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.equipes.models import EscalaTrabalho
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        loc = fabrica.local()
        tarde = eq.salvar_posto(loc, None, {'nome': 'Recepção tarde', 'hora_inicio': '14:00',
                                            'hora_fim': '22:00'})
        noite = eq.salvar_posto(loc, None, {'nome': 'Noite', 'hora_inicio': '15:00',
                                            'hora_fim': '23:00'})
        with pytest.raises(RegraDaEquipe, match='dois postos') as e:
            eq.salvar_escala(loc, {'funcionario_id': cena['ana'], 'posto_id': tarde.id,
                                   'dias_semana': '1'}, None)
        assert e.value.codigo == 409
        # Encostar não é cruzar; outra pessoa no mesmo horário também pode.
        eq.salvar_escala(loc, {'funcionario_id': cena['ana'], 'posto_id': noite.id,
                               'dias_semana': '1'}, None)
        eq.salvar_escala(loc, {'funcionario_id': cena['mariana'], 'posto_id': tarde.id,
                               'dias_semana': '1'}, None)
        # Escala encerrada antes não conflita mais.
        antiga = db.session.get(EscalaTrabalho, cena['escala'])
        eq.encerrar_escala(antiga, tempo.hoje() - timedelta(days=1))
        eq.salvar_escala(loc, {'funcionario_id': cena['ana'], 'posto_id': tarde.id,
                               'dias_semana': '2',
                               'data_inicio': (tempo.hoje() + timedelta(days=2)).isoformat()},
                         None)
        db.session.commit()


def test_mudar_horario_do_posto_confere_as_escalas(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.equipes.models import Posto
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        loc = fabrica.local()
        tarde = eq.salvar_posto(loc, None, {'nome': 'Tarde', 'hora_inicio': '16:00',
                                            'hora_fim': '22:00'})
        eq.salvar_escala(loc, {'funcionario_id': cena['ana'], 'posto_id': tarde.id,
                               'dias_semana': TODOS}, None)
        db.session.commit()
        with pytest.raises(RegraDaEquipe, match='dois postos'):
            eq.salvar_posto(loc, db.session.get(Posto, cena['posto']),
                            {'nome': 'Limpeza 2º andar — manhã', 'hora_inicio': '07:00',
                             'hora_fim': '17:00'})


# ── Presença ──────────────────────────────────────────────────────────────

def _escala():
    from facilities.equipes.models import EscalaTrabalho
    return EscalaTrabalho.query.first()


def test_presenca_so_supervisor_ou_gestao_do_local(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        e = _escala()
        hoje = tempo.hoje()
        for uid in (cena['ana_u'], cena['sup_fora']):
            with pytest.raises(RegraDaEquipe) as erro:
                eq.registrar_presenca(_u(uid), e, hoje, 'veio')
            assert erro.value.codigo == 403
        with pytest.raises(RegraDaEquipe, match='antes'):
            eq.registrar_presenca(_u(cena['sup']), e, hoje + timedelta(days=1), 'veio')
        with pytest.raises(RegraDaEquipe, match='últimos'):
            eq.registrar_presenca(_u(cena['sup']), e, hoje - timedelta(days=8), 'veio')
        with pytest.raises(RegraDaEquipe, match='veio, faltou'):
            eq.registrar_presenca(_u(cena['sup']), e, hoje, 'chegou_cedo')
        p = eq.registrar_presenca(_u(cena['sup']), e, hoje, 'atrasou', 'ônibus')
        p2 = eq.registrar_presenca(_u(cena['coord']), e, hoje, 'veio')
        db.session.commit()
        assert p.id == p2.id and p2.situacao == 'veio' and p2.registrada_por == cena['coord']


def test_quem_nao_esta_escalado_no_dia_nao_recebe_presenca(app_module, cena):
    from facilities.equipes import servico as eq
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        e = _escala()
        e.dias_semana = str((tempo.hoje() + timedelta(days=1)).isoweekday())
        with pytest.raises(RegraDaEquipe, match='não está escalado'):
            eq.registrar_presenca(_u(cena['sup']), e, tempo.hoje(), 'veio')


def test_falta_dispensa_o_pedido_de_presenca_aleatoria(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.rotas import servico as rotas
    from facilities.rotas.models import ConfirmacaoPresenca
    with app_module.app.app_context():
        hoje = tempo.hoje()
        # Começo do dia: os pedidos de presença ainda estão todos no futuro
        # (horário que já passou não vira pedido).
        cedo = tempo.para_utc(hoje, time(0, 0))
        rotas.gerar(hoje, [cena['local']], agora_utc=cedo)
        db.session.commit()
        pedidos = ConfirmacaoPresenca.query.filter_by(user_id=cena['ana_u'], data=hoje).all()
        assert len(pedidos) == 2
        eq.registrar_presenca(_u(cena['sup']), _escala(), hoje, 'faltou')
        db.session.commit()
        assert {c.status for c in pedidos} == {'dispensada'}


# ── Cobertura ─────────────────────────────────────────────────────────────

def _tarefas(uid=None, data=None):
    from facilities.rotas.models import TarefaDia
    q = TarefaDia.query.filter_by(data=data or tempo.hoje())
    return [t for t in q.all() if uid is None or t.user_id == uid]


def test_cobertura_passa_as_tarefas_da_rota_para_quem_cobriu(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.equipes.servico import RegraDaEquipe
    from facilities.rotas import servico as rotas
    from facilities.rotas.models import ConfirmacaoPresenca
    with app_module.app.app_context():
        hoje = tempo.hoje()
        # Começo do dia: os pedidos de presença ainda estão todos no futuro
        # (horário que já passou não vira pedido).
        cedo = tempo.para_utc(hoje, time(0, 0))
        rotas.gerar(hoje, [cena['local']], agora_utc=cedo)
        db.session.commit()
        assert len(_tarefas(cena['ana_u'])) == 3
        sup = _u(cena['sup'])
        p = eq.registrar_presenca(sup, _escala(), hoje, 'veio')
        with pytest.raises(RegraDaEquipe, match='só para falta'):
            eq.registrar_cobertura(sup, p, {'funcionario_id': cena['bia'], 'motivo': 'x'})
        p = eq.registrar_presenca(sup, _escala(), hoje, 'faltou')
        with pytest.raises(RegraDaEquipe, match='motivo'):
            eq.registrar_cobertura(sup, p, {'funcionario_id': cena['bia'], 'motivo': ''})
        with pytest.raises(RegraDaEquipe, match='própria falta'):
            eq.registrar_cobertura(sup, p, {'funcionario_id': cena['ana'], 'motivo': 'atestado'})
        c, passadas = eq.registrar_cobertura(sup, p, {'funcionario_id': cena['bia'],
                                                      'motivo': 'atestado médico'},
                                             agora_utc=cedo)
        db.session.commit()
        assert passadas == 3
        assert len(_tarefas(cena['bia_u'])) == 3 and not _tarefas(cena['ana_u'])
        # A Bia passa a receber os pedidos de presença da rota.
        assert ConfirmacaoPresenca.query.filter_by(user_id=cena['bia_u'], data=hoje,
                                                   status='pendente').count() == 2
        # Gerar de novo não devolve nada para a Ana.
        rotas.gerar(hoje, [cena['local']], agora_utc=cedo)
        db.session.commit()
        assert not _tarefas(cena['ana_u'])
        # Com cobertura, a falta não vira "veio" sem a gestão corrigir.
        with pytest.raises(RegraDaEquipe, match='já tem cobertura'):
            eq.registrar_presenca(sup, _escala(), hoje, 'veio')
        with pytest.raises(RegraDaEquipe, match='já foi coberta'):
            eq.registrar_cobertura(sup, p, {'funcionario_id': cena['mariana'],
                                            'motivo': 'troca'})


def test_cobertura_por_quem_nao_usa_o_app_deixa_as_tarefas_sem_escalado(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.rotas import servico as rotas
    with app_module.app.app_context():
        hoje = tempo.hoje()
        rotas.gerar(hoje, [cena['local']])
        sup = _u(cena['sup'])
        p = eq.registrar_presenca(sup, _escala(), hoje, 'faltou')
        _c, passadas = eq.registrar_cobertura(sup, p, {'funcionario_id': cena['mariana'],
                                                       'motivo': 'folga trocada'})
        db.session.commit()
        assert passadas == 3 and len(_tarefas()) == 3
        assert all(t.user_id is None for t in _tarefas())


def test_cobertura_antes_da_rodada_gera_ja_com_quem_cobre(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.rotas import servico as rotas
    with app_module.app.app_context():
        hoje = tempo.hoje()
        sup = _u(cena['sup'])
        p = eq.registrar_presenca(sup, _escala(), hoje, 'faltou')
        eq.registrar_cobertura(sup, p, {'funcionario_id': cena['bia'], 'motivo': 'atestado'})
        db.session.commit()
        rotas.gerar(hoje, [cena['local']])
        db.session.commit()
        assert len(_tarefas(cena['bia_u'])) == 3


def test_quem_tambem_faltou_nao_cobre(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    from facilities.equipes.servico import RegraDaEquipe
    with app_module.app.app_context():
        loc = fabrica.local()
        hoje = tempo.hoje()
        tarde = eq.salvar_posto(loc, None, {'nome': 'Tarde', 'hora_inicio': '15:00',
                                            'hora_fim': '23:00'})
        eb = eq.salvar_escala(loc, {'funcionario_id': cena['bia'], 'posto_id': tarde.id,
                                    'dias_semana': TODOS,
                                    'data_inicio': hoje.isoformat()}, None)
        sup = _u(cena['sup'])
        eq.registrar_presenca(sup, eb, hoje, 'faltou')
        p = eq.registrar_presenca(sup, _escala(), hoje, 'faltou')
        db.session.commit()
        with pytest.raises(RegraDaEquipe, match='também está com falta'):
            eq.registrar_cobertura(sup, p, {'funcionario_id': cena['bia'], 'motivo': 'atestado'})


# ── Mês ───────────────────────────────────────────────────────────────────

def test_mes_mostra_previsto_lancado_e_faltas(app_module, cena):
    from app import db
    from facilities.equipes import servico as eq
    with app_module.app.app_context():
        hoje = tempo.hoje()
        sup = _u(cena['sup'])
        p = eq.registrar_presenca(sup, _escala(), hoje, 'faltou')
        eq.registrar_cobertura(sup, p, {'funcionario_id': cena['mariana'], 'motivo': 'atestado'})
        db.session.commit()
        g = eq.mes(cena['local'], hoje.year, hoje.month)
        assert len(g['linhas']) == 1
        assert g['totais']['previstos'] == hoje.day
        assert g['totais']['lancados'] == 1
        assert g['totais']['faltas'] == 1 and g['totais']['cobertas'] == 1
        celula = g['linhas'][0]['celulas'][hoje.day - 1]
        assert celula['presenca'].cobertura is not None


# ── Telas ─────────────────────────────────────────────────────────────────

def test_gestao_cadastra_supervisor_so_ve(app_module, cena):
    cid = cena['local']
    coord = fabrica.entrar(app_module, 'coord.eq@trino.com')
    r = coord.post(f'/equipes/locais/{cid}/funcionarios', data={'nome': 'Carla', 'funcao': 'ASG'})
    assert r.status_code == 302
    assert 'Carla' in coord.get(f'/equipes/locais/{cid}').get_data(as_text=True)
    assert coord.get(f'/equipes/locais/{cid}/mes').status_code == 200
    sup = fabrica.entrar(app_module, 'sup.eq@trino.com')
    assert sup.get(f'/equipes/locais/{cid}').status_code == 200
    assert sup.post(f'/equipes/locais/{cid}/funcionarios',
                    data={'nome': 'Invasão'}).status_code == 403
    fora = fabrica.entrar(app_module, 'sup.fora.eq@trino.com')
    assert fora.get(f'/equipes/locais/{cid}').status_code == 403


def test_app_supervisor_lanca_falta_e_cobertura(app_module, cena):
    from facilities.equipes.models import Presenca
    sup = fabrica.entrar(app_module, 'sup.eq@trino.com')
    html = sup.get('/app/equipe').get_data(as_text=True)
    assert 'Ana' in html and 'Limpeza 2º andar' in html
    r = sup.post('/app/equipe/presenca', data={'escala_id': cena['escala'],
                                               'situacao': 'faltou'})
    assert r.status_code == 302
    with app_module.app.app_context():
        pid = Presenca.query.one().id
    assert 'Alguém cobriu' in sup.get('/app/equipe').get_data(as_text=True)
    r = sup.post(f'/app/equipe/presencas/{pid}/cobertura',
                 data={'funcionario_id': cena['mariana'], 'motivo': 'atestado'},
                 follow_redirects=True)
    assert 'Cobertura registrada: Mariana' in r.get_data(as_text=True)
    ana = fabrica.entrar(app_module, 'ana.eq@trino.com')
    assert ana.get('/app/equipe').status_code == 403
    assert ana.post('/app/equipe/presenca', data={'escala_id': cena['escala'],
                                                  'situacao': 'veio'}).status_code == 403
    fora = fabrica.entrar(app_module, 'sup.fora.eq@trino.com')
    assert 'Ana' not in fora.get('/app/equipe').get_data(as_text=True)
    assert fora.post('/app/equipe/presenca', data={'escala_id': cena['escala'],
                                                   'situacao': 'veio'}).status_code == 403
