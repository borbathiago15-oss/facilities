"""Fase 4B — confirmação de presença em horário aleatório (D48, Q4) e o
aviso da hora da tarefa.

* 2 pedidos por turno (padrão), sorteados longe do começo e do fim; rodar
  o agendador de novo dá os mesmos horários; 0 desliga;
* chegou a hora: aviso no sino e no celular; confirmou no prazo:
  confirmada (hora do servidor); passou do prazo: "sem resposta" e o
  superior direto é avisado;
* a tarefa da rota avisa o celular de quem está escalado, uma vez só.
"""
from datetime import date, timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import utc

SEGUNDA = date(2026, 10, 19)


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['sup'] = fabrica.pessoa(app_module, 'sup.pres@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['ana'] = fabrica.pessoa(app_module, 'ana.pres@trino.com', 'encarregado',
                                    locais=['Shopping Centro'], superior_id=ids['sup'])
        m = s.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Ok?'}]), {}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'Limpeza T1', 'turno': '1º Turno',
                                         'hora_inicio': '07:00', 'hora_fim': '15:00',
                                         'dias_semana': '12345'})
        s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                   'horarios': '09:00'})
        s.salvar_escala(rota, {'user_id': ids['ana'], 'dias_semana': '12345',
                               'data_inicio': '2026-10-01'})
        db.session.commit()
        ids['rota'] = rota.id
    return ids


def _pedidos():
    from facilities.rotas.models import ConfirmacaoPresenca
    return ConfirmacaoPresenca.query.order_by(ConfirmacaoPresenca.pedido_em).all()


def test_dois_pedidos_sorteados_dentro_do_turno_e_sem_duplicar(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        s.gerar(SEGUNDA)
        s.gerar(SEGUNDA)
        db.session.commit()
        p = _pedidos()
        assert len(p) == 2 and {x.user_id for x in p} == {cena['ana']}
        horas = [tempo.local(x.pedido_em) for x in p]
        assert all(h.hour * 60 + h.minute >= 7 * 60 + 30 for h in horas)
        assert all(h.hour * 60 + h.minute <= 15 * 60 - 40 for h in horas)
        assert all((x.prazo_ate - x.pedido_em) == timedelta(minutes=10) for x in p)
        # Outro dia, outro sorteio.
        s.gerar(SEGUNDA + timedelta(days=1))
        db.session.commit()
        terca = [tempo.local(x.pedido_em).time() for x in _pedidos()[2:]]
        assert terca != [h.time() for h in horas]


def test_zero_desliga(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        rota = db.session.get(Rota, cena['rota'])
        s.salvar_rota(rota.local, rota, {'nome': rota.nome, 'turno': rota.turno,
                                         'hora_inicio': '07:00', 'hora_fim': '15:00',
                                         'dias_semana': '12345', 'presencas_por_turno': '0'})
        s.gerar(SEGUNDA)
        assert _pedidos() == []
        with pytest.raises(s.RegraDaRota, match='de 0 a 6'):
            s.salvar_rota(rota.local, rota, {'nome': rota.nome, 'turno': rota.turno,
                                             'hora_inicio': '07:00', 'hora_fim': '15:00',
                                             'dias_semana': '12345', 'presencas_por_turno': '9'})


def test_aviso_confirmacao_e_sem_resposta(app_module, cena):
    from app import User, db
    from facilities.core.models import Notification
    from facilities.rotas import presenca, servico as s
    enviados = []
    app_module.app.extensions['facilities_push'] = \
        lambda insc, carga: enviados.append((insc.user_id, carga['titulo'])) or 201
    with app_module.app.app_context():
        from tests.test_push import _celular
        from facilities.core import push
        _r, d, _a = _celular()
        push.inscrever(db.session.get(User, cena['ana']), d)
        s.gerar(SEGUNDA)
        db.session.commit()
        p1, p2 = _pedidos()
        presenca.avisar_e_fechar(p1.pedido_em + timedelta(minutes=1))
        db.session.commit()
        assert (cena['ana'], 'Confirme que você está no posto') in enviados
        assert Notification.query.filter_by(user_id=cena['ana'],
                                            notification_type='presenca').count() == 1
        # Rodar de novo não repete o aviso.
        presenca.avisar_e_fechar(p1.pedido_em + timedelta(minutes=2))
        assert len([e for e in enviados if e[0] == cena['ana']]) == 1
        ana = db.session.get(User, cena['ana'])
        presenca.confirmar(p1, ana, p1.pedido_em + timedelta(minutes=5))
        db.session.commit()
        assert p1.status == 'confirmada'
        # O segundo vence sem resposta: o superior (a supervisora) é avisado.
        presenca.avisar_e_fechar(p2.prazo_ate + timedelta(minutes=1))
        db.session.commit()
        assert p2.status == 'sem_resposta'
        alertas = Notification.query.filter_by(user_id=cena['sup'],
                                               title='Presença sem resposta').all()
        assert len(alertas) == 1 and 'não confirmou' in alertas[0].message
        # Responder depois do prazo fica registrado, mas continua sem resposta.
        presenca.confirmar(p2, ana, p2.prazo_ate + timedelta(minutes=3))
        assert p2.status == 'sem_resposta' and p2.respondida_em


def test_pela_api_so_a_propria_pessoa_confirma(app_module, cena):
    from app import db
    from facilities.rotas.models import ConfirmacaoPresenca, Rota
    from datetime import datetime
    with app_module.app.app_context():
        rota = db.session.get(Rota, cena['rota'])
        agora = datetime.utcnow()
        c = ConfirmacaoPresenca(rota_id=rota.id, client_id=rota.client_id, user_id=cena['ana'],
                                data=tempo.hoje(), pedido_em=agora - timedelta(minutes=1),
                                prazo_ate=agora + timedelta(minutes=9))
        db.session.add(c)
        db.session.commit()
        cid = c.id
    sup = fabrica.entrar(app_module, 'sup.pres@trino.com')
    assert sup.post(f'/app/api/presenca/{cid}').status_code == 403
    ana = fabrica.entrar(app_module, 'ana.pres@trino.com')
    assert ana.get('/app/api/presenca').get_json()['pedido']['id'] == cid
    r = ana.post(f'/app/api/presenca/{cid}')
    assert r.status_code == 200 and r.get_json()['status'] == 'confirmada'
    assert ana.get('/app/api/presenca').get_json()['pedido'] is None


def test_aviso_da_hora_da_tarefa_uma_vez(app_module, cena):
    from app import User, db
    from facilities.rotas import servico as s
    enviados = []
    app_module.app.extensions['facilities_push'] = \
        lambda insc, carga: enviados.append(carga) or 201
    with app_module.app.app_context():
        from tests.test_push import _celular
        from facilities.core import push
        _r, d, _a = _celular()
        push.inscrever(db.session.get(User, cena['ana']), d)
        s.gerar(SEGUNDA)
        db.session.commit()
        assert s.avisar_tarefas(utc(SEGUNDA, '08:50')) == 0
        assert s.avisar_tarefas(utc(SEGUNDA, '08:59')) == 1
        assert s.avisar_tarefas(utc(SEGUNDA, '09:05')) == 0
        assert enviados[0]['titulo'].startswith('09:00') and '/app/turno?ponto=' in enviados[0]['link']


def test_rodada_completa_do_agendador(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        reg = s.rodar(agora_utc=utc(SEGUNDA, '06:00'))
        db.session.commit()
        assert reg.ok and len(_pedidos()) == 4          # segunda e terça, 2 cada
