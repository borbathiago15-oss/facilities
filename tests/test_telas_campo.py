"""O início do aplicativo de campo nas telas novas (``/api/v1/campo/inicio``).

Os mesmos dados da tela antiga (``campo.rotas.contexto_inicio``): cada
pessoa vê só os locais dela, e os endereços continuam os das telas de
sempre até cada uma ser migrada.
"""
from tests import fabrica

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
    assert d['turno'][0]['url'].startswith('/app/turno?local=')
    assert d['tem_locais'] is True and d['links']['ler_qr'] == '/app/ler-qr'
    # A tela antiga mostra os mesmos locais e os mesmos endereços.
    html = c.get('/app/').get_data(as_text=True)
    for t in d['turno']:
        assert f'href="{t["url"]}"' in html.replace('&amp;', '&')
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
