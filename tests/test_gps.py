"""GPS na leitura do QR (decisões do dono, 27/10/2026).

* A posição do local é marcada pela gestão no próprio local (raio padrão de
  300 m, ajustável).
* Leitura fora do raio: ACEITA, marcada "fora do local", e o supervisor do
  local recebe UM aviso por pessoa e dia. A precisão do celular conta a
  favor (GPS dentro de galpão erra).
* Sem GPS: aceita e marca "sem GPS". A coordenada da pessoa não é guardada.
* Os modelos de limpeza da biblioteca pedem foto de antes e de depois; na
  biblioteca já instalada sai uma versão nova, e as cópias não mudam.
"""
from datetime import timedelta

import pytest

from tests import fabrica
from tests.test_rotas_servico import (SEGUNDA, Arquivo, _respostas, _s, _tarefas,
                                      cena, utc)  # noqa: F401  (cena é fixture)

# Um ponto em Salvador e outro a ~1,1 km dali.
LOCAL = (-12.977749, -38.501630)
PERTO = {'lat': -12.978200, 'lng': -38.501900, 'precisao': 20}       # ~60 m
LONGE = {'lat': -12.987749, 'lng': -38.501630, 'precisao': 30}       # ~1,1 km


def test_avaliar_situacoes():
    from facilities.rotas import gps

    class Local:
        latitude, longitude, raio_gps_m = LOCAL[0], LOCAL[1], None
    assert gps.avaliar(Local, PERTO)[0] == gps.DENTRO
    situacao, dist, prec = gps.avaliar(Local, LONGE)
    assert situacao == gps.FORA and 1000 < dist < 1200 and prec == 30
    # A precisão do celular conta a favor (até 500 m): 1,1 km com 900 m de
    # erro ainda é "fora"; com raio de 800 m e erro de 400 m, "dentro".
    assert gps.avaliar(Local, dict(LONGE, precisao=900))[0] == gps.FORA
    Local.raio_gps_m = 800
    assert gps.avaliar(Local, dict(LONGE, precisao=400))[0] == gps.DENTRO
    assert gps.avaliar(Local, {'erro': 'negado'}) == (gps.SEM_GPS, None, None)
    assert gps.avaliar(Local, {'lat': 'x', 'lng': 1}) == (gps.SEM_GPS, None, None)
    Local.latitude = None
    assert gps.avaliar(Local, PERTO)[0] == gps.SEM_REFERENCIA
    assert gps.texto(gps.FORA, 1100) == 'Fora do local (1,1 km)'


def _local_com_posicao(raio=None):
    from app import db
    loc = fabrica.local()
    loc.latitude, loc.longitude, loc.raio_gps_m = LOCAL[0], LOCAL[1], raio
    db.session.flush()
    return loc


def _executar(user_id, tarefa, lido, gps_bruto, envio):
    from app import User, db
    dados = {'envio_id': envio, 'ponto': tarefa.ponto.codigo_qr, 'tarefa_id': tarefa.id,
             'respostas': _respostas(), 'sem_sinal': True, 'lido_em': lido.isoformat(),
             'concluida_em': lido.isoformat(), 'gps': gps_bruto}
    return _s().registrar_execucao(db.session.get(User, user_id), dados,
                                   {'depois': [Arquivo()]}, agora_utc=lido + timedelta(minutes=1))


def test_fora_do_local_aceita_marca_e_avisa_uma_vez(app_module, cena):
    from app import db
    from facilities.core.models import Notification
    from facilities.rotas.models import Execucao
    sup = fabrica.pessoa(app_module, 'sup.gps@trino.com', 'supervisor',
                         locais=['Shopping Centro'])
    _local_com_posicao()
    _s().gerar(SEGUNDA)
    t9, t11 = _tarefas()
    ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), LONGE, 'gps-fora-00001')
    db.session.commit()
    assert ex.gps_situacao == 'fora' and 1000 < ex.gps_distancia_m < 1200
    assert ex.gps_precisao_m == 30 and t9.status == 'concluida_no_prazo'
    ex2, _ = _executar(cena['ana'], t11, utc(SEGUNDA, '11:00'), LONGE, 'gps-fora-00002')
    db.session.commit()
    avisos = Notification.query.filter_by(user_id=sup, notification_type='gps_fora').all()
    assert [a.title for a in avisos] == ['Leitura fora do local: Ana']
    # A coordenada da pessoa não é guardada.
    cols = {c.name for c in Execucao.__table__.columns}
    assert not cols & {'latitude', 'longitude', 'lat', 'lng'}


def test_no_local_e_sem_gps(app_module, cena):
    from app import db
    from facilities.core.models import Notification
    sup = fabrica.pessoa(app_module, 'sup.gps2@trino.com', 'supervisor',
                         locais=['Shopping Centro'])
    _local_com_posicao()
    _s().gerar(SEGUNDA)
    t9, t11 = _tarefas()
    ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), PERTO, 'gps-perto-0001')
    ex2, _ = _executar(cena['ana'], t11, utc(SEGUNDA, '11:00'), {'erro': 'negado'},
                       'gps-sem-000001')
    db.session.commit()
    assert ex.gps_situacao == 'dentro' and ex.gps_distancia_m < 100
    assert ex2.gps_situacao == 'sem_gps' and ex2.gps_distancia_m is None
    assert Notification.query.filter_by(user_id=sup, notification_type='gps_fora').count() == 0


def test_chegada_fora_do_local(app_module, cena):
    from app import User, db
    from facilities.cadastros import servico
    from facilities.rotas import chegadas
    loc = _local_com_posicao()
    entrada = servico.salvar_ponto(loc, None, {'nome': 'Portaria', 'ambiente_id': cena['ambiente'],
                                               'entrada_do_local': '1'}, None)
    db.session.flush()
    c, nova = chegadas.registrar(db.session.get(User, cena['ana']), entrada,
                                 utc(SEGUNDA, '07:00'), gps_bruto=LONGE)
    assert nova and c.gps_situacao == 'fora'


def test_gestao_marca_a_posicao_e_ve_fora_do_local(app_module, cena):
    from app import db
    from facilities.core.models import Client
    loc_id = cena['local']
    db.session.commit()
    gerente = fabrica.pessoa(app_module, 'ger.gps@trino.com', 'master')
    db.session.commit()
    c = fabrica.entrar(app_module, 'ger.gps@trino.com')
    html = c.get(f'/centros/{loc_id}').get_data(as_text=True)
    assert 'Marcar a posição deste local' in html and 'posicao-local.js' in html
    r = c.post(f'/centros/{loc_id}/posicao', data={'lat': '', 'lng': '', 'raio': '300'},
               follow_redirects=True)
    assert 'Não chegou a posição do celular' in r.get_data(as_text=True)
    r = c.post(f'/centros/{loc_id}/posicao', data={'lat': str(LOCAL[0]), 'lng': str(LOCAL[1]),
                                                  'precisao': '12', 'raio': '30'},
               follow_redirects=True)
    assert 'O raio vai de 50 a 5000 metros.' in r.get_data(as_text=True)
    r = c.post(f'/centros/{loc_id}/posicao', data={'lat': str(LOCAL[0]), 'lng': str(LOCAL[1]),
                                                  'precisao': '12', 'raio': '250'})
    assert r.status_code == 302
    db.session.expire_all()
    loc = db.session.get(Client, loc_id)
    assert float(loc.latitude) == pytest.approx(LOCAL[0]) and loc.raio_gps_m == 250
    assert loc.posicao_marcada_por == gerente
    _s().gerar(SEGUNDA)
    ex, _ = _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'), LONGE, 'gps-tela-0001')
    db.session.commit()
    html = c.get(f'/rotas/locais/{loc_id}/dia?data={SEGUNDA.isoformat()}').get_data(as_text=True)
    assert 'Fora do local (1,1 km)' in html
    html = c.get(f'/rotas/execucoes/{ex.id}').get_data(as_text=True)
    assert 'Localização na leitura do QR' in html and 'Fora do local (1,1 km)' in html


def test_biblioteca_de_limpeza_pede_foto_antes_e_depois(app_module, cena):
    import json
    from app import db
    from facilities.rotas import servico
    from facilities.rotas.biblioteca_pronta import MODELOS, semear
    from facilities.rotas.models import ChecklistModelo
    # A biblioteca instalada ANTES (só com a foto de depois, no banheiro).
    nome = MODELOS[0]['nome']
    m = servico.criar_modelo(None, {'nome': nome}, None)
    servico.publicar(m, servico.normalizar_itens(MODELOS[0]['itens']),
                     {'exige_foto_depois': True}, None)
    copia = servico.copiar_da_biblioteca(m, cena['local'], None)
    db.session.flush()
    v_copia = copia.versao_atual.id
    feitos = semear(None)
    db.session.commit()
    assert f'{nome} (agora com foto de antes e de depois)' in feitos
    db.session.expire_all()
    m = db.session.get(ChecklistModelo, m.id)
    assert m.versao_atual.numero == 2
    assert m.versao_atual.exige_foto_antes and m.versao_atual.exige_foto_depois
    assert json.loads(m.versao_atual.itens_json) == json.loads(m.versoes[0].itens_json)
    # Os outros modelos nascem com as duas fotos; a cópia do local não muda.
    for dados in MODELOS[1:]:
        outro = ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                             ChecklistModelo.nome == dados['nome']).one()
        assert outro.versao_atual.exige_foto_antes and outro.versao_atual.exige_foto_depois
    assert db.session.get(ChecklistModelo, copia.id).versao_atual.id == v_copia
    # Rodar de novo não publica outra versão.
    semear(None)
    assert db.session.get(ChecklistModelo, m.id).versao_atual.numero == 2
