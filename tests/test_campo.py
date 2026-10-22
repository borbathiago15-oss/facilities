"""Fase 3 — o aplicativo de campo (``/app/``).

* depois do login, o pessoal do posto cai no aplicativo e a gestão no site
  (o ``next`` pedido continua valendo para todos);
* o início do posto mostra só o que é da carteira da pessoa;
* o aplicativo tem manifesto próprio, abre sem internet (service worker) e
  o leitor só aceita QR do próprio sistema.
"""
import json
import os
import subprocess

from facilities import tempo
from tests import fabrica

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _login(app_module, email, proximo=None):
    c = app_module.app.test_client()
    url = '/login' + (f'?next={proximo}' if proximo else '')
    r = c.post(url, data={'email': email, 'password': fabrica.SENHA})
    return c, r


def test_cada_perfil_cai_na_sua_porta(app_module):
    casos = {'encarregado': '/app/', 'tecnico': '/app/', 'supervisor': '/app/',
             'pleno': '/', 'gerente': '/', 'visualizador': '/'}
    for papel, destino in casos.items():
        email = f'porta.{papel}@trino.com'
        with app_module.app.app_context():
            fabrica.pessoa(app_module, email, papel, locais=['Shopping Centro'])
        _, r = _login(app_module, email)
        assert r.status_code == 302
        assert r.headers['Location'] == destino, papel
    _, r = _login(app_module, 'porta.encarregado@trino.com', proximo='/chamados/')
    assert r.headers['Location'] == '/chamados/'


def test_inicio_do_posto_so_mostra_a_carteira(app_module, auth_client):
    from app import db
    from facilities.passagem.models import DiarioPendencia
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        for nome in ('Shopping Centro', 'Hospital Norte'):
            db.session.add(DiarioPendencia(client_id=fabrica.local(nome).id,
                                           titulo=f'Pendência do {nome}', created_by=admin.id))
        db.session.commit()
        fabrica.pessoa(app_module, 'posto.app@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'posto.app@trino.com')
    html = c.get('/app/').get_data(as_text=True)
    assert 'Pendência do Shopping Centro' in html
    assert 'Pendência do Hospital Norte' not in html
    assert 'Ler o QR do local' in html
    assert tempo.fmt(tempo.agora(), '%d/%m/%Y') in html


def test_aplicativo_exige_login_mas_manifesto_e_guia_sao_publicos(app_module):
    c = app_module.app.test_client()
    assert c.get('/app/').status_code == 302
    assert c.get('/app/ler-qr').status_code == 302
    r = c.get('/app/manifest.webmanifest')
    assert r.status_code == 200 and r.mimetype == 'application/manifest+json'
    m = json.loads(r.get_data(as_text=True))
    assert m['id'] == '/app/' and m['start_url'].startswith('/app/')
    assert m['display'] == 'standalone'
    assert 'Adicionar à Tela de Início' in c.get('/app/instalar').get_data(as_text=True)


def test_telas_do_aplicativo_usam_o_manifesto_do_campo(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'manif.app@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'manif.app@trino.com')
    for url in ('/app/', '/app/ler-qr'):
        html = c.get(url).get_data(as_text=True)
        assert 'href="/app/manifest.webmanifest"' in html
        assert 'class="fc-app-nav"' in html
    assert 'vendor/jsqr/jsQR.js' in c.get('/app/ler-qr').get_data(as_text=True)
    # O site continua com o manifesto dele.
    assert 'href="/manifest.webmanifest"' in c.get('/chamados/').get_data(as_text=True)


def test_service_worker_guarda_as_telas_do_aplicativo():
    with open(os.path.join(RAIZ, 'facilities', 'static', 'pwa', 'sw.js'), encoding='utf-8') as f:
        sw = f.read()
    assert r'/^\/app\/?$/' in sw and r'/^\/app\/ler-qr\/?$/' in sw


def test_jsqr_tem_a_licenca_conferida():
    pasta = os.path.join(RAIZ, 'facilities', 'static', 'vendor', 'jsqr')
    with open(os.path.join(pasta, 'LICENSE'), encoding='utf-8') as f:
        assert 'Apache License' in f.read()
    import hashlib
    with open(os.path.join(pasta, 'jsQR.js'), 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == \
            'bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859'


def test_leitor_so_aceita_qr_do_proprio_sistema():
    """O ``destino()`` do leitor, rodado no Node com um DOM de mentira."""
    with open(os.path.join(RAIZ, 'facilities', 'static', 'js', 'leitor-qr.js'),
              encoding='utf-8') as f:
        codigo = f.read()
    harness = '''
const el = () => ({addEventListener(){}, hidden: false, textContent: ''});
global.location = {href: 'https://facilities.trino.com/app/ler-qr',
                   origin: 'https://facilities.trino.com', assign(){}};
global.document = {getElementById: el, addEventListener(){}};
global.window = global; global.navigator = {}; global.addEventListener = () => {};
global.requestAnimationFrame = () => {};
''' + codigo + '''
const d = window.TrinoLeitorQR.destino;
console.log(JSON.stringify([
  d('https://facilities.trino.com/q/yKRZYpIynxphxvqui581Iw'),
  d('/q/yKRZYpIynxphxvqui581Iw'),
  d('https://outro.site/q/yKRZYpIynxphxvqui581Iw'),
  d('https://facilities.trino.com.golpe.io/q/yKRZYpIynxphxvqui581Iw'),
  d('https://facilities.trino.com/admin/usuarios'),
  d('javascript:alert(1)'),
  d('https://facilities.trino.com/q/../admin'),
]));
'''
    saida = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=30)
    assert saida.returncode == 0, saida.stderr
    assert json.loads(saida.stdout) == ['/q/yKRZYpIynxphxvqui581Iw',
                                        '/q/yKRZYpIynxphxvqui581Iw',
                                        None, None, None, None, None]


def test_aviso_do_publico_diz_o_local(app_module):
    """Dois locais com um ambiente de mesmo nome: sem o local, as duas linhas
    de "Avisos do público" ficavam idênticas (visto na gravação de 22/10/2026)."""
    from app import db
    from facilities.cadastros import servico
    from facilities.rotas import ocorrencias
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        pontos = []
        for nome in ('Shopping Centro', 'Hospital Norte'):
            loc = fabrica.local(nome)
            setor = servico.salvar_setor(loc, None, {'nome': 'Operação'}, admin.id)
            amb = servico.salvar_ambiente(loc, None, {'nome': 'Banheiro da operação 1',
                                                      'setor_id': setor.id}, admin.id)
            pontos.append(servico.salvar_ponto(loc, None, {'nome': 'Entrada',
                                                           'ambiente_id': amb.id}, admin.id).id)
        db.session.commit()
        for pid in pontos:
            ocorrencias.abrir(db.session.get(PontoInspecao, pid), 'vazamento', '')
        db.session.commit()
        fabrica.pessoa(app_module, 'dois.locais@trino.com', 'encarregado',
                       locais=['Shopping Centro', 'Hospital Norte'])
    c = fabrica.entrar(app_module, 'dois.locais@trino.com')
    html = c.get('/app/').get_data(as_text=True)
    assert 'Avisos do público (2)' in html
    assert 'Shopping Centro · Banheiro da operação 1 · Vazamento ou entupimento' in html
    assert 'Hospital Norte · Banheiro da operação 1 · Vazamento ou entupimento' in html
