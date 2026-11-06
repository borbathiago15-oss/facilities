"""Auditoria da Fase 2 (entradas, sessão, CSRF, erros, cabeçalhos, XSS), 05/11/2026.

Testes dirigidos que completam a varredura genérica
(``test_auditoria_entradas_varredura.py``). Como na Fase 1: cada
``xfail(strict=True)`` documenta um DEFEITO (a suíte fica verde enquanto ele
existir; corrigido, vira XPASS e reprova — aí é tirar a marca). Os testes sem
marca guardam o que a auditoria conferiu e está CERTO.
"""
import io
import json
import re

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD

XSS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "');alert(1)//"]
XSS_JUNTO = ' | '.join(XSS)


@pytest.fixture()
def cena(app_module):
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ids['enc'] = fabrica.pessoa(app_module, 'aud2.enc@trino.com', 'encarregado',
                                    locais=['Shopping Centro'])
        ids['tec'] = fabrica.pessoa(app_module, 'aud2.tec@trino.com', 'tecnico',
                                    locais=['Shopping Centro'])
    return ids


def _admin(app_module):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
    assert r.status_code == 302
    return c


def _chamado(app_module, c, client_id, titulo='Lâmpada queimada', descricao=''):
    r = c.post('/api/v1/chamados/', json={'client_id': client_id, 'titulo': titulo,
                                          'descricao': descricao, 'prioridade': 'media',
                                          'categoria': 'eletrica'})
    assert r.status_code == 200, r.get_data(as_text=True)
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        return Chamado.query.filter_by(titulo=titulo[:150]).order_by(Chamado.id.desc()).first().id


# ── 1. Login: senha errada, pessoa inativa, bloqueio ──────────────────────

def test_senha_errada_inativa_e_inexistente_respondem_igual(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'aud2.inativa@trino.com', 'encarregado')
        db.session.get(User, User.por_email('aud2.inativa@trino.com').id).is_active = False
        db.session.commit()
    c = app_module.app.test_client()
    respostas = [c.post('/login', data={'email': e, 'password': s}) for e, s in (
        ('aud2.enc@trino.com', 'errada-errada'), ('aud2.inativa@trino.com', fabrica.SENHA),
        ('ninguem@trino.com', fabrica.SENHA), ('', ''), ('aud2.enc@trino.com', ''))]
    assert {r.status_code for r in respostas} == {401}
    textos = {re.sub(r'value="[^"]*"', '', r.get_data(as_text=True)) for r in respostas}
    assert len(textos) == 1, 'a resposta do login entrega qual caso foi'


def test_bloqueio_depois_de_5_erros_vale_ate_com_a_senha_certa(app_module, cena):
    c = app_module.app.test_client()
    for _ in range(5):
        c.post('/login', data={'email': 'aud2.enc@trino.com', 'password': 'errada'})
    r = c.post('/login', data={'email': 'aud2.enc@trino.com', 'password': fabrica.SENHA})
    assert r.status_code == 401


@pytest.mark.parametrize('campo', ['email', 'password'])
@pytest.mark.parametrize('valor', ['x' * 100000, 'a\x00b', '🙂' * 500])
def test_login_com_entrada_absurda_nao_quebra(app_module, cena, campo, valor):
    dados = {'email': 'aud2.enc@trino.com', 'password': fabrica.SENHA, campo: valor}
    r = app_module.app.test_client().post('/login', data=dados)
    assert r.status_code < 500


# ── 2. Sessão vencida ou adulterada: 401 em JSON, nunca 500 nem redirect mudo ──

def test_cookie_adulterado_na_api_e_401_json(app_module, cena):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    bruto = c.get_cookie('session').value
    c.set_cookie('session', bruto[:-4] + ('AAAA' if not bruto.endswith('AAAA') else 'BBBB'))
    r = c.get('/api/v1/eu')
    assert r.status_code == 401 and r.is_json and r.get_json()['error']
    r = c.post('/api/v1/chamados/', json={'titulo': 'x'})
    assert r.status_code == 401 and r.is_json


def test_sessao_derrubada_em_outro_aparelho_e_401_json(app_module, cena):
    from app import User, db
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    assert c.get('/api/v1/eu').status_code == 200
    with app_module.app.app_context():
        u = db.session.get(User, cena['enc'])
        u.session_epoch = (u.session_epoch or 0) + 1
        db.session.commit()
    for metodo, url in (('get', '/api/v1/chamados/'), ('post', '/api/v1/chamados/'),
                        ('get', f"/api/v1/passagem/turno?client_id={cena['local']}"),
                        ('post', '/passagem-de-turno/api/turnos')):
        r = getattr(c, metodo)(url, json={} if metodo == 'post' else None)
        assert r.status_code == 401 and r.is_json, (url, r.status_code, r.mimetype)


def test_todo_json_de_quem_esta_logado_fica_debaixo_de_api(app_module, cena):
    """As telas buscam por ``fetch``; com a sessão vencida, o 401 em JSON só
    vem para caminho com ``/api/`` (``_sem_login``). Conferido: nenhuma rota
    GET sem ``/api/`` responde JSON a quem está logado, fora as públicas do
    aplicativo instalável (que não pedem login)."""
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    publicas = {'/healthz', '/readyz', '/manifest.webmanifest', '/app/versao', '/app/sessao',
                '/app/manifest.webmanifest'}
    achadas = []
    for regra in app_module.app.url_map.iter_rules():
        if 'GET' not in regra.methods or regra.arguments or '/api/' in regra.rule:
            continue
        r = c.get(regra.rule, headers={'Sec-Fetch-Mode': 'cors', 'Accept': '*/*'})
        if r.status_code == 200 and r.is_json and regra.rule not in publicas:
            achadas.append(regra.rule)
    assert not achadas


@pytest.mark.xfail(strict=True, reason='BUG: formulário antigo enviado com a sessão vencida '
                   '(navegação, POST) mostra o JSON cru {"error": "Sessão expirada..."} na tela '
                   'em vez de levar ao login — facilities/__init__.py:_sem_login trata todo '
                   'não-GET como API')
def test_formulario_antigo_com_sessao_vencida_leva_ao_login(app_module, cena):
    r = app_module.app.test_client().post(
        '/chamados/', data={'client_id': cena['local'], 'titulo': 'x'},
        headers={'Sec-Fetch-Mode': 'navigate', 'Accept': 'text/html'})
    assert r.status_code in (302, 303) and '/login' in r.headers.get('Location', '')


# ── 3. CSRF ───────────────────────────────────────────────────────────────

@pytest.fixture()
def csrf_ligado(app_module):
    app_module.app.config['WTF_CSRF_ENABLED'] = True
    yield
    app_module.app.config['WTF_CSRF_ENABLED'] = False


def test_api_sem_csrf_e_400_json_e_com_o_token_passa(app_module, cena, csrf_ligado):
    # Entrar também pede o token (o formulário do login traz).
    c = app_module.app.test_client()
    html = c.get('/login').get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    assert c.post('/login', data={'email': 'aud2.enc@trino.com', 'password': fabrica.SENHA,
                                  'csrf_token': token}).status_code == 302
    corpo = {'client_id': cena['local'], 'titulo': 'Com e sem token', 'prioridade': 'media',
             'categoria': 'eletrica'}
    r = c.post('/api/v1/chamados/', json=corpo)
    assert r.status_code == 400 and r.is_json and 'Recarregue' in r.get_json()['error']
    r = c.post('/api/v1/chamados/', json=corpo, headers={'X-CSRFToken': 'falso'})
    assert r.status_code == 400 and r.is_json
    csrf = c.get('/api/v1/eu').get_json()['csrf']
    r = c.post('/api/v1/chamados/', json=corpo, headers={'X-CSRFToken': csrf})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_login_sem_csrf_e_recusado(app_module, cena, csrf_ligado):
    r = app_module.app.test_client().post('/login', data={'email': 'aud2.enc@trino.com',
                                                          'password': fabrica.SENHA})
    assert r.status_code == 400


def test_nenhuma_rota_fica_fora_do_csrf():
    """Nenhuma rota fica sem CSRF. A única que ficava, ``POST /rotas/agendador``
    (D10 da Fase 1), foi desligada pela R9 (05/11/2026)."""
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent / 'facilities'
    isentas = [str(p.relative_to(raiz)) for p in raiz.rglob('*.py')
               if 'csrf.exempt' in p.read_text(encoding='utf-8')]
    assert isentas == []


# ── 4. Erros da API sempre em JSON ────────────────────────────────────────

def test_api_404_405_413_415_em_json(app_module, cena):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.get('/api/v1/nao-existe/de-jeito-nenhum')
    assert r.status_code == 404 and r.is_json and r.get_json()['error']
    r = c.open('/api/v1/eu', method='TRACE')
    assert r.status_code == 405 and r.is_json and r.get_json()['error']
    r = c.put('/passagem-de-turno/api/turnos', json={})
    assert r.status_code == 405 and r.is_json
    r = c.post('/api/v1/chamados/', data=b'titulo=x', content_type='text/plain')
    assert r.status_code < 500 and r.is_json
    grande = io.BytesIO(b'0' * (31 * 1024 * 1024))
    r = c.post('/api/v1/chamados/', data={'titulo': 'x', 'arquivo': (grande, 'a.png')},
               content_type='multipart/form-data')
    assert r.status_code == 413 and r.is_json and 'MB' in r.get_json()['error']


def test_api_sem_login_responde_401_json_ate_em_rota_que_nao_existe(app_module):
    c = app_module.app.test_client()
    for url in ('/api/v1/eu', '/api/v1/nao-existe', '/api/v1/chamados/1'):
        r = c.get(url)
        assert r.status_code == 401 and r.is_json, url


# ── 5. Cabeçalhos de segurança e cookies ──────────────────────────────────

@pytest.mark.parametrize('url', ['/login', '/api/v1/eu', '/healthz', '/nao-existe',
                                 '/api/v1/nao-existe'])
def test_cabecalhos_de_seguranca_em_toda_resposta(client, url):
    r = client.get(url)
    h = r.headers
    csp = h.get('Content-Security-Policy', '')
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
    assert "frame-ancestors 'self'" in csp and "object-src 'none'" in csp
    assert h.get('X-Frame-Options') == 'SAMEORIGIN'
    assert h.get('X-Content-Type-Options') == 'nosniff'
    assert h.get('Referrer-Policy') == 'same-origin'


def test_qr_publico_tem_os_cabecalhos(app_module, client, cena):
    r = client.get(f"/q/{cena['qr']}")
    assert r.status_code == 200
    assert 'Content-Security-Policy' in r.headers and r.headers['X-Frame-Options'] == 'SAMEORIGIN'


def test_cookies_da_sessao_com_as_travas(app_module, cena):
    app = app_module.app
    antes = app.config['SESSION_COOKIE_SECURE'], app.config['REMEMBER_COOKIE_SECURE']
    app.config['SESSION_COOKIE_SECURE'] = app.config['REMEMBER_COOKIE_SECURE'] = True
    try:
        c = app.test_client()
        r = c.post('/login', data={'email': 'aud2.enc@trino.com', 'password': fabrica.SENHA,
                                   'lembrar': '1'}, base_url='https://localhost')
        cookies = r.headers.getlist('Set-Cookie')
        for nome in ('session=', 'remember_token='):
            ck = next((x for x in cookies if x.startswith(nome)), None)
            assert ck, f'{nome} não veio'
            assert 'Secure' in ck and 'HttpOnly' in ck and 'SameSite=Lax' in ck, ck
        assert 'max-age=31536000' in r.headers.get('Strict-Transport-Security', '')
    finally:
        app.config['SESSION_COOKIE_SECURE'], app.config['REMEMBER_COOKIE_SECURE'] = antes


def test_resposta_de_quem_esta_logado_nao_fica_no_cache(app_module, cena):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    for url in ('/api/v1/eu', '/chamados/', '/'):
        assert 'no-store' in c.get(url).headers.get('Cache-Control', ''), url


# ── 6. Data inválida não apaga a data que já estava gravada ───────────────

def _plano(app_module, cena):
    from app import User, db
    from facilities.preventiva import servico as prev
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        loc = fabrica.local()
        m = s.criar_modelo(cena['local'], {'nome': 'Filtro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]), {}, None)
        gestor = User.query.filter_by(email=ADMIN_EMAIL).one()
        p = prev.salvar_plano(loc, None, {'nome': 'Plano', 'ponto_id': cena['ponto'],
                                          'modelo_id': m.id, 'intervalo_dias': '30',
                                          'proxima_em': '2026-12-01'}, gestor)
        db.session.commit()
        return p.id, m.id


@pytest.mark.parametrize('ruim', ['2026-02-30', 'abc', '', '30/02/2026', '99999-01-01'])
def test_data_invalida_nao_apaga_o_vencimento_do_plano(app_module, cena, ruim):
    from app import db
    from facilities.preventiva.models import PlanoPreventivo
    pid, mid = _plano(app_module, cena)
    c = _admin(app_module)
    r = c.post(f'/api/v1/preventiva/{pid}', json={
        'nome': 'Plano', 'ponto_id': cena['ponto'], 'modelo_id': mid, 'intervalo_dias': '30',
        'proxima_em': ruim})
    assert r.status_code == 400 and r.get_json()['error']
    with app_module.app.app_context():
        assert db.session.get(PlanoPreventivo, pid).proxima_em.isoformat() == '2026-12-01'


@pytest.mark.parametrize('ruim', ['2026-02-30', 'abc', '20261301'])
def test_data_invalida_na_correcao_da_passagem_nao_move_o_turno(app_module, cena, ruim):
    from app import db
    from facilities.passagem.models import DiarioConfiguracao, DiarioTurno
    with app_module.app.app_context():
        cfg = DiarioConfiguracao(client_id=cena['local'], nome='Rotina', ativo=True,
                                 turnos_json=json.dumps([{'nome': 'Diurno'}]), campos_json='[]',
                                 atividades_json='[]', tipos_ocorrencia_json='[]')
        db.session.add(cfg)
        db.session.commit()
        cfg_id = cfg.id
    c = _admin(app_module)
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['local'], 'configuracao_id': cfg_id,
        'data_turno': tempo.hoje().isoformat(), 'turno': 'Diurno', 'dados': {},
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    tid = r.get_json()['id']
    rotas = [x for x in app_module.app.url_map.iter_rules()
             if 'corrig' in x.rule and 'turno_id' in x.arguments and 'POST' in x.methods]
    assert rotas, 'a rota de correção mudou de nome'
    url = rotas[0].rule.replace('<int:turno_id>', str(tid))
    r = c.post(url, json={'motivo': 'data errada', 'data_turno': ruim})
    assert r.status_code == 400 and r.is_json
    with app_module.app.app_context():
        assert db.session.get(DiarioTurno, tid).data_turno == tempo.hoje()


# ── 7. Valores fora da faixa ──────────────────────────────────────────────

@pytest.mark.parametrize('intervalo', ['0', '-5', '731', '1e308', '9' * 30, 'abc', '2.5'])
def test_intervalo_do_plano_fora_da_faixa_e_recusado_com_recado(app_module, cena, intervalo):
    pid, mid = _plano(app_module, cena)
    r = _admin(app_module).post(f'/api/v1/preventiva/{pid}', json={
        'nome': 'Plano', 'ponto_id': cena['ponto'], 'modelo_id': mid,
        'intervalo_dias': intervalo, 'proxima_em': '2026-12-01'})
    assert r.status_code == 400 and r.get_json()['error']


@pytest.mark.parametrize('qtd', ['0', '-1', 'abc', '1e308', 'NaN', 'inf', '9' * 30])
def test_quantidade_de_material_absurda_e_recusada(app_module, cena, qtd):
    from facilities.materiais import servico as mat
    from app import User, db
    with app_module.app.app_context():
        m = mat.salvar_material(None, {'nome': 'Sabão', 'unidade': 'L', 'preco_unitario': '5'})
        mat.movimentar(User.query.filter_by(email=ADMIN_EMAIL).one(), fabrica.local(),
                       {'material_id': str(m.id), 'quantidade': '10'}, 'entrada')
        db.session.commit()
        mid = m.id
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post(f"/api/v1/materiais/locais/{cena['local']}/consumo",
               json={'material_id': mid, 'quantidade': qtd, 'motivo': 'x'})
    assert r.status_code == 400 and r.get_json()['error'], (r.status_code, r.get_data(as_text=True))


# ── 8. XSS: o que a pessoa digita nunca vira código ───────────────────────

def _sem_codigo(html, onde):
    for marca in ('<script>alert(1)', '<img src=x onerror'):
        assert marca not in html, f'{onde}: {marca!r} saiu sem escapar'


def test_titulo_e_descricao_do_chamado_saem_escapados(app_module, cena):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    cid = _chamado(app_module, c, cena['local'], titulo='T ' + XSS_JUNTO, descricao=XSS_JUNTO)
    c.post(f'/api/v1/chamados/{cid}/acao', json={'acao': 'comentar', 'texto': XSS_JUNTO})
    for url in (f'/chamados/{cid}', '/chamados/', '/demandas/', '/', '/avisos'):
        _sem_codigo(c.get(url).get_data(as_text=True), url)
    _sem_codigo(_admin(app_module).get(f'/chamados/{cid}').get_data(as_text=True), 'admin')
    j = c.get(f'/api/v1/chamados/{cid}').get_json()
    assert j['chamado']['titulo'].startswith('T <script>')     # a API devolve o texto como é


def test_notas_da_passagem_saem_escapadas(app_module, cena):
    from app import db
    from facilities.passagem.models import DiarioConfiguracao
    with app_module.app.app_context():
        cfg = DiarioConfiguracao(
            client_id=cena['local'], nome='Rotina ' + XSS[1], ativo=True,
            turnos_json=json.dumps([{'nome': 'Diurno'}]), campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Banheiro ' + XSS[0], 'codigo': 'b'}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria ' + XSS[1]}]))
        db.session.add(cfg)
        db.session.commit()
        cfg_id = cfg.id
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['local'], 'configuracao_id': cfg_id,
        'data_turno': tempo.hoje().isoformat(), 'turno': 'Diurno',
        'dados': {'atividade:b': {'concluido': False, 'observacao': XSS_JUNTO}},
        'ocorrencias': [{'tipo': 'Avaria', 'descricao': XSS_JUNTO}],
        'pendencias': [{'titulo': XSS_JUNTO, 'descricao': XSS_JUNTO, 'prioridade': 'media'}],
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    tid = r.get_json()['id']
    adm = _admin(app_module)
    for url in (f'/passagem-de-turno/turno/{tid}', f"/passagem-de-turno/?client_id={cena['local']}",
                f"/passagem-de-turno/turno?client_id={cena['local']}",
                f"/passagem-de-turno/configuracao?client_id={cena['local']}",
                f"/passagem-de-turno/relatorio-mensal?client_id={cena['local']}"):
        r = adm.get(url)
        assert r.status_code < 500, url
        _sem_codigo(r.get_data(as_text=True), url)
    r = adm.get(f"/passagem-de-turno/relatorio-mensal/pdf?client_id={cena['local']}")
    assert r.status_code < 500


def test_nome_do_local_e_do_cliente_saem_escapados(app_module, cena):
    from app import Client, db
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        nome_antigo = db.session.get(Client, cena['local']).name
        db.session.get(Client, cena['local']).name = 'Local ' + XSS_JUNTO
        db.session.get(Contratante, cena['cliente']).nome = 'Cliente ' + XSS_JUNTO
        db.session.commit()
    try:
        _conferir_nomes(app_module, cena)
    finally:
        with app_module.app.app_context():
            db.session.get(Client, cena['local']).name = nome_antigo
            db.session.commit()


def _conferir_nomes(app_module, cena):
    adm = _admin(app_module)
    enc = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    for c, url in ((adm, f"/cadastros/locais/{cena['local']}"), (adm, '/clientes'),
                   (adm, '/admin/contratos'), (adm, '/chamados/novo'), (adm, '/painel'),
                   (adm, f"/rotas/locais/{cena['local']}"), (enc, '/'), (enc, '/app/'),
                   (enc, '/chamados/novo'), (adm, f"/centros/{cena['local']}")):
        r = c.get(url)
        assert r.status_code == 200, (url, r.status_code)
        _sem_codigo(r.get_data(as_text=True), url)
    r = app_module.app.test_client().get(f"/q/{cena['qr']}")
    _sem_codigo(r.get_data(as_text=True), 'QR público')


def test_ocorrencia_do_qr_publico_sai_escapada(app_module, cena):
    anon = app_module.app.test_client()
    r = anon.post(f"/q/{cena['qr']}/ocorrencia", data={'tipo': 'outro', 'texto': XSS_JUNTO})
    assert r.status_code < 500
    enc = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    for url in ('/app/', '/rotas/ocorrencias', '/', '/demandas/'):
        r = enc.get(url)
        if r.status_code == 200:
            _sem_codigo(r.get_data(as_text=True), url)


# ── 9. Defeitos achados pela varredura (um representante de cada) ────────
# A lista completa de rota × variante de cada defeito está em CONHECIDOS
# (test_auditoria_entradas_varredura.py); aqui, um caso de cada, legível.

import os  # noqa: E402

NO_POSTGRES = bool(os.environ.get('TEST_DATABASE_URL', '').strip())
so_postgres = pytest.mark.skipif(not NO_POSTGRES, reason='o defeito só aparece no Postgres')
so_sqlite = pytest.mark.skipif(NO_POSTGRES, reason='no Postgres a consulta não quebra')


def _modelo_de_passagem(app_module, client_id):
    from app import db
    from facilities.passagem.models import DiarioConfiguracao
    with app_module.app.app_context():
        cfg = DiarioConfiguracao(client_id=client_id, nome='Rotina', ativo=True,
                                 turnos_json=json.dumps([{'nome': 'Diurno'}]), campos_json='[]',
                                 atividades_json='[]', tipos_ocorrencia_json='[]')
        db.session.add(cfg)
        db.session.commit()
        return cfg.id


@pytest.fixture()
def sem_propagar(app_module):
    """Como na produção: a exceção vira o 500 da fábrica, e não traceback."""
    antes = app_module.app.config.get('PROPAGATE_EXCEPTIONS')
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = False
    yield
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = antes


@pytest.mark.xfail(strict=True, reason='BUG E1: raiz JSON que não é objeto (lista, texto, '
                   'número) dá 500 — request.get_json(silent=True) or {} seguido de .get() '
                   '(passagem/rotas.py:68, rotas/telas.py:1205/1266/1308, rotas/publico.py:128, '
                   'core/push.py:163, telas/admin.py:47)')
@pytest.mark.parametrize('url', ['/passagem-de-turno/api/turnos', '/app/api/leitura',
                                 '/app/api/chegada', '/app/api/push'])
def test_e1_raiz_json_em_lista_e_400(app_module, cena, sem_propagar, url):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post(url, json=[{'client_id': cena['local']}])
    assert r.status_code == 400 and r.is_json, r.status_code


@pytest.mark.xfail(strict=True, reason='BUG E2: campo de texto que chega como número no JSON '
                   'dá 500 — (data.get("turno") or "").strip() em passagem/rotas.py:913 (e '
                   ':490, :525, :568, :1287, :1705, :2483; core/push.py:165)')
def test_e2_turno_numerico_na_passagem_e_400(app_module, cena, sem_propagar):
    cfg = _modelo_de_passagem(app_module, cena['local'])
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['local'], 'configuracao_id': cfg, 'data_turno': tempo.hoje().isoformat(), 'turno': 5,
        'dados': {}})
    assert r.status_code == 400 and r.is_json, r.status_code


@pytest.mark.xfail(strict=True, reason='BUG E3: id do corpo que não cabe na coluna dá 500 ao '
                   'gravar (Postgres: integer out of range; SQLite: OverflowError) — '
                   'passagem/rotas.py:497-505 (área) e :566-580 (modelo)')
def test_e3_area_com_contrato_gigante_e_400(app_module, cena, sem_propagar):
    r = _admin(app_module).post('/passagem-de-turno/api/areas',
                                json={'client_id': '9' * 30, 'nome': 'Área'})
    assert r.status_code in (400, 403, 404) and r.is_json, r.status_code


@so_sqlite
@pytest.mark.xfail(strict=True, reason='BUG E3 (só SQLite): id gigante no corpo vai direto ao '
                   'db.session.get e estoura (OverflowError) — ex.: chamados/servico.py:267, '
                   'materiais/servico.py:196, preventiva/servico.py:50, cadastros/servico.py:174')
def test_e3_chamado_com_contrato_gigante_no_sqlite(app_module, cena, sem_propagar):
    c = _admin(app_module)      # o encarregado leva 403 antes (fora da carteira)
    r = c.post('/api/v1/chamados/', json={'client_id': '9' * 30, 'titulo': 'x'})
    assert r.status_code in (400, 403) and r.is_json, r.status_code


@pytest.mark.xfail(strict=True, reason='BUG E4: int() sem tratamento — modelo de passagem '
                   'sem contrato (corpo vazio) e área com contrato "abc" dão 500 '
                   '(passagem/rotas.py:441/497/566; rotas/servico.py:513/617)')
@pytest.mark.parametrize('url,corpo', [
    ('/passagem-de-turno/api/configuracoes', {}),
    ('/passagem-de-turno/api/areas', {'client_id': 'abc', 'nome': 'Área'})],
    ids=['modelo-vazio', 'area-texto'])
def test_e4_numero_que_nao_e_numero_e_400(app_module, cena, sem_propagar, url, corpo):
    r = _admin(app_module).post(url, json=corpo)
    assert r.status_code == 400 and r.is_json, r.status_code


@so_postgres
@pytest.mark.xfail(strict=True, reason='BUG E5 (Postgres): byte nulo (\\x00) num texto dá 500 '
                   '— "A string literal cannot contain NUL" (chamados/servico.py:347 e ~35 '
                   'rotas de gravação)')
def test_e5_byte_nulo_no_titulo_do_chamado_nao_quebra(app_module, cena, sem_propagar):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post('/api/v1/chamados/', json={'client_id': cena['local'], 'titulo': 'Porta\x00 quebrada',
                                          'prioridade': 'media', 'categoria': 'eletrica'})
    assert r.status_code < 500, r.status_code


@so_postgres
@pytest.mark.xfail(strict=True, reason='BUG E6 (Postgres): texto maior que a coluna dá 500 — '
                   'nome do turno vai sem corte para varchar(50) (passagem/rotas.py:913/985); '
                   'título da tarefa do turno idem (:1540)')
def test_e6_turno_com_nome_longo_nao_quebra(app_module, cena, sem_propagar):
    cfg = _modelo_de_passagem(app_module, cena['local'])
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['local'], 'configuracao_id': cfg,
        'data_turno': tempo.hoje().isoformat(), 'turno': 'T' * 80, 'dados': {}})
    assert r.status_code < 500, r.status_code


@so_sqlite
@pytest.mark.xfail(strict=True, reason='BUG E7 (só SQLite, dev/testes): id do caminho acima de '
                   '2^63 dá 500 (OverflowError) em ~170 rotas; no Postgres é 404')
def test_e7_id_gigante_no_caminho_e_404(app_module, cena, sem_propagar):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.get('/api/v1/chamados/' + str(10 ** 20))
    assert r.status_code == 404 and r.is_json, r.status_code


@pytest.mark.parametrize('inteiro', [2 ** 31, 2 ** 63 - 1])
def test_id_grande_que_cabe_no_sqlite_e_404_nos_dois_bancos(app_module, cena, inteiro):
    c = fabrica.entrar(app_module, 'aud2.enc@trino.com')
    r = c.get(f'/api/v1/chamados/{inteiro}')
    assert r.status_code == 404 and r.is_json


@pytest.mark.xfail(strict=True, reason='BUG E9: contrato que não existe é aceito para o '
                   'administrador na Passagem (área, modelo, pendência da gestão): no Postgres '
                   'a chave estrangeira recusa e sai 500; no SQLite grava a área órfã '
                   '(passagem/rotas.py:488-505, :559-580, :1280-1321)')
def test_e9_area_em_contrato_que_nao_existe_e_404(app_module, cena, sem_propagar):
    r = _admin(app_module).post('/passagem-de-turno/api/areas',
                                json={'client_id': 999999, 'nome': 'Área fantasma'})
    assert r.status_code in (400, 404) and r.is_json, r.status_code
