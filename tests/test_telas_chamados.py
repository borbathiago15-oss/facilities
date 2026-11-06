"""Os chamados, o painel de demandas e a preventiva nas telas novas (Fase 4a):
a lista, abrir e o chamado (as ações, as fotos e o material usado), as
demandas e os planos preventivos do local.

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``), com
  as horas, as datas e os números escritos do mesmo jeito;
* a mesma porta, perfil a perfil;
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id).
"""
import html as html_mod
import io
import re
from datetime import datetime, timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS
from tests.test_isolamento_varredura import _png

LOCAL_A, LOCAL_B = CONTRATOS_SEMEADOS[0], CONTRATOS_SEMEADOS[1]
SEGREDO = 'CHAMADO-SECRETO-A'


def _texto(html):
    return html_mod.unescape(re.sub(r'\s+', ' ', html))


def _flashes(c):
    with c.session_transaction() as s:
        return [{'tipo': 'danger' if t == 'error' else t, 'texto': x}
                for t, x in s.pop('_flashes', [])]


def _antiga(c, url, **kw):
    r = c.post(url, **kw)
    assert r.status_code in (302, 400), (url, r.status_code, r.get_data(as_text=True)[:300])
    return r, r.headers.get('Location', ''), _flashes(c)


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


def _foto(nome='f.png'):
    return (io.BytesIO(_png()), nome)


@pytest.fixture()
def cena(app_module, auth_client):
    """Em A: um checklist publicado, um plano preventivo com a ordem aberta,
    um técnico, um material com estoque e um chamado com foto, atribuído,
    com comentário e material lançado. Em B: um chamado."""
    from app import Client, User, db
    from facilities.chamados import servico as chs
    from facilities.chamados.models import Chamado
    from facilities.materiais import servico as mat
    from facilities.preventiva import servico as prev
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        a = ids['local']
        b = fabrica.local(LOCAL_B).id
        tec = fabrica.pessoa(app_module, 'ch4a.tec@trino.com', 'tecnico', locais=[LOCAL_A],
                             nome='Técnico Quatro')
        enc = fabrica.pessoa(app_module, 'ch4a.enc@trino.com', 'encarregado', locais=[LOCAL_A],
                             nome='Encarregada Quatro')
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        loc = db.session.get(Client, a)
        m = s.criar_modelo(a, {'nome': f'Checklist {SEGREDO}'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Filtro limpo?', 'tipo': 'sim_nao'}]), {}, None)
        plano = prev.salvar_plano(loc, None, {
            'nome': f'Plano {SEGREDO}', 'ponto_id': ids['ponto'], 'modelo_id': m.id,
            'equipamento_id': ids['equipamento'], 'intervalo_dias': '15',
            'proxima_em': tempo.hoje().isoformat(), 'responsavel_id': tec}, admin)
        db.session.flush()
        prev.gerar_ordens(tempo.hoje())
        material = mat.salvar_material(None, {'nome': 'Fita veda-rosca', 'unidade': 'un',
                                              'preco_unitario': '3,50'})
        mat.movimentar(admin, loc, {'material_id': str(material.id), 'quantidade': '20'},
                       'entrada')
        db.session.commit()
        ch, _ = chs.abrir_sem_duplicar(db.session.get(User, enc), a, f'Vazamento {SEGREDO}',
                                       descricao='Pinga sem parar', local='Copa',
                                       categoria='hidraulica', prioridade='alta')
        db.session.commit()
        chb, _ = chs.abrir_sem_duplicar(admin, b, 'Chamado de B', prioridade='baixa')
        db.session.commit()
        ids.update(modelo=m.id, plano=plano.id, tec=tec, enc=enc, material=material.id,
                   chamado=ch.id, chamado_b=chb.id, local_b=b,
                   preventiva=Chamado.query.filter_by(origem='preventiva').one().id)
    c = auth_client
    _antiga(c, f"/chamados/{ids['chamado']}/acao", data={'acao': 'atribuir', 'responsavel_id': ids['tec']})
    _antiga(c, f"/chamados/{ids['chamado']}/acao", data={'acao': 'comentar', 'texto': 'Vou olhar'})
    _antiga(c, f"/chamados/{ids['chamado']}/anexos", data={'arquivo': _foto(), 'momento': 'antes'},
            content_type='multipart/form-data')
    _antiga(c, f"/materiais/locais/{ids['local']}/consumo", data={
        'material_id': ids['material'], 'quantidade': '2', 'chamado_id': ids['chamado'],
        'voltar': 'chamado'})
    return ids


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo != 'facilities.telas.chamados':
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) == 6
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'GET']) == 5
    assert len([1 for m, u in rotas if u.startswith('/novo/')]) == 5
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


TELAS = (
    # (antiga, api) — a nova é a antiga abaixo de /novo
    ('/chamados/', '/api/v1/chamados/'),
    ('/chamados/?client_id={local}&visao=todos', '/api/v1/chamados/?client_id={local}&visao=todos'),
    ('/chamados/?client_id={local_b}', '/api/v1/chamados/?client_id={local_b}'),
    ('/chamados/novo', '/api/v1/chamados/novo'),
    ('/chamados/{chamado}', '/api/v1/chamados/{chamado}'),
    ('/chamados/{chamado_b}', '/api/v1/chamados/{chamado_b}'),
    ('/chamados/999999', '/api/v1/chamados/999999'),
    ('/demandas/', '/api/v1/demandas/'),
    ('/demandas/?local={local}&tipo=chamado', '/api/v1/demandas/?local={local}&tipo=chamado'),
    ('/preventiva/locais/{local}', '/api/v1/preventiva/locais/{local}'),
    ('/preventiva/locais/{local_b}', '/api/v1/preventiva/locais/{local_b}'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'pleno-de-b']


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta na tela antiga, na página nova e na API."""
    base = papel.split('-')[0]
    locais = [LOCAL_B] if papel.endswith('de-b') else [LOCAL_A]
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta4a.{papel}@trino.com', base, locais=locais)
    c = fabrica.entrar(app_module, f'porta4a.{papel}@trino.com')
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
    assert codigos['/chamados/'] == 200
    assert (codigos['/chamados/novo'] == 200) == (base != 'visualizador'), papel
    assert (codigos[f"/chamados/{cena['chamado']}"] == 200) == de_a, papel
    # A diretoria vê todos os locais, com ou sem a caixinha (R5, 05/11/2026).
    assert (codigos[f"/chamados/?client_id={cena['local_b']}"] == 200) == (
        papel in ('master', 'visualizador', 'pleno-de-b')), papel
    assert (codigos[f"/preventiva/locais/{cena['local']}"] == 200) == \
        ((gestao or base in ('supervisor', 'visualizador')) and de_a), papel
    assert codigos['/chamados/999999'] == 404


def test_o_cliente_do_portal_nao_entra(app_module, cena):
    """A conta de cliente fica no portal: as telas novas recusam como as antigas."""
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    try:
        with app_module.app.app_context():
            fabrica.cliente(app_module, 'cliente.ch4a@gl.com', cena['cliente'])
        c = fabrica.entrar_com_codigo(app_module, 'cliente.ch4a@gl.com')
        for antiga, api in TELAS:
            antiga, api = antiga.format(**cena), api.format(**cena)
            r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
            assert r_antiga.status_code == r_api.status_code == r_nova.status_code == 403, antiga
            assert SEGREDO not in r_api.get_data(as_text=True)
    finally:
        app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False


def test_quem_so_le_nao_recebe_as_acoes_e_o_servidor_recusa(app_module, cena):
    from app import db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'ch4a.diretoria@trino.com', 'visualizador', all_clients=True)
    c = fabrica.entrar(app_module, 'ch4a.diretoria@trino.com')
    d = c.get(f"/api/v1/chamados/{cena['chamado']}").get_json()
    antigo = c.get(f"/chamados/{cena['chamado']}").get_data(as_text=True)
    assert d['acoes'] == [] and 'O que fazer agora' not in antigo
    assert d['pode_anexar'] is False and d['materiais'] == [] and 'Lançar material' not in antigo
    assert c.get('/api/v1/chamados/').get_json()['pode_abrir'] is False
    p = c.get(f"/api/v1/preventiva/locais/{cena['local']}").get_json()
    assert p['pode_montar'] is False and 'Cadastrar plano' not in c.get(
        f"/preventiva/locais/{cena['local']}").get_data(as_text=True)
    for url, dados in ((f"/api/v1/chamados/{cena['chamado']}/acao", {'acao': 'cancelar', 'texto': 'x'}),
                       (f"/api/v1/chamados/{cena['chamado']}/anexos", {'momento': 'antes'}),
                       ('/api/v1/chamados/', {'client_id': cena['local'], 'titulo': 'Invasão'}),
                       (f"/api/v1/preventiva/{cena['plano']}", {'ativo': '0'})):
        r = c.post(url, data=dados)
        assert r.status_code == 403 and r.is_json, url
        antiga = c.post(url.replace('/api/v1', ''), data=dados)
        assert antiga.status_code == 403, url
    with app_module.app.app_context():
        assert db.session.get(Chamado, cena['chamado']).status == 'aberto'
        assert not Chamado.query.filter_by(titulo='Invasão').count()


# ── Os mesmos dados das telas antigas ─────────────────────────────────────

def test_a_lista_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    for busca in ('', '?visao=todos', f"?client_id={cena['local']}&visao=meus",
                  '?visao=atrasados', '?prioridade=alta&categoria=hidraulica', '?visao=xpto'):
        d = c.get('/api/v1/chamados/' + busca).get_json()
        antigo = c.get('/chamados/' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        assert [ch['id'] for ch in d['chamados']] == [
            int(x) for x in re.findall(r'class="ch-item[^"]*" href="/chamados/(\d+)"', antigo)], busca
        n = d['numeros']
        for valor, rotulo in ((n['em_aberto'], 'em aberto'), (n['aguardando_confirmacao'], 'aguardando confirmação'),
                              (n['pct_no_prazo'], f"resolvidos no prazo ({n['dias']} dias)"),
                              (n['tempo_medio'], 'tempo médio até resolver')):
            assert f'<b>{valor}</b><span>{rotulo}</span>' in texto, (busca, rotulo)
        assert [k for k, _ in d['visoes']] == re.findall(r'visao=(\w+)[^"]*">[^<]+</a>', antigo.split('ch-abas')[1].split('</nav>')[0])
        assert d['visao'] in ('abertos', 'atrasados', 'meus', 'confirmar', 'todos')
        assert f'class="ativo" href="/chamados/?' in antigo and d['pode_abrir']
        for ch in d['chamados']:
            meta = f"{ch['contrato']}{' · ' + ch['area'] if ch['area'] else ''}{' · ' + ch['local'] if ch['local'] else ''} · {ch['categoria_rotulo']} · "
            assert meta in texto and ch['titulo'] in texto and ch['numero'] in texto
    d = c.get('/api/v1/chamados/?visao=xpto').get_json()
    assert d['visao'] == 'abertos'
    [x] = [ch for ch in c.get('/api/v1/chamados/?visao=todos').get_json()['chamados'] if ch['id'] == cena['chamado']]
    assert x['responsavel'] == 'Técnico Quatro' and x['prioridade_rotulo'] == 'Alta'
    assert x['local'] == 'Copa' and x['categoria_rotulo'] == 'Hidráulica'


def _prazo(app_module, cid, **campos):
    from app import db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        ch = db.session.get(Chamado, cid)
        for k, v in campos.items():
            setattr(ch, k, v)
        db.session.commit()


def test_o_selo_do_prazo_e_os_numeros_sao_os_da_tela_antiga(app_module, cena, auth_client):
    """Cada caso do ``selo.prazo`` da antiga — atrasado em horas e em dias,
    vencendo perto, em menos de 1 h, numa data, resolvido — e os números do
    topo (a % e o tempo médio com vírgula)."""
    from app import User, db
    from facilities.chamados import servico as chs
    c = auth_client
    agora = datetime.utcnow()
    casos = {
        'atrasado 2h': dict(prazo=agora - timedelta(hours=2, minutes=20)),
        'atrasado 1 dia': dict(prazo=agora - timedelta(hours=30)),
        'atrasado 3 dias': dict(prazo=agora - timedelta(days=3, hours=1)),
        'atrasado pouco': dict(prazo=agora - timedelta(minutes=20)),
        'vence perto': dict(prazo=agora + timedelta(hours=2, minutes=30)),
        'vence logo': dict(prazo=agora + timedelta(minutes=30)),
        'vence longe': dict(prazo=agora + timedelta(days=4)),
        'sem prazo': dict(prazo=None),
        'resolvido': dict(status='resolvido', resolvido_em=agora - timedelta(hours=5),
                          aberto_em=agora - timedelta(hours=60)),
        'fechado': dict(status='fechado', resolvido_em=agora - timedelta(hours=1),
                        aberto_em=agora - timedelta(hours=3), prazo=agora - timedelta(hours=2)),
        'aguardando vencido': dict(status='aguardando', prazo=agora - timedelta(hours=5),
                                   motivo_espera='Peça'),
        'aguardando no prazo': dict(status='aguardando', prazo=agora + timedelta(hours=2),
                                    motivo_espera='Terceiro'),
    }
    ids = {}
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        for nome in casos:
            ch, _ = chs.abrir_sem_duplicar(admin, cena['local'], f'Caso {nome}')
            db.session.commit()
            ids[nome] = ch.id
    for nome, campos in casos.items():
        _prazo(app_module, ids[nome], **campos)
    d = c.get('/api/v1/chamados/?visao=todos').get_json()
    antigo = c.get('/chamados/?visao=todos').get_data(as_text=True)
    blocos = dict(re.findall(r'href="/chamados/(\d+)">(.*?)</a>', antigo, re.S))
    por_id = {ch['id']: ch for ch in d['chamados']}
    esperado = {'atrasado 2h': 'atrasado há 2h', 'atrasado 1 dia': 'atrasado há 1 dia',
                'atrasado 3 dias': 'atrasado há 3 dias', 'atrasado pouco': 'atrasado há menos de 1h',
                'vence perto': 'vence em 2h', 'vence logo': 'vence em menos de 1h',
                'aguardando vencido': 'prazo parado', 'aguardando no prazo': 'prazo parado'}
    for nome, cid in ids.items():
        selo, bloco = por_id[cid]['prazo_selo'], _texto(blocos[str(cid)])
        if selo is None:
            assert 'ch-prazo' not in bloco, nome
            continue
        classe = {'ok': 'ch-prazo ok', 'atrasado': 'ch-prazo atrasado', 'parado': 'ch-prazo"',
                  'vence': 'ch-prazo perto' if selo['perto'] else 'ch-prazo '}[selo['tipo']]
        assert f'class="{classe}' in bloco and selo['texto'] in bloco, (nome, selo, bloco)
        if nome in esperado:
            assert selo['texto'] == esperado[nome], nome
    assert por_id[ids['vence longe']]['prazo_selo']['texto'].startswith('vence ') and \
        re.match(r'vence \d\d/\d\d \d\d:\d\d$', por_id[ids['vence longe']]['prazo_selo']['texto'])
    assert por_id[ids['vence perto']]['prazo_selo']['perto'] is True
    assert por_id[ids['sem prazo']]['prazo_selo'] is None and por_id[ids['fechado']]['prazo_selo'] is None
    assert por_id[ids['resolvido']]['prazo_selo']['texto'].startswith('resolvido ')
    # Em "Aguardando" o relógio do prazo está parado (D8): nem "atrasado há"
    # nem "vence em" — o selo diz "prazo parado", como a borda e os contadores.
    for nome in ('aguardando vencido', 'aguardando no prazo'):
        assert por_id[ids[nome]]['prazo_selo']['tipo'] == 'parado', nome
        assert 'atrasado' not in _texto(blocos[str(ids[nome])]), nome
    assert por_id[ids['aguardando vencido']]['atrasado'] is False
    assert f'class="ch-item " href="/chamados/{ids["aguardando vencido"]}"' in antigo
    assert f'class="ch-item atrasado" href="/chamados/{ids["atrasado 2h"]}"' in antigo
    # Os números do topo: 2 resolvidos (um fora do prazo) → 50,0%; média de
    # (55 h + 2 h) / 2 = 28,5 h → "28h"; a contagem dos atrasados.
    n = d['numeros']
    texto = _texto(antigo)
    assert n['pct_no_prazo'] == '50,0%' and n['tempo_medio'] == '28h'
    assert f"<b>{n['atrasados']}</b><span>atrasados</span>" in texto and n['atrasados'] == 4
    from facilities.telas.chamados import numeros_escritos
    base = {'em_aberto': 1, 'atrasados': 1, 'aguardando_confirmacao': 0, 'dias': 30}
    assert numeros_escritos({**base, 'pct_no_prazo': 66.7, 'horas_medias': 0.5}) == {
        **base, 'pct_no_prazo': '66,7%', 'tempo_medio': 'menos de 1h'}
    assert numeros_escritos({**base, 'pct_no_prazo': None, 'horas_medias': None})['tempo_medio'] == '—'
    assert numeros_escritos({**base, 'pct_no_prazo': 100.0, 'horas_medias': 61.0})['tempo_medio'] == '2,5 dias'


def test_abrir_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    import json
    c = auth_client
    with app_module.app.app_context():
        from app import db
        from facilities.passagem.models import DiarioArea
        db.session.add(DiarioArea(client_id=cena['local'], nome='Limpeza', ativo=True))
        db.session.commit()
    d = c.get(f"/api/v1/chamados/novo?client_id={cena['local']}").get_json()
    antigo = c.get(f"/chamados/novo?client_id={cena['local']}").get_data(as_text=True)
    contratos = antigo.split('id="client_id"')[1].split('</select>')[0]
    assert [x['id'] for x in d['contratos']] == [int(x) for x in re.findall(r'<option value="(\d+)"', contratos)]
    assert f'<option value="{cena["local"]}" selected>' in contratos and d['client_id'] == cena['local']
    embutido = json.loads(html_mod.unescape(antigo.split('id="areas-por-contrato" type="application/json">')[1].split('</script>')[0]))
    assert d['areas'] == embutido and d['areas'][str(cena['local'])][0]['nome'] == 'Limpeza'
    assert [k for k, _ in d['prioridades']] == re.findall(r'<option value="(\w+)"', antigo.split('id="prioridade"')[1].split('</select>')[0])
    assert [k for k, _ in d['categorias']] == re.findall(r'<option value="(\w+)"', antigo.split('id="categoria"')[1].split('</select>')[0])


def test_o_chamado_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    d = c.get(f"/api/v1/chamados/{cena['chamado']}").get_json()
    antigo = c.get(f"/chamados/{cena['chamado']}").get_data(as_text=True)
    texto = _texto(antigo)
    ch = d['chamado']
    assert ch['titulo'] == f'Vazamento {SEGREDO}' and ch['numero'] in texto
    for dt, dd in (('Contrato', ch['contrato']), ('Onde', ch['local']), ('Categoria', ch['categoria_rotulo']),
                   ('Pedido por', f"{ch['solicitante']} · {ch['aberto_em']}"),
                   ('Responsável', ch['responsavel']), ('Prazo', ch['prazo'])):
        assert f'<dt>{dt}</dt><dd>{dd}</dd>' in texto, dt
    assert re.match(r'\d\d/\d\d/\d{4} \d\d:\d\d$', ch['aberto_em'])
    assert f'<p class="ch-desc">{ch["descricao"]}</p>' in texto
    assert set(d['acoes']) == set(re.findall(r'name="acao" value="(\w+)"', antigo))
    assert [t['id'] for t in d['tecnicos']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('name="responsavel_id"')[1].split('</select>')[0])]
    assert [f"{e['autor']} {e['rotulo']} {e['quando']}" for e in d['eventos']] == [
        re.sub(r'<[^>]+>', '', x).strip() for x in re.findall(r'<li class="ev-\w+">\s*<div>(.*?)</div>', texto)]
    assert [e['tipo'] for e in d['eventos']] == ['aberto', 'atribuido', 'comentario']
    assert d['eventos'][2]['texto'] == 'Vou olhar' and '<p>Vou olhar</p>' in texto
    [a] = d['anexos']
    assert a['imagem'] and a['momento'] == 'antes' and f'href="{a["url"]}"' in antigo and f'<img src="{a["url"]}"' in antigo
    [m] = d['consumos']
    assert f"{m['quantidade']} {m['unidade']} · {m['material']}" in texto and m['quantidade'] == '2'
    assert f"{m['pessoa']} · {m['quando']}" in texto and m['valor'] in texto and m['valor'] == 'R$ 7,00'
    assert d['ve_custo'] and [x['id'] for x in d['materiais']] == [
        int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('name="material_id"')[1].split('</select>')[0])]
    assert d['pode_anexar'] and 'name="momento"' in antigo
    # A ordem da preventiva: a origem e o aviso de como fazer.
    d = c.get(f"/api/v1/chamados/{cena['preventiva']}").get_json()
    texto = _texto(c.get(f"/chamados/{cena['preventiva']}").get_data(as_text=True))
    assert d['chamado']['origem'] == 'preventiva' and 'Manutenção preventiva programada' in texto
    assert d['chamado']['responsavel'] == 'Técnico Quatro'


def test_o_tempo_parado_e_a_solucao_como_na_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    _prazo(app_module, cena['chamado'], pausa_total_seg=2 * 3600 + 5 * 60, status='resolvido',
           solucao='Troquei o reparo', resolvido_em=datetime.utcnow())
    d = c.get(f"/api/v1/chamados/{cena['chamado']}").get_json()
    texto = _texto(c.get(f"/chamados/{cena['chamado']}").get_data(as_text=True))
    assert d['chamado']['pausa'] == '2 h 5 min aguardando (somado ao prazo)'
    assert f"<dt>Tempo parado</dt><dd>{d['chamado']['pausa']}</dd>" in texto
    assert '<b>O que foi feito:</b> Troquei o reparo' in texto and d['chamado']['solucao'] == 'Troquei o reparo'
    assert set(d['acoes']) == {'confirmar', 'reabrir', 'comentar'}


def test_as_demandas_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    for busca in ('', f"?local={cena['local']}", '?tipo=preventiva', '?situacao=no_prazo',
                  f"?local={cena['local']}&tipo=chamado&situacao=", '?local=999999'):
        d = c.get('/api/v1/demandas/' + busca).get_json()
        antigo = c.get('/demandas/' + busca).get_data(as_text=True)
        texto = _texto(antigo)
        lista = antigo.split('<div class="fc-cartao p-0">')[1]
        assert ['/novo' + x if x.startswith(('/chamados/', '/rotas/', '/materiais/')) else x
                for x in re.findall(r'<a class="d-flex[^"]*" href="([^"]+)"', lista)] == [i['link'] for i in d['itens']], busca
        for i in d['itens']:
            assert i['titulo'] in texto and f"{i['local']} · {i['estado']}" in texto
            if i['prazo']:
                assert f"prazo {i['prazo']}" in texto
        for k, v in d['situacoes']:
            assert f'<div class="small text-muted">{v}</div><div class="fs-4 fw-bold">{d["contagem"][k]}</div>' in texto
        assert [x['id'] for x in d['locais']] == [int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="flocal"')[1].split('</select>')[0])]
    # Os cartões contam com o mesmo filtro de tipo (e de local) da lista:
    # sem situação escolhida, a soma deles é o tamanho da lista.
    for busca in ('', '?tipo=preventiva', '?tipo=chamado', f"?local={cena['local']}&tipo=chamado"):
        d = c.get('/api/v1/demandas/' + busca).get_json()
        assert sum(d['contagem'].values()) == len(d['itens']), busca
    so_chamados = c.get('/api/v1/demandas/?tipo=chamado').get_json()
    assert len(so_chamados['itens']) < len(c.get('/api/v1/demandas/').get_json()['itens'])
    for k in so_chamados['contagem']:
        com_situacao = c.get(f'/api/v1/demandas/?tipo=chamado&situacao={k}').get_json()
        assert so_chamados['contagem'][k] == len(com_situacao['itens']), k
    d = c.get(f"/api/v1/demandas/?local={cena['local']}").get_json()
    tipos = {i['tipo'] for i in d['itens']}
    assert {'chamado', 'preventiva'} <= tipos and d['local'] == cena['local']
    [p] = [i for i in d['itens'] if i['tipo'] == 'preventiva']
    assert p['link'] == f"/novo/chamados/{cena['preventiva']}" and p['tipo_rotulo'] == 'Preventiva'
    assert re.match(r'\d\d/\d\d \d\d:\d\d$', p['prazo'])
    assert d['links']['cobrancas'] == '/cobrancas/'


def test_a_preventiva_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get(f'/api/v1/preventiva/locais/{a}').get_json()
    antigo = c.get(f'/preventiva/locais/{a}').get_data(as_text=True)
    texto = _texto(antigo)
    [p] = d['planos']
    assert p['nome'] == f'Plano {SEGREDO}' and p['ativo']
    assert f"{p['ponto']} · {p['equipamento']} · a cada {p['intervalo_dias']} dia(s)" in texto
    assert f"próximo vencimento <strong>{p['proxima_em']}</strong>" in texto
    assert re.match(r'\d\d/\d\d/\d{4}$', p['proxima_em'])
    assert f"Checklist: {p['modelo']} · {p['prioridade_rotulo']} · {p['responsavel']}" in texto
    [ciclo] = p['ciclos']
    assert ciclo['chamado']['url'] == f"/novo/chamados/{cena['preventiva']}"
    assert f"Venceu {ciclo['vencimento']} · <a href=\"/chamados/{cena['preventiva']}\">{ciclo['chamado']['numero']}</a> — {ciclo['chamado']['status_rotulo']}" in texto
    assert [x['id'] for x in d['pontos']] == [int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="pontonovo"')[1].split('</select>')[0])]
    assert [x['rotulo'] for x in d['pontos']] == re.findall(r'<option value="\d+"[^>]*>([^<]+)</option>', texto.split('id="pontonovo"')[1].split('</select>')[0])
    assert [x['id'] for x in d['modelos']] == [int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="modelonovo"')[1].split('</select>')[0])]
    assert [x['id'] for x in d['tecnicos']] == [int(x) for x in re.findall(r'<option value="(\d+)"', antigo.split('id="respnovo"')[1].split('</select>')[0])]
    assert f'value="{d["hoje"]}"' in antigo and d['pode_montar']
    assert d['links'] == {'pontos': f'/novo/cadastros/locais/{a}', 'checklists': f'/novo/rotas/locais/{a}'}


# ── Os envios: a mesma ação das telas antigas ─────────────────────────────

def _retrato(app_module, cid):
    from app import db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        ch = db.session.get(Chamado, cid)
        return {'status': ch.status, 'prioridade': ch.prioridade, 'responsavel': ch.responsavel_id,
                'solucao': ch.solucao, 'motivo_espera': ch.motivo_espera, 'categoria': ch.categoria,
                'local': ch.local, 'descricao': ch.descricao, 'area': ch.area_id,
                'eventos': [(e.tipo, e.texto) for e in ch.eventos],
                'anexos': [(a.momento, a.mime) for a in ch.anexos],
                'prazo_desde_abertura': round((ch.prazo - ch.aberto_em).total_seconds()) if ch.prazo else None}


def test_abrir_chamado_como_na_tela_antiga(app_module, cena):
    c = fabrica.entrar(app_module, 'ch4a.enc@trino.com')
    a = cena['local']
    form = lambda titulo: {'client_id': str(a), 'titulo': titulo, 'local': 'Hall', 'descricao': 'Lâmpada',  # noqa: E731
                           'categoria': 'eletrica', 'prioridade': 'urgente',
                           'arquivo': [_foto('a.png'), _foto('b.png')]}
    _, d1, rec = _antiga(c, '/chamados/', data=form('Lâmpada queimada (antiga)'), content_type='multipart/form-data')
    r, j = _nova(c, '/api/v1/chamados/', data=form('Lâmpada queimada (nova)'), content_type='multipart/form-data')
    assert r.status_code == 200
    n1, n2 = int(d1.rsplit('/', 1)[1]), int(j['destino'].rsplit('/', 1)[1])
    assert n1 != n2 and j['destino'] == f'/novo/chamados/{n2}' and d1 == f'/chamados/{n1}'
    _mesmo_recado(rec, j['recados'], [(f'OS-{n1:05d}', f'OS-{n2:05d}')])
    assert j['recados'][0]['texto'].startswith(f'Chamado OS-{n2:05d} aberto')
    x, y = _retrato(app_module, n1), _retrato(app_module, n2)
    assert x == y and len(y['anexos']) == 2 and y['prioridade'] == 'urgente'
    # O formulário enviado duas vezes (duplo toque): o mesmo chamado, sem
    # gravar as fotos de novo — nas duas.
    _, d3, rec = _antiga(c, '/chamados/', data=form('Lâmpada queimada (antiga)'), content_type='multipart/form-data')
    r, j = _nova(c, '/api/v1/chamados/', data=form('Lâmpada queimada (nova)'), content_type='multipart/form-data')
    assert d3 == d1 and j['destino'] == f'/novo/chamados/{n2}'
    _mesmo_recado(rec, j['recados'], [(f'OS-{n1:05d}', f'OS-{n2:05d}')])
    assert _retrato(app_module, n1) == _retrato(app_module, n2) == y
    # Foto que não confere: o chamado abre, com o aviso (nas duas).
    ruim = lambda t: {'client_id': str(a), 'titulo': t, 'arquivo': (io.BytesIO(b'nada'), 'x.png')}  # noqa: E731
    _, d1, rec = _antiga(c, '/chamados/', data=ruim('Foto ruim antiga'), content_type='multipart/form-data')
    r, j = _nova(c, '/api/v1/chamados/', data=ruim('Foto ruim nova'), content_type='multipart/form-data')
    n1, n2 = int(d1.rsplit('/', 1)[1]), int(j['destino'].rsplit('/', 1)[1])
    _mesmo_recado(rec, j['recados'], [(f'OS-{n1:05d}', f'OS-{n2:05d}')])
    assert j['recados'][0]['tipo'] == 'warning' and r.status_code == 200
    # A recusa: sem título, e em contrato que não é da carteira.
    for dados in ({'client_id': str(a), 'titulo': ''}, {'client_id': str(cena['local_b']), 'titulo': 'Fora'}):
        _, d1, rec = _antiga(c, '/chamados/', data=dados)
        r, j = _nova(c, '/api/v1/chamados/', json=dados)
        assert r.status_code == 400 and j['error'] == rec[0]['texto'] and rec[0]['tipo'] == 'danger'
        assert j['destino'] == '/novo' + d1 and d1.startswith('/chamados/novo?client_id=')


def test_o_ciclo_do_chamado_como_na_tela_antiga(app_module, cena, auth_client):
    """A mesma sequência de ações num chamado pela tela antiga e noutro pela
    nova: o mesmo recado a cada passo e o mesmo chamado no fim."""
    from app import User, db
    from facilities.chamados import servico as chs
    c = auth_client
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        par = []
        for titulo in ('Ciclo antigo', 'Ciclo novo'):
            ch, _ = chs.abrir_sem_duplicar(admin, cena['local'], titulo, prioridade='media')
            db.session.commit()
            par.append(ch.id)
    x, y = par
    passos = [
        ({'acao': 'atribuir', 'responsavel_id': str(cena['tec'])}, False),
        ({'acao': 'atribuir', 'responsavel_id': str(cena['tec'])}, False),     # já é o responsável
        ({'acao': 'prioridade', 'prioridade': 'urgente', 'texto': 'Piorou'}, False),
        ({'acao': 'iniciar'}, False),
        ({'acao': 'aguardar', 'texto': ''}, False),                              # recusa: sem motivo
        ({'acao': 'aguardar', 'texto': 'Peça encomendada'}, False),
        ({'acao': 'retomar'}, True),                                            # em JSON
        ({'acao': 'comentar', 'texto': 'Chegou a peça'}, True),
        ({'acao': 'resolver', 'texto': 'Troquei o reparo', 'arquivo': None}, False),
        ({'acao': 'reabrir', 'texto': 'Ainda pinga'}, False),
        ({'acao': 'resolver', 'texto': 'Apertei de novo'}, False),
        ({'acao': 'confirmar'}, False),
        ({'acao': 'confirmar'}, False),                                         # já fechado: recusa
        ({'acao': 'xpto'}, False),
    ]
    for dados, em_json in passos:
        dados = dict(dados)
        foto = 'arquivo' in dados
        if foto:
            dados['arquivo'] = _foto('depois.png')
        _, d1, rec = _antiga(c, f'/chamados/{x}/acao', data=dados,
                             content_type='multipart/form-data' if foto else None)
        if foto:
            dados['arquivo'] = _foto('depois.png')
            r, j = _nova(c, f'/api/v1/chamados/{y}/acao', data=dados, content_type='multipart/form-data')
        elif em_json:
            r, j = _nova(c, f'/api/v1/chamados/{y}/acao', json=dados)
        else:
            r, j = _nova(c, f'/api/v1/chamados/{y}/acao', data=dados)
        _mesmo_recado(rec, j['recados'], [(f'OS-{x:05d}', f'OS-{y:05d}')])
        assert d1 == f'/chamados/{x}' and j['destino'] == f'/novo/chamados/{y}', dados
        recusou = any(t['tipo'] == 'danger' for t in rec)
        assert r.status_code == (400 if recusou else 200), dados
        if recusou:
            assert j['error'] == rec[0]['texto']
    a, b = _retrato(app_module, x), _retrato(app_module, y)
    assert a == b and b['status'] == 'fechado' and b['anexos'] == [('depois', 'image/png')]
    assert [t for t, _ in b['eventos']].count('resolvido') == 2
    # Cancelar: noutro par.
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        par = []
        for titulo in ('Cancelar antigo', 'Cancelar novo'):
            ch, _ = chs.abrir_sem_duplicar(admin, cena['local'], titulo)
            db.session.commit()
            par.append(ch.id)
    x, y = par
    _, _, rec = _antiga(c, f'/chamados/{x}/acao', data={'acao': 'cancelar', 'texto': 'Duplicado', 'arquivo': _foto()},
                        content_type='multipart/form-data')
    r, j = _nova(c, f'/api/v1/chamados/{y}/acao', data={'acao': 'cancelar', 'texto': 'Duplicado', 'arquivo': _foto()},
                 content_type='multipart/form-data')
    _mesmo_recado(rec, j['recados'], [(f'OS-{x:05d}', f'OS-{y:05d}')])
    assert [t['tipo'] for t in j['recados']] == ['success', 'warning']
    assert _retrato(app_module, x) == _retrato(app_module, y)
    assert _retrato(app_module, y)['status'] == 'cancelado' and _retrato(app_module, y)['anexos'] == []


def test_a_acao_da_rota_antiga_aceita_corpo_json(app_module, cena, auth_client):
    """``POST /chamados/<id>/acao`` lê o corpo como a API das telas novas
    (``_dados``): em JSON, a ação é feita como pelo formulário; a recusa
    volta em JSON; o formulário segue igual."""
    from facilities.chamados.models import Chamado
    c = auth_client
    url = f"/chamados/{cena['chamado']}/acao"
    r = c.post(url, json={'acao': 'comentar', 'texto': 'Comentário em JSON'})
    assert r.status_code == 302 and r.headers['Location'] == f"/chamados/{cena['chamado']}"
    with app_module.app.app_context():
        from app import db
        ch = db.session.get(Chamado, cena['chamado'])
        assert [e.texto for e in ch.eventos if e.tipo == 'comentario'][-1] == 'Comentário em JSON'
    r = c.post(url, json={'acao': 'iniciar'})
    assert r.status_code == 302
    with app_module.app.app_context():
        from app import db
        assert db.session.get(Chamado, cena['chamado']).status == 'em_atendimento'
    # A recusa por um campo do corpo (o motivo vazio) volta em JSON.
    r = c.post(url, json={'acao': 'aguardar', 'texto': ''})
    assert r.status_code == 400 and r.is_json and r.get_json()['error'].startswith('Diga o que está faltando')
    r = c.post(url, data={'acao': 'comentar', 'texto': 'Comentário no formulário'})
    assert r.status_code == 302 and r.headers['Location'] == f"/chamados/{cena['chamado']}"


def test_quem_nao_e_responsavel_e_recusado_como_na_tela_antiga(app_module, cena):
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'ch4a.tec2@trino.com', 'tecnico', locais=[LOCAL_A])
    c = fabrica.entrar(app_module, 'ch4a.tec2@trino.com')
    _, _, rec = _antiga(c, f"/chamados/{cena['chamado']}/acao", data={'acao': 'iniciar'})
    r, j = _nova(c, f"/api/v1/chamados/{cena['chamado']}/acao", data={'acao': 'iniciar'})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and 'não está disponível' in j['error']
    with app_module.app.app_context():
        from app import db
        assert db.session.get(Chamado, cena['chamado']).status == 'aberto'


def test_anexar_e_o_material_como_na_tela_antiga(app_module, cena, auth_client):
    from facilities.chamados.models import ChamadoAnexo
    c = auth_client
    ch = cena['chamado']
    for dados in ({'arquivo': _foto(), 'momento': 'depois'}, {'momento': 'antes'},
                  {'arquivo': (io.BytesIO(b'nada'), 'x.png'), 'momento': 'xpto'}):
        _, d1, rec = _antiga(c, f'/chamados/{ch}/anexos', data=dict(dados), content_type='multipart/form-data')
        if 'arquivo' in dados:
            dados['arquivo'] = _foto() if dados['momento'] == 'depois' else (io.BytesIO(b'nada'), 'x.png')
        r, j = _nova(c, f'/api/v1/chamados/{ch}/anexos', data=dados, content_type='multipart/form-data')
        _mesmo_recado(rec, j['recados'])
        assert j['destino'] == '/novo' + d1 == f'/novo/chamados/{ch}' and r.status_code == 200
    with app_module.app.app_context():
        assert [a.momento for a in ChamadoAnexo.query.filter_by(chamado_id=ch).order_by(ChamadoAnexo.id)] == \
            ['antes', 'depois', 'depois']
    # O material usado: a mesma ação do formulário antigo, de volta ao chamado.
    form = {'material_id': str(cena['material']), 'quantidade': '1,5', 'chamado_id': str(ch), 'voltar': 'chamado'}
    _, d1, rec = _antiga(c, f"/materiais/locais/{cena['local']}/consumo", data=form)
    r, j = _nova(c, f"/api/v1/materiais/locais/{cena['local']}/consumo", data=form)
    _mesmo_recado(rec, j['recados'])
    assert d1 == f'/chamados/{ch}' and j['destino'] == f'/novo/chamados/{ch}'
    assert j['recados'][0]['texto'].startswith('Consumo registrado: 1,5 un de Fita veda-rosca')
    d = c.get(f'/api/v1/chamados/{ch}').get_json()
    assert [x['quantidade'] for x in d['consumos']] == ['2', '1,5', '1,5']
    for ruim in ({**form, 'quantidade': 'abc'}, {**form, 'material_id': '999999'}):
        _, d1, rec = _antiga(c, f"/materiais/locais/{cena['local']}/consumo", data=ruim)
        r, j = _nova(c, f"/api/v1/materiais/locais/{cena['local']}/consumo", json=ruim)
        assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == '/novo' + d1
    # Sem voltar ao chamado: o destino é o estoque do local (na tela nova
    # desde a Fase 4b: o mesmo endereço abaixo de /novo).
    _, d1, _ = _antiga(c, f"/materiais/locais/{cena['local']}/consumo", data={**form, 'voltar': ''})
    r, j = _nova(c, f"/api/v1/materiais/locais/{cena['local']}/consumo", data={**form, 'voltar': ''})
    assert j['destino'] == '/novo' + d1 and d1 == f"/materiais/locais/{cena['local']}"


def test_a_preventiva_como_na_tela_antiga(app_module, cena, auth_client):
    from facilities.preventiva.models import PlanoPreventivo
    c = auth_client
    a = cena['local']
    form = lambda nome: {'nome': nome, 'ponto_id': str(cena['ponto']), 'modelo_id': str(cena['modelo']),  # noqa: E731
                         'equipamento_id': '', 'intervalo_dias': '7',
                         'proxima_em': (tempo.hoje() + timedelta(days=3)).isoformat(),
                         'antecedencia_dias': '1', 'prioridade': 'alta', 'responsavel_id': str(cena['tec'])}
    _, d1, rec = _antiga(c, f'/preventiva/locais/{a}', data=form('Plano antigo'))
    r, j = _nova(c, f'/api/v1/preventiva/locais/{a}', data=form('Plano novo'))
    _mesmo_recado(rec, j['recados'])
    assert j['destino'] == '/novo' + d1 == f'/novo/preventiva/locais/{a}'
    for ruim in ({**form('X'), 'intervalo_dias': '0'}, {**form(''), 'nome': ''},
                 {**form('Y'), 'ponto_id': '999999'}):
        _, d1, rec = _antiga(c, f'/preventiva/locais/{a}', data=ruim)
        r, j = _nova(c, f'/api/v1/preventiva/locais/{a}', json=ruim)
        assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == '/novo' + d1

    def retrato(nome):
        with app_module.app.app_context():
            p = PlanoPreventivo.query.filter_by(nome=nome).one()
            return (p.id, (p.ponto_id, p.modelo_id, p.equipamento_id, p.intervalo_dias, p.proxima_em,
                           p.antecedencia_dias, p.prioridade, p.responsavel_id, p.is_active))
    (p1, x), (p2, y) = retrato('Plano antigo'), retrato('Plano novo')
    assert x == y
    # Editar e desativar/reativar.
    _, _, rec = _antiga(c, f'/preventiva/{p1}', data={**form('Plano antigo'), 'intervalo_dias': '10'})
    r, j = _nova(c, f'/api/v1/preventiva/{p2}', data={**form('Plano novo'), 'intervalo_dias': '10'})
    _mesmo_recado(rec, j['recados'])
    for ativo in ('0', '1', '0'):
        _, _, rec = _antiga(c, f'/preventiva/{p1}', data={'ativo': ativo})
        r, j = _nova(c, f'/api/v1/preventiva/{p2}', json={'ativo': ativo})
        _mesmo_recado(rec, j['recados'])
        assert j['destino'] == f'/novo/preventiva/locais/{a}'
    assert retrato('Plano antigo')[1] == retrato('Plano novo')[1]
    assert retrato('Plano novo')[1][3] == 10 and retrato('Plano novo')[1][-1] is False
    assert c.post('/api/v1/preventiva/999999', data={'ativo': '1'}).status_code == 404 == \
        c.post('/preventiva/999999', data={'ativo': '1'}).status_code


def test_editar_plano_com_ponto_checklist_e_equipamento_desativados(app_module, cena, auth_client):
    """O "Editar" do plano mantém o ponto, o checklist e o equipamento atuais
    dele mesmo desativados (com "(desativado)"); salvar sem mexer não muda o
    plano de lugar. O desativado não aparece no "Novo plano", e outro plano
    (ou um novo) não pode escolhê-lo."""
    from app import Client, db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Equipamento, PontoInspecao
    from facilities.preventiva.models import PlanoPreventivo
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistModelo
    c = auth_client
    a, pid = cena['local'], cena['plano']
    with app_module.app.app_context():
        loc = db.session.get(Client, a)
        # Outras opções ativas, que vêm antes na ordem alfabética: era nelas
        # que o seletor caía.
        cad.salvar_equipamento(loc, None, {'nome': 'Ar-condicionado', 'ambiente_id': cena['ambiente']}, None)
        cad.salvar_ponto(loc, None, {'nome': 'Entrada', 'ambiente_id': cena['ambiente']}, None)
        m2 = s.criar_modelo(a, {'nome': 'A checklist ativo'}, None)
        s.publicar(m2, s.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]), {}, None)
        for modelo, oid in ((PontoInspecao, cena['ponto']), (ChecklistModelo, cena['modelo']),
                            (Equipamento, cena['equipamento'])):
            db.session.get(modelo, oid).is_active = False
        db.session.commit()
        p = db.session.get(PlanoPreventivo, pid)
        rotulos = {'ponto': f'{p.ponto.ambiente.nome} · {p.ponto.nome} (desativado)',
                   'modelo': f'{p.modelo.nome} (desativado)', 'eq': f'{p.equipamento.nome} (desativado)'}
        atual = (p.ponto_id, p.modelo_id, p.equipamento_id)
    antigo = c.get(f'/preventiva/locais/{a}').get_data(as_text=True)
    d = c.get(f'/api/v1/preventiva/locais/{a}').get_json()

    def selecionada(campo, sufixo):
        bloco = antigo.split(f'id="{campo}{sufixo}"')[1].split('</select>')[0]
        return html_mod.unescape(re.findall(r'<option value="\d+" selected>([^<]+)</option>', bloco)[0])
    for campo, oid in (('ponto', cena['ponto']), ('modelo', cena['modelo']), ('eq', cena['equipamento'])):
        assert selecionada(campo, pid) == rotulos[campo], campo
        assert f'<option value="{oid}"' not in antigo.split(f'id="{campo}novo"')[1].split('</select>')[0], campo
    for lista, oid in (('pontos', cena['ponto']), ('modelos', cena['modelo']), ('equipamentos', cena['equipamento'])):
        [x] = [x for x in d[lista] if x['id'] == oid]
        assert x['ativo'] is False, lista
        assert any(y['ativo'] for y in d[lista]), lista
    # Salvar sem mexer: aceito, nas duas telas, e o plano fica onde estava.
    form = {'nome': 'Plano editado', 'ponto_id': str(cena['ponto']), 'modelo_id': str(cena['modelo']),
            'equipamento_id': str(cena['equipamento']), 'intervalo_dias': '20',
            'proxima_em': tempo.hoje().isoformat(), 'antecedencia_dias': '0', 'prioridade': 'media',
            'responsavel_id': str(cena['tec'])}
    _, _, rec = _antiga(c, f'/preventiva/{pid}', data=form)
    assert [x['tipo'] for x in rec] == ['success'], rec
    r, j = _nova(c, f'/api/v1/preventiva/{pid}', json={**form, 'intervalo_dias': '21'})
    assert r.status_code == 200 and [x['tipo'] for x in j['recados']] == ['success'], j
    with app_module.app.app_context():
        p = db.session.get(PlanoPreventivo, pid)
        assert (p.ponto_id, p.modelo_id, p.equipamento_id) == atual and p.intervalo_dias == 21
    # O desativado não serve para um plano novo.
    _, _, rec = _antiga(c, f'/preventiva/locais/{a}', data={**form, 'nome': 'Outro'})
    assert rec[0]['tipo'] == 'danger' and 'ponto ativo' in rec[0]['texto']
    r, j = _nova(c, f'/api/v1/preventiva/locais/{a}', json={**form, 'nome': 'Outro'})
    assert r.status_code == 400 and 'ponto ativo' in j['error']


# ── Isolamento ────────────────────────────────────────────────────────────

def test_quem_e_de_outro_local_nao_ve_nem_altera_a(app_module, cena):
    from app import db
    from facilities.chamados.models import Chamado, ChamadoAnexo
    from facilities.preventiva.models import PlanoPreventivo
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'ch4a.plenob@trino.com', 'pleno', locais=[LOCAL_B])
        antes = _retrato(app_module, cena['chamado'])
    c = fabrica.entrar(app_module, 'ch4a.plenob@trino.com')
    a, ch = cena['local'], cena['chamado']
    for url in (f'/api/v1/chamados/{ch}', f'/api/v1/chamados/?client_id={a}',
                f'/api/v1/preventiva/locais/{a}', f'/api/v1/chamados/{cena["preventiva"]}'):
        r = c.get(url)
        assert r.status_code in (403, 404) and r.is_json and SEGREDO not in r.get_data(as_text=True), url
    for url in ('/api/v1/chamados/', '/api/v1/chamados/?visao=todos', '/api/v1/demandas/',
                f'/api/v1/demandas/?local={a}', f'/api/v1/chamados/novo?client_id={a}'):
        r = c.get(url)
        assert r.status_code == 200 and SEGREDO not in r.get_data(as_text=True), url
    for url, dados in ((f'/api/v1/chamados/{ch}/acao', {'acao': 'cancelar', 'texto': 'Invasão'}),
                       (f'/api/v1/chamados/{ch}/acao', {'acao': 'comentar', 'texto': 'Invasão'}),
                       (f'/api/v1/chamados/{ch}/anexos', {'arquivo': _foto(), 'momento': 'antes'}),
                       (f'/api/v1/materiais/locais/{a}/consumo', {'material_id': str(cena['material']),
                                                                  'quantidade': '1', 'chamado_id': str(ch)}),
                       (f'/api/v1/preventiva/locais/{a}', {'nome': 'Invasão'}),
                       (f"/api/v1/preventiva/{cena['plano']}", {'ativo': '0'})):
        r = c.post(url, data=dados, content_type='multipart/form-data')
        assert r.status_code in (403, 404) and r.is_json, url
    r, j = _nova(c, '/api/v1/chamados/', data={'client_id': str(a), 'titulo': 'Invasão'})
    assert r.status_code == 400 and 'Invasão' not in str(j.get('recados'))
    assert _retrato(app_module, ch) == antes
    with app_module.app.app_context():
        assert not Chamado.query.filter_by(titulo='Invasão').count()
        assert db.session.get(PlanoPreventivo, cena['plano']).is_active
        assert ChamadoAnexo.query.filter_by(chamado_id=ch).count() == 1


# ── Dentro das telas novas, os links levam às novas ───────────────────────

def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):
    c = auth_client
    # As telas antigas e o menu não mudam.
    assert f'href="/chamados/{cena["chamado"]}"' in c.get('/chamados/').get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert '/chamados/' in menu and not any(u.startswith(('/novo/chamados', '/novo/demandas')) for u in menu)
    # A rotina nova leva à preventiva nova; o chamado novo, às fotos do servidor.
    d = c.get(f"/api/v1/rotas/locais/{cena['local']}").get_json()
    assert d['links']['preventiva'] == f"/novo/preventiva/locais/{cena['local']}"
    d = c.get(f"/api/v1/chamados/{cena['chamado']}").get_json()
    assert d['anexos'][0]['url'].startswith('/chamados/anexos/')
    # O início do aplicativo novo leva aos chamados novos.
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'ch4a.tec@trino.com', 'tecnico', locais=[LOCAL_A])
    tec = fabrica.entrar(app_module, 'ch4a.tec@trino.com')
    d = tec.get('/api/v1/campo/inicio').get_json()
    assert d['links']['chamados'] == '/novo/chamados/'
    assert d['chamados'] and all(x['url'].startswith('/novo/chamados/') for x in d['chamados'])
