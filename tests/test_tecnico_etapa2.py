"""Bloco do técnico, etapa 2 (decisões do dono, 22/10/2026): o que as TELAS
recebem do servidor.

* ``/app/``: um cartão por local da carteira — "ler o QR da entrada" quando
  o local tem entrada e a pessoa ainda não chegou; "Você está no …" depois
  da chegada; direto ao turno quando o local não tem entrada.
* ``/app/turno``: o JSON traz os locais (entrada e chegada de hoje), o
  ``local_id`` e a marca de entrada dos pontos, e o tempo previsto das
  tarefas — o que o aplicativo usa para abrir a tela certa, também sem sinal.
* ``/app/api/materiais?local=``: o catálogo para o "Faltou material".
* ``/q/<código>``: "É aqui?", os itens do checklist como problemas, e o POST
  sem tipo grava o tipo "itens" com os itens marcados (só texto: "outro").
"""
import json
import re

from tests import fabrica
from tests.test_tecnico_etapa1 import _entrada
from tests.test_rotas_servico import montar_cena


def _cena(app_module):
    with app_module.app.app_context():
        return montar_cena(app_module)


def _dados_do_turno(c, url='/app/turno'):
    html = c.get(url).get_data(as_text=True)
    return json.loads(re.search(r'<script type="application/json" id="turno-dados">(.*?)</script>',
                                html, re.S).group(1))


def test_inicio_mostra_um_cartao_por_local(app_module):
    cena = _cena(app_module)
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')
    html = c.get('/app/').get_data(as_text=True)
    # Sem ponto de entrada: o turno abre direto.
    assert re.search(r'data-local="%d" data-situacao="sem_entrada"' % cena['local'], html)
    assert 'Ver o turno' in html and 'Ler o QR da entrada' not in html
    assert f'/app/turno?local={cena["local"]}' in html
    assert 'Meu turno (tarefas da rota)' not in html
    with app_module.app.app_context():
        entrada = _entrada(app_module, cena)
        qr_entrada = entrada.codigo_qr
    html = c.get('/app/').get_data(as_text=True)
    assert re.search(r'data-local="%d" data-situacao="sem_chegada"' % cena['local'], html)
    assert 'Ler o QR da entrada' in html and 'leia o QR da entrada (Portaria)' in html
    assert 'Você está no' not in html
    # Chegou: o cartão diz a hora e leva ao turno.
    r = c.post('/app/api/chegada', json={'ponto': qr_entrada})
    assert r.status_code == 201
    html = c.get('/app/').get_data(as_text=True)
    assert re.search(r'data-local="%d" data-situacao="chegou"' % cena['local'], html)
    assert 'Você está no Shopping Centro' in html
    assert f'Chegou às {r.get_json()["chegada"]["hora"]}' in html


def test_turno_leva_os_locais_as_entradas_e_o_tempo_previsto(app_module):
    cena = _cena(app_module)
    from app import db
    from facilities.rotas.models import RotaItem
    with app_module.app.app_context():
        db.session.get(RotaItem, cena['item']).tempo_previsto_min = 30
        db.session.commit()
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')
    dados = _dados_do_turno(c)
    assert dados['locais'] == [{'id': cena['local'], 'nome': 'Shopping Centro', 'entrada': None,
                                'entrada_nome': None, 'chegada': None}]
    assert dados['pontos'][cena['qr']]['local_id'] == cena['local']
    assert dados['pontos'][cena['qr']]['entrada'] is False
    for t in dados['tarefas']:
        assert t['local_id'] == cena['local'] and t['tempo_previsto_min'] == 30
    assert dados['motivos_nao_feito']['faltou_material'] == 'Faltou material'
    assert 'entradas' not in dados
    with app_module.app.app_context():
        entrada = _entrada(app_module, cena)
        qr_entrada = entrada.codigo_qr
    c.post('/app/api/chegada', json={'ponto': qr_entrada})
    dados = _dados_do_turno(c, f'/app/turno?local={cena["local"]}')
    local = dados['locais'][0]
    assert local['entrada'] == qr_entrada and local['entrada_nome'] == 'Portaria'
    assert local['chegada'] and re.match(r'\d\d:\d\d$', local['chegada']['hora'])
    assert dados['pontos'][qr_entrada]['entrada'] is True
    # A tela tem o endereço do leitor para o botão "Ler o QR".
    html = c.get('/app/turno').get_data(as_text=True)
    assert 'id="turno-app" data-ler-qr="/app/ler-qr"' in html
    assert 'js/rotas-turno.js' in html


def test_api_de_materiais_do_local(app_module):
    cena = _cena(app_module)
    with app_module.app.app_context():
        from app import db
        from facilities.materiais import servico as materiais
        sabao = materiais.salvar_material(None, {'nome': 'Sabão em pó', 'unidade': 'kg'})
        pano = materiais.salvar_material(None, {'nome': 'Pano de chão', 'unidade': 'un'})
        materiais.salvar_material(None, {'nome': 'Água sanitária', 'unidade': 'L'})
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        materiais.movimentar(admin, fabrica.local(), {'material_id': pano.id, 'quantidade': '3'},
                             'entrada')
        db.session.commit()
        fora = fabrica.local('Hospital Norte').id
        ids = (pano.id, sabao.id)
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')
    lista = c.get(f"/app/api/materiais?local={cena['local']}").get_json()
    # Primeiro o que o local já tem em estoque, depois o resto do catálogo.
    assert lista[0] == {'id': ids[0], 'nome': 'Pano de chão', 'unidade': 'un', 'no_local': True}
    assert [m['nome'] for m in lista[1:]] == ['Água sanitária', 'Sabão em pó']
    assert not any(m['no_local'] for m in lista[1:])
    assert c.get(f'/app/api/materiais?local={fora}').status_code == 403
    assert c.get('/app/api/materiais').status_code == 400


def test_pagina_publica_pergunta_e_aqui_e_lista_os_itens(app_module):
    cena = _cena(app_module)
    c = app_module.app.test_client()
    html = c.get(f"/q/{cena['qr']}").get_data(as_text=True)
    assert 'Você está no Porta do banheiro · Shopping Centro. É aqui?' in html
    assert 'data-passo="lugar"' in html and 'data-passo="problema"' in html \
        and 'data-passo="foto"' in html
    assert '>Sim<' in html and 'Não, voltar' in html
    # Os itens do checklist do ponto, como caixas; os tipos de antes não aparecem.
    assert 'name="itens" value="papel_higienico_reposto"' in html
    assert 'Problema: Papel higiênico reposto?' in html
    assert 'name="tipo"' not in html and 'Local sujo' not in html
    assert 'Outro (escreva)' in html and 'name="site"' in html      # campo-isca
    assert 'js/publico-qr.js' in html and 'Não pedimos seu nome' in html
    # Ponto sem checklist: os tipos de antes, menos o "itens".
    with app_module.app.app_context():
        from facilities.cadastros import servico as cad
        solto = cad.salvar_ponto(fabrica.local(), None, {'nome': 'Copa', 'ambiente_id':
                                                         cena['ambiente']}, None)
        from app import db
        db.session.commit()
        qr_solto = solto.codigo_qr
    html = c.get(f'/q/{qr_solto}').get_data(as_text=True)
    assert 'name="tipo" value="sujo"' in html and 'name="itens"' not in html
    assert 'Itens do checklist' not in html


def test_post_publico_sem_tipo_grava_os_itens(app_module):
    cena = _cena(app_module)
    from facilities.rotas.models import OcorrenciaPublica
    c = app_module.app.test_client()
    r = c.post(f"/q/{cena['qr']}/ocorrencia",
               data={'itens': ['papel_higienico_reposto', 'mictorios'], 'texto': ''},
               content_type='multipart/form-data')
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    with app_module.app.app_context():
        oc = OcorrenciaPublica.query.one()
        assert oc.tipo == 'itens' and oc.itens == ['papel_higienico_reposto', 'mictorios']
        assert json.loads(oc.itens_json) == ['papel_higienico_reposto', 'mictorios']
        assert oc.texto is None and oc.autor_id is None
    html = c.get(r.headers['Location']).get_data(as_text=True)
    assert 'Itens do checklist' in html and 'Recebida' in html
    # Só o texto: "outro". Nada: recusado com a mensagem da tela.
    r = c.post(f"/q/{cena['qr']}/ocorrencia", data={'texto': 'Porta não fecha'},
               content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        assert OcorrenciaPublica.query.filter_by(tipo='outro').one().texto == 'Porta não fecha'
    r = c.post(f"/q/{cena['qr']}/ocorrencia", data={'texto': ''}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'Marque o que está acontecendo' in r.get_data(as_text=True)
    # O tipo de antes continua aceito (ponto sem checklist, formulário antigo).
    r = c.post(f"/q/{cena['qr']}/ocorrencia", data={'tipo': 'sujo'}, content_type='multipart/form-data')
    assert r.status_code == 302

