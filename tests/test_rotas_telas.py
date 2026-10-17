"""Fase 4A — as rotas pela tela (site) e pelo aplicativo.

* a gestão monta checklist, rota, atividade e escala pela tela;
* o encarregado abre "Meu turno" (com os dados para funcionar sem sinal),
  lê o QR (selo do servidor) e registra a execução com foto;
* quem não é da gestão não monta; quem não é do local não vê;
* o agendador por HTTP exige o token.
"""
import io
import json
import re

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import _png


@pytest.fixture()
def montado(app_module, auth_client):
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        fabrica.pessoa(app_module, 'ana.tela@trino.com', 'encarregado',
                       locais=['Shopping Centro'], nome='Ana Tela')
        ana = app_module.User.query.filter_by(email='ana.tela@trino.com').one().id
    cid = ids['local']
    r = auth_client.post(f'/rotas/locais/{cid}/modelos', data={'nome': 'Limpeza de banheiro'})
    mid = int(r.headers['Location'].rsplit('/', 1)[1])
    auth_client.post(f'/rotas/modelos/{mid}', data={
        'texto': ['Papel reposto?', 'Piso limpo?'], 'tipo': ['sim_nao', 'conforme'],
        'opcoes': ['', ''], 'minimo': ['', ''], 'maximo': ['', ''],
        'problema_se': ['nao', ''], 'mostrar_se': ['', ''], 'codigo': ['', ''],
        'ordem': ['1', '2'], 'obrigatorio': ['0', '1'], 'exige_foto_depois': '1'})
    r = auth_client.post(f'/rotas/locais/{cid}/rotas', data={
        'nome': 'Limpeza T1', 'turno': '1º Turno', 'hora_inicio': '00:00', 'hora_fim': '23:59',
        'tolerancia_min': '240', 'dias_semana': list('1234567')})
    rid = int(r.headers['Location'].rsplit('/', 1)[1])
    agora = tempo.agora()
    hora = agora.strftime('%H:%M')
    r = auth_client.post(f'/rotas/{rid}/itens', data={'ponto_id': ids['ponto'], 'modelo_id': mid,
                                                     'horarios': hora})
    auth_client.post(f'/rotas/{rid}/escalas', data={'user_id': ana,
                                                   'data_inicio': agora.date().isoformat(),
                                                   'dias_semana': list('1234567')})
    ids.update(mid=mid, rid=rid, ana=ana)
    return ids


def test_gestao_monta_pela_tela(app_module, montado, auth_client):
    with app_module.app.app_context():
        from facilities.rotas.models import ChecklistModelo, Rota
        m = app_module.db.session.get(ChecklistModelo, montado['mid'])
        assert m.versao_atual.numero == 1 and m.versao_atual.exige_foto_depois
        assert [i['texto'] for i in json.loads(m.versao_atual.itens_json)] == \
            ['Papel reposto?', 'Piso limpo?']
        r = app_module.db.session.get(Rota, montado['rid'])
        assert len(r.itens) == 1 and r.escalas[0].pessoa.name == 'Ana Tela'
    html = auth_client.get(f"/rotas/{montado['rid']}").get_data(as_text=True)
    assert 'Ana Tela' in html and 'Porta do banheiro' in html
    assert auth_client.get(f"/rotas/locais/{montado['local']}").status_code == 200
    assert auth_client.get(f"/rotas/modelos/{montado['mid']}").status_code == 200


def test_encarregado_executa_pelo_aplicativo(app_module, montado):
    c = fabrica.entrar(app_module, 'ana.tela@trino.com')
    html = c.get(f"/app/turno?ponto={montado['qr']}").get_data(as_text=True)
    dados = json.loads(re.search(r'<script type="application/json" id="turno-dados">(.*?)</script>',
                                 html, re.S).group(1))
    assert montado['qr'] in dados['pontos']
    t = dados['tarefas'][0]
    assert t['minha'] and t['ponto'] == montado['qr']
    versao = dados['versoes'][str(t['versao'])]
    assert versao['foto_depois'] and versao['itens'][0]['texto'] == 'Papel reposto?'
    selo = c.post('/app/api/leitura', json={'ponto': montado['qr']}).get_json()['selo']
    corpo = {'envio_id': 'tela-envio-0001', 'ponto': montado['qr'], 'tarefa_id': t['id'],
             'respostas': {'papel_reposto': 'nao', 'piso_limpo': 'conforme'},
             'selo_leitura': selo}
    r = c.post('/app/api/execucoes', data={'corpo': json.dumps(corpo),
                                           'depois': (io.BytesIO(_png()), 'd.png')},
               content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()['nao_conformes'] == 1
    assert r.get_json()['status'] == 'concluida_no_prazo'
    # Reenvio (a fila) devolve a mesma execução.
    r2 = c.post('/app/api/execucoes', data={'corpo': json.dumps(corpo),
                                            'depois': (io.BytesIO(_png()), 'd.png')},
                content_type='multipart/form-data')
    assert r2.status_code == 200 and r2.get_json()['id'] == r.get_json()['id']


def test_gestao_acompanha_o_dia_e_ve_a_execucao(app_module, montado, auth_client):
    test_encarregado_executa_pelo_aplicativo(app_module, montado)
    html = auth_client.get(f"/rotas/locais/{montado['local']}/dia").get_data(as_text=True)
    assert 'Ana Tela' in html and 'Concluída no prazo' in html and '100.0%' in html
    with app_module.app.app_context():
        from facilities.rotas.models import Execucao, ExecucaoFoto
        eid = Execucao.query.one().id
        fid = ExecucaoFoto.query.one().id
    html = auth_client.get(f'/rotas/execucoes/{eid}').get_data(as_text=True)
    assert 'Papel reposto?' in html and 'Não conformidades' in html
    assert auth_client.get(f'/rotas/fotos/{fid}').mimetype == 'image/png'


def test_quem_nao_e_gestao_nao_monta(app_module, montado):
    c = fabrica.entrar(app_module, 'ana.tela@trino.com')
    assert c.post(f"/rotas/locais/{montado['local']}/rotas",
                  data={'nome': 'X', 'turno': 'X', 'hora_inicio': '07:00',
                        'hora_fim': '08:00', 'dias_semana': '1'}).status_code == 403
    assert c.post(f"/rotas/modelos/{montado['mid']}", data={'texto': ['Hack']}).status_code == 403
    assert c.get('/rotas/').status_code == 403
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'sup.tela@trino.com', 'supervisor', locais=['Shopping Centro'])
    sup = fabrica.entrar(app_module, 'sup.tela@trino.com')
    assert sup.get(f"/rotas/locais/{montado['local']}/dia").status_code == 200
    assert sup.post(f"/rotas/{montado['rid']}/itens", data={}).status_code == 403


def test_biblioteca_so_o_administrador_edita(app_module, montado, auth_client):
    r = auth_client.post('/rotas/biblioteca', data={'nome': 'Padrão Trino — copa'})
    mid = int(r.headers['Location'].rsplit('/', 1)[1])
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'coord.lib@trino.com', 'pleno', locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'coord.lib@trino.com')
    assert c.get(f'/rotas/modelos/{mid}').status_code == 200
    assert c.post(f'/rotas/modelos/{mid}', data={'texto': ['X']}).status_code == 403


def test_qr_leva_o_posto_ao_turno(app_module, montado):
    c = fabrica.entrar(app_module, 'ana.tela@trino.com')
    r = c.get(f"/q/{montado['qr']}")
    assert r.status_code == 302 and r.headers['Location'].endswith(f"/app/turno?ponto={montado['qr']}")


def test_agendador_http_exige_token(app_module, monkeypatch):
    c = app_module.app.test_client()
    monkeypatch.delenv('AGENDADOR_TOKEN', raising=False)
    assert c.post('/rotas/agendador').status_code == 404
    monkeypatch.setenv('AGENDADOR_TOKEN', 'segredo-do-relogio')
    assert c.post('/rotas/agendador').status_code == 403
    assert c.post('/rotas/agendador', headers={'Authorization': 'Bearer errado'}).status_code == 403
    r = c.post('/rotas/agendador', headers={'Authorization': 'Bearer segredo-do-relogio'})
    assert r.status_code == 200 and r.get_json()['ok'] is True


def test_comando_do_agendador(app_module):
    runner = app_module.app.test_cli_runner()
    r = runner.invoke(args=['agendador', 'rodar'])
    assert r.exit_code == 0 and 'tarefa(s) gerada(s)' in r.output
