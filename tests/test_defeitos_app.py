"""Defeitos do aplicativo corrigidos em 21/10/2026, para não voltarem.

* o service worker tinha dois tratadores de push: cada aviso virava duas
  notificações (a primeira vazia) e o toque abria duas telas;
* ao subir UMA execução guardada sem sinal, todas as tarefas do aparelho
  passavam a "Enviada";
* o encarregado via, em Demandas, um link para a tela "Hoje" do local, que
  é da gestão (403); o supervisor via "Pontos e QR do local" sem poder abrir;
* o Chart.js (205 KB) carregava em toda tela, inclusive no celular do posto.
"""
import os
import re

from tests import fabrica

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arquivo(*partes):
    with open(os.path.join(RAIZ, 'facilities', *partes), encoding='utf-8') as f:
        return f.read()


def test_service_worker_trata_o_push_uma_vez_so():
    sw = _arquivo('static', 'pwa', 'sw.js')
    assert sw.count("addEventListener('push'") == 1
    assert sw.count("addEventListener('notificationclick'") == 1
    # O servidor manda {titulo, texto, link, marca} (core/push.py).
    assert 'd.texto' in sw and 'd.corpo' not in sw


def test_fila_marca_enviada_so_a_tarefa_que_subiu():
    js = _arquivo('static', 'js', 'rotas-turno.js')
    bloco = re.search(r"addEventListener\('trino-fila:enviado'.*?\n  \}\);", js, re.S).group(0)
    assert "f[ev.detail.tarefa_id] = 'Enviada'" in bloco
    # Item guardado por uma versão anterior (sem tarefa_id) não fica preso.
    assert "f[k] === 'Guardada no aparelho'" in bloco
    assert "tarefa_id: it.tarefa_id" in _arquivo('static', 'js', 'fila-offline.js')
    # E o servidor manda: tarefa já registrada apaga a marca local.
    assert 'desmarcarFeita(t.id)' in js


def test_chart_js_so_no_painel_da_passagem():
    assert 'chart.umd' not in _arquivo('templates', 'base.html')
    assert 'chart.umd' in _arquivo('templates', 'diario_operacional', 'dashboard.html')


def test_encarregado_nao_recebe_link_que_da_403(app_module):
    from app import db
    from facilities.rotas import ocorrencias
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ocorrencias.abrir(db.session.get(PontoInspecao, ids['ponto']), 'outro', 'Vazamento')
        db.session.commit()
        fabrica.pessoa(app_module, 'enc.def@trino.com', 'encarregado', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'sup.def@trino.com', 'supervisor', locais=['Shopping Centro'])
        cid = ids['local']
    enc = fabrica.entrar(app_module, 'enc.def@trino.com')
    for tela in ('/demandas/', '/'):
        html = enc.get(tela).get_data(as_text=True)
        assert 'Banheiro masculino 2º andar' in html, tela
        assert f'/rotas/locais/{cid}/dia' not in html and 'href="/app/"' in html, tela
    sup = fabrica.entrar(app_module, 'sup.def@trino.com')
    html = sup.get(f'/rotas/locais/{cid}').get_data(as_text=True)
    assert 'Pontos e QR do local' not in html
    assert sup.get(f'/cadastros/locais/{cid}').status_code == 403
