"""O portal do cliente e as cobranças vistas pela equipe nas telas novas
(Fase 5).

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* a porta: só a conta de cliente entra no portal novo (a equipe recebe 403,
  como na antiga), e a conta de cliente continua fora do resto das telas
  novas (só o portal e o ``/api/v1/eu`` da casca);
* local, chamado, relatório e cobrança de OUTRO cliente: o mesmo 404 da
  antiga, na página nova e na API, sem nada do outro na resposta;
* os mesmos dados que a tela antiga escreve, e só eles (nada de custo,
  material, comentário interno, PDF de orçamento ou nome de quem é da equipe);
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova; o mesmo
  limite de cobranças por hora.
"""
import html as html_mod
import re
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_portal_cliente import COMENTARIO, MATERIAL, cena, liberado  # noqa: F401

MODULOS = ('facilities.telas.portal',)
PROIBIDOS = (MATERIAL, 'R$', COMENTARIO, 'Carla Coordenadora', 'orcamento', 'Eva Encarregada')


def _texto(html):
    return html_mod.unescape(re.sub(r'\s+', ' ', html))


def _flashes(c):
    with c.session_transaction() as s:
        return [{'tipo': 'danger' if t == 'error' else t, 'texto': x}
                for t, x in s.pop('_flashes', [])]


def _par(c, antiga, nova, dados, destino_igual=True):
    """O mesmo envio pela tela antiga e pela nova: o mesmo recado, o mesmo
    destino (abaixo de /novo) e, na recusa, 400 com a mesma frase."""
    r = c.post(antiga, data=dados)
    assert r.status_code == 302, (antiga, r.status_code)
    d1, rec = r.headers['Location'], _flashes(c)
    r = c.post(nova, data=dados)
    assert r.is_json, (nova, r.status_code)
    j = r.get_json()
    recusou = any(x['tipo'] == 'danger' for x in rec)
    if destino_igual:
        assert j['recados'] == rec, (nova, j['recados'], rec)
        assert j['destino'] == '/novo' + d1, (nova, j['destino'], d1)
    assert r.status_code == (400 if recusou else 200), (nova, rec)
    if recusou:
        assert j['error'] == j['recados'][0]['texto']
    return d1, rec, j


def _data(dias):
    return (tempo.hoje() + timedelta(days=dias)).isoformat()


def _cliente(app_module):
    return fabrica.entrar_com_codigo(app_module, 'cliente@gl.com')


@pytest.fixture()
def mais(app_module, cena, liberado):  # noqa: F811
    """O relatório do mês passado liberado; uma cobrança respondida; um aviso
    pelo QR resolvido; o Hospital Norte de OUTRO cliente, com chamado,
    cobrança e relatório liberado."""
    from app import User, db
    from facilities.cadastros import servico as cad
    from facilities.chamados import servico as chs
    from facilities.portal import servico as portal
    from facilities.relatorios import cliente as rel
    from facilities.rotas import ocorrencias
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        passado = rel.mes_anterior(tempo.hoje().replace(day=1))
        rel.salvar_recado(cena['local'], passado, 'Recado ao GL', admin)
        rel.liberar(cena['local'], passado, admin)
        cob = portal.abrir(db.session.get(User, cena['cli']), {
            'client_id': str(cena['local']), 'titulo': 'Vidros', 'texto': 'Limpar os vidros',
            'prazo': _data(3)})
        db.session.flush()
        portal.responder(db.session.get(User, cena['coord']), cob, {'texto': 'Vidros limpos.'})
        ponto = db.session.get(PontoInspecao, cena['ponto'])
        oc = ocorrencias.abrir(ponto, 'sujo', 'Pia entupida', None)
        db.session.flush()
        ocorrencias.resolver(oc, db.session.get(User, cena['coord']), 'Desentupida')
        # O outro cliente.
        emp = cad.salvar_empresa(None, {'nome': 'Outra empresa'}, None)
        hn = cad.salvar_contratante(None, {'nome': 'Grupo HN', 'empresa_id': emp.id}, None)
        db.session.flush()
        hosp = fabrica.local('Hospital Norte')
        hosp.contratante_id = hn.id
        cli_hn = fabrica.cliente(app_module, 'cliente@hn.com', hn.id)
        ch_hn = chs.abrir(db.session.get(User, cena['outro']), hosp.id, 'Segredo do HN')
        db.session.flush()
        cob_hn = portal.abrir(db.session.get(User, cli_hn), {
            'client_id': str(hosp.id), 'titulo': 'Segredo do HN', 'texto': 'x',
            'prazo': _data(3)})
        rel.liberar(hosp.id, passado, admin)
        db.session.commit()
        cena.update(mes=passado.strftime('%Y-%m'), cobranca=cob.id, aviso=oc.id,
                    hosp=hosp.id, chamado_hn=ch_hn.id, cobranca_hn=cob_hn.id)
    return cena


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo not in MODULOS:
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1').replace(f'<{arg}>', 'x')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) == 3
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'GET']) == 9
    assert len([1 for m, u in rotas if u.startswith('/novo/')]) == 9
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


def _telas_do_cliente(m):
    a, h = m['local'], m['hosp']
    return [
        # (antiga, código para o cliente de A) — a nova é a antiga abaixo de
        # /novo e a API abaixo de /api/v1
        ('/cliente/', 200),
        ('/cliente/?de=2026-01-01&ate=2026-01-31', 200),
        (f'/cliente/locais/{a}', 200),
        (f'/cliente/locais/{h}', 404),
        ('/cliente/locais/999999', 404),
        (f"/cliente/chamados/{m['chamado']}", 200),
        (f"/cliente/chamados/{m['chamado_hn']}", 404),
        ('/cliente/chamados/999999', 404),
        ('/cliente/relatorios', 200),
        (f"/cliente/relatorios/{a}/{m['mes']}", 200),
        (f"/cliente/relatorios/{h}/{m['mes']}", 404),
        (f'/cliente/relatorios/{a}/2020-01', 404),      # não liberado
        ('/cliente/cobrancas', 200),
        ('/cliente/cobrancas?aba=qr', 200),
        ('/cliente/cobrancas?aba=qr&situacao=resolvida', 200),
        (f"/cliente/cobrancas/{m['cobranca']}", 200),
        (f"/cliente/cobrancas/{m['cobranca_hn']}", 404),
        ('/cliente/cobrancas/999999', 404),
    ]


def test_a_porta_do_cliente_e_a_mesma_da_tela_antiga(app_module, mais):
    c = _cliente(app_module)
    for antiga, codigo in _telas_do_cliente(mais):
        api = '/api/v1' + antiga
        r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
        assert r_antiga.status_code == r_api.status_code == codigo, (antiga, r_api.status_code)
        assert r_nova.status_code in ((200, 503) if codigo == 200 else (codigo,)), antiga
        corpo = r_api.get_data(as_text=True)
        assert 'Segredo do HN' not in corpo and 'Grupo HN' not in corpo, antiga
        assert 'Hospital Norte' not in corpo, antiga
        if codigo != 200:
            assert r_api.is_json
    # O cliente do outro contratante não vê nada de A, nas duas telas.
    hn = fabrica.entrar_com_codigo(app_module, 'cliente@hn.com')
    a = mais['local']
    for antiga in (f'/cliente/locais/{a}', f"/cliente/chamados/{mais['chamado']}",
                   f"/cliente/relatorios/{a}/{mais['mes']}",
                   f"/cliente/cobrancas/{mais['cobranca']}"):
        assert hn.get(antiga).status_code == hn.get('/api/v1' + antiga).status_code == \
            hn.get('/novo' + antiga).status_code == 404, antiga
    for antiga in ('/cliente/', '/cliente/cobrancas', '/cliente/cobrancas?aba=qr',
                   '/cliente/relatorios'):
        corpo = hn.get('/api/v1' + antiga).get_data(as_text=True)
        for de_a in ('Shopping Centro', 'Vidros', 'Pia entupida', 'Lâmpada'):
            assert de_a not in corpo, (antiga, de_a)


@pytest.mark.parametrize('papel', ['master', 'gerente', 'pleno', 'supervisor', 'visualizador',
                                   'encarregado', 'tecnico'])
def test_a_equipe_nao_abre_o_portal_novo(app_module, mais, papel):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta5.{papel}@trino.com', papel,
                       locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, f'porta5.{papel}@trino.com')
    for antiga, codigo in _telas_do_cliente(mais):
        if codigo != 200:
            continue
        assert c.get(antiga).status_code == c.get('/api/v1' + antiga).status_code == \
            c.get('/novo' + antiga).status_code == 403, (papel, antiga)
    r = c.post('/api/v1/cliente/cobrancas', data={'client_id': mais['local'], 'titulo': 'x',
                                                   'texto': 'x', 'prazo': _data(3)})
    assert r.status_code == 403 and r.is_json
    r = c.post(f"/api/v1/cliente/cobrancas/{mais['cobranca']}/confirmar")
    assert r.status_code == 403 and r.is_json
    from app import db
    from facilities.portal.models import Cobranca
    with app_module.app.app_context():
        assert db.session.get(Cobranca, mais['cobranca']).status == 'respondida'
        assert Cobranca.query.filter_by(titulo='x').count() == 0


# (O Início novo, ``/novo/``, leva o cliente ao portal novo, como o antigo
# leva ao antigo — Fase 6a, ``tests/test_telas_conta.py``; a API dele,
# ``/api/v1/inicio``, continua fechada.)
@pytest.mark.parametrize('url', ['/novo/chamados/', '/novo/painel', '/novo/cobrancas/',
                                 '/novo/relatorios/', '/novo/app', '/api/v1/chamados/',
                                 '/api/v1/cobrancas/', '/api/v1/painel', '/api/v1/campo/inicio',
                                 '/api/v1/relatorios/', '/api/v1/inicio',
                                 '/novo/admin/usuarios', '/api/v1/admin/usuarios',
                                 '/api/v1/qualquer'])
def test_o_cliente_continua_fora_do_resto_das_telas_novas(app_module, mais, url):
    c = _cliente(app_module)
    r = c.get(url)
    assert r.status_code == 403, url
    assert 'Lâmpada' not in r.get_data(as_text=True)
    if url.startswith('/api/'):
        assert r.is_json


def test_o_eu_da_casca_do_cliente(app_module, mais):
    d = _cliente(app_module).get('/api/v1/eu').get_json()
    assert d['cliente'] is True and d['links']['inicio'] == '/cliente/'
    rotulos = [i['rotulo'] for g in d['menu'] for i in g['itens']]
    assert 'Seus locais' in rotulos and 'Chamados' not in rotulos


def test_sem_segunda_etapa_ou_com_o_portal_desligado(app_module, mais):
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cliente@gl.com', mais['cliente'], segunda_etapa=False)
    c = fabrica.entrar(app_module, 'cliente@gl.com')
    for url in ('/api/v1/cliente/', '/api/v1/eu'):
        r = c.get(url)
        assert r.status_code == 403 and r.is_json and 'segunda etapa' in r.get_json()['error']
    assert c.get('/novo/cliente/').status_code == 302
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cliente@gl.com', mais['cliente'])
    c = _cliente(app_module)
    assert c.get('/api/v1/cliente/').status_code == 200
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False
    r = c.get('/api/v1/cliente/')
    assert r.status_code == 401 and r.is_json
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    assert c.get('/api/v1/cliente/').status_code == 401        # a sessão caiu


# ── O que o cliente vê: os mesmos dados da tela antiga, e só eles ─────────

def _sem_nada_da_equipe(corpo):
    for p in PROIBIDOS:
        assert p not in corpo, p


def test_o_inicio_traz_os_dados_da_tela_antiga(app_module, mais):
    c = _cliente(app_module)
    for busca in ('', '?de=2026-01-01&ate=2026-01-31', '?de=xpto'):
        r = c.get('/api/v1/cliente/' + busca)
        _sem_nada_da_equipe(r.get_data(as_text=True))
        d = r.get_json()
        antigo = c.get('/cliente/' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        assert f'value="{d["de"]}"' in texto and f'value="{d["ate"]}"' in texto
        assert f'Período de {d["de_br"]} a {d["ate_br"]}.' in texto
        assert [x['url'] for x in d['linhas']] == [
            '/novo' + html_mod.unescape(u) for u in re.findall(
                r'class="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-3 '
                r'text-reset text-decoration-none" href="([^"]+)"', antigo)]
        for x in d['linhas']:
            assert f'{x["abertos"]} chamado(s) em aberto' in texto
            if x['nota']:
                assert f'fc-nota-{x["nota"]["faixa"]}">{x["nota"]["texto"]}</span>' in texto
            else:
                assert 'sem dado no período' in texto
        assert [x['url'] for x in d['cobrancas']] == [
            '/novo' + u for u in re.findall(r'href="(/cliente/cobrancas/\d+)"', antigo)]
        for x in d['cobrancas']:
            assert (f'<span class="badge {x["situacao"]["classe"]}">{x["situacao"]["texto"]}'
                    f'</span>') in texto
            assert f'prazo {x["prazo"]}' in texto
    d = c.get('/api/v1/cliente/').get_json()
    assert [x['nome'] for x in d['linhas']] == ['Shopping Centro']
    assert d['links']['cobrancas'] == '/novo/cliente/cobrancas'
    [cob] = d['cobrancas']
    assert cob['situacao'] == {'classe': 'text-bg-primary',
                               'texto': 'Respondida — confirme ou reabra'}


def test_o_local_traz_os_dados_da_tela_antiga(app_module, mais):
    c = _cliente(app_module)
    url = f"/cliente/locais/{mais['local']}"
    r = c.get('/api/v1' + url)
    _sem_nada_da_equipe(r.get_data(as_text=True))
    d = r.get_json()
    antigo = c.get(url).get_data(as_text=True)
    texto = _texto(antigo)
    assert d['local']['nome'] == 'Shopping Centro'
    for i in d['indicadores']:
        assert (f'<div class="small text-muted">{i["rotulo"]}</div> <div class="fs-4 fw-bold">'
                f'{i["pct"]}</div> <div class="small text-muted">{i["base"]}</div>') in texto
    assert [x['url'] for x in d['chamados']] == [
        '/novo' + u for u in re.findall(r'href="(/cliente/chamados/\d+)"', antigo)]
    [ch] = d['chamados']
    assert ch['titulo'] == 'Lâmpada queimada no hall' and ch['fotos'] == 1
    assert f'{ch["fotos"]} foto(s)' in texto and ch['quando'] in texto
    assert ch['quando'].startswith('resolvido ')
    [ex] = d['execucoes']
    assert ex['onde'] in texto and ex['detalhe'] in texto
    assert 'Encarregado / ASG' in ex['detalhe']                # R5: a função, não o nome
    assert [f['url'] for f in ex['fotos']] == re.findall(
        r'<img class="fc-miniatura" src="(/cliente/fotos/checklist/\d+)"', antigo)
    # As fotos e os POP/FIT continuam servidos pelo servidor.
    assert not ex['fotos'][0]['url'].startswith('/novo')
    assert c.get(ex['fotos'][0]['url']).status_code == 200
    assert d['links'] == {'inicio': '/novo/cliente/',
                          'cobrar': f"/novo/cliente/cobrancas?local={mais['local']}"}


def test_o_chamado_traz_so_o_que_a_tela_antiga_mostra(app_module, mais):
    c = _cliente(app_module)
    url = f"/cliente/chamados/{mais['chamado']}"
    r = c.get('/api/v1' + url)
    _sem_nada_da_equipe(r.get_data(as_text=True))
    d = r.get_json()
    texto = _texto(c.get(url).get_data(as_text=True))
    assert f'{d["numero"]} · {d["titulo"]}' in texto
    for rotulo, valor in (('Situação', d['situacao']), ('Tipo', d['categoria']),
                          ('Onde', d['onde']), ('Aberto em', d['aberto_em']),
                          ('Resolvido em', d['resolvido_em']),
                          ('O que foi feito', d['solucao'])):
        assert f'{rotulo}</dt><dd class="col-sm-8">{valor}</dd>' in texto, rotulo
    assert d['solucao'] == 'Lâmpada trocada' and d['situacao'].startswith('Resolvido')
    assert [f['url'] for f in d['fotos']] == [f"/cliente/fotos/chamado/{mais['foto']}"]
    assert d['fotos'][0]['legenda'] == 'Depois'
    assert set(d) == {'id', 'numero', 'titulo', 'situacao', 'categoria', 'onde', 'aberto_em',
                      'prazo', 'aguardando', 'resolvido_em', 'solucao', 'fotos', 'local', 'links'}


def test_o_relatorio_liberado_e_so_o_corpo_do_cliente(app_module, mais):
    from tests.test_telas_relatorios_integracao import _confere_corpo
    c = _cliente(app_module)
    d = c.get('/api/v1/cliente/relatorios').get_json()
    antigo = c.get('/cliente/relatorios').get_data(as_text=True)
    assert [x['url'] for x in d['relatorios']] == [
        '/novo' + u for u in re.findall(r'href="(/cliente/relatorios/\d+/\d{4}-\d\d)"', antigo)]
    [x] = d['relatorios']
    assert f'>{x["mes"]}</span> <span class="fc-fila-tit">{x["local"]}</span>' in _texto(antigo)
    assert x['pdf'] == f"/cliente/relatorios/{mais['local']}/{mais['mes']}/arquivo.pdf"
    url = f"/cliente/relatorios/{mais['local']}/{mais['mes']}"
    r = c.get('/api/v1' + url)
    d = r.get_json()
    texto = _texto(c.get(url).get_data(as_text=True))
    _confere_corpo(d['corpo'], texto)
    assert d['recado'] == 'Recado ao GL' and 'Recado ao GL' in texto
    assert set(d) == {'local', 'mes', 'nome_do_mes', 'recado', 'corpo', 'links'}
    assert all(f['url'].startswith('/cliente/fotos/') for f in d['corpo']['fotos'])
    assert d['links']['pdf'] == x['pdf'] and c.get(x['pdf']).mimetype == 'application/pdf'
    assert d['links']['inicio'] == '/novo/cliente/relatorios'
    # Congelado: o recado que a gestão muda depois não chega ao cliente.
    from app import User, db
    from facilities.relatorios import cliente as rel
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        rel.salvar_recado(mais['local'], rel.mes_de(mais['mes']), 'Recado novo', admin)
        db.session.commit()
    assert c.get('/api/v1' + url).get_json()['recado'] == 'Recado ao GL'


def test_as_cobrancas_trazem_os_dados_da_tela_antiga(app_module, mais):
    c = _cliente(app_module)
    for busca in ('', f"?local={mais['local']}", '?local=xpto'):
        d = c.get('/api/v1/cliente/cobrancas' + busca).get_json()
        antigo = c.get('/cliente/cobrancas' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        assert d['aba'] == 'cobrancas'
        assert f'min="{d["minimo"]}"' in texto and f'A partir de {d["minimo_br"]}.' in texto
        assert ('<details class="fc-cartao mb-3" open>' in texto) == d['abrir_aberto']
        assert [x['url'] for x in d['cobrancas']] == [
            '/novo' + u for u in re.findall(r'href="(/cliente/cobrancas/\d+)"', antigo)]
        assert [x['id'] for x in d['locais']] == [
            int(v) for v in re.findall(r'<option value="(\d+)"', antigo)]
        if d['local_escolhido']:
            assert f'<option value="{d["local_escolhido"]}" selected>' in texto
    assert d['abas'] == {'cobrancas': '/novo/cliente/cobrancas',
                         'qr': '/novo/cliente/cobrancas?aba=qr'}


def test_os_avisos_pelo_qr_do_cliente(app_module, mais):
    c = _cliente(app_module)
    for busca in ('?aba=qr', '?aba=qr&situacao=resolvida', '?aba=qr&situacao=aberta',
                  '?aba=qr&situacao=xpto'):
        r = c.get('/api/v1/cliente/cobrancas' + busca)
        corpo = r.get_data(as_text=True)
        assert 'Carla Coordenadora' not in corpo and 'responsavel' not in corpo
        d = r.get_json()
        texto = _texto(c.get('/cliente/cobrancas' + busca).get_data(as_text=True))
        assert d['aba'] == 'qr'
        for x in d['avisos']:
            assert (f'<span class="badge fc-sit fc-ocor-{x["status"]}">{x["situacao"]}</span> '
                    f'<span class="fw-semibold">{x["titulo"]}</span>') in texto
            assert x['onde'] in texto and x['quando'] in texto
            assert f'resolvido {x["resolvido"]}: {x["resolucao"]}' in texto
        if not d['avisos']:
            assert 'Nenhum aviso pelo QR aqui.' in texto
        for rotulo, url, ativo in d['filtros']:
            classe = 'btn-primary' if ativo else 'btn-outline-primary'
            assert f'btn btn-sm {classe}" href="{url[len("/novo"):]}">{rotulo}</a>' in texto
    d = c.get('/api/v1/cliente/cobrancas?aba=qr').get_json()
    [aviso] = d['avisos']
    assert aviso['texto'] == 'Pia entupida' and aviso['resolucao'] == 'Desentupida'


def test_a_cobranca_traz_a_trilha_com_coordenacao(app_module, mais):
    c = _cliente(app_module)
    url = f"/cliente/cobrancas/{mais['cobranca']}"
    r = c.get('/api/v1' + url)
    _sem_nada_da_equipe(r.get_data(as_text=True))
    d = r.get_json()
    texto = _texto(c.get(url).get_data(as_text=True))
    assert f'{d["numero"]} · {d["titulo"]}' in texto
    assert f'prazo {d["prazo"]}' in texto and f'a partir de {d["minimo_br"]}' in texto
    assert d['respondida'] and not d['aberta']
    for e in d['eventos']:
        assert f'{e["quando"]} · {e["autor"]} · <span class="fw-semibold">{e["tipo"]}</span>' \
            in texto
    assert [e['autor'] for e in d['eventos']] == ['Cliente GL', 'Coordenação'] or \
        d['eventos'][1]['autor'] == 'Coordenação'
    assert d['eventos'][0]['prazo'] == d['prazo'] and d['eventos'][1]['prazo'] is None


# ── Os envios do cliente, como na tela antiga ─────────────────────────────

def test_abrir_cobranca_como_na_tela_antiga(app_module, mais):
    from facilities.portal.models import Cobranca
    c = _cliente(app_module)
    with app_module.app.app_context():
        antes = Cobranca.query.count()
    base = {'client_id': str(mais['local']), 'titulo': 'Banheiro', 'texto': 'Sujo'}
    # As recusas: menos de 24 h, sem assunto, local de OUTRO cliente.
    for dados in ({**base, 'prazo': _data(0)}, {**base, 'titulo': '', 'prazo': _data(3)},
                  {**base, 'client_id': str(mais['hosp']), 'prazo': _data(3)}):
        _, rec, j = _par(c, '/cliente/cobrancas', '/api/v1/cliente/cobrancas', dados)
        assert rec[0]['tipo'] == 'danger' and j['destino'] == '/novo/cliente/cobrancas'
    with app_module.app.app_context():
        assert Cobranca.query.count() == antes
        assert Cobranca.query.filter_by(client_id=mais['hosp'], titulo='Banheiro').count() == 0
    d1, rec, j = _par(c, '/cliente/cobrancas', '/api/v1/cliente/cobrancas',
                      {**base, 'prazo': _data(3)}, destino_igual=False)
    n_antiga = int(d1.rsplit('/', 1)[1])
    assert j['destino'] == f'/novo/cliente/cobrancas/{n_antiga + 1}'
    assert rec == [{'tipo': 'success', 'texto':
                    f'Cobrança CB-{n_antiga:05d} enviada à coordenação do contrato.'}]
    assert j['recados'] == [{'tipo': 'success', 'texto':
                             f'Cobrança CB-{n_antiga + 1:05d} enviada à coordenação do contrato.'}]
    with app_module.app.app_context():
        a, b = Cobranca.query.filter_by(titulo='Banheiro').order_by(Cobranca.id).all()
        assert (a.client_id, a.texto, a.prazo, a.status) == (b.client_id, b.texto, b.prazo,
                                                              b.status)


def test_o_mesmo_limite_de_cobrancas_por_hora():
    """30 cobranças por hora, contadas JUNTAS nas duas telas: o mesmo limite
    compartilhado (mesmo escopo) na rota antiga e na da tela nova. Com um
    contador por rota, o cliente chegava a 60 por hora."""
    from facilities.extensions import limiter
    grupos = {k.rsplit('.', 1)[-1]: list(v) for k, v in limiter.limit_manager._decorated_limits.items()}
    antiga, nova = grupos['abrir_cobranca'], grupos['api_portal_abrir_cobranca']
    assert [(g.limit_provider, g.shared, g.scope) for g in antiga] == \
        [(g.limit_provider, g.shared, g.scope) for g in nova] == \
        [('30 per hour', True, 'portal-abrir-cobranca')]

def test_confirmar_e_reabrir_como_na_tela_antiga(app_module, mais):
    from app import User, db
    from facilities.portal import servico as portal
    from facilities.portal.models import Cobranca
    c = _cliente(app_module)
    cid = mais['cobranca']
    url, api = f'/cliente/cobrancas/{cid}', f'/api/v1/cliente/cobrancas/{cid}'
    # Reabrir sem dizer o que falta, e com prazo curto: a mesma recusa.
    _par(c, url + '/reabrir', api + '/reabrir', {'texto': '', 'prazo': _data(5)})
    _par(c, url + '/reabrir', api + '/reabrir', {'texto': 'Ainda sujo', 'prazo': _data(0)})
    # A nova reabre; a antiga, depois, recusa (já está aberta) — e vice-versa.
    r = c.post(api + '/reabrir', data={'texto': 'Ainda sujo', 'prazo': _data(5)})
    assert r.status_code == 200
    assert r.get_json() == {'recados': [{'tipo': 'success', 'texto':
                                         'Cobrança reaberta. A coordenação foi avisada.'}],
                            'destino': f'/novo/cliente/cobrancas/{cid}'}
    with app_module.app.app_context():
        cob = db.session.get(Cobranca, cid)
        assert cob.status == 'aberta' and cob.reaberturas == 1
        assert tempo.local(cob.prazo).date().isoformat() == _data(5)
    _par(c, url + '/confirmar', api + '/confirmar', {})       # falta a resposta: recusa
    with app_module.app.app_context():
        portal.responder(db.session.get(User, mais['coord']), db.session.get(Cobranca, cid),
                         {'texto': 'Refeito.'})
        db.session.commit()
    r = c.post(api + '/confirmar', data={'texto': 'Agora sim'})
    assert r.get_json()['recados'] == [{'tipo': 'success', 'texto': 'Obrigado! Cobrança encerrada.'}]
    with app_module.app.app_context():
        cob = db.session.get(Cobranca, cid)
        assert cob.status == 'fechada'
        assert [e.tipo for e in cob.eventos] == ['aberta', 'resposta', 'reaberta', 'resposta',
                                                 'confirmada']
    assert c.post(api + '/xpto').status_code == c.post(url + '/xpto').status_code == 404
    # A cobrança do outro cliente: 404, e nada muda.
    hn = f"/api/v1/cliente/cobrancas/{mais['cobranca_hn']}/confirmar"
    assert c.post(hn).status_code == 404
    with app_module.app.app_context():
        assert db.session.get(Cobranca, mais['cobranca_hn']).status == 'aberta'


# ── A cobrança vista pela equipe ──────────────────────────────────────────

INTERNAS = ('/cobrancas/', '/cobrancas/?status=aberta', '/cobrancas/?status=xpto',
            '/cobrancas/?aba=qr', '/cobrancas/?aba=qr&situacao=resolvida')


@pytest.mark.parametrize('papel', ['master', 'gerente', 'pleno', 'supervisor', 'visualizador',
                                   'encarregado', 'tecnico', 'pleno-de-b'])
def test_a_porta_da_equipe_e_a_mesma_da_tela_antiga(app_module, mais, papel):
    base = papel.split('-')[0]
    locais = ['Hospital Norte'] if papel.endswith('de-b') else ['Shopping Centro']
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta5i.{papel}@trino.com', base, locais=locais)
    c = fabrica.entrar(app_module, f'porta5i.{papel}@trino.com')
    for antiga in INTERNAS + (f"/cobrancas/{mais['cobranca']}", '/cobrancas/999999'):
        r_antiga, r_api, r_nova = c.get(antiga), c.get('/api/v1' + antiga), c.get('/novo' + antiga)
        assert r_api.status_code == r_antiga.status_code, (papel, antiga, r_antiga.status_code)
        assert r_nova.status_code in ((200, 503) if r_antiga.status_code == 200
                                      else (r_antiga.status_code,)), (papel, antiga)
        if r_api.status_code != 200:
            assert r_api.is_json and 'Vidros' not in r_api.get_data(as_text=True)
        if papel.endswith('de-b'):
            assert 'Vidros' not in r_api.get_data(as_text=True)
            assert 'Pia entupida' not in r_api.get_data(as_text=True)


def test_a_lista_da_equipe_traz_os_dados_da_tela_antiga(app_module, mais):
    c = fabrica.entrar(app_module, 'coord.gl@trino.com')
    for busca in INTERNAS:
        d = c.get('/api/v1' + busca).get_json()
        antigo = c.get(busca).get_data(as_text=True)
        texto = _texto(antigo)
        if d['aba'] == 'qr':
            for x in d['avisos']:
                assert x['url'] == '/novo' + html_mod.unescape(re.search(
                    r'href="(/rotas/locais/[^"]+)"', antigo).group(1))
                assert (f'<span class="badge fc-sit fc-ocor-{x["status"]}">{x["situacao"]}'
                        f'</span>') in texto and x['onde'] in texto
                assert f'tarefa de {x["responsavel"]}' in texto if x['responsavel'] else True
                assert ('Fora do prazo' in texto) == any(y['atrasada'] for y in d['avisos'])
            continue
        assert [x['url'] for x in d['itens']] == [
            '/novo' + u for u in re.findall(r'href="(/cobrancas/\d+)"', antigo)]
        for x in d['itens']:
            assert (f'<span class="badge {x["situacao"]["classe"]}">{x["situacao"]["texto"]}'
                    f'</span>') in texto
            assert f'{x["local"]} · {x["autor"]}' in texto and f'prazo {x["prazo"]}' in texto
        for rotulo, url, ativo in d['filtros']:
            classe = 'btn-primary' if ativo else 'btn-outline-primary'
            assert f'btn btn-sm {classe}" href="{url[len("/novo"):]}">{rotulo}</a>' in texto


def test_responder_como_na_tela_antiga(app_module, mais):
    from app import User, db
    from facilities.portal import servico as portal
    from facilities.portal.models import Cobranca
    with app_module.app.app_context():
        cob = portal.abrir(db.session.get(User, mais['cli']), {
            'client_id': str(mais['local']), 'titulo': 'Piso', 'texto': 'Encerar',
            'prazo': _data(3)})
        db.session.commit()
        cid = cob.id
    url, api = f'/cobrancas/{cid}', f'/api/v1/cobrancas/{cid}'
    coord = fabrica.entrar(app_module, 'coord.gl@trino.com')
    d = coord.get(api).get_json()
    texto = _texto(coord.get(url).get_data(as_text=True))
    assert d['pode_responder'] and 'Resposta para o cliente' in texto
    assert f'{d["local"]} · pedida por {d["autor"]}' in texto
    for e in d['eventos']:
        assert f'{e["quando"]} · {e["autor"]} · <span class="fw-semibold">{e["tipo"]}</span>' in texto
    # O supervisor vê, mas não responde: a mesma recusa nas duas.
    sup = fabrica.entrar(app_module, 'sup.gl@trino.com')
    assert sup.get(api).get_json()['pode_responder'] is False
    _par(sup, url + '/responder', api + '/responder', {'texto': 'do supervisor'})
    _par(coord, url + '/responder', api + '/responder', {'texto': ''})
    r = coord.post(api + '/responder', data={'texto': 'Encerado às 10h.'})
    assert r.get_json() == {'recados': [{'tipo': 'success', 'texto':
                                         'Resposta enviada. O cliente confirma ou reabre pelo portal.'}],
                            'destino': f'/novo/cobrancas/{cid}'}
    _par(coord, url + '/responder', api + '/responder', {'texto': 'segunda'})
    with app_module.app.app_context():
        cob = db.session.get(Cobranca, cid)
        assert cob.status == 'respondida' and [e.tipo for e in cob.eventos] == ['aberta', 'resposta']
    # Coordenador de outro local: 403, nas duas.
    outro = fabrica.entrar(app_module, 'coord.hn@trino.com')
    assert outro.post(api + '/responder', data={'texto': 'x'}).status_code == 403
    assert outro.post(url + '/responder', data={'texto': 'x'}).status_code == 403
    # O cliente não responde pela equipe.
    assert _cliente(app_module).post(api + '/responder', data={'texto': 'x'}).status_code == 403


# ── Dentro das telas novas, os endereços migrados levam às novas ──────────

def test_nova_leva_o_portal_e_as_cobrancas_as_telas_novas(app_module):
    from facilities.telas.cadastros import nova
    assert nova('/cliente/') == '/novo/cliente/'
    assert nova('/cliente/locais/3?de=2026-01-01') == '/novo/cliente/locais/3?de=2026-01-01'
    assert nova('/cliente/cobrancas?aba=qr') == '/novo/cliente/cobrancas?aba=qr'
    assert nova('/cobrancas/5') == '/novo/cobrancas/5'
    for arquivo in ('/cliente/fotos/chamado/1', '/cliente/fotos/checklist/1',
                    '/cliente/fotos/visita/1', '/cliente/documentos/1',
                    '/cliente/relatorios/3/2026-09/arquivo.pdf',
                    '/cliente/relatorios/3/2026-09/arquivo.xlsx'):
        assert nova(arquivo) == arquivo
