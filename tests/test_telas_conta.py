"""A conta, os avisos, o Início e a administração (pessoas e locais) nas
telas novas (Fase 6a).

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* a mesma porta (a administração: só o administrador; as travas da sessão
  levam às telas antigas; a conta de cliente abre a conta e os avisos);
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``);
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* o segredo da segunda etapa e a senha temporária: a leitura nunca os traz;
  só a resposta do envio que os cria, sem cópia (``no-store``) e sem recado;
* a senha atual errada conta no MESMO contador nas duas telas (o bloqueio
  da conta), e a sessão gira do mesmo jeito.
"""
import html as html_mod
import re

import pytest

from tests import fabrica
from tests.conftest import ADMIN_EMAIL

MODULOS = ('facilities.telas.conta', 'facilities.telas.administracao')
SENHA = fabrica.SENHA


def _texto(html):
    return html_mod.unescape(re.sub(r'\s+', ' ', html))


def _flashes(c):
    with c.session_transaction() as s:
        return [{'tipo': 'danger' if t == 'error' else t, 'texto': x}
                for t, x in s.pop('_flashes', [])]


def _antiga(c, url, **kw):
    r = c.post(url, **kw)
    assert r.status_code == 302, (url, r.status_code, r.get_data(as_text=True)[:300])
    return r.headers.get('Location', ''), _flashes(c)


def _nova(c, url, **kw):
    r = c.post(url, **kw)
    assert r.is_json, (url, r.status_code, r.get_data(as_text=True)[:300])
    return r, r.get_json()


def _par(c, antiga, nova, dados_antigo, dados_novo=None, json=False):
    """O mesmo envio pela tela antiga e pela nova: o mesmo recado, o mesmo
    destino (abaixo de /novo) e, na recusa, 400 com a mesma frase."""
    d1, rec = _antiga(c, antiga, data=dados_antigo)
    corpo = dados_novo if dados_novo is not None else dados_antigo
    r, j = _nova(c, nova, **({'json': corpo} if json else {'data': corpo}))
    assert j['recados'] == rec, (nova, j['recados'], rec)
    assert j['destino'] == '/novo' + d1, (nova, j['destino'], d1)
    recusou = any(x['tipo'] == 'danger' for x in rec)
    assert r.status_code == (400 if recusou else 200), (nova, rec)
    if recusou:
        assert j['error'] == j['recados'][0]['texto']
    return d1, rec, j


def _pessoa(app_module, email, papel='encarregado', **extra):
    with app_module.app.app_context():
        return fabrica.pessoa(app_module, email, papel, **extra)


def _usuario(app_module, uid):
    from app import User, db
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        db.session.expunge(u)
        return u


def _admin_id(app_module):
    from app import User
    with app_module.app.app_context():
        return User.query.filter_by(email=ADMIN_EMAIL).one().id


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo not in MODULOS:
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len(rotas) >= 24
    for m, caminho in rotas:
        r = getattr(client, m.lower())(caminho)
        if caminho.startswith('/api/v1/') or m != 'GET':
            assert r.status_code == 401 and r.is_json, (m, caminho, r.status_code)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], caminho


def test_as_paginas_entregam_a_casca(app_module, auth_client, monkeypatch):
    from facilities import telas
    monkeypatch.setattr(telas, '_manifesto', lambda: {telas.ENTRADA: {'file': 'x.js'}})
    for caminho in ('/novo/', '/novo/avisos', '/novo/conta/seguranca', '/novo/trocar-senha',
                    '/novo/admin/usuarios', '/novo/admin/contratos'):
        r = auth_client.get(caminho)
        assert r.status_code == 200 and '/static/app/x.js' in r.get_data(as_text=True), caminho


@pytest.mark.parametrize('papel', ['visualizador', 'gerente', 'pleno', 'supervisor',
                                   'encarregado', 'tecnico'])
def test_a_administracao_e_so_do_administrador(app_module, papel):
    _pessoa(app_module, f'adm.{papel}@trino.com', papel)
    c = fabrica.entrar(app_module, f'adm.{papel}@trino.com')
    for antiga, nova, api in (('/admin/usuarios', '/novo/admin/usuarios', '/api/v1/admin/usuarios'),
                              ('/admin/contratos', '/novo/admin/contratos',
                               '/api/v1/admin/contratos')):
        assert c.get(antiga).status_code == 302
        assert c.get(nova).status_code == 302          # a mesma volta ao início
        r = c.get(api)
        assert r.status_code == 403 and r.get_json() == {'error': 'Acesso restrito ao administrador.'}
    uid = _admin_id(app_module)
    for url in ('/api/v1/admin/usuarios', f'/api/v1/admin/usuarios/{uid}',
                f'/api/v1/admin/usuarios/{uid}/nova-senha',
                f'/api/v1/admin/usuarios/{uid}/desligar-codigo', '/api/v1/admin/contratos',
                '/api/v1/admin/contratos/1'):
        r = c.post(url, data={'name': 'x', 'email': 'x@x.com', 'role': 'master'})
        assert r.status_code == 403, url
    u = _usuario(app_module, uid)
    assert u.role == 'master' and u.check_password(__import__('os').environ['ADMIN_PASSWORD'])


def test_as_travas_da_sessao_levam_as_telas_antigas(app_module):
    """Com a senha a trocar ou a segunda etapa obrigatória ainda não ativada,
    as travas só abrem as telas antigas (a casca nova precisa do
    ``/api/v1/eu``, que a trava não abre); a API responde JSON."""
    from app import User, db
    _pessoa(app_module, 'trava.senha@trino.com', 'pleno')
    c = fabrica.entrar(app_module, 'trava.senha@trino.com')
    with app_module.app.app_context():
        u = User.query.filter_by(email='trava.senha@trino.com').one()
        u.must_change_password = True
        db.session.commit()
        uid = u.id
    for pagina in ('/novo/trocar-senha', '/novo/conta/seguranca', '/novo/'):
        r = c.get(pagina)
        assert r.status_code == 302 and r.headers['Location'].endswith('/trocar-senha'), pagina
    for api in ('/api/v1/trocar-senha', '/api/v1/conta/seguranca'):
        assert c.get(api).get_json() == {'error': 'Troque a sua senha antes de continuar.'}
    r = c.post('/api/v1/trocar-senha', data={'atual': SENHA, 'nova': 'Outra-senha-9x',
                                              'confirma': 'Outra-senha-9x'})
    assert r.status_code == 403
    assert _usuario(app_module, uid).must_change_password is True
    # A segunda etapa obrigatória (gestão), antes de ativar.
    _pessoa(app_module, 'trava.mfa@trino.com', 'gerente')
    c = fabrica.entrar(app_module, 'trava.mfa@trino.com')
    app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = True
    for pagina in ('/novo/conta/seguranca', '/novo/trocar-senha', '/novo/'):
        r = c.get(pagina)
        assert r.status_code == 302 and r.headers['Location'].endswith('/conta/seguranca'), pagina
    r = c.post('/api/v1/conta/seguranca/codigo-novo')
    assert r.status_code == 403 and 'segredo' not in r.get_data(as_text=True)
    assert c.get('/conta/seguranca').status_code == 200        # a antiga abre


def test_a_conta_de_cliente_abre_a_conta_e_os_avisos(app_module):
    from facilities.cadastros import servico as cad
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        emp = cad.salvar_empresa(None, {'nome': 'Empresa do teste'}, None)
        k = cad.salvar_contratante(None, {'nome': 'Cliente do teste', 'empresa_id': emp.id}, None)
        app_module.db.session.commit()
        fabrica.cliente(app_module, 'cliente.conta@x.com', k.id)
    c = fabrica.entrar_com_codigo(app_module, 'cliente.conta@x.com')
    r = c.get('/novo/')
    assert r.status_code == 302 and r.headers['Location'].endswith('/novo/cliente/')
    assert c.get('/').headers['Location'].endswith('/cliente/')
    for url in ('/api/v1/avisos', '/api/v1/conta/seguranca', '/api/v1/trocar-senha'):
        assert c.get(url).status_code == 200, url
    assert c.post('/api/v1/avisos/ler-todos').status_code == 200
    # Como na antiga: no perfil do cliente, desligar a etapa nem chega à regra.
    assert c.post('/conta/seguranca/desativar', data={'senha': SENHA}).status_code == 403
    r = c.post('/api/v1/conta/seguranca/desativar', data={'senha': SENHA})
    assert r.status_code == 403
    assert c.get('/api/v1/inicio').status_code == 403
    assert c.get('/api/v1/admin/usuarios').status_code == 403
    assert c.get('/novo/admin/usuarios').status_code == 403


# ── O Início ──────────────────────────────────────────────────────────────

def test_o_inicio_traz_o_que_a_tela_antiga_mostra(app_module, auth_client):
    from app import User, db
    from facilities.chamados import servico as chs
    with app_module.app.app_context():
        admin = User.query.filter_by(email=ADMIN_EMAIL).one()
        chs.abrir(admin, fabrica.local().id, 'Torneira pingando', prioridade='alta')
        db.session.commit()
    d = auth_client.get('/api/v1/inicio').get_json()
    texto = _texto(auth_client.get('/').get_data(as_text=True))
    assert f'Olá, {d["primeiro_nome"]}' in texto
    assert f'{d["data"]} · {d["perfil"]}' in texto and d['locais_na_carteira'] is None
    assert d['abrir_chamado'] == '/novo/chamados/novo'
    assert [x['rotulo'] for x in d['numeros']] == re.findall(r'<span class="fc-numero-r">([^<]+)</span>', texto)
    assert [str(x['n']) for x in d['numeros']] == re.findall(r'<span class="fc-numero-n">(\d+)</span>', texto)
    assert [x['url'] for x in d['numeros']] == [
        '/novo' + u for u in re.findall(r'<a class="fc-numero[^"]*" href="([^"]+)"', texto)]
    assert [x['nome'] for x in d['atalhos']] == re.findall(r'<h3>([^<]+)</h3> <p>', texto)
    assert [x['url'] for x in d['atalhos']] == [
        '/novo' + u if not u.startswith('/passagem') else u
        for u in re.findall(r'<a class="fc-cartao fc-modulo" href="([^"]+)"', texto)]
    assert d['primeiro'] and d['primeiro'][0]['titulo'] == 'Torneira pingando'
    p = d['primeiro'][0]
    assert f'{p["situacao_rotulo"]}</span>' in texto and p['link'].startswith('/novo/chamados/')
    assert f'{p["tipo_rotulo"]} · {p["numero"]}</span>Torneira pingando' in texto
    assert (p['prazo'] in texto) and re.fullmatch(r'\d\d/\d\d \d\d:\d\d', p['prazo'])
    assert d['administrador']['pessoas'] == '/novo/admin/usuarios'
    assert 'Primeiros passos do administrador' in texto


def test_o_inicio_de_quem_tem_carteira(app_module):
    _pessoa(app_module, 'inicio.sup@trino.com', 'supervisor', locais=['Shopping Centro'],
            nome='Sara Supervisora')
    c = fabrica.entrar(app_module, 'inicio.sup@trino.com')
    d = c.get('/api/v1/inicio').get_json()
    texto = _texto(c.get('/').get_data(as_text=True))
    assert d['primeiro_nome'] == 'Sara' and d['locais_na_carteira'] == 1
    assert '· 1 local(is) na sua carteira' in texto
    assert d['administrador'] is None and 'Primeiros passos' not in texto
    assert (d['abrir_chamado'] is None) == ('Abrir chamado' not in texto)


# ── Os avisos ─────────────────────────────────────────────────────────────

def _aviso(app_module, uid, titulo, link='/chamados/', status='unread'):
    from app import db
    from facilities.core.models import Notification
    with app_module.app.app_context():
        n = Notification(user_id=uid, title=titulo, message='m ' + titulo, link=link,
                         status=status)
        db.session.add(n)
        db.session.commit()
        return n.id


def test_os_avisos_trazem_o_que_a_tela_antiga_mostra(app_module, auth_client):
    uid = _admin_id(app_module)
    _aviso(app_module, uid, 'Lido', status='read')
    _aviso(app_module, uid, 'Novo')
    outro = _pessoa(app_module, 'aviso.outro@trino.com')
    _aviso(app_module, outro, 'De outra pessoa')
    d = auth_client.get('/api/v1/avisos').get_json()
    texto = _texto(auth_client.get('/avisos').get_data(as_text=True))
    assert [a['titulo'] for a in d['avisos']] == re.findall(r'<h3>([^<]+)</h3>', texto)
    assert 'De outra pessoa' not in str(d)
    assert [a['em'] for a in d['avisos']] == re.findall(r'<time>([^<]+)</time>', texto)
    assert [a['nao_lido'] for a in d['avisos']] == [
        'nao-lido' in x for x in re.findall(r'class="fc-aviso [^"]+"', texto)]
    assert d['nao_lidos'] == 1 and 'Marcar todos como lidos' in texto


def test_abrir_e_ler_todos_como_na_tela_antiga(app_module, auth_client):
    from facilities.core.models import Notification
    uid = _admin_id(app_module)
    a1 = _aviso(app_module, uid, 'Um', link='/passagem-de-turno/')
    a2 = _aviso(app_module, uid, 'Dois', link='/passagem-de-turno/')
    loc, rec = _antiga(auth_client, f'/avisos/{a1}/abrir')
    r, j = _nova(auth_client, f'/api/v1/avisos/{a2}/abrir')
    assert loc.endswith('/passagem-de-turno/') and j == {'recados': [], 'destino': '/passagem-de-turno/'}
    # O link já migrado leva à tela nova; o link de fora vira a lista.
    a3 = _aviso(app_module, uid, 'Três', link='/chamados/5')
    a4 = _aviso(app_module, uid, 'Quatro', link='//outro.site/x')
    assert _nova(auth_client, f'/api/v1/avisos/{a3}/abrir')[1]['destino'] == '/novo/chamados/5'
    assert _nova(auth_client, f'/api/v1/avisos/{a4}/abrir')[1]['destino'] == '/novo/avisos'
    with app_module.app.app_context():
        assert {Notification.query.get(x).status for x in (a1, a2, a3, a4)} == {'read'}
    # O aviso de outra pessoa: 404 nas duas, e ele continua não lido.
    outro = _aviso(app_module, _pessoa(app_module, 'aviso.b@trino.com'), 'Alheio')
    assert auth_client.post(f'/avisos/{outro}/abrir').status_code == 404
    assert auth_client.post(f'/api/v1/avisos/{outro}/abrir').status_code == 404
    _aviso(app_module, uid, 'Cinco')
    _par(auth_client, '/avisos/ler-todos', '/api/v1/avisos/ler-todos', {})
    with app_module.app.app_context():
        assert Notification.query.filter_by(user_id=uid, status='unread').count() == 0
        assert Notification.query.get(outro).status == 'unread'


# ── A segunda etapa ───────────────────────────────────────────────────────

def _segredo_da_pagina(html):
    m = re.search(r'<code class="user-select-all">([A-Z2-7]+)</code>', html)
    return m.group(1) if m else None


def test_a_leitura_nunca_traz_o_segredo(app_module):
    _pessoa(app_module, 'mfa.leitura@trino.com', 'pleno')
    c = fabrica.entrar(app_module, 'mfa.leitura@trino.com')
    r = c.get('/api/v1/conta/seguranca')
    assert r.get_json() == {'ativo': False} and r.headers['Cache-Control'] == 'no-store'
    segredo = _segredo_da_pagina(c.get('/conta/seguranca').get_data(as_text=True))
    assert segredo
    # O envio que prepara traz o MESMO segredo da tela antiga (o da sessão).
    r = c.post('/api/v1/conta/seguranca/codigo-novo')
    assert r.headers['Cache-Control'] == 'no-store'
    novo = r.get_json()['novo']
    assert novo['segredo'] == segredo and novo['qr'].startswith('<svg') and '<script' not in novo['qr']
    assert c.post('/api/v1/conta/seguranca/codigo-novo').get_json()['novo']['segredo'] == segredo
    assert _flashes(c) == []
    for url in ('/api/v1/conta/seguranca', '/api/v1/eu', '/novo/conta/seguranca'):
        assert segredo not in c.get(url).get_data(as_text=True), url


def test_ativar_pela_tela_nova_como_na_antiga(app_module):
    from facilities.core import totp
    uid = _pessoa(app_module, 'mfa.ativar@trino.com', 'pleno')
    c = fabrica.entrar(app_module, 'mfa.ativar@trino.com')
    outro = fabrica.entrar(app_module, 'mfa.ativar@trino.com')
    # Sem segredo preparado: volta à tela, sem recado (as duas).
    _par(c, '/conta/seguranca/ativar', '/api/v1/conta/seguranca/ativar',
         {'codigo': '123456', 'senha': SENHA})
    segredo = c.post('/api/v1/conta/seguranca/codigo-novo').get_json()['novo']['segredo']
    # Código errado: o mesmo recado.
    _par(c, '/conta/seguranca/ativar', '/api/v1/conta/seguranca/ativar',
         {'codigo': '000000', 'senha': SENHA})
    epoca = _usuario(app_module, uid).session_epoch or 0
    r, j = _nova(c, '/api/v1/conta/seguranca/ativar', json={'codigo': totp.codigo(segredo),
                                                            'senha': SENHA})
    assert r.status_code == 200 and j == {'recados': [{'tipo': 'success', 'texto':
        'Segunda etapa ativada. A partir de agora, o login pede a senha e o código do aplicativo.'}],
        'destino': '/novo/conta/seguranca'}
    u = _usuario(app_module, uid)
    assert u.totp_ativo and u.totp_segredo == segredo and u.session_epoch == epoca + 1
    # Este aparelho segue logado (a sessão girou); o outro caiu.
    assert c.get('/api/v1/conta/seguranca').get_json() == {'ativo': True}
    assert outro.get('/api/v1/eu').status_code == 401
    # Ativada: nenhum segredo novo, e o da sessão foi embora.
    assert c.post('/api/v1/conta/seguranca/codigo-novo').get_json() == {'novo': None}
    with c.session_transaction() as s:
        assert '_totp_novo' not in s



def test_ativar_pede_a_senha_atual_nas_duas_telas(app_module):
    """Ativar a segunda etapa pede a senha atual (auditoria da Fase 6a): só
    com a sessão (um cookie copiado, um computador aberto), ninguém cadastra
    o próprio autenticador e tranca o dono fora. Sem a senha, ou com ela
    errada, nada muda, mesmo com o código certo; o erro conta no MESMO
    contador do login, nas duas telas, e o 5º bloqueia e derruba a sessão."""
    from facilities.core import totp
    from facilities.core.auth import MSG_LOGIN_RECUSADO
    uid = _pessoa(app_module, 'mfa.senha@trino.com', 'pleno')
    c = fabrica.entrar(app_module, 'mfa.senha@trino.com')
    outro = fabrica.entrar(app_module, 'mfa.senha@trino.com')
    segredo = c.post('/api/v1/conta/seguranca/codigo-novo').get_json()['novo']['segredo']
    for dados in ({'codigo': totp.codigo(segredo)},
                  {'codigo': totp.codigo(segredo), 'senha': 'errada'}):
        d1, rec, j = _par(c, '/conta/seguranca/ativar', '/api/v1/conta/seguranca/ativar', dados)
        assert d1 == '/conta/seguranca'
        assert rec == [{'tipo': 'danger', 'texto': 'A senha atual não confere.'}]
    u = _usuario(app_module, uid)
    assert not u.totp_ativo and u.failed_login_count == 4
    assert outro.get('/api/v1/eu').status_code == 200        # ninguém caiu
    r, j = _nova(c, '/api/v1/conta/seguranca/ativar', data={'codigo': totp.codigo(segredo),
                                                            'senha': 'errada'})
    assert r.status_code == 400 and j == {'destino': '/login', 'error': MSG_LOGIN_RECUSADO}
    u = _usuario(app_module, uid)
    assert not u.totp_ativo and u.lockout_until is not None
    assert c.get('/api/v1/eu').status_code == 401
    assert MSG_LOGIN_RECUSADO in _texto(c.get('/login').get_data(as_text=True))
    # A tela antiga: o 5º erro leva ao login do mesmo jeito.
    uid2 = _pessoa(app_module, 'mfa.senha2@trino.com', 'pleno')
    c = fabrica.entrar(app_module, 'mfa.senha2@trino.com')
    c.get('/conta/seguranca')
    with app_module.app.app_context():
        from app import User, db
        db.session.get(User, uid2).failed_login_count = 4
        db.session.commit()
    r = c.post('/conta/seguranca/ativar', data={'codigo': '123456', 'senha': 'errada'})
    assert r.status_code == 302 and r.headers['Location'] == '/login'
    assert _usuario(app_module, uid2).lockout_until is not None
    assert c.get('/api/v1/eu').status_code == 401


def test_as_telas_de_seguranca_pedem_a_senha_atual(app_module):
    _pessoa(app_module, 'mfa.campo@trino.com', 'encarregado')
    c = fabrica.entrar(app_module, 'mfa.campo@trino.com')
    html = c.get('/conta/seguranca').get_data(as_text=True)
    form = re.search(r'<form method="post" action="/conta/seguranca/ativar">(.*?)</form>',
                     html, re.S).group(1)
    assert 'Sua senha atual' in form
    assert re.search(r'<input[^>]*name="senha"[^>]*type="password"[^>]*required', form)

def test_desativar_como_na_tela_antiga(app_module):
    from facilities.core import totp
    uid = _pessoa(app_module, 'mfa.desativar@trino.com', 'encarregado')

    def ligar():
        from app import User, db
        with app_module.app.app_context():
            u = db.session.get(User, uid)
            u.totp_ativo, u.totp_segredo, u.totp_ultimo_passo = True, totp.novo_segredo(), None
            u.failed_login_count = 0
            db.session.commit()
    c = fabrica.entrar(app_module, 'mfa.desativar@trino.com')
    ligar()
    _par(c, '/conta/seguranca/desativar', '/api/v1/conta/seguranca/desativar', {'senha': 'errada'})
    assert _usuario(app_module, uid).failed_login_count == 2      # as duas contam
    _par(c, '/conta/seguranca/desativar', '/api/v1/conta/seguranca/desativar', {'senha': SENHA},
         dados_novo={'senha': SENHA})
    assert not _usuario(app_module, uid).totp_ativo
    ligar()
    r, j = _nova(c, '/api/v1/conta/seguranca/desativar', json={'senha': SENHA})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Segunda etapa desativada.'}]
    u = _usuario(app_module, uid)
    assert not u.totp_ativo and u.totp_segredo is None
    # Obrigatória no perfil: o mesmo aviso, e nada muda.
    ligar()
    app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = True
    with app_module.app.app_context():
        from app import User, db
        db.session.get(User, uid).role = 'pleno'
        db.session.commit()
    _par(c, '/conta/seguranca/desativar', '/api/v1/conta/seguranca/desativar', {'senha': SENHA})
    assert _usuario(app_module, uid).totp_ativo


# ── Trocar a senha ────────────────────────────────────────────────────────

def test_trocar_a_senha_recusa_como_a_tela_antiga(app_module):
    uid = _pessoa(app_module, 'senha.recusa@trino.com', 'supervisor')
    c = fabrica.entrar(app_module, 'senha.recusa@trino.com')
    casos = [
        ({'atual': SENHA, 'nova': 'curta', 'confirma': 'curta'},
         'A senha nova precisa ter pelo menos 8 caracteres.'),
        ({'atual': SENHA, 'nova': 'Uma-senha-boa-9', 'confirma': 'Outra-senha-boa-9'},
         'A confirmação não é igual à senha nova.'),
        ({'atual': SENHA, 'nova': SENHA, 'confirma': SENHA},
         'A senha nova precisa ser diferente da atual.'),
        ({'atual': SENHA, 'nova': '12345678', 'confirma': '12345678'}, None),
        ({'atual': 'errada', 'nova': 'Uma-senha-boa-9', 'confirma': 'Uma-senha-boa-9'},
         'A senha atual não confere.'),
    ]
    for dados, frase in casos:
        antiga = c.post('/trocar-senha', data=dados)
        assert antiga.status_code == 400
        recado = _texto(antiga.get_data(as_text=True))
        r, j = _nova(c, '/api/v1/trocar-senha', data=dados)
        assert r.status_code == 400 and j['destino'] is None
        assert j['recados'] == [{'tipo': 'danger', 'texto': j['error']}]
        assert j['error'] in recado
        if frase:
            assert j['error'] == frase
    assert _usuario(app_module, uid).check_password(SENHA)
    assert _usuario(app_module, uid).failed_login_count == 2


def test_trocar_a_senha_gira_a_sessao_como_a_tela_antiga(app_module):
    uid = _pessoa(app_module, 'senha.troca@trino.com', 'supervisor')
    c = fabrica.entrar(app_module, 'senha.troca@trino.com')
    outro = fabrica.entrar(app_module, 'senha.troca@trino.com')
    epoca = _usuario(app_module, uid).session_epoch or 0
    r, j = _nova(c, '/api/v1/trocar-senha', json={'atual': SENHA, 'nova': 'Nova-senha-do-teste-7',
                                                   'confirma': 'Nova-senha-do-teste-7'})
    assert r.status_code == 200
    assert j == {'recados': [{'tipo': 'success', 'texto': 'Senha trocada.'}], 'destino': '/novo/'}
    u = _usuario(app_module, uid)
    assert u.check_password('Nova-senha-do-teste-7') and u.session_epoch == epoca + 1
    assert not u.must_change_password
    assert c.get('/api/v1/trocar-senha').status_code == 200        # este aparelho segue
    assert outro.get('/api/v1/eu').status_code == 401              # o outro caiu
    # A antiga, do mesmo jeito.
    antiga = c.post('/trocar-senha', data={'atual': 'Nova-senha-do-teste-7',
                                           'nova': 'Mais-uma-senha-8', 'confirma': 'Mais-uma-senha-8'})
    assert antiga.status_code == 302 and antiga.headers['Location'] == '/'
    assert _usuario(app_module, uid).session_epoch == epoca + 2
    assert c.get('/api/v1/trocar-senha').status_code == 200


def test_o_mesmo_bloqueio_por_senha_errada_nas_duas_telas(app_module):
    """A senha atual errada (trocar a senha, desligar o código) conta no
    MESMO contador nas duas telas — o do banco: 5 erros, somando a antiga e a
    nova, bloqueiam a conta e derrubam a sessão. Com um contador por tela,
    quem roubou a sessão teria o dobro de tentativas."""
    uid = _pessoa(app_module, 'senha.bloqueio@trino.com', 'encarregado')
    c = fabrica.entrar(app_module, 'senha.bloqueio@trino.com')
    errada = {'atual': 'errada', 'nova': 'Uma-senha-boa-9', 'confirma': 'Uma-senha-boa-9'}
    for _ in range(2):
        assert c.post('/trocar-senha', data=errada).status_code == 400
    assert c.post('/conta/seguranca/desativar', data={'senha': 'errada'}).status_code == 302
    _flashes(c)
    assert _nova(c, '/api/v1/conta/seguranca/desativar', data={'senha': 'errada'})[0].status_code == 400
    assert _usuario(app_module, uid).failed_login_count == 4
    r, j = _nova(c, '/api/v1/trocar-senha', data=errada)       # o 5º: bloqueia
    from facilities.core.auth import MSG_LOGIN_RECUSADO
    assert r.status_code == 400 and j == {'destino': '/login', 'error': MSG_LOGIN_RECUSADO}
    u = _usuario(app_module, uid)
    assert u.lockout_until is not None and u.failed_login_count == 0
    assert c.get('/api/v1/eu').status_code == 401
    # O recado ficou para a tela de login, como na antiga.
    assert MSG_LOGIN_RECUSADO in _texto(c.get('/login').get_data(as_text=True))


def test_nenhuma_das_rotas_tem_limite_proprio_como_nas_antigas(app_module):
    """As rotas antigas da conta e da administração não têm limite do
    Flask-Limiter (a proteção da senha é o bloqueio da conta, acima); as novas
    também não — nenhuma tela soma nem dobra limite."""
    from facilities.extensions import limiter
    marcadas = {k.rsplit('.', 1)[-1] for k in limiter.limit_manager._decorated_limits}
    antigas = {'trocar_senha', 'ativar_codigo', 'desativar_codigo', 'criar_usuario',
               'editar_usuario', 'nova_senha', 'desligar_codigo', 'criar_contrato',
               'editar_contrato', 'abrir_aviso', 'ler_todos'}
    novas = {f.rsplit('.', 1)[-1] for f in app_module.app.view_functions
             if f.startswith('api_v1.') and getattr(app_module.app.view_functions[f], '__module__', '')
             in MODULOS}
    assert len(novas) >= 18
    assert not (antigas | novas) & marcadas


# ── Pessoas ──────────────────────────────────────────────────────────────

def test_a_lista_das_pessoas_traz_os_dados_da_tela_antiga(app_module, auth_client):
    from app import User, db
    sup = _pessoa(app_module, 'lista.sup@trino.com', 'supervisor', nome='Sueli Supervisora')
    _pessoa(app_module, 'lista.enc@trino.com', 'encarregado', locais=['Shopping Centro'],
            nome='Eva Encarregada')
    with app_module.app.app_context():
        enc = User.query.filter_by(email='lista.enc@trino.com').one()
        enc.superior_id = sup
        enc.totp_ativo = True
        db.session.commit()
    d = auth_client.get('/api/v1/admin/usuarios').get_json()
    texto = _texto(auth_client.get('/admin/usuarios').get_data(as_text=True))
    assert [p['nome'] for p in d['pessoas']] == re.findall(r'<summary class="d-flex[^"]*"> <strong>([^<]+)</strong>', texto)
    assert [p['email'] for p in d['pessoas']] == re.findall(r'</span>(?: <span class="badge text-bg-secondary">inativo</span>)? <span class="small text-muted">([^<]+@[^<]+)</span>', texto)
    eva = next(p for p in d['pessoas'] if p['nome'] == 'Eva Encarregada')
    assert eva['alcance'] == '1 local(is) direto(s)' and eva['segunda_etapa']
    assert eva['cadeia'] == [{'nome': 'Sueli Supervisora', 'perfil': 'Supervisor'}]
    assert 'Cadeia: Sueli Supervisora (Supervisor) › Eva Encarregada' in texto
    # A ordem é a do banco (ORDER BY name, que segue a collation do Postgres:
    # en_US ignora espaço e caixa; o sorted() do Python não): compara com a
    # lista do primeiro "Superior" da tela antiga, que sai da mesma consulta.
    bruto = auth_client.get('/admin/usuarios').get_data(as_text=True)
    sel = re.search(r'name="superior_id">(.*?)</select>', bruto, re.S).group(1)
    na_antiga = [html_mod.unescape(n) for n in re.findall(r'<option value="\d+"[^>]*>([^<]+?) — ', sel)]
    assert [s['nome'] for s in d['superiores']] == na_antiga
    assert d['perfis'][0] == ['master', 'Administrador']
    corpo = auth_client.get('/api/v1/admin/usuarios').get_data(as_text=True)
    assert 'password' not in corpo and 'pbkdf2' not in corpo and 'scrypt' not in corpo


def test_cadastrar_a_senha_so_na_resposta_do_envio(app_module, auth_client):
    from app import User
    fabrica.CRIADAS.update({'nova.pessoa@trino.com', 'antiga.pessoa@trino.com'})
    loc, rec = _antiga(auth_client, '/admin/usuarios', data={
        'name': 'Pessoa Antiga', 'email': 'antiga.pessoa@trino.com', 'role': 'encarregado'})
    assert loc == '/admin/usuarios' and 'Senha temporária:' in rec[0]['texto']
    r, j = _nova(auth_client, '/api/v1/admin/usuarios', data={
        'name': 'Pessoa Nova', 'email': 'NOVA.pessoa@trino.com', 'role': 'supervisor',
        'clients': [str(fabrica_local_id(app_module))]})
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert j['recados'] == [] and j['destino'] == '/novo/admin/usuarios'
    senha = j['senha']['senha']
    assert j['senha']['texto'] == (f'Cadastro de Pessoa Nova criado. Senha temporária: {senha} — '
                                   'entregue pessoalmente; no primeiro acesso o sistema pede uma '
                                   'senha nova.')
    assert re.fullmatch(r'[a-km-zA-HJ-NP-Z2-9]{12}', senha)
    assert _flashes(auth_client) == []                         # nada no cookie da sessão
    with app_module.app.app_context():
        u = User.query.filter_by(email='nova.pessoa@trino.com').one()
        assert u.role == 'supervisor' and u.must_change_password and len(u.clients) == 1
    assert senha not in auth_client.get('/api/v1/admin/usuarios').get_data(as_text=True)
    assert senha not in auth_client.get('/novo/admin/usuarios').get_data(as_text=True)
    novo = app_module.app.test_client()
    assert novo.post('/login', data={'email': 'nova.pessoa@trino.com', 'password': senha}) \
        .headers['Location'].endswith('/trocar-senha')


def fabrica_local_id(app_module):
    with app_module.app.app_context():
        return fabrica.local().id


def test_cadastrar_e_editar_recusam_como_a_tela_antiga(app_module, auth_client):
    _pessoa(app_module, 'existe@trino.com', 'encarregado')
    for dados in ({'name': '', 'email': 'a@b.com'}, {'name': 'X', 'email': 'sem-arroba'},
                  {'name': 'X', 'email': 'existe@trino.com'},
                  {'name': 'X', 'email': 'cli.sem@trino.com', 'role': 'cliente'}):
        loc, rec = _antiga(auth_client, '/admin/usuarios', data=dados)
        r, j = _nova(auth_client, '/api/v1/admin/usuarios', data=dados)
        assert r.status_code == 400 and j['recados'] == rec and j['destino'] == '/novo' + loc
        assert 'senha' not in j
    admin = _admin_id(app_module)
    # Tirar o próprio acesso de administrador: a mesma recusa.
    _par(auth_client, f'/admin/usuarios/{admin}', f'/api/v1/admin/usuarios/{admin}',
         {'name': 'Administrador', 'email': ADMIN_EMAIL, 'role': 'pleno', 'is_active': '1'})
    assert _usuario(app_module, admin).role == 'master'
    uid = _pessoa(app_module, 'editar@trino.com', 'encarregado', nome='Edu')
    outro = fabrica.entrar(app_module, 'editar@trino.com')
    _par(auth_client, f'/admin/usuarios/{uid}', f'/api/v1/admin/usuarios/{uid}',
         {'name': 'Edu Editado', 'email': 'editar@trino.com', 'role': 'tecnico', 'is_active': '1',
          'permissoes': ['diario_config', 'inventada']})
    u = _usuario(app_module, uid)
    assert u.name == 'Edu Editado' and u.role == 'tecnico' and u.permissions == ['diario_config']
    assert outro.get('/api/v1/eu').status_code == 200
    # Desativar derruba as sessões abertas (a nova, como a antiga).
    r, j = _nova(auth_client, f'/api/v1/admin/usuarios/{uid}', json={
        'name': 'Edu Editado', 'email': 'editar@trino.com', 'role': 'tecnico'})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Cadastro de Edu Editado atualizado.'}]
    assert not _usuario(app_module, uid).is_active
    assert outro.get('/api/v1/eu').status_code == 401
    assert auth_client.post('/api/v1/admin/usuarios/999999').status_code == 404


def test_nova_senha_e_desligar_o_codigo_como_a_tela_antiga(app_module, auth_client):
    from app import User, db
    uid = _pessoa(app_module, 'perdeu@trino.com', 'encarregado', nome='Pedro')
    sessao = fabrica.entrar(app_module, 'perdeu@trino.com')
    r, j = _nova(auth_client, f'/api/v1/admin/usuarios/{uid}/nova-senha')
    assert r.headers['Cache-Control'] == 'no-store' and j['recados'] == []
    senha = j['senha']['senha']
    assert j['senha']['texto'] == f'Senha temporária de Pedro: {senha}'
    assert _flashes(auth_client) == []
    u = _usuario(app_module, uid)
    assert u.check_password(senha) and u.must_change_password
    assert sessao.get('/api/v1/eu').status_code == 401
    loc, rec = _antiga(auth_client, f'/admin/usuarios/{uid}/nova-senha')
    assert rec[0]['texto'].startswith('Senha temporária de Pedro: ')
    with app_module.app.app_context():
        u = db.session.get(User, uid)
        u.totp_ativo, u.totp_segredo = True, 'JBSWY3DPEHPK3PXP'
        db.session.commit()
    d1, rec, j = _par(auth_client, f'/admin/usuarios/{uid}/desligar-codigo',
                      f'/api/v1/admin/usuarios/{uid}/desligar-codigo', {})
    assert rec[0]['texto'].startswith('Segunda etapa de Pedro desligada.')
    u = _usuario(app_module, uid)
    assert not u.totp_ativo and u.totp_segredo is None
    assert auth_client.post('/api/v1/admin/usuarios/999999/nova-senha').status_code == 404


# ── Locais ───────────────────────────────────────────────────────────────

@pytest.fixture()
def apagar_locais(app_module):
    nomes = []
    yield nomes
    from app import Client, db
    with app_module.app.app_context():
        for c in Client.query.filter(Client.name.in_(nomes)):
            c.is_active, c.is_deleted = False, True
        db.session.commit()


def test_a_lista_dos_locais_traz_os_dados_da_tela_antiga(app_module, auth_client):
    d = auth_client.get('/api/v1/admin/contratos').get_json()
    texto = _texto(auth_client.get('/admin/contratos').get_data(as_text=True))
    assert [x['nome'] for x in d['locais']] == re.findall(r'<summary class="d-flex[^"]*"> <strong>([^<]+)</strong>', texto)
    for x in d['locais']:
        assert x['links']['estrutura'] == f'/novo/cadastros/locais/{x["id"]}'
        assert x['links']['passagem'] == f'/passagem-de-turno/configuracao?client_id={x["id"]}'
        if x['centro_de_custo']:
            assert f'CC {x["centro_de_custo"]}' in texto
    assert [g['nome'] for g in d['gestores']] == re.findall(
        r'<option value="\d+" >([^<]+)</option>', texto.split('name="responsible_user_id"')[1].split('</select>')[0])
    assert len(d['estados']) == 27


def test_cadastrar_e_editar_locais_como_a_tela_antiga(app_module, auth_client, apagar_locais):
    from app import Client
    apagar_locais.extend(['Local da tela antiga', 'Local da tela nova', 'Local renomeado'])
    enc = _pessoa(app_module, 'enc.local@trino.com', 'encarregado')
    _par(auth_client, '/admin/contratos', '/api/v1/admin/contratos', {'name': ''})
    _par(auth_client, '/admin/contratos', '/api/v1/admin/contratos',
         {'name': 'Pirata', 'responsible_user_id': str(enc)})
    loc, rec = _antiga(auth_client, '/admin/contratos',
                       data={'name': 'Local da tela antiga', 'cost_center': 'CC-1'})
    r, j = _nova(auth_client, '/api/v1/admin/contratos',
                 data={'name': 'Local da tela nova', 'cost_center': 'CC-1'})
    assert r.status_code == 200 and j['destino'] == '/novo' + loc
    assert j['recados'] == [{**rec[0], 'texto': rec[0]['texto'].replace('antiga', 'nova')}]
    with app_module.app.app_context():
        assert Client.query.filter_by(name='Pirata').first() is None
        nova = Client.query.filter_by(name='Local da tela nova').one()
        assert nova.is_active and nova.cost_center == 'CC-1'
        cid = nova.id
    # Editar pelo JSON (o estado inativo vai junto com o vínculo do formulário).
    r, j = _nova(auth_client, f'/api/v1/admin/contratos/{cid}', json={
        'name': 'Local renomeado', 'cost_center': '', 'endereco': 'Rua 1'})
    assert j == {'recados': [{'tipo': 'success', 'texto': 'Local Local renomeado atualizado.'}],
                 'destino': '/novo/admin/contratos'}
    with app_module.app.app_context():
        c = Client.query.get(cid)
        assert c.name == 'Local renomeado' and not c.is_active and c.endereco == 'Rua 1'
        assert c.cost_center is None
    _par(auth_client, f'/admin/contratos/{cid}', f'/api/v1/admin/contratos/{cid}',
         {'name': 'Local renomeado', 'is_active': '1', 'estado_id': '999'})
    assert auth_client.post('/api/v1/admin/contratos/999999', data={'name': 'x'}).status_code == 404


# ── Os endereços dentro das telas novas ──────────────────────────────────

def test_os_enderecos_migrados_levam_as_telas_novas():
    from facilities.telas.cadastros import nova
    assert nova('/') == '/novo/'
    assert nova('/?x=1') == '/novo/?x=1'
    for url in ('/avisos', '/conta/seguranca', '/trocar-senha', '/admin/usuarios',
                '/admin/contratos'):
        assert nova(url) == '/novo' + url
    # O resto da administração e o que é do servidor continuam onde estão.
    for url in ('/admin/armazenamento', '/login', '/logout', '/login/codigo', '/convite/x',
                '/app/', '/passagem-de-turno/'):
        assert nova(url) == url
