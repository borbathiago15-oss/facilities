"""O aplicativo de campo nas telas novas (``/api/v1/campo/...``).

* o início: os mesmos dados da tela antiga (``campo.rotas.contexto_inicio``);
  o turno e o leitor de QR apontam para as telas novas (``/novo/app/...``),
  os demais endereços continuam os das telas de sempre;
* o "Meu turno": o MESMO JSON que a tela antiga leva embutido
  (``rotas.telas._dados_do_turno``);
* cada pessoa vê só os locais dela.
"""
import json
import re

from tests import fabrica
from tests.test_rotas_servico import montar_cena

LOCAL_A, LOCAL_B = fabrica.CONTRATOS_SEMEADOS[0], fabrica.CONTRATOS_SEMEADOS[1]


def test_inicio_pede_login(client):
    r = client.get('/api/v1/campo/inicio')
    assert r.status_code == 401 and r.is_json


def test_inicio_traz_o_turno_de_cada_local_da_pessoa(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'campo.ana@trino.com', papel='encarregado', locais=[LOCAL_A])
    c = fabrica.entrar(app_module, 'campo.ana@trino.com')
    d = c.get('/api/v1/campo/inicio').get_json()
    assert [t['local'] for t in d['turno']] == [LOCAL_A]
    assert d['turno'][0]['situacao'] == 'sem_entrada'
    assert d['turno'][0]['url'].startswith('/novo/app/turno?local=')
    assert d['tem_locais'] is True and d['links']['ler_qr'] == '/novo/app/ler-qr'
    # A tela antiga mostra os mesmos locais, nos endereços das telas de sempre.
    html = c.get('/app/').get_data(as_text=True)
    for t in d['turno']:
        assert f'href="{t["url"].removeprefix("/novo")}"' in html.replace('&amp;', '&')
    assert [p['nome'] for p in d['passagem']] == [LOCAL_A]


def test_inicio_nunca_mostra_local_de_outra_pessoa(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'campo.bia@trino.com', papel='tecnico', locais=[LOCAL_B])
    d = fabrica.entrar(app_module, 'campo.bia@trino.com').get('/api/v1/campo/inicio').get_json()
    nomes = [t['local'] for t in d['turno']] + [p['nome'] for p in (d['passagem'] or [])]
    assert LOCAL_A not in nomes and LOCAL_B in [t['local'] for t in d['turno']]


def test_sem_local_liberado(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'campo.sem@trino.com', papel='encarregado')
    d = fabrica.entrar(app_module, 'campo.sem@trino.com').get('/api/v1/campo/inicio').get_json()
    assert d['tem_locais'] is False and d['turno'] == []


# ── "Meu turno" (/api/v1/campo/turno) ─────────────────────────────────────

def _embutido(c, url='/app/turno'):
    html = c.get(url).get_data(as_text=True)
    return json.loads(re.search(r'<script type="application/json" id="turno-dados">(.*?)</script>',
                                html, re.S).group(1))


def test_turno_pede_login(client):
    for url in ('/api/v1/campo/turno', '/api/v1/campo/links'):
        r = client.get(url)
        assert r.status_code == 401 and r.is_json


def test_turno_traz_o_mesmo_json_da_tela_antiga(app_module):
    cena = _cena(app_module)
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')
    r = c.get('/api/v1/campo/turno')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    novo, antigo = r.get_json()['dados'], _embutido(c)
    assert novo['pontos'] and novo['versoes'] and novo['locais']
    assert novo['usuario'] == antigo['usuario']
    # ``agora`` é a hora de cada resposta; o resto é igual, campo por campo.
    novo.pop('agora'), antigo.pop('agora')
    assert novo == antigo
    assert [l['id'] for l in novo['locais']] == [cena['local']]
    assert r.get_json()['links']['ler_qr'] == '/novo/app/ler-qr'


def test_turno_nunca_mostra_local_de_outra_pessoa(app_module):
    cena = _cena(app_module)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'turno.bia@trino.com', papel='tecnico', locais=[LOCAL_B])
    c = fabrica.entrar(app_module, 'turno.bia@trino.com')
    d = c.get('/api/v1/campo/turno').get_json()['dados']
    assert [l['nome'] for l in d['locais']] == [LOCAL_B]
    assert 'Shopping Centro' not in json.dumps(d, ensure_ascii=False)
    assert d['tarefas'] == [] and all(p['local'] == LOCAL_B for p in d['pontos'].values())
    # Nem pedindo o local de outra pessoa pelo endereço.
    r = c.get(f'/api/v1/campo/turno?local={cena["local"]}&client_id={cena["local"]}')
    assert 'Shopping Centro' not in r.get_data(as_text=True)


def test_links_seguem_o_perfil(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'links.tec@trino.com', papel='tecnico', locais=[LOCAL_A])
    d = fabrica.entrar(app_module, 'links.tec@trino.com').get('/api/v1/campo/links').get_json()
    inicio = fabrica.entrar(app_module, 'links.tec@trino.com').get('/api/v1/campo/inicio').get_json()
    assert d == inicio['links'] and d['ler_qr'] == '/novo/app/ler-qr'


def _cena(app_module):
    with app_module.app.app_context():
        return montar_cena(app_module)
