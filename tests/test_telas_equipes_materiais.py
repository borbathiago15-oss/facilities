"""A equipe, os materiais e as visitas de supervisão nas telas novas (Fase
4b): a equipe do local e a grade do mês, o catálogo, o estoque do local, o
consumo do mês, o custo operacional, os pedidos de insumo e as visitas do
local.

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``), com
  as datas, as quantidades e os valores escritos do mesmo jeito;
* a mesma porta, perfil a perfil;
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id).
"""
import html as html_mod
import re
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS

LOCAL_A, LOCAL_B = CONTRATOS_SEMEADOS[0], CONTRATOS_SEMEADOS[1]
SEGREDO = 'EQUIPE-SECRETA-A'
MODULOS = ('facilities.telas.equipes', 'facilities.telas.materiais')


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


def _mesmo_recado(antigo, novo, troca=()):
    textos = [x['texto'] for x in antigo]
    for a, b in troca:
        textos = [t.replace(a, b) for t in textos]
    assert [x['texto'] for x in novo] == textos
    assert [x['tipo'] for x in novo] == [x['tipo'] for x in antigo]


def _par(c, antiga, nova, dados_antigo, dados_novo=None, troca=(), json=False):
    """O mesmo envio pela tela antiga e pela nova: o mesmo recado, o mesmo
    destino (abaixo de /novo) e, na recusa, 400 com a mesma frase."""
    d1, rec = _antiga(c, antiga, data=dados_antigo)
    corpo = dados_novo if dados_novo is not None else dados_antigo
    r, j = _nova(c, nova, **({'json': corpo} if json else {'data': corpo}))
    _mesmo_recado(rec, j['recados'], troca)
    assert j['destino'] == '/novo' + d1, (nova, j['destino'], d1)
    recusou = any(x['tipo'] == 'danger' for x in rec)
    assert r.status_code == (400 if recusou else 200), (nova, rec)
    if recusou:
        assert j['error'] == j['recados'][0]['texto'] and j['recados'][0]['tipo'] == 'danger'
    return d1, rec, j


def _ordem(padrao, html):
    """Os ids na ordem em que aparecem, sem repetir (o "Editar" e o
    "Desativar" do mesmo item apontam para o mesmo endereço)."""
    vistos = []
    for x in re.findall(padrao, html):
        if int(x) not in vistos:
            vistos.append(int(x))
    return vistos


@pytest.fixture()
def cena(app_module, auth_client):
    """Em A: dois funcionários ativos (um com login) e um desligado, dois
    postos (um com rota, um desativado), uma escala com falta coberta hoje e
    atraso ontem; um checklist publicado e duas visitas programadas (uma
    desativada) com a de hoje aberta; três materiais (com preço, sem preço,
    desativado), entrada, consumo e um pedido de insumo. Em B: um local."""
    from app import Client, User, db
    from facilities.equipes import servico as eq
    from facilities.materiais import servico as mat
    from facilities.rotas import servico as s
    from facilities.visitas import servico as vis
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        a = ids['local']
        b = fabrica.local(LOCAL_B).id
        loc = db.session.get(Client, a)
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        enc = fabrica.pessoa(app_module, 'eq4b.enc@trino.com', 'encarregado', locais=[LOCAL_A],
                             nome='Encarregada Quatro')
        sup = fabrica.pessoa(app_module, 'eq4b.sup@trino.com', 'supervisor', locais=[LOCAL_A],
                             nome='Supervisora Quatro')
        m = s.criar_modelo(a, {'nome': f'Checklist {SEGREDO}'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Uniforme?', 'tipo': 'sim_nao'}]), {}, None)
        rota = s.salvar_rota(loc, None, {'nome': f'Rota {SEGREDO}', 'turno': 'T1',
                                         'hora_inicio': '00:00', 'hora_fim': '23:59',
                                         'tolerancia_min': '60', 'dias_semana': '1234567'})
        ana = eq.salvar_funcionario(loc, None, {'nome': f'Ana {SEGREDO}', 'funcao': 'ASG',
                                                'matricula': '123', 'user_id': str(enc)}, admin)
        mariana = eq.salvar_funcionario(loc, None, {'nome': 'Mariana', 'funcao': 'ASG'}, admin)
        velho = eq.salvar_funcionario(loc, None, {'nome': 'Zé Desligado'}, admin)
        velho.is_active = False
        posto = eq.salvar_posto(loc, None, {'nome': 'Limpeza 2º andar — manhã',
                                            'hora_inicio': '07:00', 'hora_fim': '15:00',
                                            'rota_id': str(rota.id)})
        p2 = eq.salvar_posto(loc, None, {'nome': 'Portaria noite', 'hora_inicio': '22:00',
                                         'hora_fim': '06:00'})
        p2.is_active = False
        esc = eq.salvar_escala(loc, {'funcionario_id': ana.id, 'posto_id': posto.id,
                                     'dias_semana': '1234567',
                                     'data_inicio': (tempo.hoje() - timedelta(days=20)).isoformat(),
                                     'data_fim': (tempo.hoje() + timedelta(days=60)).isoformat()},
                               admin)
        db.session.flush()
        falta = eq.registrar_presenca(admin, esc, tempo.hoje(), 'faltou', 'atestado')
        eq.registrar_cobertura(admin, falta, {'funcionario_id': str(mariana.id),
                                              'motivo': 'Folga trocada'})
        eq.registrar_presenca(admin, esc, tempo.hoje() - timedelta(days=1), 'atrasou', '')
        prog = vis.salvar_programada(loc, None, {
            'nome': f'Visita {SEGREDO}', 'modelo_id': str(m.id), 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat(), 'supervisor_id': str(sup)}, admin)
        parada = vis.salvar_programada(loc, None, {
            'nome': 'Visita parada', 'modelo_id': str(m.id), 'intervalo_dias': '30',
            'proxima_em': (tempo.hoje() + timedelta(days=5)).isoformat()}, admin)
        parada.is_active = False
        db.session.flush()
        vis.gerar_visitas(tempo.hoje())
        detergente = mat.salvar_material(None, {'nome': 'Detergente neutro', 'unidade': 'L',
                                                'preco_unitario': '1.234,5'})
        pano = mat.salvar_material(None, {'nome': 'Pano de chão', 'unidade': 'un'})
        sumido = mat.salvar_material(None, {'nome': 'Cera antiga', 'unidade': 'L'})
        sumido.is_active = False
        mat.movimentar(admin, loc, {'material_id': str(detergente.id), 'quantidade': '10'},
                       'entrada')
        mat.movimentar(admin, loc, {'material_id': str(pano.id), 'quantidade': '3'}, 'entrada')
        mat.consumir(admin, loc, {'material_id': str(detergente.id), 'quantidade': '1,5',
                                  'motivo': f'Consumo {SEGREDO}'})
        mat.consumir(admin, loc, {'material_id': str(pano.id), 'quantidade': '1'})
        pedido = mat.pedir(db.session.get(User, enc), loc, {
            'material_id': str(pano.id), 'quantidade': '5', 'texto': f'Pedido {SEGREDO}'})
        db.session.commit()
        from facilities.visitas.models import Visita
        ids.update(local_b=b, enc=enc, sup=sup, modelo=m.id, rota=rota.id, ana=ana.id,
                   mariana=mariana.id, velho=velho.id, posto=posto.id, posto_parado=p2.id,
                   escala=esc.id, programada=prog.id, parada=parada.id,
                   visita=Visita.query.filter_by(programada_id=prog.id).one().id,
                   detergente=detergente.id, pano=pano.id, sumido=sumido.id, pedido=pedido.id)
    return ids


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
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) == 12
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'GET']) == 8
    assert len([1 for m, u in rotas if u.startswith('/novo/')]) == 8
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


TELAS = (
    # (antiga, api) — a nova é a antiga abaixo de /novo
    ('/equipes/locais/{local}', '/api/v1/equipes/locais/{local}'),
    ('/equipes/locais/{local}/mes?m=2026-02', '/api/v1/equipes/locais/{local}/mes?m=2026-02'),
    ('/equipes/locais/{local_b}', '/api/v1/equipes/locais/{local_b}'),
    ('/equipes/locais/999999/mes', '/api/v1/equipes/locais/999999/mes'),
    ('/visitas/locais/{local}', '/api/v1/visitas/locais/{local}'),
    ('/visitas/locais/{local_b}', '/api/v1/visitas/locais/{local_b}'),
    ('/materiais/', '/api/v1/materiais/'),
    ('/materiais/custo?de=2026-01-01&ate=2026-12-31', '/api/v1/materiais/custo?de=2026-01-01&ate=2026-12-31'),
    ('/materiais/pedidos', '/api/v1/materiais/pedidos'),
    ('/materiais/locais/{local}', '/api/v1/materiais/locais/{local}'),
    ('/materiais/locais/{local}/mes?m=xpto', '/api/v1/materiais/locais/{local}/mes?m=xpto'),
    ('/materiais/locais/{local_b}', '/api/v1/materiais/locais/{local_b}'),
    ('/materiais/locais/999999', '/api/v1/materiais/locais/999999'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'pleno-de-b']


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta na tela antiga, na página nova e na API."""
    base = papel.split('-')[0]
    locais = [LOCAL_B] if papel.endswith('de-b') else [LOCAL_A]
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta4b.{papel}@trino.com', base, locais=locais)
    c = fabrica.entrar(app_module, f'porta4b.{papel}@trino.com')
    codigos = {}
    for antiga, api in TELAS:
        antiga, api = antiga.format(**cena), api.format(**cena)
        r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
        assert r_api.status_code == r_antiga.status_code, (papel, api, r_antiga.status_code)
        assert r_nova.status_code in ((200, 503) if r_antiga.status_code == 200
                                      else (r_antiga.status_code,)), (papel, antiga)
        if r_api.status_code != 200:
            assert r_api.is_json and SEGREDO not in r_api.get_data(as_text=True), (papel, api)
        codigos[antiga] = r_api.status_code
    # Contraprova: quem a porta deixa entrar e quem ela recusa.
    de_a = not papel.endswith('de-b')
    gestao = base in ('master', 'gerente', 'pleno')
    ve_custo = gestao or base in ('supervisor', 'visualizador')
    a = cena['local']
    assert (codigos[f'/equipes/locais/{a}'] == 200) == (ve_custo and de_a), papel
    assert (codigos[f'/visitas/locais/{a}'] == 200) == (ve_custo and de_a), papel
    assert (codigos['/materiais/'] == 200) == ve_custo, papel
    assert (codigos['/materiais/pedidos'] == 200) == ve_custo, papel
    assert (codigos[f'/materiais/locais/{a}'] == 200) == (ve_custo and de_a), papel
    assert codigos['/equipes/locais/999999/mes'] == (404 if ve_custo else 403)
    assert codigos['/materiais/locais/999999'] == (404 if ve_custo else 403)


def test_o_cliente_do_portal_nao_entra(app_module, cena):
    """A conta de cliente fica no portal: as telas novas recusam como as antigas."""
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    try:
        with app_module.app.app_context():
            fabrica.cliente(app_module, 'cliente.eq4b@gl.com', cena['cliente'])
        c = fabrica.entrar_com_codigo(app_module, 'cliente.eq4b@gl.com')
        for antiga, api in TELAS:
            antiga, api = antiga.format(**cena), api.format(**cena)
            r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
            assert r_antiga.status_code == r_api.status_code == r_nova.status_code == 403, antiga
            assert SEGREDO not in r_api.get_data(as_text=True)
    finally:
        app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False


def test_quem_so_le_nao_recebe_as_acoes_e_o_servidor_recusa(app_module, cena):
    from app import db
    from facilities.equipes.models import Funcionario
    from facilities.materiais.models import Material, PedidoInsumo
    from facilities.visitas.models import VisitaProgramada
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'eq4b.diretoria@trino.com', 'visualizador', all_clients=True)
    c = fabrica.entrar(app_module, 'eq4b.diretoria@trino.com')
    a = cena['local']
    for api, antiga, texto in ((f'/api/v1/equipes/locais/{a}', f'/equipes/locais/{a}', 'Cadastrar funcionário'),
                               (f'/api/v1/visitas/locais/{a}', f'/visitas/locais/{a}', 'Programar visita'),
                               ('/api/v1/materiais/', '/materiais/', 'Cadastrar material'),
                               (f'/api/v1/materiais/locais/{a}', f'/materiais/locais/{a}', 'Lançar entrada')):
        assert c.get(api).get_json()['pode_montar'] is False, api
        assert texto not in c.get(antiga).get_data(as_text=True), antiga
    assert not any(p['pode_marcar'] for p in c.get('/api/v1/materiais/pedidos').get_json()['pedidos'])
    for url, dados in ((f'/api/v1/equipes/locais/{a}/funcionarios', {'nome': 'Invasão'}),
                       (f"/api/v1/equipes/funcionarios/{cena['ana']}", {'ativo': '0'}),
                       (f'/api/v1/equipes/locais/{a}/postos', {'nome': 'Invasão'}),
                       (f"/api/v1/equipes/postos/{cena['posto']}", {'ativo': '0'}),
                       (f'/api/v1/equipes/locais/{a}/escalas', {'funcionario_id': str(cena['mariana'])}),
                       (f"/api/v1/equipes/escalas/{cena['escala']}/encerrar", {'data_fim': '2026-01-01'}),
                       (f'/api/v1/visitas/locais/{a}', {'nome': 'Invasão'}),
                       (f"/api/v1/visitas/programadas/{cena['programada']}", {'ativo': '0'}),
                       ('/api/v1/materiais/', {'nome': 'Invasão', 'unidade': 'un'}),
                       (f"/api/v1/materiais/{cena['detergente']}", {'ativo': '0'})):
        r = c.post(url, data=dados)
        assert r.status_code == 403 and r.is_json, url
        assert c.post(url.replace('/api/v1', ''), data=dados).status_code == 403, url
    # O movimento e o "visto" recusam pela regra (recado e volta, na antiga).
    for url, dados in ((f'/api/v1/materiais/locais/{a}/movimento',
                        {'tipo': 'saida', 'material_id': str(cena['detergente']), 'quantidade': '1',
                         'motivo': 'x'}),
                       (f"/api/v1/materiais/pedidos/{cena['pedido']}/visto", {})):
        _par(c, url.replace('/api/v1', ''), url, dados)
    with app_module.app.app_context():
        assert db.session.get(Funcionario, cena['ana']).is_active
        assert db.session.get(VisitaProgramada, cena['programada']).is_active
        assert db.session.get(Material, cena['detergente']).is_active
        assert db.session.get(PedidoInsumo, cena['pedido']).status == 'aberto'
        assert not Funcionario.query.filter_by(nome='Invasão').count()


# ── Os mesmos dados das telas antigas ─────────────────────────────────────

def test_a_equipe_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get(f'/api/v1/equipes/locais/{a}').get_json()
    antigo = c.get(f'/equipes/locais/{a}').get_data(as_text=True)
    texto = _texto(antigo)
    assert [f['id'] for f in d['funcionarios']] == _ordem(r'action="/equipes/funcionarios/(\d+)"', antigo)
    assert [p['id'] for p in d['postos']] == _ordem(r'action="/equipes/postos/(\d+)"', antigo)
    assert [e['id'] for e in d['escalas']] == _ordem(r'action="/equipes/escalas/(\d+)/encerrar"', antigo)
    por_id = {f['id']: f for f in d['funcionarios']}
    ana = por_id[cena['ana']]
    assert ana['nome'] == f'Ana {SEGREDO}' and ana['usa_app'] and ana['matricula'] == '123'
    assert f'<span class="small text-muted">matrícula {ana["matricula"]}</span>' in texto
    assert por_id[cena['velho']]['ativo'] is False and not por_id[cena['mariana']]['usa_app']
    assert texto.count('usa o aplicativo') == 1 and texto.count('sem login</span>') == 2
    [p1, p2] = d['postos']
    assert (p1['hora_inicio'], p1['hora_fim'], p1['rota']) == ('07:00', '15:00', f'Rota {SEGREDO}')
    assert f"{p1['hora_inicio']} às {p1['hora_fim']} · rota \"{p1['rota']}\"" in texto
    assert f"{p2['hora_inicio']} às {p2['hora_fim']}</span>" in texto and not p2['ativo']
    [e] = d['escalas']
    assert e['dias'] == 'Seg Ter Qua Qui Sex Sáb Dom '
    assert f"{e['posto']} · {e['dias']}· desde {e['data_inicio']} até {e['data_fim']}" in texto
    assert re.match(r'\d\d/\d\d/\d{4}$', e['data_inicio'])
    assert [u['id'] for u in d['logins']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="nfu"')[1].split('</select>')[0])]
    assert [r['id'] for r in d['rotas']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="npr"')[1].split('</select>')[0])]
    assert f'value="{d["hoje"]}"' in antigo and d['pode_montar']
    assert d['dias'][0] == ['1', 'Seg'] and len(d['dias']) == 7
    assert d['links'] == {'local': f'/novo/rotas/locais/{a}', 'mes': f'/novo/equipes/locais/{a}/mes',
                          'visitas': f'/novo/visitas/locais/{a}'}
    for k in ('local', 'mes', 'visitas'):
        assert f'href="{d["links"][k].removeprefix("/novo")}"' in antigo


def test_a_grade_do_mes_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    hoje = tempo.hoje()
    for busca in ('', f'?m={hoje.strftime("%Y-%m")}', '?m=2026-13', '?m=xpto',
                  f'?m={(hoje.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}', '?m=2020-01'):
        d = c.get(f'/api/v1/equipes/locais/{a}/mes{busca}').get_json()
        antigo = c.get(f'/equipes/locais/{a}/mes{busca}').get_data(as_text=True)
        texto = _texto(antigo)
        assert f"Escala e presença · {d['mes']}" in texto, busca
        for chave, rotulo in (('previstos', 'Dias escalados até hoje'), ('lancados', 'Presença lançada'),
                              ('faltas', 'Faltas'), ('cobertas', 'Faltas cobertas')):
            assert f'<div class="small text-muted">{rotulo}</div><div class="fs-4 fw-bold">{d["totais"][chave]}</div>' in texto
        cabeca = antigo.split('<thead>')[1].split('</thead>')[0]
        assert [int(x) for x in re.findall(r'class="text-center">(\d+)</th>', cabeca)] == d['dias']
        corpo = _texto(antigo.split('<tbody>')[1].split('</tbody>')[0])
        celulas = re.findall(r'<span class="(fc-pres fc-pres-\w+|text-muted small)" title="([^"]*)">(.)</span>', corpo)
        esperadas = [('text-muted small' if x['tipo'] == 'previsto' else f"fc-pres fc-pres-{x['tipo']}",
                      x['titulo'], x['letra']) for linha in d['linhas'] for x in linha['celulas'] if x]
        assert celulas == esperadas, busca
        assert len(re.findall(r'<td class="text-center">', corpo)) == sum(len(x['celulas']) for x in d['linhas'])
        for x in d['linhas']:
            assert f"{x['funcionario']}<br><span class=\"text-muted\">{x['posto']}</span>" in corpo
        assert f'href="/equipes/locais/{a}/mes?m={d["anterior"]}"' in antigo
        assert f'href="/equipes/locais/{a}/mes?m={d["seguinte"]}"' in antigo
        if not d['linhas']:
            assert 'Nenhuma escala neste mês.' in texto
    d = c.get(f'/api/v1/equipes/locais/{a}/mes').get_json()
    tipos = [x['tipo'] for x in d['linhas'][0]['celulas'] if x]
    assert 'coberta' in tipos and 'atrasou' in tipos
    [coberta] = [x for x in d['linhas'][0]['celulas'] if x and x['tipo'] == 'coberta']
    assert coberta['titulo'] == 'Faltou; cobriu Mariana (Folga trocada)'
    assert d['totais']['faltas'] == d['totais']['cobertas'] == 1
    assert d['links'] == {'equipe': f'/novo/equipes/locais/{a}'}
    assert c.get(f'/api/v1/equipes/locais/{a}/mes?m=2026-13').get_json()['m'] == hoje.strftime('%Y-%m')


def test_as_visitas_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get(f'/api/v1/visitas/locais/{a}').get_json()
    antigo = c.get(f'/visitas/locais/{a}').get_data(as_text=True)
    texto = _texto(antigo)
    assert [p['id'] for p in d['programadas']] == _ordem(r'action="/visitas/programadas/(\d+)"', antigo)
    ativa, parada = d['programadas']
    assert ativa['supervisor'] == 'Supervisora Quatro' and parada['supervisor'] is None
    for p in d['programadas']:
        assert f"{p['modelo']} · a cada {p['intervalo_dias']} dia(s) · {p['supervisor'] or 'qualquer supervisor'}" in texto
    assert f"próxima <strong>{ativa['proxima_em']}</strong>" in texto
    assert f"<strong>{parada['proxima_em']}</strong>" not in texto and not parada['ativo']
    # A visita em si leva ao aplicativo novo do supervisor (Fase 1d).
    assert [v['url'] for v in d['recentes']] == [
        '/novo' + u for u in re.findall(r'href="(/app/visitas/\d+)"', antigo)]
    [v] = d['recentes']
    assert v['url'] == f"/novo/app/visitas/{cena['visita']}" and v['status'] == 'prevista'
    assert f"até {v['vencimento']}" in texto and f">{v['situacao_rotulo']}</span>" in texto
    assert [m['id'] for m in d['modelos']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="vmnova"')[1].split('</select>')[0])]
    assert [s['id'] for s in d['supervisores']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="vsnova"')[1].split('</select>')[0])]
    for s in d['supervisores']:
        assert f"{s['nome']} ({s['perfil']})" in texto
    assert f'value="{d["hoje"]}"' in antigo and d['pode_montar']
    assert d['links'] == {'checklists': f'/novo/rotas/locais/{a}'}


def test_o_catalogo_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    d = c.get('/api/v1/materiais/').get_json()
    antigo = c.get('/materiais/').get_data(as_text=True)
    texto = _texto(antigo)
    assert [m['id'] for m in d['materiais']] == _ordem(r'action="/materiais/(\d+)"', antigo)
    por_id = {m['id']: m for m in d['materiais']}
    det = por_id[cena['detergente']]
    assert det['preco'] == 'R$ 1.234,50' and det['preco_campo'] == '1.234,50'
    assert f"{det['preco']} / {det['unidade']}" in texto
    assert f'id="mp{det["id"]}" name="preco_unitario" inputmode="decimal" value="{det["preco_campo"]}"' in antigo
    assert por_id[cena['pano']]['preco'] is None and por_id[cena['pano']]['preco_campo'] == ''
    assert texto.count('<span class="text-muted">sem preço</span>') == 2
    assert not por_id[cena['sumido']]['ativo'] and d['materiais'][-1]['id'] == cena['sumido']
    assert [x['url'] for x in d['locais']] == ['/novo' + x for x in re.findall(r'href="(/materiais/locais/\d+)"', antigo)]
    assert d['links'] == {'catalogo': '/novo/materiais/', 'custo': '/novo/materiais/custo',
                          'pedidos': '/novo/materiais/pedidos'} and d['pode_montar']


def test_o_estoque_do_local_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get(f'/api/v1/materiais/locais/{a}').get_json()
    antigo = c.get(f'/materiais/locais/{a}').get_data(as_text=True)
    texto = _texto(antigo)
    saldo = _texto(antigo.split('id="tit-saldo"')[1].split('</section>')[0])
    assert [(s['nome'], s['saldo'], s['unidade']) for s in d['com_saldo']] == re.findall(
        r'<span class="fw-semibold">([^<]+)</span> <span class="ms-auto fw-bold ">([^ ]+) ([^<]+)</span>', saldo)
    assert {s['nome']: s['saldo'] for s in d['com_saldo']} == {'Detergente neutro': '8,5', 'Pano de chão': '2'}
    linhas = re.findall(r'<tr><td class="text-nowrap">(.*?)</tr>', _texto(antigo.split('<tbody>')[1]))
    assert len(linhas) == len(d['movimentos']) == 4
    for linha, mv in zip(linhas, d['movimentos']):
        celulas = [re.sub(r'<[^>]+>', '', x).strip() for x in re.split(r'</td>\s*<td[^>]*>', linha)]
        quem = mv['pessoa'] + (f" · {mv['motivo']}" if mv['motivo'] else '')
        assert celulas[:5] == [mv['dia'], mv['tipo_rotulo'], mv['material'], mv['quantidade'], mv['valor']]
        assert celulas[5].removesuffix('</td>').strip() == quem
    assert [mv['valor'] for mv in d['movimentos'] if mv['material'] == 'Pano de chão'] == ['—', '—']
    consumo = [mv for mv in d['movimentos'] if mv['motivo'] == f'Consumo {SEGREDO}']
    assert consumo and consumo[0]['quantidade'] == '-1,5 L' and consumo[0]['valor'] == 'R$ 1.851,75'
    assert [k for k, _ in d['tipos']] == re.findall(r'<option value="(\w+)"', antigo.split('id="mvt"')[1].split('</select>')[0])
    assert [m['id'] for m in d['materiais']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="mvm"')[1].split('</select>')[0])]
    assert [r['id'] for r in d['rotas']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="csr"')[1].split('</select>')[0])]
    assert d['gestor_do_contrato'] and texto.count('name="autorizar_negativo"') == 2
    assert d['links']['mes'] == f'/novo/materiais/locais/{a}/mes'


def test_o_saldo_negativo_e_o_autorizado_como_na_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    _antiga(c, f'/materiais/locais/{a}/consumo', data={
        'material_id': str(cena['pano']), 'quantidade': '5', 'autorizar_negativo': '1',
        'motivo': 'Acabou no meio do serviço'})
    d = c.get(f'/api/v1/materiais/locais/{a}').get_json()
    antigo = _texto(c.get(f'/materiais/locais/{a}').get_data(as_text=True))
    [pano] = [s for s in d['com_saldo'] if s['id'] == cena['pano']]
    assert pano['negativo'] and pano['saldo'] == '-3'
    assert '<span class="ms-auto fw-bold text-danger">-3 un</span>' in antigo
    assert d['movimentos'][0]['autorizou'] and d['movimentos'][0]['motivo'] == 'Acabou no meio do serviço'
    assert f"<b>saldo negativo autorizado por {d['movimentos'][0]['autorizou']}</b>" in antigo


def test_o_consumo_do_mes_e_o_custo_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    for busca in ('', '?m=2020-01', '?m=abc'):
        d = c.get(f'/api/v1/materiais/locais/{a}/mes{busca}').get_json()
        antigo = c.get(f'/materiais/locais/{a}/mes{busca}').get_data(as_text=True)
        texto = _texto(antigo)
        assert f"Consumo · {d['mes']}" in texto
        assert f'<div class="small text-muted">Custo do mês</div><div class="fs-4 fw-bold">{d["total"]}</div>' in texto
        for x in d['linhas']:
            assert f"<tr><td>{x['material']}</td><td class=\"text-end text-nowrap\">{x['quantidade']}</td><td class=\"text-end\">{x['vezes']}</td><td class=\"text-end text-nowrap\">{x['valor']}</td></tr>" in texto
        if d['sem_preco']:
            assert f"Fora do custo (material sem preço): {', '.join(d['sem_preco'])}." in texto
        else:
            assert 'Fora do custo' not in texto
        assert f'href="/materiais/locais/{a}/mes?m={d["anterior"]}"' in antigo
    d = c.get(f'/api/v1/materiais/locais/{a}/mes').get_json()
    assert d['total'] == 'R$ 1.851,75' and d['sem_preco'] == ['Pano de chão']
    assert [x['valor'] for x in d['linhas']] == ['R$ 1.851,75', 'sem preço']
    assert [x['quantidade'] for x in d['linhas']] == ['1,5 L', '1 un']
    # O custo: o período (invertido, inválido) e as três somas.
    hoje = tempo.hoje()
    for busca in ('', f'?de={hoje.isoformat()}&ate={hoje.isoformat()}',
                  f'?de={hoje.isoformat()}&ate=2020-01-01', '?de=xpto&ate=', '?de=2020-01-01&ate=2020-01-31'):
        d = c.get('/api/v1/materiais/custo' + busca).get_json()
        antigo = c.get('/materiais/custo' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        assert f'value="{d["de"]}"' in antigo and f'value="{d["ate"]}"' in antigo
        assert f"Total de {d['de_br']} a {d['ate_br']}</div><div class=\"fs-4 fw-bold\">{d['total']}</div>" in texto
        for k, v in d['clientes'] + d['estados']:
            assert f'<span>{k}</span><span class="ms-auto fw-semibold">{v}</span>' in texto
        assert [x['url'] for x in d['locais']] == ['/novo' + x for x in re.findall(r'href="(/materiais/locais/\d+)"', antigo)]
        for x in d['locais']:
            extra = f", {x['sem_preco']} sem preço" if x['sem_preco'] else ''
            assert f"{x['cliente']} · {x['estado']} · {x['consumos']} lançamento(s){extra}" in texto
        assert (f"{d['sem_preco']} consumo(s) de material sem preço" in texto) == bool(d['sem_preco'])
    d = c.get('/api/v1/materiais/custo').get_json()
    assert d['total'] == 'R$ 1.851,75' and d['sem_preco'] == 1
    [x] = d['locais']
    assert (x['consumos'], x['sem_preco'], x['estado']) == (2, 1, 'BA')


def test_os_pedidos_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    from datetime import datetime
    from app import db
    from facilities.materiais.models import PedidoInsumo
    c = auth_client
    d = c.get('/api/v1/materiais/pedidos').get_json()
    antigo = c.get('/materiais/pedidos').get_data(as_text=True)
    texto = _texto(antigo)
    [p] = d['pedidos']
    assert p['resumo'] == f'5 un de Pano de chão · Pedido {SEGREDO}' and p['pode_marcar']
    assert f'<span class="badge fc-dem fc-dem-no_prazo">{p["situacao_rotulo"]}</span>' in texto
    meta = f"{p['local']} · {p['pessoa']} · {p['criado_em']} · prazo {p['prazo']}"
    assert meta in texto and re.match(r'\d\d/\d\d \d\d:\d\d$', p['prazo'])
    assert f'action="/materiais/pedidos/{p["id"]}/visto"' in antigo and p['foto'] is None
    # Atrasado: o selo vermelho e o "· atrasado"; visto: o cinza e quem viu.
    with app_module.app.app_context():
        db.session.get(PedidoInsumo, cena['pedido']).prazo = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
    [p] = c.get('/api/v1/materiais/pedidos').get_json()['pedidos']
    texto = _texto(c.get('/materiais/pedidos').get_data(as_text=True))
    assert p['selo'] == 'atrasada' and p['atrasado']
    assert f'<span class="badge fc-dem fc-dem-atrasada">{p["situacao_rotulo"]} · atrasado</span>' in texto
    _antiga(c, f"/materiais/pedidos/{cena['pedido']}/visto", data={})
    [p] = c.get('/api/v1/materiais/pedidos').get_json()['pedidos']
    texto = _texto(c.get('/materiais/pedidos').get_data(as_text=True))
    assert p['selo'] == 'visto' and not p['atrasado'] and p['prazo'] is None and not p['pode_marcar']
    assert f'<span class="badge text-bg-light">{p["situacao_rotulo"]}</span>' in texto
    assert f"{p['local']} · {p['pessoa']} · {p['criado_em']} · visto por {p['quem_viu']} em {p['visto_em']}" in texto
    assert 'Marcar como visto' not in texto


# ── Os envios: a mesma ação das telas antigas ─────────────────────────────

def _func(app_module, nome):
    from facilities.equipes.models import Funcionario
    with app_module.app.app_context():
        f = Funcionario.query.filter_by(nome=nome).one()
        return f.id, (f.client_id, f.funcao, f.matricula, f.user_id, f.is_active)


def _posto(app_module, nome):
    from facilities.equipes.models import Posto
    with app_module.app.app_context():
        p = Posto.query.filter_by(nome=nome).one()
        return p.id, (p.client_id, p.hora_inicio, p.hora_fim, p.rota_id, p.is_active)


def test_funcionarios_e_postos_como_na_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    form = lambda nome: {'nome': nome, 'funcao': 'Porteiro', 'matricula': '', 'user_id': ''}  # noqa: E731
    _par(c, f'/equipes/locais/{a}/funcionarios', f'/api/v1/equipes/locais/{a}/funcionarios',
         form('João antigo'), form('João novo'))
    (f1, x), (f2, y) = _func(app_module, 'João antigo'), _func(app_module, 'João novo')
    assert x == y and x[1] == 'Porteiro'
    _par(c, f'/equipes/funcionarios/{f1}', f'/api/v1/equipes/funcionarios/{f2}',
         {**form('João antigo'), 'matricula': '77', 'user_id': ''},
         {**form('João novo'), 'matricula': '78', 'user_id': ''})
    for ativo in ('0', '1', '0'):
        _par(c, f'/equipes/funcionarios/{f1}', f'/api/v1/equipes/funcionarios/{f2}',
             {'ativo': ativo}, json=True)
    assert _func(app_module, 'João antigo')[1][3:] == _func(app_module, 'João novo')[1][3:] == (None, False)
    # As recusas: sem nome; matrícula repetida no local.
    _par(c, f'/equipes/locais/{a}/funcionarios', f'/api/v1/equipes/locais/{a}/funcionarios', {'nome': ''}, json=True)
    _par(c, f'/equipes/funcionarios/{f1}', f'/api/v1/equipes/funcionarios/{f2}',
         {'nome': 'João antigo', 'matricula': '123'}, {'nome': 'João novo', 'matricula': '123'})
    # O login que já é de outro funcionário (a Ana) e o que não atende o local.
    for uid in (cena['enc'], 999999):
        _par(c, f'/equipes/funcionarios/{f1}', f'/api/v1/equipes/funcionarios/{f2}',
             {'nome': 'João antigo', 'user_id': str(uid)}, {'nome': 'João novo', 'user_id': str(uid)})
    assert c.post('/api/v1/equipes/funcionarios/999999', data={'ativo': '1'}).status_code == 404 == \
        c.post('/equipes/funcionarios/999999', data={'ativo': '1'}).status_code
    # Os postos.
    posto = lambda nome: {'nome': nome, 'hora_inicio': '06:00', 'hora_fim': '14:00',  # noqa: E731
                          'rota_id': str(cena['rota'])}
    _par(c, f'/equipes/locais/{a}/postos', f'/api/v1/equipes/locais/{a}/postos',
         posto('Recepção antiga'), posto('Recepção nova'))
    (p1, x), (p2, y) = _posto(app_module, 'Recepção antiga'), _posto(app_module, 'Recepção nova')
    assert x == y
    _par(c, f'/equipes/postos/{p1}', f'/api/v1/equipes/postos/{p2}',
         {**posto('Recepção antiga'), 'hora_fim': '18:00', 'rota_id': ''},
         {**posto('Recepção nova'), 'hora_fim': '18:00', 'rota_id': ''})
    for ativo in ('0', '1'):
        _par(c, f'/equipes/postos/{p1}', f'/api/v1/equipes/postos/{p2}', {'ativo': ativo})
    assert _posto(app_module, 'Recepção antiga')[1] == _posto(app_module, 'Recepção nova')[1]
    assert _posto(app_module, 'Recepção nova')[1][3:] == (None, True)
    for ruim in ({**posto('X'), 'nome': ''}, {**posto('Y'), 'hora_inicio': 'xx'},
                 posto('Limpeza 2º andar — manhã')):
        _par(c, f'/equipes/locais/{a}/postos', f'/api/v1/equipes/locais/{a}/postos', ruim, json=True)


def test_a_escala_como_na_tela_antiga(app_module, cena, auth_client):
    from facilities.equipes.models import EscalaTrabalho
    c = auth_client
    a = cena['local']
    hoje = tempo.hoje()
    with app_module.app.app_context():
        from app import Client, db
        from facilities.equipes import servico as eq
        loc = db.session.get(Client, a)
        x = eq.salvar_funcionario(loc, None, {'nome': 'Escala antiga'}, None)
        y = eq.salvar_funcionario(loc, None, {'nome': 'Escala nova'}, None)
        db.session.commit()
        fx, fy = x.id, y.id
    form = lambda fid: {'funcionario_id': str(fid), 'posto_id': str(cena['posto']),  # noqa: E731
                        'data_inicio': hoje.isoformat(), 'data_fim': '',
                        'dia_1': '1', 'dia_3': '1', 'dia_5': '1'}
    _par(c, f'/equipes/locais/{a}/escalas', f'/api/v1/equipes/locais/{a}/escalas', form(fx), form(fy))

    def escala(fid):
        with app_module.app.app_context():
            e = EscalaTrabalho.query.filter_by(funcionario_id=fid).one()
            return e.id, (e.posto_id, e.dias_semana, e.data_inicio, e.data_fim, e.is_active)
    (ex, vx), (ey, vy) = escala(fx), escala(fy)
    assert vx == vy and vx[1] == '135'
    # As recusas: a mesma pessoa no mesmo horário; sem dia; o fim antes do começo.
    for ruim in (lambda f: form(f),
                 lambda f: {k: v for k, v in form(f).items() if not k.startswith('dia_')},
                 lambda f: {**form(f), 'data_fim': (hoje - timedelta(days=3)).isoformat()},
                 lambda f: {**form(f), 'posto_id': str(cena['posto_parado'])}):
        _par(c, f'/equipes/locais/{a}/escalas', f'/api/v1/equipes/locais/{a}/escalas', ruim(fx), ruim(fy),
             troca=[('Escala antiga', 'Escala nova')])
    # Encerrar (e a data que não é data, recusada sem gravar).
    fim = (hoje + timedelta(days=9)).isoformat()
    _, rec, _ = _par(c, f'/equipes/escalas/{ex}/encerrar', f'/api/v1/equipes/escalas/{ey}/encerrar',
                     {'data_fim': fim}, troca=[('Escala antiga', 'Escala nova')])
    assert rec[0]['texto'] == f"Escala de Escala antiga encerrada em {(hoje + timedelta(days=9)).strftime('%d/%m/%Y')}."
    _par(c, f'/equipes/escalas/{ex}/encerrar', f'/api/v1/equipes/escalas/{ey}/encerrar', {'data_fim': 'amanhã'})
    assert escala(fx)[1] == escala(fy)[1] and escala(fy)[1][3].isoformat() == fim


def test_as_visitas_como_na_tela_antiga(app_module, cena, auth_client):
    from facilities.visitas.models import VisitaProgramada
    c = auth_client
    a = cena['local']
    form = lambda nome: {'nome': nome, 'modelo_id': str(cena['modelo']), 'intervalo_dias': '14',  # noqa: E731
                         'proxima_em': (tempo.hoje() + timedelta(days=2)).isoformat(),
                         'supervisor_id': str(cena['sup'])}
    _par(c, f'/visitas/locais/{a}', f'/api/v1/visitas/locais/{a}', form('Qualidade antiga'), form('Qualidade nova'))

    def retrato(nome):
        with app_module.app.app_context():
            p = VisitaProgramada.query.filter_by(nome=nome).one()
            return p.id, (p.modelo_id, p.intervalo_dias, p.proxima_em, p.supervisor_id, p.is_active)
    (p1, x), (p2, y) = retrato('Qualidade antiga'), retrato('Qualidade nova')
    assert x == y
    _par(c, f'/visitas/programadas/{p1}', f'/api/v1/visitas/programadas/{p2}',
         {**form('Qualidade antiga'), 'intervalo_dias': '21', 'supervisor_id': ''},
         {**form('Qualidade nova'), 'intervalo_dias': '21', 'supervisor_id': ''})
    for ativo in ('0', '1', '0'):
        _par(c, f'/visitas/programadas/{p1}', f'/api/v1/visitas/programadas/{p2}', {'ativo': ativo}, json=True)
    assert retrato('Qualidade antiga')[1] == retrato('Qualidade nova')[1]
    assert retrato('Qualidade nova')[1][1:] == (21, (tempo.hoje() + timedelta(days=2)), None, False)
    for ruim in ({**form('X'), 'nome': ''}, {**form('Y'), 'intervalo_dias': '0'},
                 {**form('Z'), 'modelo_id': '999999'}):
        _par(c, f'/visitas/locais/{a}', f'/api/v1/visitas/locais/{a}', ruim, json=True)
    assert c.post('/api/v1/visitas/programadas/999999', data={'ativo': '1'}).status_code == 404 == \
        c.post('/visitas/programadas/999999', data={'ativo': '1'}).status_code


def test_o_catalogo_e_o_estoque_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.materiais.models import Material, MovimentoEstoque
    c = auth_client
    a = cena['local']
    _par(c, '/materiais/', '/api/v1/materiais/', {'nome': 'Sabão antigo', 'unidade': 'kg', 'preco_unitario': '7,5'},
         {'nome': 'Sabão novo', 'unidade': 'kg', 'preco_unitario': '7,5'}, troca=[('antigo', 'novo')])

    def retrato(nome):
        with app_module.app.app_context():
            m = Material.query.filter_by(nome=nome).one()
            return m.id, (m.unidade, m.preco_unitario, m.is_active)
    (m1, x), (m2, y) = retrato('Sabão antigo'), retrato('Sabão novo')
    assert x == y and str(x[1]) == '7.50'
    _par(c, f'/materiais/{m1}', f'/api/v1/materiais/{m2}', {'nome': 'Sabão antigo', 'unidade': 'kg', 'preco_unitario': ''},
         {'nome': 'Sabão novo', 'unidade': 'kg', 'preco_unitario': ''})
    for ativo in ('0', '1'):
        _par(c, f'/materiais/{m1}', f'/api/v1/materiais/{m2}', {'ativo': ativo}, json=True)
    assert retrato('Sabão antigo')[1] == retrato('Sabão novo')[1] == ('kg', None, True)
    for ruim in ({'nome': '', 'unidade': 'un'}, {'nome': 'Detergente NEUTRO', 'unidade': 'L'},
                 {'nome': 'Caro', 'unidade': 'un', 'preco_unitario': 'muito'}):
        _par(c, '/materiais/', '/api/v1/materiais/', ruim, json=True)
    assert c.post('/api/v1/materiais/999999', data={'ativo': '1'}).status_code == 404 == \
        c.post('/materiais/999999', data={'ativo': '1'}).status_code
    # Entrada, saída e ajuste: cada uma num material do par.
    for tipo, q, motivo in (('entrada', '10', ''), ('saida', '2', 'Quebrou'), ('ajuste', '-1', 'Inventário')):
        _par(c, f'/materiais/locais/{a}/movimento', f'/api/v1/materiais/locais/{a}/movimento',
             {'tipo': tipo, 'material_id': str(m1), 'quantidade': q, 'motivo': motivo},
             {'tipo': tipo, 'material_id': str(m2), 'quantidade': q, 'motivo': motivo},
             troca=[('Sabão antigo', 'Sabão novo')])
    # O consumo do local (o mesmo formulário do estoque, sem voltar ao chamado).
    _, rec, j = _par(c, f'/materiais/locais/{a}/consumo', f'/api/v1/materiais/locais/{a}/consumo',
                     {'material_id': str(m1), 'quantidade': '1,5', 'rota_id': str(cena['rota']), 'motivo': 'Piso'},
                     {'material_id': str(m2), 'quantidade': '1,5', 'rota_id': str(cena['rota']), 'motivo': 'Piso'},
                     troca=[('Sabão antigo', 'Sabão novo')])
    assert j['destino'] == f'/novo/materiais/locais/{a}'
    # As recusas: o tipo, o motivo que falta, o saldo que não dá.
    for ruim in ({'tipo': 'consumo', 'material_id': str(m1), 'quantidade': '1'},
                 {'tipo': 'xpto'},
                 {'tipo': 'saida', 'material_id': str(m1), 'quantidade': '1', 'motivo': ''},
                 {'tipo': 'saida', 'material_id': str(m1), 'quantidade': '999', 'motivo': 'x'},
                 {'tipo': 'entrada', 'material_id': '999999', 'quantidade': '1'}):
        _par(c, f'/materiais/locais/{a}/movimento', f'/api/v1/materiais/locais/{a}/movimento', ruim, json=True)
    _par(c, f'/materiais/locais/{a}/consumo', f'/api/v1/materiais/locais/{a}/consumo',
         {'material_id': str(m1), 'quantidade': '999'}, json=True)
    with app_module.app.app_context():
        def mov(mid):
            return [(x.tipo, str(x.quantidade), str(x.valor), x.motivo, x.data)
                    for x in MovimentoEstoque.query.filter_by(material_id=mid).order_by(MovimentoEstoque.id)]
        assert mov(m1) == mov(m2) and [t for t, *_ in mov(m2)] == ['entrada', 'saida', 'ajuste', 'consumo']
        assert db.session.get(Material, m2).is_active


def test_marcar_o_pedido_como_visto_como_na_tela_antiga(app_module, cena, auth_client):
    from app import Client, User, db
    from facilities.materiais import servico as mat
    from facilities.materiais.models import PedidoInsumo
    c = auth_client
    with app_module.app.app_context():
        loc = db.session.get(Client, cena['local'])
        outro = mat.pedir(db.session.get(User, cena['enc']), loc, {'texto': 'Saco de lixo'})
        db.session.commit()
        outro = outro.id
    _par(c, f"/materiais/pedidos/{cena['pedido']}/visto", f'/api/v1/materiais/pedidos/{outro}/visto', {})
    # De novo: o pedido já visto é recusado do mesmo jeito.
    _par(c, f"/materiais/pedidos/{cena['pedido']}/visto", f'/api/v1/materiais/pedidos/{outro}/visto', {})
    with app_module.app.app_context():
        a, b = db.session.get(PedidoInsumo, cena['pedido']), db.session.get(PedidoInsumo, outro)
        assert (a.status, a.visto_por) == (b.status, b.visto_por) and b.status == 'visto'
    assert c.post('/api/v1/materiais/pedidos/999999/visto').status_code == 404 == \
        c.post('/materiais/pedidos/999999/visto').status_code


# ── Isolamento ────────────────────────────────────────────────────────────

def test_quem_e_de_outro_local_nao_ve_nem_altera_a(app_module, cena):
    from app import db
    from facilities.equipes.models import EscalaTrabalho, Funcionario, Posto
    from facilities.materiais.models import MovimentoEstoque, PedidoInsumo
    from facilities.visitas.models import VisitaProgramada
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'eq4b.plenob@trino.com', 'pleno', locais=[LOCAL_B])
        movimentos = MovimentoEstoque.query.count()
    c = fabrica.entrar(app_module, 'eq4b.plenob@trino.com')
    a = cena['local']
    for url in (f'/api/v1/equipes/locais/{a}', f'/api/v1/equipes/locais/{a}/mes',
                f'/api/v1/visitas/locais/{a}', f'/api/v1/materiais/locais/{a}',
                f'/api/v1/materiais/locais/{a}/mes'):
        r = c.get(url)
        assert r.status_code in (403, 404) and r.is_json and SEGREDO not in r.get_data(as_text=True), url
    for url in ('/api/v1/materiais/', '/api/v1/materiais/pedidos', '/api/v1/materiais/custo'):
        r = c.get(url)
        assert r.status_code == 200 and SEGREDO not in r.get_data(as_text=True), url
    assert c.get('/api/v1/materiais/pedidos').get_json()['pedidos'] == []
    assert c.get('/api/v1/materiais/custo').get_json()['locais'] == []
    for url, dados in ((f'/api/v1/equipes/locais/{a}/funcionarios', {'nome': 'Invasão'}),
                       (f"/api/v1/equipes/funcionarios/{cena['ana']}", {'ativo': '0'}),
                       (f'/api/v1/equipes/locais/{a}/postos', {'nome': 'Invasão', 'hora_inicio': '07:00', 'hora_fim': '08:00'}),
                       (f"/api/v1/equipes/postos/{cena['posto']}", {'ativo': '0'}),
                       (f'/api/v1/equipes/locais/{a}/escalas', {'funcionario_id': str(cena['mariana']),
                                                                'posto_id': str(cena['posto']), 'dia_1': '1'}),
                       (f"/api/v1/equipes/escalas/{cena['escala']}/encerrar", {'data_fim': '2026-01-01'}),
                       (f'/api/v1/visitas/locais/{a}', {'nome': 'Invasão', 'modelo_id': str(cena['modelo'])}),
                       (f"/api/v1/visitas/programadas/{cena['programada']}", {'ativo': '0'}),
                       (f'/api/v1/materiais/locais/{a}/movimento', {'tipo': 'entrada', 'quantidade': '1',
                                                                   'material_id': str(cena['pano'])}),
                       (f'/api/v1/materiais/locais/{a}/consumo', {'quantidade': '1', 'material_id': str(cena['pano'])}),
                       (f"/api/v1/materiais/pedidos/{cena['pedido']}/visto", {})):
        r = c.post(url, data=dados)
        assert r.status_code in (403, 404) and r.is_json, url
    with app_module.app.app_context():
        assert db.session.get(Funcionario, cena['ana']).is_active
        assert db.session.get(Posto, cena['posto']).is_active
        assert db.session.get(EscalaTrabalho, cena['escala']).data_fim > tempo.hoje()
        assert db.session.get(VisitaProgramada, cena['programada']).is_active
        assert db.session.get(PedidoInsumo, cena['pedido']).status == 'aberto'
        assert MovimentoEstoque.query.count() == movimentos
        assert not Funcionario.query.filter_by(nome='Invasão').count()
        assert not VisitaProgramada.query.filter_by(nome='Invasão').count()


# ── Dentro das telas novas, os links levam às novas ───────────────────────

def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    # As telas antigas e o menu não mudam.
    assert f'href="/materiais/locais/{a}"' in c.get('/materiais/').get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert '/materiais/' in menu and not any(u.startswith(('/novo/materiais', '/novo/equipes',
                                                            '/novo/visitas')) for u in menu)
    # A rotina nova leva à equipe e às visitas novas; o painel de demandas,
    # aos pedidos de insumo novos.
    d = c.get(f'/api/v1/rotas/locais/{a}').get_json()
    assert d['links']['equipe'] == f'/novo/equipes/locais/{a}'
    assert d['links']['visitas'] == f'/novo/visitas/locais/{a}'
    itens = c.get('/api/v1/demandas/').get_json()['itens']
    assert [i['link'] for i in itens if i['tipo'] == 'insumo'] == ['/novo/materiais/pedidos']
    # A visita em si e o aplicativo do supervisor: nas telas novas desde a Fase 1d.
    assert all(i['link'].startswith('/novo/app/visitas/') for i in itens if i['tipo'] == 'visita')
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'eq4b.sup@trino.com', 'supervisor', locais=[LOCAL_A])
    sup = fabrica.entrar(app_module, 'eq4b.sup@trino.com')
    d = sup.get('/api/v1/campo/inicio').get_json()
    assert d['equipe'] == '/novo/app/equipe' and d['material'] == '/novo/app/materiais'
    assert d['visitas']['url'] == '/novo/app/visitas'
