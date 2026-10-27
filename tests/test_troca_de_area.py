"""Troca de área no aplicativo (decisões do dono, 27/10/2026).

* O técnico pode ir a outra área antes da ordem da rota; o app pergunta o
  motivo (pedido da gestão, pedido do cliente, área mais suja, outro).
* Área da rota: a tarefa é ADIANTADA e fica concluída (no prazo), com o
  motivo. Sem motivo, continua recusada antes da janela do horário.
* Área fora da rota: atividade extra com o escopo da área e o motivo.
* A gestão vê "Adiantada" e o motivo no dia e na execução.
"""
import io
import json
import re
from datetime import timedelta

import pytest

from tests import fabrica
from tests.test_rotas_servico import (SEGUNDA, Arquivo, _png, _respostas, _s, _tarefas,
                                      cena, montar_cena, utc)  # noqa: F401  (cena é fixture)


def _adiantar(user_id, tarefa, lido, motivo=None, texto=None, envio=None):
    from app import User, db
    dados = {'envio_id': envio or f'troca-{tarefa.id}-{lido.isoformat()}',
             'ponto': tarefa.ponto.codigo_qr, 'tarefa_id': tarefa.id,
             'respostas': _respostas(), 'sem_sinal': True, 'lido_em': lido.isoformat(),
             'concluida_em': lido.isoformat()}
    if motivo:
        dados['motivo_troca'] = motivo
    if texto:
        dados['motivo_troca_texto'] = texto
    return _s().registrar_execucao(db.session.get(User, user_id), dados,
                                   {'depois': [Arquivo()]},
                                   agora_utc=lido + timedelta(minutes=1))


def test_adiantar_sem_motivo_e_recusado(app_module, cena):
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        with pytest.raises(_s().RegraDaRota) as erro:
            _adiantar(cena['ana'], t9, utc(SEGUNDA, '07:10'))
        assert erro.value.codigo == 422 and erro.value.codigo_app == 'motivo_troca'
        assert 'adiantar' in erro.value.mensagem


def test_adiantar_com_motivo_conclui_a_tarefa(app_module, cena):
    from app import db
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, PREVISTA
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9, t11 = _tarefas()
        ex, nova = _adiantar(cena['ana'], t9, utc(SEGUNDA, '07:10'), 'pedido_cliente')
        db.session.commit()
        assert nova and not ex.extra and ex.tarefa_id == t9.id
        assert t9.status == CONCLUIDA_NO_PRAZO and t11.status == PREVISTA
        assert ex.motivo_troca == 'pedido_cliente' and ex.adiantada
        # A aderência conta a adiantada como feita no prazo.
        assert _s().aderencia([t9], utc(SEGUNDA, '10:00'))[:2] == (1, 1)


@pytest.mark.parametrize('motivo,texto', [('inventado', None), ('outro', None)])
def test_motivo_invalido_ou_outro_sem_texto(app_module, cena, motivo, texto):
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        with pytest.raises(_s().RegraDaRota) as erro:
            _adiantar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '07:10'), motivo, texto)
        assert erro.value.codigo_app == 'motivo_troca'


def test_outro_com_texto_vale(app_module, cena):
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        ex, _ = _adiantar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '07:10'), 'outro',
                          'Vazamento na recepção')
        assert (ex.motivo_troca, ex.motivo_troca_texto) == ('outro', 'Vazamento na recepção')


def test_no_horario_o_motivo_nao_muda_nada(app_module, cena):
    """Dentro da janela do horário a tarefa é a da vez: não é "adiantada"."""
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        ex, _ = _adiantar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'), 'pedido_gestao')
        assert not ex.adiantada


def test_area_fora_da_rota_com_motivo(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        u = db.session.get(User, cena['ana'])
        _s().gerar(SEGUNDA)
        qr = _tarefas()[0].ponto.codigo_qr
        lido = utc(SEGUNDA, '07:30')
        ex, _ = _s().registrar_execucao(u, {
            'envio_id': 'fora-da-rota-01', 'ponto': qr, 'versao_id': cena['versao'],
            'respostas': _respostas(), 'sem_sinal': True, 'lido_em': lido.isoformat(),
            'motivo_troca': 'area_mais_suja'}, {'depois': [Arquivo()]},
            agora_utc=lido + timedelta(minutes=5))
        assert ex.extra and ex.tarefa_id is None and ex.user_id == cena['ana']
        assert ex.motivo_troca == 'area_mais_suja' and not ex.adiantada


# ── Pelo aplicativo e na tela da gestão ───────────────────────────────────

@pytest.fixture()
def montado(app_module):
    with app_module.app.app_context():
        ids = montar_cena(app_module)
    return ids


def _turno(c, qr):
    html = c.get(f'/app/turno?ponto={qr}').get_data(as_text=True)
    return json.loads(re.search(r'<script type="application/json" id="turno-dados">(.*?)</script>',
                                html, re.S).group(1))


def test_app_recebe_motivos_e_escopo_da_area(app_module, montado):
    ana = fabrica.entrar(app_module, 'ana.rota@trino.com')
    dados = _turno(ana, montado['qr'])
    assert dados['motivos_troca_ordem'] == ['pedido_gestao', 'pedido_cliente',
                                            'area_mais_suja', 'outro']
    assert dados['motivos_troca']['pedido_cliente'] == 'Pedido do cliente'
    assert dados['pontos'][montado['qr']]['escopo'] == [montado['versao']]


def test_api_pede_o_motivo_e_a_gestao_ve_a_adiantada(app_module, montado, auth_client):
    """De ponta a ponta, com o relógio de verdade: uma tarefa de hoje daqui a
    duas horas, adiantada agora pelo aplicativo."""
    from app import db
    from facilities import tempo
    from facilities.rotas.models import Rota, TarefaDia
    agora = tempo.agora()
    if agora.hour >= 21:
        pytest.skip('a tarefa "daqui a duas horas" passaria da meia-noite')
    hora = (agora + timedelta(hours=2)).strftime('%H:%M')
    with app_module.app.app_context():
        loc = fabrica.local()
        rota = _s().salvar_rota(loc, None, {'nome': 'Rota do dia', 'turno': 'T',
                                            'hora_inicio': '00:00', 'hora_fim': '23:59',
                                            'dias_semana': '1234567'})
        _s().salvar_item(rota, None, {'ponto_id': montado['ponto'],
                                      'modelo_id': montado['modelo'], 'horarios': hora})
        _s().salvar_escala(rota, {'user_id': montado['ana'], 'dias_semana': '1234567',
                                  'data_inicio': agora.date().isoformat()})
        _s().garantir_hoje([loc.id])
        db.session.commit()
        t = (TarefaDia.query.join(Rota).filter(Rota.nome == 'Rota do dia',
                                               TarefaDia.data == agora.date()).one())
        tid, qr = t.id, t.ponto.codigo_qr
    ana = fabrica.entrar(app_module, 'ana.rota@trino.com')
    selo = ana.post('/app/api/leitura', json={'ponto': qr}).get_json()['selo']
    corpo = {'envio_id': 'api-troca-0001', 'ponto': qr, 'tarefa_id': tid,
             'respostas': _respostas(), 'selo_leitura': selo}
    r = ana.post('/app/api/execucoes', data={'corpo': json.dumps(corpo),
                                             'depois': (io.BytesIO(_png()), 'd.png')},
                 content_type='multipart/form-data')
    assert r.status_code == 422 and r.get_json()['motivo'] == 'motivo_troca'
    corpo.update(envio_id='api-troca-0002', motivo_troca='pedido_gestao')
    r = ana.post('/app/api/execucoes', data={'corpo': json.dumps(corpo),
                                             'depois': (io.BytesIO(_png()), 'd.png')},
                 content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()['status'] == 'concluida_no_prazo'
    eid = r.get_json()['id']
    html = auth_client.get(f"/rotas/locais/{montado['local']}/dia").get_data(as_text=True)
    assert 'Adiantada' in html and 'Pedido da gestão' in html
    html = auth_client.get(f'/rotas/execucoes/{eid}').get_data(as_text=True)
    assert 'adiantada' in html and 'Pedido da gestão' in html
