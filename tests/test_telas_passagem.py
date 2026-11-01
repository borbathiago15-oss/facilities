"""A Passagem de turno nas telas novas (``/api/v1/passagem/...``, Fase 2a).

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* a nova passagem: os mesmos dados que a tela antiga escreve
  (``passagem.rotas.contexto_turno``) — os modelos, os turnos já
  encerrados, as pendências e o turno anterior de cada área;
* a leitura: os mesmos dados de ``contexto_ver_turno`` — checklist, provas,
  pendências, ocorrências, correção;
* a porta é a mesma: a diretoria (só leitura) não abre a nova passagem e lê
  a passagem lançada; quem é de outro local não vê a passagem de A, nem
  pelo id;
* dentro das telas novas, os endereços da passagem apontam para elas.
"""
import html as html_mod
import io
import json
import re

import pytest

from facilities import tempo
from tests import fabrica

LOCAL_A, LOCAL_B = fabrica.CONTRATOS_SEMEADOS[0], fabrica.CONTRATOS_SEMEADOS[1]
SEGREDO = 'SEGREDO-DA-PASSAGEM-A'


def _png():
    import struct
    import zlib

    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00\x0a\x78\x1e')) + bloco(b'IEND', b''))


@pytest.fixture()
def cena(app_module):
    """O local A com uma área, um modelo (rotina + número), uma passagem
    encerrada com ocorrência, pendência e foto, e uma pendência aberta."""
    from app import db
    from facilities.passagem.models import DiarioArea, DiarioConfiguracao
    with app_module.app.app_context():
        a = fabrica.local(LOCAL_A).id
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        area = DiarioArea(client_id=a, nome='Expedição', ativo=True, created_by=admin.id)
        db.session.add(area)
        db.session.flush()
        cfg = DiarioConfiguracao(
            client_id=a, area_id=area.id, nome='Expedição — rotina',
            turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'}]),
            campos_json=json.dumps([{'nome': 'Volumes', 'codigo': 'vol', 'tipo': 'numero'}]),
            atividades_json=json.dumps([{'nome': 'Doca limpa', 'codigo': 'doca'}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]), ativo=True, created_by=admin.id)
        db.session.add(cfg)
        db.session.commit()
        ids = {'local': a, 'cfg': cfg.id, 'area': area.id}
        fabrica.pessoa(app_module, 'passagem.ana@trino.com', 'encarregado', locais=[LOCAL_A],
                       nome='Ana Passagem')
    ana = fabrica.entrar(app_module, 'passagem.ana@trino.com')
    r = ana.post('/passagem-de-turno/api/turnos', json={
        'client_id': a, 'configuracao_id': ids['cfg'], 'data_turno': tempo.hoje().isoformat(),
        'turno': '1º Turno', 'dados': {'atividade:doca': {'concluido': True, 'observacao': 'Varrida'},
                                       'vol': '42'},
        'observacao': f'Observação {SEGREDO}',
        'ocorrencias': [{'tipo': 'Avaria', 'referencia': 'NF 9', 'descricao': f'Pallet {SEGREDO}',
                         'gravidade': 'critica'}],
        'pendencias': [{'titulo': f'Devolução {SEGREDO}', 'referencia': 'NF 10', 'prioridade': 'alta'}],
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    ids['turno'] = r.get_json()['id']
    r = ana.post(f"/passagem-de-turno/api/turnos/{ids['turno']}/anexos",
                 data={'atividade': 'doca', 'arquivo': (io.BytesIO(_png()), 'doca.png')},
                 content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    ids['ana'] = ana
    return ids


def test_pede_login(client):
    for url in ('/api/v1/passagem/turno', '/api/v1/passagem/turno/1'):
        r = client.get(url)
        assert r.status_code == 401 and r.is_json
    for url in ('/novo/passagem-de-turno/turno', '/novo/passagem-de-turno/turno/1'):
        r = client.get(url)
        assert r.status_code == 302 and '/login' in r.headers['Location']


def _atributo(html, nome):
    m = re.search(nome + r"""='(.*?)'""", html, re.S)
    return json.loads(html_mod.unescape(m.group(1)))


def test_nova_passagem_traz_os_dados_da_tela_antiga(app_module, cena):
    c = cena['ana']
    url = f"?client_id={cena['local']}"
    r = c.get('/api/v1/passagem/turno' + url)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    novo = r.get_json()
    antigo = c.get('/passagem-de-turno/turno' + url).get_data(as_text=True)
    # Os modelos e os turnos encerrados: o MESMO JSON que a tela antiga embute.
    assert novo['configs'] == _atributo(antigo, 'data-configs')
    encerrados = re.search(r'<script type="application/json" id="dt-turnos-encerrados">(.*?)</script>',
                           antigo, re.S).group(1)
    assert novo['encerrados'] == json.loads(encerrados)
    assert novo['encerrados'] == {str(cena['cfg']): {tempo.hoje().isoformat(): ['1º Turno']}}
    assert novo['client_id'] == cena['local'] and novo['hoje'] == tempo.hoje().isoformat()
    assert novo['usuario'] == {'nome': 'Ana Passagem', 'perfil': 'Encarregado / ASG'}
    assert novo['areas'] == [{'id': cena['area'], 'nome': 'Expedição'}]
    # As pendências em aberto: as mesmas, na mesma ordem, com o que a tela escreve.
    ids_antigos = [int(x) for x in re.findall(r'id="pendencia-(\d+)"', antigo)]
    assert [p['id'] for p in novo['pendencias']] == ids_antigos and ids_antigos
    p = novo['pendencias'][0]
    assert p['titulo'] == f'Devolução {SEGREDO}' and p['referencia'] == 'NF 10' and p['alta'] is True
    assert p['origem_turno'] == '1º Turno' and p['origem_data'] == tempo.hoje().strftime('%d/%m')
    # O turno anterior, um bloco por área (as mesmas chaves do HTML).
    assert [b['chave'] for b in novo['anteriores']] == re.findall(r'data-area="([^"]+)"', antigo)
    b = novo['anteriores'][0]
    assert b['turno'] == {'turno': '1º Turno', 'data': tempo.hoje().strftime('%d/%m'),
                          'observacao': f'Observação {SEGREDO}'}
    assert b['autor'] == 'Ana Passagem' and b['area'] == 'Expedição' and b['tem_o_que_ler'] is True
    assert b['ocorrencias'] == [{'tipo': 'Avaria', 'referencia': 'NF 9', 'gravidade': 'critica',
                                 'descricao': f'Pallet {SEGREDO}'}]
    assert [a['url'] for a in b['anexos']] == re.findall(
        r'href="(/passagem-de-turno/anexos/\d+)"', antigo)
    assert novo['anterior_inicial'] == f"area-{cena['area']}"
    assert novo['links']['painel'] == f"/passagem-de-turno/?client_id={cena['local']}"
    assert novo['links']['ver_turno'] == '/novo/passagem-de-turno/turno/'


def test_leitura_traz_os_dados_da_tela_antiga(app_module, cena):
    c = cena['ana']
    r = c.get(f"/api/v1/passagem/turno/{cena['turno']}")
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    d = r.get_json()
    antigo = c.get(f"/passagem-de-turno/turno/{cena['turno']}").get_data(as_text=True)
    assert d['turno']['turno'] == '1º Turno' and d['turno']['status'] == 'encerrado'
    assert d['cliente'] == LOCAL_A and d['configuracao'] == 'Expedição — rotina'
    assert d['autor'] == 'Ana Passagem' and d['congelada'] is True
    # Corrigir é do autor, enquanto o turno seguinte não fechou: a tela
    # antiga mostra o botão, a nova recebe ``pode_corrigir``.
    assert d['pode_corrigir'] is True and 'data-acao="vtCorrigir"' in antigo
    assert d['turno']['encerrado_em'] and d['turno']['encerrado_em'] in antigo
    assert [(x['nome'], x['feito'], x['observacao']) for x in d['linhas']] == [('Doca limpa', True, 'Varrida')]
    assert [a['nome'] for a in d['linhas'][0]['anexos']] == ['doca.png']
    assert d['linhas'][0]['anexos'][0]['url'] in antigo
    assert d['campos'] == [{'nome': 'Volumes', 'valor': '42', 'anexos': []}]
    assert [p['titulo'] for p in d['pendencias']] == [f'Devolução {SEGREDO}']
    assert d['pendencias'][0]['status'] == 'aberta'
    assert d['ocorrencias'] == [{'tipo': 'Avaria', 'referencia': 'NF 9', 'gravidade': 'critica',
                                 'descricao': f'Pallet {SEGREDO}'}]
    for texto in ('Doca limpa', 'Varrida', 'Volumes', f'Pallet {SEGREDO}', f'Devolução {SEGREDO}'):
        assert texto in antigo
    assert d['links']['corrigir'] == f"/passagem-de-turno/api/turnos/{cena['turno']}/corrigir"
    # A correção aparece nas duas (quem, o que mudou e por quê).
    r = c.post(d['links']['corrigir'], json={'data_turno': tempo.hoje().isoformat(),
                                              'turno': '1º Turno', 'observacao': 'Corrigida',
                                              'motivo': 'Faltou a doca 3'})
    assert r.status_code == 200, r.get_data(as_text=True)
    d = c.get(f"/api/v1/passagem/turno/{cena['turno']}").get_json()
    assert [(x['quem'], x['campos'], x['motivo']) for x in d['correcoes']] == [
        ('Ana Passagem', 'observação', 'Faltou a doca 3')]
    assert 'Faltou a doca 3' in c.get(f"/passagem-de-turno/turno/{cena['turno']}").get_data(as_text=True)


def test_quem_nao_e_o_autor_nao_corrige(app_module, cena):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'passagem.mari@trino.com', 'encarregado', locais=[LOCAL_A])
    c = fabrica.entrar(app_module, 'passagem.mari@trino.com')
    assert c.get(f"/api/v1/passagem/turno/{cena['turno']}").get_json()['pode_corrigir'] is False


@pytest.mark.parametrize('papel', ['visualizador', 'encarregado', 'tecnico', 'supervisor', 'pleno'])
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta nas telas antigas, nas páginas novas e na API."""
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta.{papel}@trino.com', papel, locais=[LOCAL_A])
    c = fabrica.entrar(app_module, f'porta.{papel}@trino.com')
    q = f"?client_id={cena['local']}"
    for antiga, nova, api in (
            ('/passagem-de-turno/turno' + q, '/novo/passagem-de-turno/turno' + q,
             '/api/v1/passagem/turno' + q),
            (f"/passagem-de-turno/turno/{cena['turno']}",
             f"/novo/passagem-de-turno/turno/{cena['turno']}",
             f"/api/v1/passagem/turno/{cena['turno']}")):
        esperado = c.get(antiga).status_code
        assert c.get(api).status_code == esperado, (papel, api)
        if esperado != 200:
            r = c.get(api)
            assert r.is_json and SEGREDO not in r.get_data(as_text=True)
        # A página nova: a mesma porta (sem a compilação, 503 em vez de 200).
        assert c.get(nova).status_code in ((200, 503) if esperado == 200 else (esperado,)), (papel, nova)
    if papel == 'visualizador':
        # A diretoria lê a passagem lançada, mas não abre a tela de lançar.
        assert c.get('/api/v1/passagem/turno' + q).status_code == 403
        assert c.get(f"/api/v1/passagem/turno/{cena['turno']}").status_code == 200


def test_quem_e_de_outro_local_nao_ve_a_passagem_de_a(app_module, cena):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'passagem.bia@trino.com', 'encarregado', locais=[LOCAL_B])
    c = fabrica.entrar(app_module, 'passagem.bia@trino.com')
    r = c.get(f"/api/v1/passagem/turno/{cena['turno']}")
    assert r.status_code == 403 and r.is_json and SEGREDO not in r.get_data(as_text=True)
    assert c.get(f"/novo/passagem-de-turno/turno/{cena['turno']}").status_code == 403
    assert c.get('/api/v1/passagem/turno/999999').status_code == 404
    # Pedindo o local de A pelo endereço, a tela abre sem nada de A.
    r = c.get(f"/api/v1/passagem/turno?client_id={cena['local']}")
    assert r.status_code == 200
    d = r.get_json()
    assert SEGREDO not in r.get_data(as_text=True)
    assert d['client_id'] is None and d['configs'] == [] and d['pendencias'] == []
    assert [x['nome'] for x in d['clients']] == [LOCAL_B]


def test_dentro_das_telas_novas_a_passagem_e_a_nova(app_module, cena):
    """O início do campo (tela nova) leva à passagem nova; a antiga não muda."""
    c = cena['ana']
    d = c.get('/api/v1/campo/inicio').get_json()
    assert d['links']['passagem'] == '/novo/passagem-de-turno/turno'
    assert [x['url'] for x in d['passagem']] == [f"/novo/passagem-de-turno/turno?client_id={cena['local']}"]
    assert c.get('/api/v1/campo/links').get_json()['passagem'] == '/novo/passagem-de-turno/turno'
    assert 'href="/passagem-de-turno/turno' in c.get('/app/').get_data(as_text=True)
