"""As telas novas (React, ``frontend/``) e a API delas (``/api/v1``).

* ``/novo/`` pede login como o resto do site e entrega a casca compilada,
  sem script inline (a CSP não muda);
* sem a compilação no servidor, um aviso claro (503), nunca uma página quebrada;
* ``/api/v1/eu`` responde JSON — inclusive nas travas (senha a trocar,
  sessão vencida), que no site redirecionam;
* o menu da API é o mesmo das telas antigas (``core/menu.py``) e não leva
  e-mail nem dado de mais ninguém.
"""
import pytest

from facilities import telas
from tests import fabrica

MANIFESTO = {'src/main.tsx': {'file': 'assets/main-abc123.js', 'css': ['assets/main-abc123.css'],
                              'isEntry': True}}


@pytest.fixture()
def compilado(monkeypatch):
    monkeypatch.setattr(telas, '_manifesto', lambda: MANIFESTO)


def test_casca_pede_login(client, compilado):
    r = client.get('/novo/')
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_casca_entrega_o_react_sem_script_inline(auth_client, compilado):
    for caminho in ('/novo/', '/novo/qualquer/tela/123'):
        r = auth_client.get(caminho)
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert '<script type="module" src="/static/app/assets/main-abc123.js"></script>' in html
        assert '/static/app/assets/main-abc123.css' in html
        assert '/static/css/app.css' in html            # a mesma marca do site
        assert "script-src 'self'" in r.headers['Content-Security-Policy']
        assert html.count('<script') == 1
        assert r.headers['Cache-Control'] == 'no-store'


def test_sem_compilacao_avisa_em_portugues(auth_client, monkeypatch):
    monkeypatch.setattr(telas, '_manifesto', lambda: None)
    r = auth_client.get('/novo/')
    assert r.status_code == 503
    assert 'não foram compiladas' in r.get_data(as_text=True)


def test_eu_sem_login_e_401_em_json(client):
    r = client.get('/api/v1/eu')
    assert r.status_code == 401 and r.is_json


def test_eu_traz_pessoa_menu_e_csrf(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'telas.sup@trino.com', papel='supervisor',
                       nome='Bruna Lima', locais=[fabrica.CONTRATOS_SEMEADOS[0]])
    c = fabrica.entrar(app_module, 'telas.sup@trino.com')
    r = c.get('/api/v1/eu')
    d = r.get_json()
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert d['nome'] == 'Bruna Lima' and d['primeiro_nome'] == 'Bruna'
    assert d['papel'] == 'supervisor' and d['cliente'] is False and d['csrf']
    rotulos = [i['rotulo'] for g in d['menu'] for i in g['itens']]
    assert 'Rotina dos locais' in rotulos and 'Pessoas e acessos' not in rotulos
    assert '@' not in r.get_data(as_text=True)           # nenhum e-mail sai daqui
    # O mesmo menu da tela antiga.
    html = c.get('/').get_data(as_text=True)
    for rotulo in rotulos:
        assert f'<span>{rotulo}</span>' in html


def test_eu_com_senha_a_trocar_responde_json(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'telas.troca@trino.com', must_change_password=True)
    c = fabrica.entrar(app_module, 'telas.troca@trino.com')
    r = c.get('/api/v1/eu')
    assert r.status_code == 403 and r.is_json and 'Troque a sua senha' in r.get_json()['error']


def test_rota_inexistente_da_api_e_404_em_json(auth_client):
    r = auth_client.get('/api/v1/nao-existe')
    assert r.status_code == 404 and r.is_json


def test_envio_sem_csrf_e_recusado(app_module, auth_client):
    app_module.app.config['WTF_CSRF_ENABLED'] = True
    try:
        r = auth_client.post('/api/v1/qualquer', json={})
        assert r.status_code == 400 and r.is_json and 'Recarregue' in r.get_json()['error']
    finally:
        app_module.app.config['WTF_CSRF_ENABLED'] = False
