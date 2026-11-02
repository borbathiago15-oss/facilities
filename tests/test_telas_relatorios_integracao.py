"""Os relatórios do cliente, o painel e as chaves da integração nas telas
novas (Fase 4c).

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``), com
  os números, as datas e as horas escritos do mesmo jeito;
* a mesma porta, perfil a perfil (a integração: só o administrador);
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* a chave da integração: a leitura nunca traz o texto nem o hash; o texto
  vai só na resposta que a cria, sem cópia (``no-store``) e sem recado;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id).
"""
import html as html_mod
import re
from datetime import date, datetime

import pytest

from tests import fabrica
from tests.test_relatorio_cliente import SETEMBRO, cena  # noqa: F401 (a fixture)

MODULOS = ('facilities.telas.relatorios', 'facilities.telas.integracao')
MES = '2026-09'


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
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'GET']) == 4
    assert len([1 for m, u in rotas if u.startswith('/novo/')]) == 4
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


TELAS = (
    # (antiga, api) — a nova é a antiga abaixo de /novo
    ('/relatorios/', '/api/v1/relatorios/'),
    ('/relatorios/?mes=2026-09', '/api/v1/relatorios/?mes=2026-09'),
    ('/relatorios/cliente/{local}/2026-09', '/api/v1/relatorios/cliente/{local}/2026-09'),
    ('/relatorios/cliente/{local}/xpto', '/api/v1/relatorios/cliente/{local}/xpto'),
    ('/relatorios/cliente/{hosp}/2026-09', '/api/v1/relatorios/cliente/{hosp}/2026-09'),
    ('/relatorios/cliente/999999/2026-09', '/api/v1/relatorios/cliente/999999/2026-09'),
    ('/painel', '/api/v1/painel'),
    ('/painel?de=2026-09-01&ate=2026-09-30', '/api/v1/painel?de=2026-09-01&ate=2026-09-30'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'pleno-de-b']


@pytest.fixture()
def hosp(app_module, cena):  # noqa: F811
    from tests.conftest import CONTRATOS_SEMEADOS
    with app_module.app.app_context():
        cena['hosp'] = fabrica.local(CONTRATOS_SEMEADOS[1]).id
    return cena


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, hosp, papel):
    """O mesmo código de resposta na tela antiga, na página nova e na API."""
    base = papel.split('-')[0]
    locais = ['Hospital Norte'] if papel.endswith('de-b') else ['Shopping Centro']
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta4c.{papel}@trino.com', base, locais=locais)
    c = fabrica.entrar(app_module, f'porta4c.{papel}@trino.com')
    codigos = {}
    for antiga, api in TELAS:
        antiga, api = antiga.format(**hosp), api.format(**hosp)
        r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
        assert r_api.status_code == r_antiga.status_code, (papel, api, r_antiga.status_code)
        assert r_nova.status_code in ((200, 503) if r_antiga.status_code == 200
                                      else (r_antiga.status_code,)), (papel, antiga)
        if r_api.status_code != 200:
            assert r_api.is_json and 'Lâmpada' not in r_api.get_data(as_text=True)
        codigos[antiga] = r_api.status_code
    # Contraprova: quem a porta deixa entrar e quem ela recusa.
    le = base in ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')
    de_a = not papel.endswith('de-b')
    a = hosp['local']
    assert (codigos['/relatorios/'] == 200) == le, papel
    assert (codigos['/painel'] == 200) == le, papel
    assert (codigos[f'/relatorios/cliente/{a}/2026-09'] == 200) == (le and de_a), papel
    assert codigos['/relatorios/cliente/999999/2026-09'] == (404 if le else 403)
    # A integração é só do administrador, nas duas telas.
    r_antiga = c.get('/admin/integracao/')
    r_api = c.get('/api/v1/admin/integracao/')
    r_nova = c.get('/novo/admin/integracao/')
    if base == 'master':
        assert r_antiga.status_code == r_api.status_code == 200
        assert r_nova.status_code in (200, 503)
    else:
        assert r_antiga.status_code == r_nova.status_code == 302
        assert r_api.status_code == 403 and r_api.is_json
        assert c.post('/api/v1/admin/integracao/', data={'nome': 'x', 'todos': '1'}).status_code == 403
        assert c.post('/api/v1/admin/integracao/1/revogar').status_code == 403


def test_o_cliente_do_portal_nao_entra(app_module, hosp):
    """A conta de cliente fica no portal: as telas novas recusam como as antigas."""
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    try:
        with app_module.app.app_context():
            fabrica.cliente(app_module, 'cliente.rel4c@gl.com', hosp['cliente'])
        c = fabrica.entrar_com_codigo(app_module, 'cliente.rel4c@gl.com')
        for antiga, api in TELAS + (('/admin/integracao/', '/api/v1/admin/integracao/'),):
            antiga, api = antiga.format(**hosp), api.format(**hosp)
            r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
            assert r_antiga.status_code == r_api.status_code == r_nova.status_code == 403, antiga
            assert 'Lâmpada' not in r_api.get_data(as_text=True)
    finally:
        app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False


# ── Relatórios: os mesmos dados das telas antigas ─────────────────────────

def test_o_inicio_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):  # noqa: F811
    c = auth_client
    c.post(f"/relatorios/cliente/{cena['local']}/{MES}/liberar")
    for busca in ('', f'?mes={MES}', '?mes=xpto', '?mes=2026-08'):
        d = c.get('/api/v1/relatorios/' + busca).get_json()
        antigo = c.get('/relatorios/' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        assert [x['url'] for x in d['locais']] == [
            '/novo' + x for x in re.findall(r'class="fc-fila-item" href="([^"]+)"', antigo)]
        assert f'<span class="fw-bold">{d["nome_do_mes"]}</span>' in texto
        assert d['links']['anterior'] == '/novo' + html_mod.unescape(
            re.search(r'href="([^"]+)" aria-label="Mês anterior"', antigo).group(1))
        assert d['links']['seguinte'] == '/novo' + html_mod.unescape(
            re.search(r'href="([^"]+)" aria-label="Mês seguinte"', antigo).group(1))
        for x in d['locais']:
            assert f'<span class="small text-muted">{x["cliente"]}</span>{x["nome"]}</span>' in texto
            if x['liberado']:
                assert f'em {x["liberado_em"]}</span>' in texto
        assert texto.count('>Liberado<') == sum(x['liberado'] for x in d['locais'])
    d = c.get(f'/api/v1/relatorios/?mes={MES}').get_json()
    [shop] = [x for x in d['locais'] if x['id'] == cena['local']]
    assert shop['liberado'] and re.match(r'\d\d/\d\d \d\d:\d\d$', shop['liberado_em'])
    assert shop['cliente'] == 'Grupo GL' and d['nome_do_mes'] == 'Setembro de 2026'
    assert any(x['cliente'] == 'Sem cliente' and not x['liberado'] for x in d['locais'])


def _confere_corpo(corpo, texto):
    """O corpo do relatório da API escrito igual ao da tela antiga."""
    if corpo['nota']:
        assert f"fc-nota-{corpo['nota']['faixa']} fs-4\">{corpo['nota']['texto']}</span>" in texto
    else:
        assert 'sem movimento no mês' in texto
    assert f'<div class="small text-muted mt-1">{corpo["variacao"]}</div>' in texto
    for i in corpo['indicadores']:
        assert (f'<div class="small text-muted">{i["rotulo"]}</div><div class="fs-5 fw-bold">'
                f'{i["pct"]}</div><div class="small text-muted">{i["base"]}</div>') in texto
    for r in corpo['rotinas']:
        assert (f'<th scope="row" class="small">{r["ambiente"]}</th><td class="text-end">'
                f'{r["previstas"]}</td><td class="text-end">{r["no_prazo"]}</td><td class="text-end">'
                f'{r["com_atraso"]}</td><td class="text-end">{r["nao_feitas"]}</td>'
                f'<td class="text-end fw-semibold">{r["pct"]}</td>') in texto
    ch = corpo['chamados']
    assert f'<b class="fs-5">{ch["pct_no_prazo"]}</b> no prazo' in texto
    assert f'<b class="fs-5">{ch["tempo_medio"]}</b> tempo médio de solução' in texto
    for x in ch['lista']:
        assert (f'<td>{x["numero"]}</td><td>{x["titulo"]}</td><td>{x["categoria"]}</td>'
                f'<td>{x["aberto_em"]}</td><td>{x["resolvido_em"]}</td><td>{x["situacao"]}</td>') in texto
    n = corpo['ncs']
    assert (f'{n["total"]} item(ns) não conforme(s) nos checklists; {n["corrigidas"]} já '
            f'corrigido(s) por chamado.') in texto
    for item, vezes in n['itens']:
        assert f'<li>{item} <span class="text-muted">({vezes}×)</span></li>' in texto
    o = corpo['ocorrencias']
    assert (f'Avisos pelo QR: {o["total"]} recebido(s), {o["resolvidas"]} resolvido(s), '
            f'{o["pct_no_prazo"]} no prazo, tempo médio {o["tempo_medio"]}.') in texto
    v, cb = corpo['visitas'], corpo['cobrancas']
    assert (f'Visitas de supervisão: {v["feitas"]} de {v["programadas"]} feitas, '
            f'{v["conformes"]} sem item não conforme.') in texto
    assert (f'Cobranças: {cb["abertas"]} aberta(s), {cb["respondidas"]} respondida(s) '
            f'({cb["no_prazo"]} no prazo), {cb["encerradas"]} encerrada(s).') in texto
    el = corpo['elogios']
    assert el is not None and 'Elogios do público' in texto
    if el['total']:
        assert f'{el["media"]} de 5</span> · {el["total"]} avaliação(ões)' in texto
        for x in el['comentarios']:
            assert (f'<li>"{x["texto"]}" <span class="text-muted">({x["nota"]} {x["estrelas"]} · '
                    f'{x["onde"]} · {x["quando"]})</span></li>') in texto
    else:
        assert 'Nenhuma avaliação pelo QR no mês.' in texto
    assert [f['url'] for f in corpo['fotos']] == re.findall(
        r'<figure class="m-0"><a href="([^"]+)"', texto)
    for f in corpo['fotos']:
        assert f'<figcaption class="small text-muted">{f["legenda"]}</figcaption>' in texto


def test_o_relatorio_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):  # noqa: F811
    from app import db
    from facilities.rotas.models import ElogioPublico
    with app_module.app.app_context():
        for nota, texto in ((5, 'Banheiro impecável'), (1, None)):
            db.session.add(ElogioPublico(client_id=cena['local'], ponto_id=cena['ponto'], nota=nota,
                                         texto=texto,
                                         criado_em=datetime(2026, 9, 20, 15)))
        db.session.commit()
    c = auth_client
    url = f"/relatorios/cliente/{cena['local']}/{MES}"
    d = c.get('/api/v1' + url).get_json()
    texto = _texto(c.get(url).get_data(as_text=True))
    assert d['nome_do_mes'] == 'Setembro de 2026' and d['cliente'] == 'Grupo GL'
    assert f'<span>{d["nome_do_mes"]}</span> · ainda não liberado ao cliente' in texto
    assert d['pode_gerir'] and d['mes_fechado'] and d['mudou'] == [] and d['recado'] == ''
    _confere_corpo(d['corpo'], texto)
    corpo = d['corpo']
    assert corpo['chamados']['lista'][0]['titulo'] == 'Lâmpada queimada'
    assert corpo['chamados']['tempo_medio'] == '24,0 h' and corpo['chamados']['pct_no_prazo'] == '100,0%'
    assert corpo['rotinas'][0]['pct'] == '50,0%' and corpo['ncs']['itens'] == [['Piso limpo?', 1]]
    assert corpo['elogios']['media'] == '3,0' and corpo['elogios']['comentarios'][0]['estrelas'] == 'estrelas'
    assert corpo['ocorrencias']['pct_no_prazo'] == '—' and corpo['ocorrencias']['tempo_medio'] == '—'
    # A escolha das fotos: as candidatas do mês, as marcadas e o "até 12".
    e = d['escolha']
    assert f'Escolher as fotos ({len(e["todas"])} no mês, até {e["fotos_max"]})' in texto
    assert [f['ref'] for f in e['todas']] == re.findall(r'name="foto" value="([^"]+)"', texto)
    assert [f['ref'] for f in e['todas'] if f['escolhida']] == re.findall(
        r'name="foto" value="([^"]+)" checked', texto)
    assert e['automatica'] and 'Hoje vale a amostra automática.' in texto
    # O PDF e o Excel: os mesmos endereços da antiga, no servidor.
    assert f'href="{d["links"]["pdf"]}"' in texto and f'href="{d["links"]["xlsx"]}"' in texto
    assert not d['links']['pdf'].startswith('/novo') and d['links']['pdf'].endswith('/arquivo.pdf')
    assert c.get(d['links']['pdf']).mimetype == 'application/pdf'
    assert d['links']['inicio'] == f'/novo/relatorios/?mes={MES}'
    # O mês inválido vira o mês passado, como na antiga.
    assert c.get(f"/api/v1/relatorios/cliente/{cena['local']}/xpto").get_json()['mes'] == \
        re.search(r'href="/relatorios/cliente/\d+/(\d{4}-\d\d)/arquivo.pdf"',
                  c.get(f"/relatorios/cliente/{cena['local']}/xpto").get_data(as_text=True)).group(1)


def test_quem_so_le_nao_recebe_a_gestao_e_o_servidor_recusa(app_module, cena):  # noqa: F811
    from facilities.relatorios import cliente as rel
    sup = fabrica.entrar(app_module, 'sup.rel@trino.com')
    url = f"/relatorios/cliente/{cena['local']}/{MES}"
    d = sup.get('/api/v1' + url).get_json()
    antigo = sup.get(url).get_data(as_text=True)
    assert d['pode_gerir'] is False and d['escolha'] is None
    assert 'Antes de liberar' not in antigo and 'Escolher as fotos' not in antigo
    _confere_corpo(d['corpo'], _texto(antigo))
    for acao, dados in (('liberar', {}), ('recado', {'recado': 'Invasão'}), ('fotos', {'foto': 'x'}),
                        ('amostra', {}), ('recolher', {})):
        _par(sup, f'{url}/{acao}', f'/api/v1{url}/{acao}', dados)
    with app_module.app.app_context():
        assert rel.relatorio_do_mes(cena['local'], SETEMBRO) is None


# ── Relatórios: os envios, como na tela antiga ────────────────────────────

def test_os_envios_do_relatorio_como_na_tela_antiga(app_module, cena, auth_client):  # noqa: F811
    from app import db
    from facilities.relatorios import cliente as rel
    from facilities.rotas.models import ElogioPublico
    c = auth_client
    url = f"/relatorios/cliente/{cena['local']}/{MES}"
    api = '/api/v1' + url
    _par(c, url + '/recado', api + '/recado', {'recado': 'Reforçamos o 2º andar.'})
    with app_module.app.app_context():
        assert rel.relatorio_do_mes(cena['local'], SETEMBRO).recado == 'Reforçamos o 2º andar.'
    d = c.get(api).get_json()
    assert d['recado'] == 'Reforçamos o 2º andar.'
    refs = [f['ref'] for f in d['escolha']['todas']]
    _par(c, url + '/fotos', api + '/fotos', {'foto': refs[:1]}, json=False)
    _par(c, url + '/fotos', api + '/fotos', {'foto': refs[:1]}, {'foto': refs[:1]}, json=True)
    d = c.get(api).get_json()
    assert [f['ref'] for f in d['corpo']['fotos']] == refs[:1] and not d['escolha']['automatica']
    assert 'Voltar para a amostra automática' in c.get(url).get_data(as_text=True)
    _par(c, url + '/amostra', api + '/amostra', {})
    # Mais fotos do que cabe: a recusa, com a mesma frase.
    _, rec, _ = _par(c, url + '/fotos', api + '/fotos', {'foto': refs * 13},
                     {'foto': refs * 13}, json=True)
    assert rec[0]['tipo'] == 'success'   # repetidas contam uma vez só
    # Liberar o mês que ainda não acabou: a recusa da regra.
    hoje = __import__('facilities').tempo.hoje()
    aberto = hoje.strftime('%Y-%m')
    _, rec, j = _par(c, f"/relatorios/cliente/{cena['local']}/{aberto}/liberar",
                     f"/api/v1/relatorios/cliente/{cena['local']}/{aberto}/liberar", {})
    assert 'ainda não acabou' in j['error']
    assert c.get(f"/api/v1/relatorios/cliente/{cena['local']}/{aberto}").get_json()['mes_fechado'] is False
    # Liberar, mudar um número e ver o aviso como a antiga.
    _par(c, url + '/liberar', api + '/liberar', {})
    with app_module.app.app_context():
        r = rel.relatorio_do_mes(cena['local'], SETEMBRO)
        assert r.liberado_em is not None and r.congelado_json
        db.session.add(ElogioPublico(client_id=cena['local'], ponto_id=cena['ponto'], nota=5,
                                     criado_em=datetime(2026, 9, 20, 15)))
        db.session.commit()
    d = c.get(api).get_json()
    texto = _texto(c.get(url).get_data(as_text=True))
    assert d['liberado_em'] and f'liberado ao cliente em {d["liberado_em"]}</span>' in texto
    assert d['mudou'] == [['Elogios do público', '0', '1']]
    for o_que, antes, agora in d['mudou']:
        assert f'<li>{o_que}: {antes} → {agora}</li>' in texto
    assert 'Liberar a versão atual' in texto and 'Recolher do portal' in texto
    _par(c, url + '/recolher', api + '/recolher', {})
    with app_module.app.app_context():
        assert rel.relatorio_do_mes(cena['local'], SETEMBRO).liberado_em is None
    # Ação que não existe: 404 nas duas.
    assert c.post(url + '/apagar').status_code == 404
    r = c.post(api + '/apagar')
    assert r.status_code == 404 and r.is_json


def test_quem_e_de_outro_local_nao_ve_nem_altera_o_relatorio(app_module, cena):  # noqa: F811
    from facilities.relatorios import cliente as rel
    fora = fabrica.entrar(app_module, 'fora.rel@trino.com')
    url = f"/api/v1/relatorios/cliente/{cena['local']}/{MES}"
    r = fora.get(url)
    assert r.status_code == 403 and r.is_json and 'Lâmpada' not in r.get_data(as_text=True)
    for acao in ('recado', 'fotos', 'amostra', 'liberar', 'recolher'):
        r = fora.post(f'{url}/{acao}', data={'recado': 'Invasão'})
        assert r.status_code == 403 and r.is_json, acao
    d = fora.get('/api/v1/relatorios/').get_json()
    assert cena['local'] not in [x['id'] for x in d['locais']]
    d = fora.get('/api/v1/painel').get_json()
    assert 'Shopping Centro' not in str(d)
    with app_module.app.app_context():
        assert rel.relatorio_do_mes(cena['local'], SETEMBRO) is None


# ── O painel ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('quem', ['admin', 'sup.rel@trino.com'])
def test_o_painel_traz_os_dados_da_tela_antiga(app_module, cena, auth_client, quem):  # noqa: F811
    from app import db
    from facilities.rotas.models import ElogioPublico
    with app_module.app.app_context():
        db.session.add(ElogioPublico(client_id=cena['local'], ponto_id=cena['ponto'], nota=4,
                                     criado_em=datetime(2026, 9, 20, 15)))
        db.session.commit()
    c = auth_client if quem == 'admin' else fabrica.entrar(app_module, quem)
    for busca in ('?de=2026-09-01&ate=2026-09-30', '?de=2026-09-30&ate=2026-09-01', '',
                  '?de=xpto', '?de=2020-01-01&ate=2026-09-30'):
        d = c.get('/api/v1/painel' + busca).get_json()
        texto = _texto(c.get('/painel' + busca).get_data(as_text=True))
        assert f'value="{d["de"]}"' in texto and f'value="{d["ate"]}"' in texto
        assert f'O período vai de {d["de_br"]} a {d["ate_br"]}.' in texto
        assert (f'Abaixo de {d["faixa_critica"]}: crítica; de {d["faixa_critica"]} a '
                f'{d["faixa_boa"] - 1}: atenção; {d["faixa_boa"]} ou mais: boa.') in texto
        r = d['resumo']
        assert f'Nota média</div><div class="fs-4 fw-bold">{r["media"]}</div>' in texto
        for rotulo, n in r['faixas']:
            assert f'{rotulo}</div><div class="fs-4 fw-bold">{n}</div>' in texto
        assert ('Sem dado</div>' in texto) == (r['sem_dado'] > 0)
        for v in d['indicadores']:
            assert f'<th scope="col" class="text-center small">{v}</th>' in texto
        assert (d['grupos'] is None) == (quem.startswith('sup.'))
        linhas = d['linhas'] if d['grupos'] is None else [x for g in d['grupos'] for x in g['linhas']]
        assert [x['local'] for x in linhas] == re.findall(r'<th scope="row" class="small">([^<]+)</th>', texto)
        assert sorted(x['local'] for x in linhas) == sorted(x['local'] for x in d['linhas'])
        for g in d['grupos'] or []:
            assert f'{g["cliente"]} <span class="small text-muted fw-normal">· nota média {g["media"]}</span>' in texto
        for x in linhas:
            if x['nota']:
                assert f'fc-nota-{x["faixa"]}">{x["nota"]}</span>' in texto
            for i in x['indicadores']:
                if i:
                    assert f'{i["pct"]}<br><span class="text-muted">{i["base"]}</span>' in texto
            if x['elogios']:
                assert (f'{x["elogios"]["media"]}</span><br><span class="text-muted">'
                        f'{x["elogios"]["total"]} avaliação(ões)</span>') in texto
            assert x['atrasadas_url'].startswith('/novo/demandas/?')
    d = c.get('/api/v1/painel?de=2026-09-01&ate=2026-09-30').get_json()
    [shop] = [x for x in d['linhas'] if x['local'] == 'Shopping Centro']
    assert shop['elogios'] == {'media': '4,0', 'total': 1}
    assert shop['indicadores'][0] == {'pct': '50,0%', 'base': '1 de 2'}
    assert shop['nota'] and re.match(r'\d+,\d · ', shop['nota'])
    # Mais de 366 dias: o mesmo corte da antiga.
    d = c.get('/api/v1/painel?de=2020-01-01&ate=2026-09-30').get_json()
    assert (date.fromisoformat(d['ate']) - date.fromisoformat(d['de'])).days == 365


# ── A integração ──────────────────────────────────────────────────────────

def _chave_da_pagina(html):
    return re.search(r'fac_[0-9a-f]{8}_[A-Za-z0-9_-]{20,}', html).group(0)


def test_a_lista_das_chaves_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):  # noqa: F811
    from app import db
    from facilities.integracao import servico
    from facilities.integracao.models import IntegracaoChave
    c = auth_client
    _chave_da_pagina(c.post('/admin/integracao/', data={'nome': 'Produção', 'todos': '1'})
                     .get_data(as_text=True))
    _chave_da_pagina(c.post('/admin/integracao/', data={
        'nome': 'Só o shopping', 'client_id': [str(cena['local'])]}).get_data(as_text=True))
    with app_module.app.app_context():
        ch = IntegracaoChave.query.filter_by(nome='Só o shopping').one()
        servico.revogar(ch)
        servico.registrar_acesso(None, 'locais', {'de': '2026-09-01', 'x': 'y'}, 401)
        db.session.commit()
    d = c.get('/api/v1/admin/integracao/').get_json()
    texto = _texto(c.get('/admin/integracao/').get_data(as_text=True))
    assert [x['nome'] for x in d['chaves']] == re.findall(r'<span class="fw-semibold">([^<]+)</span>', texto)
    for x in d['chaves']:
        assert f'<code class="small">{x["prefixo"]}</code>' in texto
        linha = f'{x["locais"]} · criada {x["criada_em"]}'
        if x['ultimo_uso_em']:
            linha += f' · último uso {x["ultimo_uso_em"]}'
        assert linha + '</span>' in texto
    assert [x['ativa'] for x in d['chaves']] == [True, False] and texto.count('>revogada</span>') == 1
    assert d['chaves'][1]['locais'] == 'Shopping Centro'
    [a] = d['acessos']
    assert (f'<td class="text-nowrap small">{a["em"]}</td><td class="small">{a["chave"]}</td>'
            f'<td class="small">{a["rota"]}</td><td class="small">{a["parametros"]}</td>'
            f'<td class="small">{a["status"]}</td><td class="text-end small">{a["itens"]}</td>') in texto
    assert a['chave'] == 'chave inválida' and a['parametros'] == 'de=2026-09-01'
    assert [x['id'] for x in d['locais']] == [
        int(x) for x in re.findall(r'name="client_id" value="(\d+)"', texto)]


def test_a_leitura_nunca_traz_o_texto_nem_o_hash_da_chave(app_module, cena, auth_client):  # noqa: F811
    from facilities.integracao.models import IntegracaoChave
    c = auth_client
    r, j = _nova(c, '/api/v1/admin/integracao/', json={'nome': 'Intelligence', 'todos': '1'})
    texto = j['chave']['texto']
    with app_module.app.app_context():
        hashes = [x.hash_chave for x in IntegracaoChave.query.all()]
    corpo = c.get('/api/v1/admin/integracao/').get_data(as_text=True)
    segredo = texto.split('_', 2)[2]
    for proibido in [texto, segredo] + hashes:
        assert proibido not in corpo
    assert 'hash' not in corpo
    # Também não sai na página nova (a casca) nem num recado guardado na sessão.
    assert texto not in c.get('/novo/admin/integracao/').get_data(as_text=True)
    with c.session_transaction() as s:
        assert texto not in str(dict(s))


def test_criar_e_revogar_como_na_tela_antiga(app_module, cena, auth_client):  # noqa: F811
    from tests.test_paineis_integracao import _get
    from facilities.integracao.models import IntegracaoChave
    c = auth_client
    # Criar: a antiga mostra a chave na própria resposta; a nova, no JSON.
    antiga = c.post('/admin/integracao/', data={'nome': 'Antiga', 'todos': '1'})
    assert antiga.headers['Cache-Control'] == 'no-store' and 'Copie agora' in antiga.get_data(as_text=True)
    assert _flashes(c) == []
    r, j = _nova(c, '/api/v1/admin/integracao/', data={'nome': 'Nova', 'client_id': [str(cena['local'])]})
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert j['recados'] == [] and j['destino'] == '/novo/admin/integracao/'
    assert j['chave']['nome'] == 'Nova' and re.match(r'fac_[0-9a-f]{8}_', j['chave']['texto'])
    assert _flashes(c) == []
    assert _get(app_module, 'locais', j['chave']['texto']).status_code == 200
    assert _get(app_module, 'locais', _chave_da_pagina(antiga.get_data(as_text=True))).status_code == 200
    with app_module.app.app_context():
        nova = IntegracaoChave.query.filter_by(nome='Nova').one()
        assert not nova.todos_os_locais and [x.id for x in nova.locais] == [cena['local']]
        kid = nova.id
        antes = IntegracaoChave.query.count()
    # As recusas: sem nome, sem local.
    for dados in ({'nome': '', 'todos': '1'}, {'nome': 'Sem local'}):
        _par(c, '/admin/integracao/', '/api/v1/admin/integracao/', dados)
    with app_module.app.app_context():
        assert IntegracaoChave.query.count() == antes
    # Revogar.
    with app_module.app.app_context():
        antiga_id = IntegracaoChave.query.filter_by(nome='Antiga').one().id
    d1, rec = _antiga(c, f'/admin/integracao/{antiga_id}/revogar')
    r, j2 = _nova(c, f'/api/v1/admin/integracao/{kid}/revogar')
    assert rec == [{'tipo': 'success', 'texto': 'Chave "Antiga" revogada: deixa de funcionar agora.'}]
    assert r.status_code == 200 and j2['destino'] == '/novo' + d1 == '/novo/admin/integracao/'
    assert j2['recados'] == [{'tipo': 'success', 'texto': 'Chave "Nova" revogada: deixa de funcionar agora.'}]
    assert _get(app_module, 'locais', j['chave']['texto']).status_code == 401
    # Revogar de novo (segunda aba, envio repetido): a data da revogação é
    # auditoria e não muda; as duas telas dizem que já estava revogada.
    from facilities import tempo
    with app_module.app.app_context():
        datas = {k: IntegracaoChave.query.get(k).revogada_em for k in (antiga_id, kid)}
    d2, rec = _antiga(c, f'/admin/integracao/{antiga_id}/revogar')
    r, j3 = _nova(c, f'/api/v1/admin/integracao/{kid}/revogar')
    assert d2 == d1 and r.status_code == 200 and j3['destino'] == '/novo' + d1
    assert rec == [{'tipo': 'info', 'texto': f'A chave "Antiga" já estava revogada desde '
                                            f'{tempo.fmt(datas[antiga_id])}. Nada mudou.'}]
    assert j3['recados'] == [{'tipo': 'info', 'texto': f'A chave "Nova" já estava revogada desde '
                                                     f'{tempo.fmt(datas[kid])}. Nada mudou.'}]
    with app_module.app.app_context():
        assert {k: IntegracaoChave.query.get(k).revogada_em for k in (antiga_id, kid)} == datas
    r = c.post('/api/v1/admin/integracao/999999/revogar')
    assert r.status_code == 404 and r.is_json


# ── Dentro das telas novas, os links levam às novas ───────────────────────

def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):  # noqa: F811
    from facilities.telas.cadastros import nova
    assert nova('/relatorios/') == '/novo/relatorios/'
    assert nova('/relatorios/?mes=2026-09') == '/novo/relatorios/?mes=2026-09'
    assert nova('/relatorios/cliente/1/2026-09') == '/novo/relatorios/cliente/1/2026-09'
    # O PDF e o Excel continuam onde estão; o portal do cliente entrou na Fase 5.
    assert nova('/relatorios/cliente/1/2026-09/arquivo.pdf') == '/relatorios/cliente/1/2026-09/arquivo.pdf'
    assert nova('/relatorios/cliente/1/2026-09/arquivo.xlsx') == '/relatorios/cliente/1/2026-09/arquivo.xlsx'
    assert nova('/cliente/relatorios/1/2026-09') == '/novo/cliente/relatorios/1/2026-09'
    assert nova('/cliente/relatorios/1/2026-09/arquivo.pdf') == '/cliente/relatorios/1/2026-09/arquivo.pdf'
    assert nova('/painel') == '/novo/painel'
    assert nova('/painel?de=2026-09-01') == '/novo/painel?de=2026-09-01'
    assert nova('/painel-x') == '/painel-x' and nova('/painelzinho') == '/painelzinho'
    assert nova('/admin/integracao/') == '/novo/admin/integracao/'
    assert nova('/admin/usuarios') == '/admin/usuarios'
    assert nova('/api/integracao/v1/locais') == '/api/integracao/v1/locais'
    # As telas antigas e o menu não mudam.
    c = auth_client
    assert 'href="/relatorios/cliente/' in c.get('/relatorios/').get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert {'/painel', '/relatorios/', '/admin/integracao/'} <= set(menu)
    assert not any(u.startswith(('/novo/painel', '/novo/relatorios', '/novo/admin/integracao'))
                   for u in menu)
