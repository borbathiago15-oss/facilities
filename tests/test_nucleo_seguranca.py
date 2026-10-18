"""Endurecimento do núcleo: login, cookies, cabeçalhos, links e telas.

* o login responde IGUAL (mensagem, status e trabalho de hash) para e-mail
  inexistente, senha errada e conta bloqueada;
* o limite de login é por IP + e-mail: um IP insistindo (o proxy, o 4G, o
  Wi-Fi do posto) não trava o login de todo mundo;
* o cookie "Manter conectado" tem as travas do cookie de sessão;
* HSTS e Permissions-Policy;
* link de aviso só leva a caminho interno; o wrapper do fetch não manda o
  token CSRF para outro site;
* o nome da pessoa não vira JavaScript no confirm() da tela de Pessoas;
* o base.html liga os tooltips, mostra o recado "fc-aviso" e o menu do
  celular mostra todos os módulos.
"""
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD
from tests.test_nucleo import _entrar, _pessoa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _recado(r):
    """O texto do alerta da tela de login."""
    m = re.search(r'<div class="alert[^"]*"[^>]*>\s*(.*?)\s*</div>', r.get_data(as_text=True), re.S)
    return m.group(1) if m else None


# ── Login: a mesma resposta para todos os casos ───────────────────────────

def test_conta_bloqueada_responde_igual_a_email_inexistente(app_module):
    with app_module.app.app_context():
        _pessoa(app_module, 'igual.bloqueio@trino.com')
    for _ in range(5):
        _entrar(app_module, 'igual.bloqueio@trino.com', 'errada')
    _, bloqueada_senha_certa = _entrar(app_module, 'igual.bloqueio@trino.com')
    _, bloqueada_senha_errada = _entrar(app_module, 'igual.bloqueio@trino.com', 'errada')
    _, inexistente = _entrar(app_module, 'ninguem.aqui@trino.com', 'qualquer')
    assert (bloqueada_senha_certa.status_code == bloqueada_senha_errada.status_code
            == inexistente.status_code == 401)
    assert (_recado(bloqueada_senha_certa) == _recado(bloqueada_senha_errada)
            == _recado(inexistente))
    assert 'bloqueada' not in _recado(inexistente)


def test_email_inexistente_tambem_confere_um_hash(app_module, monkeypatch):
    """Sem hash para e-mail inexistente a resposta saía ~50x mais rápida, e o
    tempo dizia quais e-mails existem."""
    from facilities.core import auth
    conferidos = []
    original = auth.check_password_hash

    def espiao(hash_, senha):
        conferidos.append(hash_)
        return original(hash_, senha)
    monkeypatch.setattr(auth, 'check_password_hash', espiao)
    _, r = _entrar(app_module, 'nao.existe.mesmo@trino.com', 'qualquer')
    assert r.status_code == 401
    assert len(conferidos) == 1
    with app_module.app.app_context():
        from app import User
        real = User.query.filter_by(email=ADMIN_EMAIL).one().password_hash
    # O hash de mentira é do MESMO algoritmo (e custo) das senhas reais.
    assert conferidos[0].split('$')[0] == real.split('$')[0]


def test_conta_bloqueada_tambem_confere_o_hash(app_module, monkeypatch):
    from facilities.core import auth
    with app_module.app.app_context():
        _pessoa(app_module, 'bloq.hash@trino.com')
    for _ in range(5):
        _entrar(app_module, 'bloq.hash@trino.com', 'errada')
    conferidos = []
    original = auth.check_password_hash
    monkeypatch.setattr(auth, 'check_password_hash',
                        lambda h, s: conferidos.append(h) or original(h, s))
    _entrar(app_module, 'bloq.hash@trino.com')
    assert len(conferidos) == 1


# ── Limite de login por IP + e-mail ───────────────────────────────────────

def test_chave_do_limite_e_ip_mais_email(app_module):
    from facilities.core.auth import _chave_do_login
    ctx = dict(method='POST', environ_base={'REMOTE_ADDR': '10.0.0.1'})
    with app_module.app.test_request_context('/login', data={'email': ' Ana@Trino.com '}, **ctx):
        ana = _chave_do_login()
    with app_module.app.test_request_context('/login', data={'email': 'bia@trino.com'}, **ctx):
        bia = _chave_do_login()
    assert ana == '10.0.0.1|ana@trino.com'
    assert ana != bia


def test_um_ip_insistindo_nao_trava_o_login_dos_outros(app_module, tmp_path, monkeypatch):
    """Todos atrás do mesmo proxy (mesmo REMOTE_ADDR): quem insiste com um
    e-mail recebe 429; quem chega com o seu e-mail e a senha certa entra."""
    from facilities import create_app
    from facilities.extensions import db, limiter
    monkeypatch.setenv('RATELIMIT_ENABLED', '1')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "limite.db"}')
    app = create_app({'WTF_CSRF_ENABLED': False, 'TESTING': True})
    try:
        with app.app_context():
            from facilities.core.models import User
            db.create_all()
            u = User(name='Encarregada', email='turno.certo@trino.com', role='encarregado')
            u.set_password('senha-certa-123')
            db.session.add(u)
            db.session.commit()
        c = app.test_client()
        proxy = {'REMOTE_ADDR': '10.0.0.1'}
        respostas = [c.post('/login', data={'email': 'chuta@trino.com', 'password': 'x'},
                            environ_base=proxy).status_code for _ in range(21)]
        assert respostas[:20] == [401] * 20 and respostas[20] == 429
        travado = c.post('/login', data={'email': 'chuta@trino.com', 'password': 'x'},
                         environ_base=proxy)
        assert travado.status_code == 429 and 'Espere um minuto' in travado.get_json()['error']
        certo = c.post('/login', data={'email': 'turno.certo@trino.com',
                                       'password': 'senha-certa-123'}, environ_base=proxy)
        assert certo.status_code == 302
        with app.app_context():
            db.engine.dispose()
    finally:
        # Devolve o limitador (singleton) desligado ao app da suíte.
        limiter.init_app(app_module.app)


# ── Cookies e cabeçalhos ──────────────────────────────────────────────────

def test_cookie_manter_conectado_tem_as_travas_do_cookie_de_sessao(app_module):
    cfg = app_module.app.config
    assert cfg['REMEMBER_COOKIE_SECURE'] == cfg['SESSION_COOKIE_SECURE']
    assert cfg['REMEMBER_COOKIE_SAMESITE'] == 'Lax'
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD,
                               'lembrar': '1'})
    lembrar = [h for h in r.headers.getlist('Set-Cookie') if h.startswith('remember_token=')]
    assert lembrar and 'SameSite=Lax' in lembrar[0] and 'HttpOnly' in lembrar[0]


def test_permissions_policy_em_toda_resposta(client):
    r = client.get('/healthz')
    assert r.headers['Permissions-Policy'] == 'camera=(self), microphone=(), geolocation=()'


def test_hsts_em_https_e_nao_em_http_de_desenvolvimento(client):
    assert 'Strict-Transport-Security' not in client.get('/healthz').headers
    r = client.get('/healthz', base_url='https://localhost')
    assert r.headers['Strict-Transport-Security'].startswith('max-age=')


def test_hsts_quando_o_cookie_e_secure_atras_do_proxy(app_module, client):
    """https terminado no proxy: o pedido chega em http, mas o cookie é Secure."""
    app_module.app.config['SESSION_COOKIE_SECURE'] = True
    try:
        assert 'Strict-Transport-Security' in client.get('/healthz').headers
    finally:
        app_module.app.config['SESSION_COOKIE_SECURE'] = False


# ── Links de aviso ────────────────────────────────────────────────────────

@pytest.mark.parametrize('link, destino', [
    ('//evil.com', '/avisos'),
    ('/\\evil.com', '/avisos'),
    ('/\t/evil.com', '/avisos'),
    ('https://evil.com/x', '/avisos'),
    ('chamados/1', '/avisos'),
    ('/chamados/1', '/chamados/1'),
    ('/passagem-de-turno/?client_id=3', '/passagem-de-turno/?client_id=3'),
])
def test_aviso_so_leva_a_caminho_interno(app_module, auth_client, link, destino):
    with app_module.app.app_context():
        from app import User, db
        from facilities.core.models import Notification
        uid = User.query.filter_by(email=ADMIN_EMAIL).one().id
        n = Notification(user_id=uid, title='Teste', message='m', link=link, status='unread')
        db.session.add(n)
        db.session.commit()
        nid = n.id
    r = auth_client.post(f'/avisos/{nid}/abrir')
    assert r.status_code == 302
    assert r.headers['Location'] == destino


# ── XSS no confirm() da tela de Pessoas ───────────────────────────────────

class _FormularioDeSenha(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and '/nova-senha' in (a.get('action') or ''):
            self.forms.append(a)


def test_nome_da_pessoa_nao_vira_javascript_no_confirm(app_module, auth_client):
    nome = "x'+alert(document.cookie)+'"
    auth_client.post('/admin/usuarios', data={'name': nome, 'email': 'xss.nome@trino.com',
                                              'role': 'encarregado'})
    p = _FormularioDeSenha()
    p.feed(auth_client.get('/admin/usuarios').get_data(as_text=True))
    alvo = [f for f in p.forms if f.get('data-nome') == nome]
    assert alvo, 'o nome deve ir (escapado) no data-nome'
    # Desde a Fase 9A não há JS no HTML: a pergunta é um texto fixo com
    # {nome}, que static/js/acoes.js troca pelo data-nome (como texto).
    assert 'onsubmit' not in alvo[0]
    assert 'alert' not in alvo[0]['data-confirmar']
    assert '{nome}' in alvo[0]['data-confirmar']


# ── base.html ─────────────────────────────────────────────────────────────

def _scripts_do_base(auth_client):
    # Fase 9A: o script do base.html foi para static/js/base.js (CSP).
    html = auth_client.get('/').get_data(as_text=True)
    assert "js/base.js" in html and 'id="fc-aviso-js"' in html
    with open(os.path.join(RAIZ, 'facilities', 'static', 'js', 'base.js'),
              encoding='utf-8') as f:
        return html + f.read()


def test_base_liga_os_tooltips(auth_client):
    assert "bootstrap.Tooltip.getOrCreateInstance" in _scripts_do_base(auth_client)


def test_base_mostra_o_recado_fc_aviso_e_apaga(auth_client):
    html = _scripts_do_base(auth_client)
    assert 'id="fc-aviso-js"' in html
    assert "sessionStorage.getItem('fc-aviso')" in html
    assert "sessionStorage.removeItem('fc-aviso')" in html
    assert 'caixa.textContent = texto' in html          # texto puro, nunca HTML


def _wrapper_do_fetch(html):
    m = re.search(r'/\* CSRF: injeta X-CSRFToken.*?\n\}\)\(\);\n', html, re.S)
    assert m, 'o wrapper do fetch sumiu do base.js'
    return m.group(0)


@pytest.mark.skipif(not shutil.which('node'), reason='sem node para rodar o JS')
def test_wrapper_do_fetch_nao_manda_o_token_para_outro_site(auth_client):
    codigo = _wrapper_do_fetch(_scripts_do_base(auth_client))
    harness = '''
const enviados = [];
globalThis.location = new URL('https://app.com/passagem-de-turno/');
globalThis.document = {querySelector: () => ({content: 'TOKEN'})};
globalThis.window = globalThis;
globalThis.fetch = (input, init) => { enviados.push(init && init.headers
  ? new Headers(init.headers).get('X-CSRFToken') : null); return Promise.resolve(); };
''' + codigo + '''
for (const u of ['/api/x', 'https://app.com/api/x', '//evil.com/x',
                 'https://app.com.evil.io/x', 'https://evil.com/x']) {
  window.fetch(u, {method: 'POST'});
}
console.log(JSON.stringify(enviados));
'''
    saida = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=30)
    assert saida.returncode == 0, saida.stderr
    assert json.loads(saida.stdout) == ['TOKEN', 'TOKEN', None, None, None]


def test_menu_tem_rotulo_curto_e_marca_o_modulo_aberto(auth_client):
    html = auth_client.get('/chamados/').get_data(as_text=True)
    nav = re.search(r'<nav class="fc-nav".*?</nav>', html, re.S).group(0)
    # "Contratos" virou "Locais" na Fase 1 (cliente → local), e entrou "Cadastros".
    for modulo in ('Chamados', 'Cadastros', 'Locais', 'Pessoas'):
        assert f'>{modulo}</a>' in nav
    assert '<span class="fc-rot-curto">Passagem</span>' in nav
    assert re.search(r'class="ativo"\s+aria-current="page">Chamados</a>', nav)


def _css():
    with open(os.path.join(RAIZ, 'facilities', 'static', 'css', 'app.css'), encoding='utf-8') as f:
        return f.read()


def _bloco_720(css):
    """As regras dos blocos @media (max-width: 720px), juntas."""
    blocos = re.findall(r'@media \(max-width: 720px\) \{(.*?)\n\}', css, re.S)
    return '\n'.join(blocos)


def test_css_menu_do_celular_mostra_todos_os_modulos():
    bloco = _bloco_720(_css())
    regra = re.search(r'\.fc-nav \{([^}]*)\}', bloco).group(1)
    assert 'display: grid' in regra and 'overflow: visible' in regra
    assert '.fc-rot-curto { display: inline; }' in bloco


def test_css_abas_dos_chamados_quebram_linha_no_celular():
    regra = re.search(r'\.ch-abas \{([^}]*)\}', _bloco_720(_css())).group(1)
    assert 'flex-wrap: wrap' in regra and 'overflow: visible' in regra
