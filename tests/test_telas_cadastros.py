"""Os Cadastros nas telas novas (Fase 3a): os cadastros do grupo, a estrutura
do local, o cadastro simplificado (cliente, centro de custo, áreas e rotas) e
o assistente "Novo contrato" com os convites.

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``);
* a mesma porta, perfil a perfil (o administrador, a gestão, a diretoria que
  só lê, quem é do posto e o cliente);
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id).
"""
import html as html_mod
import io
import re
import uuid

import pytest

from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS

LOCAL_A, LOCAL_B = CONTRATOS_SEMEADOS[0], CONTRATOS_SEMEADOS[1]
SEGREDO = 'CADASTRO-SECRETO-A'


def _png(lado=40):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (lado, lado), (157, 32, 44, 255)).save(buf, format='PNG')
    return buf.getvalue()


def _texto(html):
    return html_mod.unescape(re.sub(r'\s+', ' ', html))


def _flashes(c):
    """Os recados que a tela antiga deixou (e que a próxima página mostraria)."""
    with c.session_transaction() as s:
        return [{'tipo': 'danger' if t == 'error' else t, 'texto': x}
                for t, x in s.pop('_flashes', [])]


def _antiga(c, url, **kw):
    r = c.post(url, **kw)
    assert r.status_code in (302, 400), (url, r.status_code, r.get_data(as_text=True)[:300])
    destino = r.headers.get('Location', '')
    return r, destino, _flashes(c)


def _nova(c, url, **kw):
    r = c.post(url, **kw)
    assert r.is_json, (url, r.status_code, r.get_data(as_text=True)[:300])
    return r, r.get_json()


def _mesmo_recado(antigo, novo, troca=()):
    """O recado da nova é o da antiga (com os nomes que cada envio usou)."""
    textos = [x['texto'] for x in antigo]
    for a, b in troca:
        textos = [t.replace(a, b) for t in textos]
    assert [x['texto'] for x in novo] == textos
    assert [x['tipo'] for x in novo] == [x['tipo'] for x in antigo]


@pytest.fixture()
def cena(app_module):
    """A estrutura de A (empresa, cliente, local com setor, ambiente,
    equipamento e ponto), um gerente responsável pelo cliente de A, áreas e
    uma rota no centro de custo, e um convite aberto para A."""
    from app import db
    from facilities.cadastros import montagem
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        gerente = fabrica.pessoa(app_module, 'cad.gerente@trino.com', 'gerente',
                                 locais=[LOCAL_A], nome='Gerente Cadastros')
        db.session.get(Contratante, ids['cliente']).gerente_id = gerente
        db.session.commit()
    c = fabrica.entrar(app_module, 'cad.gerente@trino.com')
    a = ids['local']
    assert c.post(f'/centros/{a}/areas', data={'areas': f'Banheiro {SEGREDO}\nCopa'}
                  ).status_code == 302
    r = c.post(f'/centros/{a}/rotas', data={'nome': f'Rota {SEGREDO}', 'turno': '1º Turno',
                                            'hora_inicio': '06:00', 'hora_fim': '14:00',
                                            'dias_semana': ['1', '2', '3']})
    rid = int(re.search(r'/rotas/(\d+)$', r.headers['Location']).group(1))
    with app_module.app.app_context():
        from facilities.cadastros.models import PontoInspecao
        area = PontoInspecao.query.filter_by(client_id=a, nome=f'Banheiro {SEGREDO}').one().id
    c.post(f'/centros/{a}/rotas/{rid}/linhas', data={'hora': ['06:00', '07:30'],
                                                      'area': [str(area), str(area)]})
    _flashes(c)
    with app_module.app.app_context():
        from app import User
        conv, _ = montagem.criar_convite(db.session.get(User, gerente), {
            'nome': f'Convidada {SEGREDO}', 'email': f'conv.{uuid.uuid4().hex[:6]}@trino.com',
            'role': 'encarregado', 'locais': [str(a)]})
        db.session.commit()
        conv = conv.id
    return {**ids, 'gerente': c, 'gerente_id': gerente, 'rota': rid, 'area': area,
            'convite': conv}


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo != 'facilities.telas.cadastros':
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1').replace(f'<{arg}>', 'setor')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) >= 25
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


TELAS = (
    # (antiga, nova, api)
    ('/cadastros/', '/novo/cadastros/', '/api/v1/cadastros/inicio'),
    ('/cadastros/empresas', '/novo/cadastros/empresas', '/api/v1/cadastros/empresas'),
    ('/cadastros/clientes', '/novo/cadastros/clientes', '/api/v1/cadastros/clientes'),
    ('/cadastros/estados', '/novo/cadastros/estados', '/api/v1/cadastros/estados'),
    ('/cadastros/trilha', '/novo/cadastros/trilha', '/api/v1/cadastros/trilha'),
    ('/cadastros/locais/{local}', '/novo/cadastros/locais/{local}', '/api/v1/cadastros/locais/{local}'),
    ('/cadastros/locais/{local}/trilha', '/novo/cadastros/locais/{local}/trilha',
     '/api/v1/cadastros/locais/{local}/trilha'),
    ('/clientes', '/novo/clientes', '/api/v1/cadastros/centros/clientes'),
    ('/clientes/{cliente}', '/novo/clientes/{cliente}', '/api/v1/cadastros/centros/clientes/{cliente}'),
    ('/centros/{local}', '/novo/centros/{local}', '/api/v1/cadastros/centros/{local}'),
    ('/centros/{local}/rotas/{rota}', '/novo/centros/{local}/rotas/{rota}',
     '/api/v1/cadastros/centros/{local}/rotas/{rota}'),
    ('/novo-contrato', '/novo/novo-contrato', '/api/v1/cadastros/novo-contrato'),
    ('/novo-contrato/cliente/{cliente}/local', '/novo/novo-contrato/cliente/{cliente}/local',
     '/api/v1/cadastros/novo-contrato/cliente/{cliente}/local'),
    ('/novo-contrato/{local}/estrutura', '/novo/novo-contrato/{local}/estrutura',
     '/api/v1/cadastros/novo-contrato/{local}/estrutura'),
    ('/novo-contrato/{local}/equipe', '/novo/novo-contrato/{local}/equipe',
     '/api/v1/cadastros/novo-contrato/{local}/equipe'),
    ('/convites', '/novo/convites', '/api/v1/cadastros/convites'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'pleno-de-b', 'gerente-sem-cliente']


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta nas telas antigas, nas páginas novas e na
    API. O que é só do administrador volta ao início com um aviso na página
    (antiga e nova) e responde 403 em JSON na API."""
    base = papel.split('-')[0]
    locais = [LOCAL_B] if papel.endswith('de-b') else [LOCAL_A]
    if papel == 'gerente':
        c = cena['gerente']
    else:
        with app_module.app.app_context():
            fabrica.pessoa(app_module, f'porta3a.{papel}@trino.com', base, locais=locais)
        c = fabrica.entrar(app_module, f'porta3a.{papel}@trino.com')
    for antiga, nova, api in TELAS:
        antiga, nova, api = (u.format(**cena) for u in (antiga, nova, api))
        r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get(nova)
        if r_antiga.status_code == 302:
            assert r_api.status_code == 403 and r_api.is_json, (papel, api)
            assert r_nova.status_code == 302, (papel, nova)
            assert r_nova.headers['Location'] == r_antiga.headers['Location'], (papel, nova)
        else:
            assert r_api.status_code == r_antiga.status_code, (papel, api, r_antiga.status_code)
            assert r_nova.status_code in ((200, 503) if r_antiga.status_code == 200
                                          else (r_antiga.status_code,)), (papel, nova)
        if r_api.status_code != 200:
            assert r_api.is_json and SEGREDO not in r_api.get_data(as_text=True), (papel, api)
    # Contraprova: quem a porta deixa entrar e quem ela recusa.
    admin = c.get('/api/v1/cadastros/empresas').status_code == 200
    monta = c.get('/api/v1/cadastros/novo-contrato').status_code == 200
    abre_local = c.get(f"/api/v1/cadastros/locais/{cena['local']}").status_code == 200
    abre_centro = c.get(f"/api/v1/cadastros/centros/{cena['local']}").status_code == 200
    assert admin == (papel == 'master'), papel
    assert monta == (base in ('master', 'gerente', 'pleno')), papel
    if papel in ('master', 'gerente', 'pleno', 'gerente-sem-cliente'):
        assert abre_local and abre_centro, papel
    elif papel == 'visualizador':
        assert abre_local and not abre_centro
    else:
        assert not abre_local and not abre_centro, papel


def test_quem_so_le_nao_recebe_as_acoes_e_o_servidor_recusa(app_module, cena):
    """A diretoria consulta a estrutura do local (sem os botões, como na
    antiga) e o envio direto é recusado, sem mudar nada."""
    from app import db
    from facilities.cadastros.models import Setor
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'cad.diretoria@trino.com', 'visualizador', all_clients=True)
    c = fabrica.entrar(app_module, 'cad.diretoria@trino.com')
    d = c.get(f"/api/v1/cadastros/locais/{cena['local']}").get_json()
    antigo = c.get(f"/cadastros/locais/{cena['local']}").get_data(as_text=True)
    assert d['pode_alterar'] is False and 'Cadastrar setor' not in antigo
    for url in (f"/api/v1/cadastros/locais/{cena['local']}/setor",
                f"/api/v1/cadastros/locais/{cena['local']}/setor/{cena['setor']}/ativo"):
        r = c.post(url, data={'nome': 'Invasão', 'ativo': '0'})
        assert r.status_code == 403 and r.is_json
        assert r.status_code == c.post(url.replace('/api/v1', ''),
                                       data={'nome': 'Invasão', 'ativo': '0'}).status_code
    with app_module.app.app_context():
        assert db.session.get(Setor, cena['setor']).is_active
        assert not Setor.query.filter_by(nome='Invasão').count()


# ── Os mesmos dados das telas antigas ─────────────────────────────────────

def test_cadastros_do_grupo_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    d = c.get('/api/v1/cadastros/inicio').get_json()
    antigo = _texto(c.get('/cadastros/').get_data(as_text=True))
    assert d['e_admin'] and d['pode_novo_contrato']
    assert f"{d['n_empresas']} cadastrada(s)" in antigo and f"{d['n_clientes']} cadastrado(s)" in antigo
    assert f"{d['n_estados']} em uso" in antigo
    assert [x['id'] for x in d['locais']] == [
        int(x) for x in re.findall(r'href="/cadastros/locais/(\d+)"', antigo)]
    [a] = [x for x in d['locais'] if x['id'] == cena['local']]
    assert a == {'id': cena['local'], 'nome': LOCAL_A, 'cliente': 'Grupo GL', 'estado': 'BA'}
    assert d['links']['locais_admin'] == '/admin/contratos'

    d = c.get('/api/v1/cadastros/empresas').get_json()
    antigo = _texto(c.get('/cadastros/empresas').get_data(as_text=True))
    assert [e['id'] for e in d['empresas']] == [
        int(x) for x in re.findall(r'action="/cadastros/empresas/(\d+)"', antigo)]
    assert d['empresas'][0]['nome'] == 'Trino Serviços' and d['empresas'][0]['ativo']

    d = c.get('/api/v1/cadastros/clientes').get_json()
    antigo = _texto(c.get('/cadastros/clientes').get_data(as_text=True))
    assert [x['id'] for x in d['clientes']] == [
        int(x) for x in re.findall(r'action="/cadastros/clientes/(\d+)"', antigo)]
    [gl] = [x for x in d['clientes'] if x['id'] == cena['cliente']]
    assert gl['nome'] == 'Grupo GL' and gl['centro_custo'] == 'GL' and gl['gerente'] == 'Gerente Cadastros'
    assert gl['locais'] == [{'id': cena['local'], 'nome': LOCAL_A, 'estado': 'BA'}]
    for k, v in d['prioridades']:
        assert f"{v} (padrão {d['regua_padrao'][k]} h)" in antigo
    assert [k for k, _ in d['tipos_ocorrencia']] == re.findall(
        r'name="prazo_([a-z_]+)" type="number" min="5"', antigo)[:len(d['tipos_ocorrencia'])]
    assert {g['nome'] for g in d['gerentes']} >= {'Gerente Cadastros'}

    d = c.get('/api/v1/cadastros/estados').get_json()
    antigo = c.get('/cadastros/estados').get_data(as_text=True)
    assert [e['id'] for e in d['estados']] == [
        int(x) for x in re.findall(r'action="/cadastros/estados/(\d+)/ativo"', antigo)]
    assert d['estados'][0] == {'id': cena['estado'], 'nome': 'Bahia', 'sigla': 'BA', 'ativo': True}


def test_estrutura_do_local_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    # Um ponto desativado: some sem ``inativos=1`` e aparece com ele, nas duas.
    r = c.post(f'/cadastros/locais/{a}/ponto', data={'nome': f'Ponto {SEGREDO}',
                                                     'ambiente_id': cena['ambiente']})
    with app_module.app.app_context():
        from facilities.cadastros.models import PontoInspecao
        pid = PontoInspecao.query.filter_by(nome=f'Ponto {SEGREDO}').one().id
    c.post(f'/cadastros/locais/{a}/ponto/{pid}/ativo', data={'ativo': '0'})
    _flashes(c)
    for q in ('', '?inativos=1'):
        d = c.get(f'/api/v1/cadastros/locais/{a}{q}').get_json()
        antigo = _texto(c.get(f'/cadastros/locais/{a}{q}').get_data(as_text=True))
        assert d['com_inativos'] == (q != '') and d['pode_alterar']
        assert d['local'] == {'id': a, 'nome': LOCAL_A, 'cliente': 'Grupo GL', 'estado': 'Bahia',
                              'subcentro': 'CC-SHO'}
        [s] = [x for x in d['setores'] if x['nome'] == 'Administrativo']
        [amb] = s['ambientes']
        assert s['nome'] == 'Administrativo' and amb['nome'] == 'Banheiro masculino 2º andar'
        # O que a tela nova desenha: o mesmo filtro da antiga.
        visiveis = [p['nome'] for p in amb['pontos'] if p['ativo'] or d['com_inativos']]
        assert visiveis == (['Ponto ' + SEGREDO, 'Porta do banheiro'] if q else ['Porta do banheiro'])
        for nome in visiveis:
            assert nome in antigo
        assert (f'Ponto {SEGREDO}' in antigo) == bool(q)
        assert [e['nome'] for e in amb['equipamentos']] == ['Secador de mãos']
        assert d['todos_setores'][0] == {'id': cena['setor'], 'nome': 'Administrativo',
                                         'ambientes': [{'id': cena['ambiente'],
                                                        'nome': 'Banheiro masculino 2º andar'}]}
        assert [x['nome'] for x in d['todos_setores']] == ['Administrativo', 'Geral']
        assert d['links']['etiquetas'] == f'/cadastros/locais/{a}/etiquetas.pdf'
        assert d['links']['etiquetas'] in antigo


def test_trilha_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    for api, antiga in ((f"/api/v1/cadastros/locais/{cena['local']}/trilha",
                         f"/cadastros/locais/{cena['local']}/trilha"),
                        ('/api/v1/cadastros/trilha?entidade=ponto', '/cadastros/trilha?entidade=ponto'),
                        ('/api/v1/cadastros/trilha?entidade=xpto', '/cadastros/trilha?entidade=xpto')):
        d = c.get(api).get_json()
        antigo = _texto(c.get(antiga).get_data(as_text=True))
        assert d['eventos'], api
        assert len(d['eventos']) == antigo.count('<div class="border-bottom px-3 py-2">'), api
        for ev in d['eventos'][:5]:
            assert f"{ev['quando']} · {ev['autor']}" in antigo
            for campo, antes, depois in ev['mudancas']:
                linha = f'<code>{campo}</code>: ' + (f'{antes} → ' if ev['com_antes'] else '') + depois
                assert html_mod.unescape(linha) in antigo, linha
    d = c.get('/api/v1/cadastros/trilha?entidade=ponto').get_json()
    assert d['entidade'] == 'ponto' and {e['entidade'] for e in d['eventos']} == {'Ponto'}
    assert c.get('/api/v1/cadastros/trilha?entidade=xpto').get_json()['entidade'] is None
    d = c.get(f"/api/v1/cadastros/locais/{cena['local']}/trilha").get_json()
    assert d['local'] == {'id': cena['local'], 'nome': LOCAL_A} and d['entidade'] is None


def test_cadastro_simplificado_traz_os_dados_da_tela_antiga(app_module, cena):
    c = cena['gerente']
    a = cena['local']
    d = c.get('/api/v1/cadastros/centros/clientes').get_json()
    antigo = _texto(c.get('/clientes').get_data(as_text=True))
    assert [x['id'] for x in d['clientes']] == [int(x) for x in re.findall(r'href="/clientes/(\d+)"', antigo)]
    assert d['clientes'][0]['centros'] == [{'id': a, 'nome': LOCAL_A, 'centro_custo': 'CC-SHO'}]
    assert d['pode_criar'] and 'Novo cliente' in antigo

    d = c.get(f"/api/v1/cadastros/centros/clientes/{cena['cliente']}").get_json()
    antigo = _texto(c.get(f"/clientes/{cena['cliente']}").get_data(as_text=True))
    [centro] = d['centros']
    assert f"{centro['areas']} área(s) · {centro['rotas']} rota(s)" in antigo
    assert centro['areas'] == 3 and centro['rotas'] == 1
    assert [e['nome'] for e in d['estados']] == ['Bahia']

    for aba in ('areas', 'rotas'):
        d = c.get(f'/api/v1/cadastros/centros/{a}?aba={aba}').get_json()
        antigo = _texto(c.get(f'/centros/{a}?aba={aba}').get_data(as_text=True))
        assert d['aba'] == aba and d['raio'] and not d['local']['marcada']
        assert f"1. Áreas ({len(d['areas'])})" in antigo
        assert f"2. Rotas ({len([r for r in d['rotas'] if r['ativa']])})" in antigo
        if aba == 'areas':
            assert [f"QR {p['numero']:03d}" for p in d['areas']] == re.findall(r'(QR \d{3})', antigo)
            assert [p['id'] for p in d['areas']] == [
                int(x) for x in re.findall(r'action="/centros/\d+/areas/(\d+)/checklist"', antigo)]
            assert all(m['nome'] in antigo for m in d['checklists']) and d['checklists']
            assert d['local']['cliente'] == {'id': cena['cliente'], 'nome': 'Grupo GL'}
        else:
            [r] = d['rotas']
            assert f"{r['turno']} · {r['inicio']} às {r['fim']}" in antigo
            assert f"{r['areas']} área(s)" in antigo and r['nome'] == f'Rota {SEGREDO}'

    d = c.get(f"/api/v1/cadastros/centros/{a}/rotas/{cena['rota']}").get_json()
    antigo = _texto(c.get(f"/centros/{a}/rotas/{cena['rota']}").get_data(as_text=True))
    assert [x['hora'] for x in d['linhas']] == re.findall(r'data-linha="([^"]+)"', antigo) == ['06:00', '07:30']
    assert d['rota']['dias'] == ['seg', 'ter', 'qua'] and '06:00 às 14:00 · seg, ter, qua' in antigo
    assert d['vazias'] == 8 and len(re.findall(r'name="hora" type="time"', antigo)) == 8
    assert d['links']['avancado'] in antigo
    assert d['escalados'] == [] and 'Ninguém escalado' in antigo


def test_novo_contrato_traz_os_dados_da_tela_antiga(app_module, cena):
    c = cena['gerente']
    a = cena['local']
    d = c.get('/api/v1/cadastros/novo-contrato').get_json()
    antigo = _texto(c.get('/novo-contrato').get_data(as_text=True))
    [cli] = d['clientes']
    [loc] = cli['locais']
    an = loc['andamento']
    assert f"{an['pontos']} QR · {an['equipe']} pessoa(s) · {an['convites']} convite(s) aberto(s)" in antigo
    assert an['pontos'] == 3 and an['convites'] == 1
    assert d['passos'] == {'atual': 1, 'local': None, 'cliente': None}
    assert d['pode_criar'] and [e['nome'] for e in d['empresas']] == ['Trino Serviços']

    d = c.get(f"/api/v1/cadastros/novo-contrato/cliente/{cena['cliente']}/local").get_json()
    assert d['passos'] == {'atual': 2, 'local': None, 'cliente': {'id': cena['cliente'], 'nome': 'Grupo GL'}}
    assert d['pode_logo'] and d['cliente']['logo'] is None and d['estados'] == [{'id': cena['estado'], 'nome': 'Bahia'}]

    d = c.get(f'/api/v1/cadastros/novo-contrato/{a}/estrutura').get_json()
    antigo = _texto(c.get(f'/novo-contrato/{a}/estrutura').get_data(as_text=True))
    badges = [f"QR {p['numero']:03d} · {p['nome']}" + (' · entrada' if p['entrada'] else '')
              for s in d['setores'] for amb in s['ambientes'] for p in amb['pontos']]
    assert badges == re.findall(r'<span class="badge text-bg-light">(QR [^<]+)</span>', antigo)
    assert f"{d['andamento']['pontos']} QR neste local, ainda sem o QR da entrada" in antigo
    assert d['links']['etiquetas'] == f'/cadastros/locais/{a}/etiquetas.pdf'
    for link in d['links'].values():
        assert link in antigo, link
    assert d['passos']['local'] == {'id': a, 'nome': LOCAL_A}

    d = c.get(f'/api/v1/cadastros/novo-contrato/{a}/equipe').get_json()
    antigo = _texto(c.get(f'/novo-contrato/{a}/equipe').get_data(as_text=True))
    assert [v for v, _ in d['perfis']] == re.findall(r'<option value="([a-z]+)"[^>]*>[^<]+</option>',
                                                    antigo.split('id="role"')[1].split('</select>')[0])
    assert d['eu'] == {'nome': 'Gerente Cadastros', 'e_admin': False}
    assert 'Você (Gerente Cadastros)' in antigo
    assert [x['nome'] for x in d['convites']] == [f'Convidada {SEGREDO}']
    assert d['convites'][0]['situacao'] == 'pendente' and 'aguardando' in antigo
    assert [x['nome'] for x in d['equipe']] == re.findall(
        r'<div class="border-top px-3 py-2 d-flex flex-wrap gap-2"><strong>([^<]+)</strong>', antigo)
    assert [x['id'] for x in d['locais']] == [int(x) for x in re.findall(r'name="locais" value="(\d+)"', antigo)]
    assert d['links']['concluir'] in antigo

    d = c.get('/api/v1/cadastros/convites').get_json()
    antigo = _texto(c.get('/convites').get_data(as_text=True))
    [conv] = d['convites']
    assert f"{conv['onde']} · convidado por {conv['criado_por']} em {conv['criado_em']}" in antigo
    assert conv['onde'] == LOCAL_A and conv['situacao'] == 'pendente'


# ── Os envios: a mesma ação das telas antigas ─────────────────────────────

def test_empresas_clientes_e_estados_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.cadastros.models import Contratante, Empresa, Estado
    c = auth_client
    # Cadastrar: o mesmo recado, o mesmo registro.
    r, destino, recados = _antiga(c, '/cadastros/empresas', data={'nome': 'Empresa Antiga', 'cnpj': '1'})
    r2, j = _nova(c, '/api/v1/cadastros/empresas', data={'nome': 'Empresa Nova', 'cnpj': '1'})
    assert r2.status_code == 200 and j['destino'] == '/novo' + destino == '/novo/cadastros/empresas'
    _mesmo_recado(recados, j['recados'], [('Antiga', 'Nova')])
    # Também em JSON (a API das telas novas aceita os dois corpos).
    r3, j3 = _nova(c, '/api/v1/cadastros/empresas', json={'nome': 'Empresa Json', 'cnpj': '1'})
    assert r3.status_code == 200 and j3['recados'][0]['texto'] == 'Empresa Empresa Json cadastrada.'
    with app_module.app.app_context():
        velha, nova, js = (Empresa.query.filter_by(nome=n).one() for n in
                           ('Empresa Antiga', 'Empresa Nova', 'Empresa Json'))
        assert (velha.cnpj, velha.is_active) == (nova.cnpj, nova.is_active) == (js.cnpj, js.is_active)
        ids = velha.id, nova.id
    # A recusa: a mesma frase, 400 na nova.
    _, destino, recados = _antiga(c, '/cadastros/empresas', data={'nome': 'empresa antiga'})
    r, j = _nova(c, '/api/v1/cadastros/empresas', data={'nome': 'empresa antiga'})
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'Já existe uma empresa com este nome.'
    _mesmo_recado(recados, j['recados'])
    # Desativar e editar.
    _, _, recados = _antiga(c, f'/cadastros/empresas/{ids[0]}/ativo', data={'ativo': '0'})
    r, j = _nova(c, f'/api/v1/cadastros/empresas/{ids[1]}/ativo', data={'ativo': '0'})
    _mesmo_recado(recados, j['recados'])
    _, _, recados = _antiga(c, f'/cadastros/empresas/{ids[0]}', data={'nome': 'Empresa Antiga 2'})
    r, j = _nova(c, f'/api/v1/cadastros/empresas/{ids[1]}', data={'nome': 'Empresa Nova 2'})
    _mesmo_recado(recados, j['recados'])
    with app_module.app.app_context():
        a, b = (db.session.get(Empresa, i) for i in ids)
        assert (a.is_active, a.nome, a.cnpj) == (b.is_active, 'Empresa Antiga 2', None) \
            and b.nome == 'Empresa Nova 2'

    # Cliente: com régua, prazos e o nome de quem fez (só o administrador).
    form = {'empresa_id': str(cena['empresa']), 'centro_custo': 'CC', 'regua_alta': '5',
            'prazo_sujo': '30', 'prazo_pedido_insumo_horas': '12', 'mostrar_nome_executor': '1',
            'gerente_id': str(cena['gerente_id'])}
    _, destino, recados = _antiga(c, '/cadastros/clientes', data={**form, 'nome': 'Cliente Antigo'})
    r, j = _nova(c, '/api/v1/cadastros/clientes', data={**form, 'nome': 'Cliente Novo'})
    assert j['destino'] == '/novo' + destino
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        x, y = (Contratante.query.filter_by(nome=n).one() for n in ('Cliente Antigo', 'Cliente Novo'))
        campos = ('empresa_id', 'centro_custo', 'gerente_id', 'prazos_chamado_json',
                  'prazos_ocorrencia_json', 'prazo_pedido_insumo_horas', 'mostrar_nome_executor')
        assert [getattr(x, k) for k in campos] == [getattr(y, k) for k in campos]
        assert y.mostrar_nome_executor is True and y.prazo_pedido_insumo_horas == 12
        cid = y.id
    ruim = {**form, 'nome': 'Cliente Ruim', 'regua_alta': '99999'}
    _, _, recados = _antiga(c, '/cadastros/clientes', data=ruim)
    r, j = _nova(c, '/api/v1/cadastros/clientes', data=ruim)
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] and 'de 1 a 2160' in j['error']
    r, j = _nova(c, f'/api/v1/cadastros/clientes/{cid}/ativo', data={'ativo': '0'})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Cliente desativado.'}]
    r, j = _nova(c, f'/api/v1/cadastros/clientes/{cid}', data={**form, 'nome': 'Cliente Novo'})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Cliente atualizado.'}]

    # Estado: o mesmo recado; e a recusa com local ativo nele.
    with app_module.app.app_context():
        mg = Estado.query.filter_by(sigla='MG').one().id
    _, destino, recados = _antiga(c, f'/cadastros/estados/{mg}/ativo', data={'ativo': '1'})
    r, j = _nova(c, f'/api/v1/cadastros/estados/{mg}/ativo', data={'ativo': '0'})
    assert recados[0]['texto'] == 'Minas Gerais ativado.' and j['recados'][0]['texto'] == 'Minas Gerais desativado.'
    assert j['destino'] == '/novo/cadastros/estados'
    _, _, recados = _antiga(c, f"/cadastros/estados/{cena['estado']}/ativo", data={'ativo': '0'})
    r, j = _nova(c, f"/api/v1/cadastros/estados/{cena['estado']}/ativo", data={'ativo': '0'})
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] and 'local(is) ativo(s)' in j['error']
    with app_module.app.app_context():
        assert not db.session.get(Estado, mg).is_active and db.session.get(Estado, cena['estado']).is_active


def test_estrutura_do_local_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.cadastros.models import Ambiente, CadastroEvento, Equipamento, PontoInspecao, Setor
    c = auth_client
    a = cena['local']
    velho, novo = f'/cadastros/locais/{a}', f'/api/v1/cadastros/locais/{a}'
    # Setor, ambiente, equipamento e ponto: o mesmo recado e o mesmo destino
    # (com os desativados à mostra, a volta continua mostrando).
    _, destino, recados = _antiga(c, velho + '/setor', data={'nome': 'Setor Antigo', 'inativos': '1'})
    r, j = _nova(c, novo + '/setor', data={'nome': 'Setor Novo', 'inativos': '1'})
    assert destino == f'/cadastros/locais/{a}?inativos=1' and j['destino'] == '/novo' + destino
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        s1, s2 = (Setor.query.filter_by(client_id=a, nome=n).one().id for n in ('Setor Antigo', 'Setor Novo'))
    _, _, recados = _antiga(c, velho + '/ambiente', data={'nome': 'Copa', 'setor_id': s1, 'descricao': 'x'})
    r, j = _nova(c, novo + '/ambiente', data={'nome': 'Copa', 'setor_id': s2, 'descricao': 'x'})
    _mesmo_recado(recados, j['recados'])
    with app_module.app.app_context():
        a1, a2 = (Ambiente.query.filter_by(setor_id=s, nome='Copa').one().id for s in (s1, s2))
    for amb in (a1, a2):
        url = (velho if amb == a1 else novo) + '/equipamento'
        c.post(url, data={'nome': 'Geladeira', 'ambiente_id': amb, 'patrimonio': 'P1'})
    _flashes(c)
    with app_module.app.app_context():
        e1, e2 = (Equipamento.query.filter_by(ambiente_id=x).one().id for x in (a1, a2))
    _, _, recados = _antiga(c, velho + '/ponto', data={'nome': 'Bancada', 'ambiente_id': a1,
                                                       'equipamento_id': e1})
    r, j = _nova(c, novo + '/ponto', data={'nome': 'Bancada', 'ambiente_id': a2, 'equipamento_id': e2})
    _mesmo_recado(recados, j['recados'])
    # A recusa: o mesmo nome no mesmo ambiente.
    _, _, recados = _antiga(c, velho + '/ponto', data={'nome': 'bancada', 'ambiente_id': a1})
    r, j = _nova(c, novo + '/ponto', data={'nome': 'bancada', 'ambiente_id': a2})
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'Já existe "Bancada" aqui.'
    # O equipamento de outro ambiente é recusado igual.
    _, _, recados = _antiga(c, velho + '/ponto', data={'nome': 'Pia', 'ambiente_id': a1, 'equipamento_id': e2})
    r, j = _nova(c, novo + '/ponto', data={'nome': 'Pia', 'ambiente_id': a2, 'equipamento_id': e1})
    assert r.status_code == 400 and j['error'] == recados[0]['texto']
    # Editar e desativar em cascata.
    _, _, recados = _antiga(c, velho + f'/ambiente/{a1}', data={'nome': 'Copa 2', 'setor_id': s1})
    r, j = _nova(c, novo + f'/ambiente/{a2}', data={'nome': 'Copa 2', 'setor_id': s2})
    _mesmo_recado(recados, j['recados'])
    _, _, recados = _antiga(c, velho + f'/setor/{s1}/ativo', data={'ativo': '0'})
    r, j = _nova(c, novo + f'/setor/{s2}/ativo', data={'ativo': '0'})
    _mesmo_recado(recados, j['recados'])
    assert j['destino'] == f'/novo/cadastros/locais/{a}'
    with app_module.app.app_context():
        def retrato(s, amb):
            p = PontoInspecao.query.filter_by(ambiente_id=amb).one()
            return (db.session.get(Setor, s).is_active, db.session.get(Ambiente, amb).is_active,
                    db.session.get(Ambiente, amb).nome, p.nome, p.is_active, p.equipamento_id is not None,
                    sorted(ev.acao for ev in CadastroEvento.query.filter(
                        CadastroEvento.entidade.in_(('ambiente', 'ponto', 'equipamento')),
                        CadastroEvento.entidade_id.in_((amb, p.id))).all()))
        assert retrato(s1, a1) == retrato(s2, a2)
        assert retrato(s2, a2)[:5] == (False, False, 'Copa 2', 'Bancada', False)
    # Entidade que não existe: 404, como na antiga.
    assert c.post(novo + '/xpto', data={'nome': 'x'}).status_code == 404 == \
        c.post(velho + '/xpto', data={'nome': 'x'}).status_code
    # De outro local: 404 na nova e na antiga (o item não é deste local).
    with app_module.app.app_context():
        outro = fabrica.local(LOCAL_B).id
    assert c.post(f'/api/v1/cadastros/locais/{outro}/ponto/{cena["ponto"]}', data={'nome': 'x'}
                  ).status_code == 404 == c.post(f'/cadastros/locais/{outro}/ponto/{cena["ponto"]}',
                                                data={'nome': 'x'}).status_code


def test_cadastro_simplificado_como_na_tela_antiga(app_module, cena):
    from app import Client, db
    from facilities.cadastros.models import PontoInspecao
    from facilities.rotas.models import Rota, RotaEscala, RotaItem
    c = cena['gerente']
    a = cena['local']
    sufixo = uuid.uuid4().hex[:6]
    ct = cena['cliente']
    # O centro de custo novo: o mesmo recado e o destino (o centro novo).
    form = {'estado_id': str(cena['estado']), 'cost_center': 'X'}
    _, destino, recados = _antiga(c, f'/clientes/{ct}/centros', data={**form, 'name': f'CC Antigo {sufixo}'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/clientes/{ct}/centros', data={**form, 'name': f'CC Novo {sufixo}'})
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        c1, c2 = (Client.query.filter_by(name=f'CC {n} {sufixo}').one() for n in ('Antigo', 'Novo'))
        assert (c1.contratante_id, c1.estado_id, c1.cost_center, c1.responsible_user_id) == \
            (c2.contratante_id, c2.estado_id, c2.cost_center, c2.responsible_user_id)
        c1, c2 = c1.id, c2.id
    assert destino == f'/centros/{c1}' and j['destino'] == f'/novo/centros/{c2}'
    r, j = _nova(c, f'/api/v1/cadastros/centros/clientes/{ct}/centros', data={**form, 'name': f'CC Novo {sufixo}'})
    assert r.status_code == 400 and 'Já existe um local chamado' in j['error']
    assert j['destino'] == f'/novo/clientes/{ct}'
    # As áreas (e a recusa do nome repetido, tudo ou nada).
    _, destino, recados = _antiga(c, f'/centros/{c1}/areas', data={'areas': 'Banheiro 01\nRecepção'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/areas', data={'areas': 'Banheiro 01\nRecepção'})
    _mesmo_recado(recados, j['recados'])
    assert j['recados'][0]['texto'].startswith('2 área(s) cadastrada(s)')
    _, _, recados = _antiga(c, f'/centros/{c1}/areas', data={'areas': 'banheiro 01'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/areas', data={'areas': 'banheiro 01'})
    assert r.status_code == 400 and j['error'] == recados[0]['texto']
    with app_module.app.app_context():
        def areas(cid):
            return [(p.nome, p.checklist.nome if p.checklist else None)
                    for p in PontoInspecao.query.filter_by(client_id=cid).order_by(PontoInspecao.id)]
        assert areas(c1) == areas(c2) and len(areas(c2)) == 2
        p1, p2 = (PontoInspecao.query.filter_by(client_id=x).order_by(PontoInspecao.id).first().id
                  for x in (c1, c2))
    # Trocar o checklist: a recusa com um checklist que não é do centro.
    _, _, recados = _antiga(c, f'/centros/{c1}/areas/{p1}/checklist', data={'checklist_id': '999999'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/areas/{p2}/checklist', data={'checklist_id': '999999'})
    assert r.status_code == 400 and j['error'] == recados[0]['texto']
    # A posição do GPS: a recusa do raio e o recado de sucesso.
    pos = {'lat': '-12.97', 'lng': '-38.50', 'precisao': '10', 'raio': '10'}
    _, _, recados = _antiga(c, f'/centros/{c1}/posicao', data=pos)
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/posicao', data=pos)
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'O raio vai de 50 a 5000 metros.'
    _, _, recados = _antiga(c, f'/centros/{c1}/posicao', data={**pos, 'raio': '300'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/posicao', data={**pos, 'raio': '300'})
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        x, y = db.session.get(Client, c1), db.session.get(Client, c2)
        assert (x.latitude, x.longitude, x.raio_gps_m) == (y.latitude, y.longitude, y.raio_gps_m)
        assert y.raio_gps_m == 300
    # A rota: os dias em lista (as caixas de marcar), também em JSON.
    rota = {'nome': 'Banheiros', 'turno': '1º Turno', 'hora_inicio': '06:00', 'hora_fim': '14:00',
            'dias_semana': ['1', '3', '5']}
    _, destino, recados = _antiga(c, f'/centros/{c1}/rotas', data=rota)
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/rotas', json=rota)
    _mesmo_recado(recados, j['recados'])
    with app_module.app.app_context():
        r1, r2 = (Rota.query.filter_by(client_id=x).one() for x in (c1, c2))
        assert (r1.dias_semana, r1.hora_inicio, r1.turno) == (r2.dias_semana, r2.hora_inicio, r2.turno) \
            and r2.dias_semana == '135'
        r1, r2 = r1.id, r2.id
    assert j['destino'] == f'/novo/centros/{c2}/rotas/{r2}' and destino == f'/centros/{c1}/rotas/{r1}'
    # As linhas: as mesmas, com o recado (e o da agenda refeita, se houver).
    _, _, recados = _antiga(c, f'/centros/{c1}/rotas/{r1}/linhas', data={'hora': ['06:00', '', '08:00'],
                                                                         'area': [str(p1), '', str(p1)]})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/rotas/{r2}/linhas',
                 data={'hora': ['06:00', '', '08:00'], 'area': [str(p2), '', str(p2)]})
    _mesmo_recado(recados, j['recados'])
    assert j['recados'][0]['texto'] == 'Horários incluídos na rota.'
    _, _, recados = _antiga(c, f'/centros/{c1}/rotas/{r1}/linhas', data={'hora': ['25:00'], 'area': [str(p1)]})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/rotas/{r2}/linhas', data={'hora': ['25:00'], 'area': [str(p2)]})
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'Linha 1: escreva o horário (ex.: 06:00).'
    with app_module.app.app_context():
        i1, i2 = (RotaItem.query.filter_by(rota_id=x, is_active=True).one() for x in (r1, r2))
        assert i1.horarios == i2.horarios == '06:00, 08:00'
        i1, i2 = i1.id, i2.id
    _, _, recados = _antiga(c, f'/centros/{c1}/rotas/{r1}/linhas/{i1}/remover', data={'hora': '06:00'})
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/rotas/{r2}/linhas/{i2}/remover', data={'hora': '06:00'})
    _mesmo_recado(recados, j['recados'])
    # Escalar: a pessoa da equipe do centro.
    with app_module.app.app_context():
        enc = fabrica.pessoa(app_module, f'cad.enc.{sufixo}@trino.com', 'encarregado', locais=[c1, c2],
                             nome='Encarregada Rota')
    esc = {'user_id': str(enc), 'data_inicio': '2026-11-01'}
    _, _, recados = _antiga(c, f'/centros/{c1}/rotas/{r1}/escala', data=esc)
    r, j = _nova(c, f'/api/v1/cadastros/centros/{c2}/rotas/{r2}/escala', data=esc)
    _mesmo_recado(recados, j['recados'])
    assert j['recados'][0]['texto'] == 'Encarregada Rota faz esta rota.'
    with app_module.app.app_context():
        e1, e2 = (RotaEscala.query.filter_by(rota_id=x).one() for x in (r1, r2))
        assert (e1.dias_semana, e1.user_id, e1.data_inicio) == (e2.dias_semana, e2.user_id, e2.data_inicio)
    # A rota de outro centro: 404, como na antiga.
    assert c.post(f'/api/v1/cadastros/centros/{c2}/rotas/{r1}/escala', data=esc).status_code == 404 == \
        c.post(f'/centros/{c2}/rotas/{r1}/escala', data=esc).status_code
    assert a


def test_novo_contrato_como_na_tela_antiga(app_module, cena):
    from app import Client, db
    from facilities.cadastros.models import Contratante, Convite, PontoInspecao
    c = cena['gerente']
    sufixo = uuid.uuid4().hex[:6]
    # Passo 1: o cliente com a logo (o arquivo vai pela mesma ação).
    _, destino, recados = _antiga(c, '/novo-contrato/cliente', content_type='multipart/form-data', data={
        'nome': f'Cli Antigo {sufixo}', 'empresa_id': str(cena['empresa']), 'logo': (io.BytesIO(_png()), 'l.png')})
    r, j = _nova(c, '/api/v1/cadastros/novo-contrato/cliente', content_type='multipart/form-data', data={
        'nome': f'Cli Novo {sufixo}', 'empresa_id': str(cena['empresa']), 'logo': (io.BytesIO(_png()), 'l.png')})
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        x, y = (Contratante.query.filter_by(nome=f'Cli {n} {sufixo}').one() for n in ('Antigo', 'Novo'))
        assert x.gerente_id == y.gerente_id == cena['gerente_id'] and x.logo_key and y.logo_key
        k1, k2 = x.id, y.id
    assert j['destino'] == f'/novo/novo-contrato/cliente/{k2}/local' and destino == f'/novo-contrato/cliente/{k1}/local'
    # A logo que não é imagem: a mesma recusa.
    falso = {'logo': (io.BytesIO(b'nao e imagem'), 'l.png')}
    _, _, recados = _antiga(c, f'/novo-contrato/cliente/{k1}/logo', content_type='multipart/form-data',
                            data=dict(falso))
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/cliente/{k2}/logo', content_type='multipart/form-data',
                 data={'logo': (io.BytesIO(b'nao e imagem'), 'l.png')})
    assert r.status_code == 400 and j['error'] == recados[0]['texto']
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/cliente/{k2}/logo', content_type='multipart/form-data',
                 data={'logo': (io.BytesIO(_png(80)), 'l.png')})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Logo salva. Ela já sai nas etiquetas de QR deste cliente.'}]
    assert j['destino'] == f'/novo/novo-contrato/cliente/{k2}/local'
    # Passo 2: o local.
    form = {'estado_id': str(cena['estado'])}
    _, destino, recados = _antiga(c, f'/novo-contrato/cliente/{k1}/local', data={**form, 'name': f'L Antigo {sufixo}'})
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/cliente/{k2}/local', data={**form, 'name': f'L Novo {sufixo}'})
    _mesmo_recado(recados, j['recados'], [('Antigo', 'Novo')])
    with app_module.app.app_context():
        l1, l2 = (Client.query.filter_by(name=f'L {n} {sufixo}').one().id for n in ('Antigo', 'Novo'))
    assert j['destino'] == f'/novo/novo-contrato/{l2}/estrutura'
    _, _, recados = _antiga(c, f'/novo-contrato/cliente/{k1}/local', data={'name': f'L Sem {sufixo}'})
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/cliente/{k2}/local', data={'name': f'L Sem {sufixo}'})
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'Escolha o estado do local.'
    # Passo 3: a estrutura rápida, com a entrada.
    est = {'setor_nome': 'Administrativo', 'ambiente_nome': 'Recepção', 'pontos': 'Porta\nBalcão', 'entrada': '1'}
    _, _, recados = _antiga(c, f'/novo-contrato/{l1}/estrutura', data=est)
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/{l2}/estrutura', data=est)
    _mesmo_recado(recados, j['recados'])
    assert j['recados'][0]['texto'] == 'Recepção: 2 ponto(s) com QR cadastrado(s).'
    _, _, recados = _antiga(c, f'/novo-contrato/{l1}/estrutura', data=est)
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/{l2}/estrutura', data=est)
    assert r.status_code == 400 and j['error'] == recados[0]['texto']
    with app_module.app.app_context():
        def pontos(cid):
            return [(p.nome, p.entrada_do_local, p.ambiente.nome, p.ambiente.setor.nome)
                    for p in PontoInspecao.query.filter_by(client_id=cid).order_by(PontoInspecao.id)]
        assert pontos(l1) == pontos(l2) and pontos(l2)[0] == ('Porta', True, 'Recepção', 'Administrativo')
    # Passo 4: o convite. A nova recebe o mesmo que a página "Convite pronto".
    conv = {'nome': 'Joana', 'telefone': '71 98888-7777', 'role': 'encarregado', 'locais': [str(l1), str(l2)]}
    antigo = c.post(f'/novo-contrato/{l1}/equipe', data={**conv, 'email': f'joana.a.{sufixo}@trino.com'})
    assert antigo.status_code == 200
    antigo = _texto(antigo.get_data(as_text=True))
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/{l2}/equipe', data={**conv, 'email': f'joana.n.{sufixo}@trino.com'})
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert j['convite'] == {'nome': 'Joana', 'email': f'joana.n.{sufixo}@trino.com'}
    assert j['perfil'] == 'Encarregado / ASG'
    assert f"Joana · {j['perfil']} · {', '.join(j['locais'])}" in re.sub(r'<[^>]+>', '', antigo)
    assert j['enviado'] is None and re.search(r'/convite/[A-Za-z0-9_-]{30,}$', j['link'])
    assert j['whatsapp'].startswith('https://wa.me/5571988887777?text=') and j['email'].startswith('mailto:')
    assert re.search(r'value="http://localhost/convite/[A-Za-z0-9_-]{30,}"', antigo)
    assert j['local'] == {'id': l2, 'nome': f'L Novo {sufixo}'} and j['passos']['atual'] == 4
    with app_module.app.app_context():
        x, y = (Convite.query.filter_by(email=f'joana.{n}.{sufixo}@trino.com').one() for n in ('a', 'n'))
        assert (x.role, x.superior_id, x.locais_json, x.telefone) == (y.role, y.superior_id, y.locais_json, y.telefone)
        cx, cy = x.id, y.id
    # A recusa do convite: a mesma frase (e 400 nas duas).
    ruim = {**conv, 'email': 'sem-arroba'}
    antigo = c.post(f'/novo-contrato/{l1}/equipe', data=ruim)
    assert antigo.status_code == 400
    _flashes(c)
    r, j = _nova(c, f'/api/v1/cadastros/novo-contrato/{l2}/equipe', data=ruim)
    assert r.status_code == 400 and j['error'] == 'Informe um e-mail válido: é com ele que a pessoa vai entrar.'
    assert html_mod.escape(j['error'], quote=False) in antigo.get_data(as_text=True)
    # Os convites: link novo (a mesma página) e cancelar (o mesmo recado).
    r, j = _nova(c, f'/api/v1/cadastros/convites/{cy}/novo-link')
    assert r.status_code == 200 and j['local'] is None and j['passos'] is None and '/convite/' in j['link']
    _, destino, recados = _antiga(c, f'/convites/{cx}/cancelar')
    r, j = _nova(c, f'/api/v1/cadastros/convites/{cy}/cancelar')
    _mesmo_recado(recados, j['recados'])
    assert j['destino'] == '/novo/convites' == '/novo' + destino
    _, _, recados = _antiga(c, f'/convites/{cx}/cancelar')
    r, j = _nova(c, f'/api/v1/cadastros/convites/{cy}/cancelar')
    assert r.status_code == 400 and j['error'] == recados[0]['texto'] == 'Este convite já não está aberto.'
    with app_module.app.app_context():
        assert db.session.get(Convite, cx).cancelado_em and db.session.get(Convite, cy).cancelado_em


def test_quem_e_de_outro_local_nao_ve_nem_altera_a(app_module, cena):
    """O coordenador de B (e o gerente sem o cliente de A) não abre nada de
    A pelas telas novas, nem envia para A."""
    from app import db
    from facilities.cadastros.models import Setor
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'cad.plenob@trino.com', 'pleno', locais=[LOCAL_B])
    c = fabrica.entrar(app_module, 'cad.plenob@trino.com')
    a = cena['local']
    for url in (f'/api/v1/cadastros/locais/{a}', f'/api/v1/cadastros/locais/{a}/trilha',
                f'/api/v1/cadastros/centros/{a}', f"/api/v1/cadastros/centros/{a}/rotas/{cena['rota']}",
                f"/api/v1/cadastros/centros/clientes/{cena['cliente']}",
                f'/api/v1/cadastros/novo-contrato/{a}/estrutura', f'/api/v1/cadastros/novo-contrato/{a}/equipe',
                f"/api/v1/cadastros/novo-contrato/cliente/{cena['cliente']}/local"):
        r = c.get(url)
        assert r.status_code in (403, 404) and r.is_json and SEGREDO not in r.get_data(as_text=True), url
    for url, dados in ((f'/api/v1/cadastros/locais/{a}/setor/{cena["setor"]}/ativo', {'ativo': '0'}),
                       (f'/api/v1/cadastros/centros/{a}/areas', {'areas': 'Invasão'}),
                       (f'/api/v1/cadastros/novo-contrato/{a}/estrutura', {'ambiente_nome': 'Invasão',
                                                                           'setor_nome': 'Invasão'}),
                       (f"/api/v1/cadastros/convites/{cena['convite']}/novo-link", {})):
        r = c.post(url, data=dados)
        assert r.status_code in (403, 404) and r.is_json, url
    d = c.get('/api/v1/cadastros/inicio').get_json()
    assert a not in [x['id'] for x in d['locais']]
    assert c.get('/api/v1/cadastros/convites').get_json()['convites'] == []
    with app_module.app.app_context():
        assert db.session.get(Setor, cena['setor']).is_active
        assert not Setor.query.filter_by(nome='Invasão').count()


def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):
    """O endereço de volta é o da tela nova; as telas antigas e o menu não mudam."""
    c = auth_client
    r, j = _nova(c, f"/api/v1/cadastros/locais/{cena['local']}/setor", data={'nome': 'Setor Links'})
    assert j['destino'] == f"/novo/cadastros/locais/{cena['local']}"
    assert 'action="/cadastros/locais/' in c.get(f"/cadastros/locais/{cena['local']}").get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert not any(u.startswith(('/novo/cadastros', '/novo/clientes', '/novo/novo-contrato'))
                   for u in menu)
    from facilities.telas.cadastros import nova
    assert nova('/cadastros/locais/1/etiquetas.pdf') == '/cadastros/locais/1/etiquetas.pdf'
    assert nova('/rotas/locais/1') == '/rotas/locais/1'
    assert nova('/convites') == '/novo/convites'
