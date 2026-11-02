"""A rotina dos locais nas telas novas (Fase 3b): o início e o local, a
biblioteca e as rotas prontas, o checklist (perguntas, POP/FIT), a rota
(atividades, escala, turno), a planilha do cliente, os feriados, o dia e a
execução.

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (as funções ``contexto_*``);
* a mesma porta, perfil a perfil;
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa, com o endereço de volta já na tela nova;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id).
"""
import html as html_mod
import io
import re
import uuid
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS
from tests.test_rotas_servico import Arquivo

LOCAL_A, LOCAL_B = CONTRATOS_SEMEADOS[0], CONTRATOS_SEMEADOS[1]
SEGREDO = 'ROTINA-SECRETA-A'


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


def _planilha():
    from facilities.rotas import plano_limpeza
    with open(plano_limpeza.caminho_da_planilha_trino_frio(), 'rb') as f:
        return f.read()


@pytest.fixture()
def cena(app_module, auth_client):
    """Em A: um checklist publicado com POP/FIT, uma rota com atividade e
    escala, uma execução de hoje com não conformidade e foto, uma ocorrência
    do público e um feriado. Na biblioteca: um checklist e uma rota pronta."""
    from app import User, db
    from facilities.rotas import feriados, ocorrencias, rotas_prontas
    from facilities.rotas import servico as s
    from facilities.rotas.models import NaoConformidade
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        enc = fabrica.pessoa(app_module, 'rot.enc@trino.com', 'encarregado', locais=[LOCAL_A],
                             nome='Encarregada Rotina')
        gerente = fabrica.pessoa(app_module, 'rot.gerente@trino.com', 'gerente',
                                 locais=[LOCAL_A], nome='Gerente Rotina')
        loc = fabrica.local()
        a = ids['local']
        m = s.criar_modelo(a, {'nome': f'Checklist {SEGREDO}'}, None)
        s.publicar(m, s.normalizar_itens([
            {'texto': f'Pergunta {SEGREDO}', 'tipo': 'sim_nao', 'problema_se': 'nao',
             'obrigatorio': True, 'como_fazer': 'Olhe tudo'},
            {'texto': 'Quantos rolos?', 'tipo': 'numero', 'minimo': '1', 'maximo': '5'}]),
            {'materiais': 'Pano', 'epi': 'Luva'}, None)
        doc = s.anexar_documento(m, Arquivo(b'%PDF-1.4 x', 'pop.pdf'), None)
        rota = s.salvar_rota(loc, None, {'nome': f'Rota {SEGREDO}', 'turno': 'T1',
                                         'hora_inicio': '00:00', 'hora_fim': '23:59',
                                         'tolerancia_min': '240', 'dias_semana': '1234567',
                                         'observacoes': 'Obs da rota'})
        item = s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                          'horarios': tempo.agora().strftime('%H:%M')})
        s.salvar_escala(rota, {'user_id': enc, 'dias_semana': '12345',
                               'data_inicio': tempo.hoje().isoformat()})
        s.garantir_hoje([a])
        db.session.commit()
        tarefa = s.tarefas_do_dia([a], tempo.hoje())[0]
        codigo = s.itens_da_versao(m.versao_atual)[0]['codigo']
        ponto = db.session.get(PontoInspecao, ids['ponto'])
        ex, _ = s.registrar_execucao(db.session.get(User, enc), {
            'envio_id': 'rotina-a-0001', 'ponto': ponto.codigo_qr, 'tarefa_id': tarefa.id,
            'respostas': {codigo: 'nao'}, 'sem_sinal': True, 'observacao': 'Tudo certo',
            'lido_em': tarefa.previsto_para.isoformat()},
            {'depois': [Arquivo()]}, agora_utc=tarefa.previsto_para)
        db.session.commit()
        oc = ocorrencias.abrir(ponto, 'outro', f'Aviso {SEGREDO}')
        from datetime import date
        fer = feriados.cadastrar(loc, {'data': date(tempo.hoje().year, 7, 2).isoformat(),
                                       'nome': f'Feriado {SEGREDO}'}, None)
        lib = s.criar_modelo(None, {'nome': 'Checklist da biblioteca'}, None)
        s.publicar(lib, s.normalizar_itens([{'texto': 'Limpo?', 'tipo': 'sim_nao'}]), {}, None)
        pronta = rotas_prontas.salvar_modelo(None, {
            'nome': 'Rota pronta de teste', 'segmento': 'Escritório', 'turno': 'Diurno',
            'hora_inicio': '06:00', 'hora_fim': '18:00', 'dias_semana': '12345'}, [
            {'setor': 'Sanitários', 'ambiente': 'Banheiro', 'checklist_id': str(lib.id),
             'horarios': '08:00, 12:00', 'quantidade': '2'}])
        db.session.commit()
        nc = NaoConformidade.query.filter_by(execucao_id=ex.id).one().id
        ids.update(modelo=m.id, documento=doc.id, rota=rota.id, item=item.id, execucao=ex.id,
                   ocorrencia=oc.id, feriado=fer.id, biblioteca=lib.id, pronta=pronta.id, nc=nc,
                   enc=enc, gerente_id=gerente, tarefa=tarefa.id)
    ids['gerente'] = fabrica.entrar(app_module, 'rot.gerente@trino.com')
    return ids


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo != 'facilities.telas.rotas':
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1').replace(f'<{arg}>', 'retirar')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) >= 25
    assert len([1 for m, u in rotas if u.startswith('/novo/')]) == 12
    for metodo, url in rotas:
        r = client.open(url, method=metodo)
        if url.startswith('/api/v1/'):
            assert r.status_code == 401 and r.is_json, (metodo, url)
        else:
            assert r.status_code == 302 and '/login' in r.headers['Location'], url


TELAS = (
    # (antiga, api) — a nova é a antiga abaixo de /novo
    ('/rotas/', '/api/v1/rotas/inicio'),
    ('/rotas/locais/{local}', '/api/v1/rotas/locais/{local}'),
    ('/rotas/biblioteca', '/api/v1/rotas/biblioteca'),
    ('/rotas/biblioteca/rotas/nova', '/api/v1/rotas/biblioteca/rotas/nova'),
    ('/rotas/biblioteca/rotas/{pronta}', '/api/v1/rotas/biblioteca/rotas/{pronta}'),
    ('/rotas/locais/{local}/rota-pronta', '/api/v1/rotas/locais/{local}/rota-pronta'),
    ('/rotas/locais/{local}/importar-plano', '/api/v1/rotas/locais/{local}/importar-plano'),
    ('/rotas/modelos/{modelo}', '/api/v1/rotas/modelos/{modelo}'),
    ('/rotas/modelos/{biblioteca}', '/api/v1/rotas/modelos/{biblioteca}'),
    ('/rotas/locais/{local}/feriados', '/api/v1/rotas/locais/{local}/feriados'),
    ('/rotas/{rota}', '/api/v1/rotas/{rota}'),
    ('/rotas/locais/{local}/dia', '/api/v1/rotas/locais/{local}/dia'),
    ('/rotas/execucoes/{execucao}', '/api/v1/rotas/execucoes/{execucao}'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'pleno-de-b']


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta na tela antiga, na página nova e na API."""
    base = papel.split('-')[0]
    locais = [LOCAL_B] if papel.endswith('de-b') else [LOCAL_A]
    if papel == 'gerente':
        c = cena['gerente']
    else:
        with app_module.app.app_context():
            fabrica.pessoa(app_module, f'porta3b.{papel}@trino.com', base, locais=locais)
        c = fabrica.entrar(app_module, f'porta3b.{papel}@trino.com')
    codigos = {}
    for antiga, api in TELAS:
        antiga, api = antiga.format(**cena), api.format(**cena)
        r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
        if r_antiga.status_code == 302:
            assert r_api.status_code == 403 and r_api.is_json, (papel, api)
            assert r_nova.status_code == 302, (papel, antiga)
            assert r_nova.headers['Location'] == r_antiga.headers['Location'], (papel, antiga)
        else:
            assert r_api.status_code == r_antiga.status_code, (papel, api, r_antiga.status_code)
            assert r_nova.status_code in ((200, 503) if r_antiga.status_code == 200
                                          else (r_antiga.status_code,)), (papel, antiga)
        if r_api.status_code != 200:
            assert r_api.is_json and SEGREDO not in r_api.get_data(as_text=True), (papel, api)
        codigos[antiga.format(**cena)] = r_api.status_code
    # Contraprova: quem a porta deixa entrar e quem ela recusa.
    acompanha = base in ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')
    de_a = not papel.endswith('de-b')
    assert (codigos['/rotas/'] == 200) == acompanha, papel
    assert (codigos[f"/rotas/{cena['rota']}"] == 200) == (acompanha and de_a), papel
    assert (codigos[f"/rotas/locais/{cena['local']}/importar-plano"] == 200) == \
        (base in ('master', 'gerente', 'pleno') and de_a), papel
    assert (codigos['/rotas/biblioteca/rotas/nova'] == 200) == (papel == 'master'), papel


def test_quem_so_le_nao_recebe_as_acoes_e_o_servidor_recusa(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'rot.diretoria@trino.com', 'visualizador', all_clients=True)
    c = fabrica.entrar(app_module, 'rot.diretoria@trino.com')
    d = c.get(f"/api/v1/rotas/{cena['rota']}").get_json()
    antigo = c.get(f"/rotas/{cena['rota']}").get_data(as_text=True)
    assert d['pode_montar'] is False and 'Escalar pessoa' not in antigo
    m = c.get(f"/api/v1/rotas/modelos/{cena['modelo']}").get_json()
    assert m['pode_montar'] is False and all('foto_ref' not in it for it in m['itens'])
    for url, dados in ((f"/api/v1/rotas/{cena['rota']}/ativo", {'ativo': '0'}),
                       (f"/api/v1/rotas/locais/{cena['local']}/rotas", {'nome': 'Invasão'})):
        r = c.post(url, data=dados)
        assert r.status_code == 403 and r.is_json
        assert r.status_code == c.post(url.replace('/api/v1', ''), data=dados).status_code
    with app_module.app.app_context():
        assert db.session.get(Rota, cena['rota']).is_active
        assert not Rota.query.filter_by(nome='Invasão').count()


# ── Os mesmos dados das telas antigas ─────────────────────────────────────

def test_inicio_local_e_biblioteca_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get('/api/v1/rotas/inicio').get_json()
    antigo = _texto(c.get('/rotas/').get_data(as_text=True))
    assert [x['id'] for x in d['locais']] == [
        int(x) for x in re.findall(r'href="/rotas/locais/(\d+)/dia"', antigo)]
    [la] = [x for x in d['locais'] if x['id'] == a]
    assert la['cliente'] == 'Grupo GL' and 'Shopping Centro <small>Grupo GL</small>' in antigo
    # A preventiva já está nas telas novas (Fase 4a), a equipe e as visitas
    # desde a 4b: o mesmo endereço abaixo de /novo.
    assert la['links']['preventiva'] == f'/novo/preventiva/locais/{a}'
    assert la['links']['equipe'] == f'/novo/equipes/locais/{a}'
    assert la['links']['visitas'] == f'/novo/visitas/locais/{a}'
    for k in ('preventiva', 'equipe', 'visitas'):
        assert f'href="{la["links"][k].removeprefix("/novo")}"' in antigo
    assert la['links']['estrutura'] == f'/novo/cadastros/locais/{a}'

    d = c.get(f'/api/v1/rotas/locais/{a}').get_json()
    antigo = _texto(c.get(f'/rotas/locais/{a}').get_data(as_text=True))
    assert [m['id'] for m in d['modelos']] == [
        int(x) for x in re.findall(r'href="/rotas/modelos/(\d+)"', antigo)]
    assert d['modelos'][0] == {'id': cena['modelo'], 'nome': f'Checklist {SEGREDO}', 'versao': 1,
                               'copia': False} and 'versão 1' in antigo
    assert [b['nome'] for b in d['biblioteca']] == re.findall(
        r'<option value="\d+">([^<]+)</option>', antigo.split('id="copiar"')[1].split('</select>')[0])
    [r] = d['rotas']
    assert f"{r['turno']} · {r['inicio']} às {r['fim']} · {r['atividades']} atividade(s)" in antigo
    assert d['pode_montar'] and d['ve_estrutura'] and d['links']['estrutura'] == f'/novo/cadastros/locais/{a}'
    assert d['dias'][0] == ['1', 'seg'] and len(d['dias']) == 7

    d = c.get('/api/v1/rotas/biblioteca').get_json()
    antigo = _texto(c.get('/rotas/biblioteca').get_data(as_text=True))
    assert [m['id'] for m in d['modelos']] == [
        int(x) for x in re.findall(r'href="/rotas/modelos/(\d+)"', antigo)]
    [p] = [x for x in d['rotas_prontas'] if x['id'] == cena['pronta']]
    assert f"{p['ambientes']} tipo(s) de ambiente · {p['inicio']} às {p['fim']}" in antigo
    assert p['segmento'] == 'Escritório' and d['pode_montar']


def test_rotas_prontas_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    d = c.get(f"/api/v1/rotas/biblioteca/rotas/{cena['pronta']}").get_json()
    antigo = c.get(f"/rotas/biblioteca/rotas/{cena['pronta']}").get_data(as_text=True)
    assert d['modelo']['nome'] == 'Rota pronta de teste' and d['modelo']['dias_semana'] == '12345'
    assert [ln['ambiente'] for ln in d['linhas']] == re.findall(r'name="ambiente" maxlength="120" value="([^"]*)"', antigo)
    assert d['linhas'][0]['quantidade'] == 2 and d['linhas'][-1] == {
        'setor': '', 'ambiente': '', 'checklist_id': None, 'horarios': '', 'quantidade': 1,
        'tempo_previsto_min': ''}
    assert [m['nome'] for m in d['checklists']] == ['Checklist da biblioteca']
    d = c.get('/api/v1/rotas/biblioteca/rotas/nova').get_json()
    assert d['modelo'] is None and len(d['linhas']) == 3

    a = cena['local']
    d = c.get(f"/api/v1/rotas/locais/{a}/rota-pronta?modelo={cena['pronta']}").get_json()
    antigo = _texto(c.get(f"/rotas/locais/{a}/rota-pronta?modelo={cena['pronta']}").get_data(as_text=True))
    assert [ln['ambiente'] for ln in d['linhas']] == ['Banheiro 1', 'Banheiro 2']
    assert f"Ambientes ({len(d['linhas'])})" in antigo
    assert [o['id'] for o in d['opcoes']] == [int(x) for x in re.findall(r'<option value="(\d+)"', antigo)]
    d = c.get(f'/api/v1/rotas/locais/{a}/rota-pronta?modelo=xpto').get_json()
    assert d['modelo'] is None and d['linhas'] == []


def test_checklist_traz_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    d = c.get(f"/api/v1/rotas/modelos/{cena['modelo']}").get_json()
    antigo = _texto(c.get(f"/rotas/modelos/{cena['modelo']}").get_data(as_text=True))
    assert f"Versão publicada: 1, em {d['versao']['publicada_em']}." in antigo
    assert d['versao']['materiais'] == 'Pano' and d['versao']['epi'] == 'Luva'
    assert [it['texto'] for it in d['itens']] == [f'Pergunta {SEGREDO}', 'Quantos rolos?']
    assert [it['codigo'] for it in d['itens']] == re.findall(r'name="codigo" value="([^"]+)"', antigo)
    assert d['itens'][1]['minimo'] == re.findall(r'name="minimo" value="([^"]*)"', antigo)[1]
    assert d['itens'][0]['problema_se'] == 'nao' and d['itens'][0]['obrigatorio']
    assert d['linhas_em_branco'] == len(re.findall(r'name="texto"', antigo)) - len(d['itens'])
    [doc] = d['documentos']
    assert f'href="{doc["url"]}"' in antigo and doc['enviado_em'] in antigo
    assert d['modelo']['local'] == {'id': cena['local'], 'nome': LOCAL_A}
    assert [k for k, _ in d['tipos']] == re.findall(r'<option value="([a-z_]+)"', antigo.split('id="ti0"')[1].split('</select>')[0])
    d = c.get(f"/api/v1/rotas/modelos/{cena['biblioteca']}").get_json()
    assert d['modelo']['local'] is None and d['pode_montar']


def test_rota_feriados_dia_e_execucao_trazem_os_dados_da_tela_antiga(app_module, cena, auth_client):
    c = auth_client
    a = cena['local']
    d = c.get(f"/api/v1/rotas/{cena['rota']}").get_json()
    antigo = _texto(c.get(f"/rotas/{cena['rota']}").get_data(as_text=True))
    r = d['rota']
    assert f"{r['turno']} · {r['inicio']} às {r['fim']} · tolerância de {r['tolerancia_min']} min" in antigo
    [it] = d['itens']
    assert it['ponto'] == 'Banheiro masculino 2º andar · Porta do banheiro'
    assert 'hoje: ' + ', '.join(it['hoje']) in antigo
    assert [p['id'] for p in d['pessoas']] == [
        int(x) for x in re.findall(r'<option value="(\d+)">', antigo.split('id="epes"')[1].split('</select>')[0])]
    [e] = d['escalas']
    assert f"{e['nome']} seg, ter, qua, qui, sex · desde {e['desde']}" in re.sub(r'(\s*<[^>]+>\s*)+', ' ', antigo)
    assert d['links']['estrutura'] == f'/novo/cadastros/locais/{a}' and d['hoje'] == tempo.hoje().isoformat()

    d = c.get(f'/api/v1/rotas/locais/{a}/feriados?ano=2030').get_json()
    antigo = _texto(c.get(f'/rotas/locais/{a}/feriados?ano=2030').get_data(as_text=True))
    assert d['ano'] == 2030 and 'Feriados de 2030' in antigo
    assert [x['data'] for x in d['lista']] == re.findall(r'<strong class="nx-num">([\d/]+)</strong>', antigo)
    assert c.get(f'/api/v1/rotas/locais/{a}/feriados?ano=xx').get_json()['ano'] == tempo.hoje().year
    d = c.get(f'/api/v1/rotas/locais/{a}/feriados').get_json()
    assert [x for x in d['lista'] if x['id'] == cena['feriado']][0]['nome'] == f'Feriado {SEGREDO}'

    d = c.get(f'/api/v1/rotas/locais/{a}/dia').get_json()
    antigo = _texto(c.get(f'/rotas/locais/{a}/dia').get_data(as_text=True))
    assert d['data'] == tempo.hoje().isoformat()
    assert f"{d['aderencia']['no_prazo']} / {d['aderencia']['base']}" in antigo
    [t] = [x for x in d['tarefas'] if x['execucao']]
    ex = t['execucao']
    assert ex['id'] == cena['execucao'] and ex['sem_sinal'] and ex['nao_conformes'] == 1
    assert f"{ex['pessoa']} · {ex['inicio']}–{ex['fim']} · hora do celular · 1 não conforme(s)" in antigo
    [o] = d['ocorrencias']
    assert o['titulo'] in antigo and o['texto'] == f'Aviso {SEGREDO}' and d['pode_atender']

    d = c.get(f"/api/v1/rotas/execucoes/{cena['execucao']}").get_json()
    antigo = _texto(c.get(f"/rotas/execucoes/{cena['execucao']}").get_data(as_text=True))
    assert [x['texto'] for x in d['respostas']] == [f'Pergunta {SEGREDO}']
    assert f"{d['respostas'][0]['texto']}: <strong>{d['respostas'][0]['resposta']}</strong>" in antigo
    assert d['execucao']['observacao'] == 'Tudo certo' and d['execucao']['lido_em'] in antigo
    [nc] = d['nao_conformidades']
    assert f"NC-{nc['id']}" in antigo
    # O chamado da não conformidade abre na tela nova (Fase 4a).
    assert (f'href="{nc["chamado"].removeprefix("/novo")}"' in antigo and nc['chamado'].startswith('/novo/chamados/')) \
        if nc['chamado'] else ('Abrir chamado' in antigo)
    [f] = d['fotos']
    assert f['rotulo'] == 'Depois' and f'href="{f["url"]}"' in antigo
    assert d['pode_corrigir'] and [i['codigo'] for i in d['itens']] == re.findall(r'name="r_([^"]+)"', antigo)
    assert d['execucao']['dia'] in antigo


# ── Os envios: a mesma ação das telas antigas ─────────────────────────────

def test_checklists_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.rotas.models import ChecklistDocumento, ChecklistModelo
    c = auth_client
    a = cena['local']
    sufixo = uuid.uuid4().hex[:6]
    # Criar no local: vai para o checklist novo (sem recado), nas duas.
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/modelos', data={'nome': f'CK antigo {sufixo}'})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/modelos', data={'nome': f'CK novo {sufixo}'})
    assert rec == j['recados'] == [] and j['destino'] == '/novo' + d1.replace(
        d1.rsplit('/', 1)[1], j['destino'].rsplit('/', 1)[1])
    m1, m2 = int(d1.rsplit('/', 1)[1]), int(j['destino'].rsplit('/', 1)[1])
    _, _, rec = _antiga(c, f'/rotas/locais/{a}/modelos', data={'nome': ''})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/modelos', data={'nome': ''})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == f'/novo/rotas/locais/{a}'
    # Copiar da biblioteca.
    with app_module.app.app_context():
        from facilities.rotas import servico as s
        lib2 = s.criar_modelo(None, {'nome': 'Outro da biblioteca'}, None)
        s.publicar(lib2, s.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]), {}, None)
        db.session.commit()
        lib2 = lib2.id
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/copiar', data={'modelo_id': cena['biblioteca']})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/copiar', json={'modelo_id': lib2})
    _mesmo_recado(rec, j['recados'], [('Checklist da biblioteca', 'Outro da biblioteca')])
    assert j['destino'] == '/novo' + d1
    _, _, rec = _antiga(c, f'/rotas/locais/{a}/copiar', data={'modelo_id': lib2})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/copiar', data={'modelo_id': cena['biblioteca']})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'].replace('Outro', 'Checklist')
    # Publicar: com a foto de referência (o arquivo vai pela mesma ação).
    from tests.test_rotas_servico import _png
    form = lambda: {'texto': ['Pia limpa?', ''], 'tipo': ['sim_nao', 'sim_nao'], 'opcoes': ['', ''],  # noqa: E731
                    'minimo': ['', ''], 'maximo': ['', ''], 'problema_se': ['nao', ''],
                    'mostrar_se': ['', ''], 'codigo': ['', ''], 'ordem': ['1', ''],
                    'como_fazer': ['Esfregue', ''], 'foto_ref': ['', ''], 'obrigatorio': ['0'],
                    'descricao': 'Resumo', 'materiais': 'Pano', 'exige_foto_antes': '1',
                    'foto_ref_0': (io.BytesIO(_png()), 'ref.png')}
    _, d1, rec = _antiga(c, f'/rotas/modelos/{m1}', data=form(), content_type='multipart/form-data')
    r, j = _nova(c, f'/api/v1/rotas/modelos/{m2}', data=form(), content_type='multipart/form-data')
    _mesmo_recado(rec, j['recados'])
    assert j['recados'][0]['texto'].startswith('Versão 1 publicada') and j['destino'] == '/novo' + d1.replace(str(m1), str(m2))
    r, j = _nova(c, f'/api/v1/rotas/modelos/{m2}', data={'texto': ['']})
    _, _, rec = _antiga(c, f'/rotas/modelos/{m1}', data={'texto': ['']})
    assert r.status_code == 400 and j['error'] == rec[0]['texto']
    with app_module.app.app_context():
        from facilities.rotas import servico as s
        x, y = db.session.get(ChecklistModelo, m1), db.session.get(ChecklistModelo, m2)
        ix, iy = s.itens_da_versao(x.versao_atual), s.itens_da_versao(y.versao_atual)
        assert [(i['texto'], i['como_fazer'], i['obrigatorio'], bool(i.get('foto_ref'))) for i in ix] == \
            [(i['texto'], i['como_fazer'], i['obrigatorio'], bool(i.get('foto_ref'))) for i in iy]
        assert iy[0]['foto_ref'] and (x.descricao, x.exige_foto_antes, x.versao_atual.materiais) == \
            (y.descricao, y.exige_foto_antes, y.versao_atual.materiais)
    # POP/FIT: guardar, mostrar ao cliente, retirar.
    pdf = lambda: {'arquivo': (io.BytesIO(b'%PDF-1.4 teste'), 'pop.pdf')}  # noqa: E731
    _, _, rec = _antiga(c, f'/rotas/modelos/{m1}/documentos', data=pdf(), content_type='multipart/form-data')
    r, j = _nova(c, f'/api/v1/rotas/modelos/{m2}/documentos', data=pdf(), content_type='multipart/form-data')
    _mesmo_recado(rec, j['recados'])
    ruim = {'arquivo': (io.BytesIO(b'nada'), 'pop.exe')}
    _, _, rec = _antiga(c, f'/rotas/modelos/{m1}/documentos', data=dict(ruim), content_type='multipart/form-data')
    r, j = _nova(c, f'/api/v1/rotas/modelos/{m2}/documentos', data={'arquivo': (io.BytesIO(b'nada'), 'pop.exe')},
                 content_type='multipart/form-data')
    assert r.status_code == 400 and j['error'] == rec[0]['texto']
    with app_module.app.app_context():
        d1, d2 = (ChecklistDocumento.query.filter_by(modelo_id=x).one().id for x in (m1, m2))
    for acao in ('cliente', 'interno', 'retirar'):
        _, _, rec = _antiga(c, f'/rotas/documentos/{d1}/{acao}')
        r, j = _nova(c, f'/api/v1/rotas/documentos/{d2}/{acao}')
        _mesmo_recado(rec, j['recados'])
        assert j['destino'] == f'/novo/rotas/modelos/{m2}'
    assert c.post(f'/api/v1/rotas/documentos/{d2}/xpto').status_code == 404 == \
        c.post(f'/rotas/documentos/{d1}/xpto').status_code
    with app_module.app.app_context():
        x, y = db.session.get(ChecklistDocumento, d1), db.session.get(ChecklistDocumento, d2)
        assert (x.is_active, x.visivel_cliente) == (y.is_active, y.visivel_cliente) == (False, False)


def test_biblioteca_e_rotas_prontas_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.rotas.models import Rota, RotaModelo
    c = auth_client
    _, d1, rec = _antiga(c, '/rotas/biblioteca/modelos-prontos')
    r, j = _nova(c, '/api/v1/rotas/biblioteca/modelos-prontos')
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Os modelos prontos já estavam na biblioteca.'}]
    assert j['destino'] == '/novo' + d1 == '/novo/rotas/biblioteca'
    r, j = _nova(c, '/api/v1/rotas/biblioteca', data={'nome': 'Checklist novo da biblioteca'})
    assert j['destino'].startswith('/novo/rotas/modelos/') and j['recados'] == []
    _, _, rec = _antiga(c, '/rotas/biblioteca', data={'nome': ''})
    r, j = _nova(c, '/api/v1/rotas/biblioteca', data={'nome': ''})
    assert r.status_code == 400 and j['error'] == rec[0]['texto']
    # Rota pronta nova e editada.
    form = {'turno': 'Diurno', 'hora_inicio': '07:00', 'hora_fim': '15:00', 'segmento': 'Loja',
            'dias_semana': ['1', '2'], 'setor': ['Loja', ''], 'ambiente': ['Vitrine', ''],
            'checklist_id': [str(cena['biblioteca']), ''], 'horarios': ['09:00', ''],
            'quantidade': ['1', '1']}
    _, d1, rec = _antiga(c, '/rotas/biblioteca/rotas/nova', data={**form, 'nome': 'Pronta antiga'})
    r, j = _nova(c, '/api/v1/rotas/biblioteca/rotas/nova', data={**form, 'nome': 'Pronta nova'})
    _mesmo_recado(rec, j['recados'], [('antiga', 'nova')])
    with app_module.app.app_context():
        x, y = (RotaModelo.query.filter_by(nome=n).one() for n in ('Pronta antiga', 'Pronta nova'))
        assert (x.segmento, x.dias_semana, len(x.itens), x.itens[0].horarios) == \
            (y.segmento, y.dias_semana, len(y.itens), y.itens[0].horarios)
        p1, p2 = x.id, y.id
    assert d1 == f'/rotas/biblioteca/rotas/{p1}' and j['destino'] == f'/novo/rotas/biblioteca/rotas/{p2}'
    _, _, rec = _antiga(c, f'/rotas/biblioteca/rotas/{p1}', data={**form, 'nome': ''})
    r, j = _nova(c, f'/api/v1/rotas/biblioteca/rotas/{p2}', data={**form, 'nome': ''})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == f'/novo/rotas/biblioteca/rotas/{p2}'
    _, _, rec = _antiga(c, f'/rotas/biblioteca/rotas/{p1}/ativo')
    r, j = _nova(c, f'/api/v1/rotas/biblioteca/rotas/{p2}/ativo')
    _mesmo_recado(rec, j['recados'])
    # Aplicar a rota pronta no local: as linhas marcadas.
    a = cena['local']
    aplicar = {'nome': 'Aplicada', 'turno': 'Diurno', 'hora_inicio': '06:00', 'hora_fim': '18:00',
               'tolerancia_min': '30', 'dias_semana': ['1', '2', '3'], 'incluir': ['0'],
               'setor': ['Sanitários', 'Sanitários'], 'ambiente': ['Banheiro 1', 'Banheiro 2'],
               'checklist_id': [str(cena['biblioteca'])] * 2, 'horarios': ['08:00', '08:00']}
    _, d1, rec = _antiga(c, f"/rotas/locais/{a}/rota-pronta/{cena['pronta']}", data={**aplicar, 'nome': 'Aplicada antiga'})
    r, j = _nova(c, f"/api/v1/rotas/locais/{a}/rota-pronta/{cena['pronta']}", data={**aplicar, 'nome': 'Aplicada nova'})
    # O mesmo recado (as contagens de "novos neste local" mudam: a segunda
    # aplicação reaproveita os ambientes da primeira).
    def sem_novos(t):
        return re.sub(r'Novos neste local: [^.]+\.', '', t)
    assert [(x['tipo'], sem_novos(x['texto']).replace('nova', 'antiga')) for x in j['recados']] == \
        [(x['tipo'], sem_novos(x['texto'])) for x in rec]
    with app_module.app.app_context():
        x, y = (Rota.query.filter_by(client_id=a, nome=n).one() for n in ('Aplicada antiga', 'Aplicada nova'))
        assert (x.dias_semana, len(x.itens), x.presencas_por_turno) == (y.dias_semana, len(y.itens), y.presencas_por_turno)
        assert j['destino'] == f'/novo/rotas/{y.id}' and d1 == f'/rotas/{x.id}'
    _, d1, rec = _antiga(c, f"/rotas/locais/{a}/rota-pronta/{cena['pronta']}", data={**aplicar, 'incluir': []})
    r, j = _nova(c, f"/api/v1/rotas/locais/{a}/rota-pronta/{cena['pronta']}", data={**aplicar, 'incluir': []})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == '/novo' + d1
    with app_module.app.app_context():
        assert db.session.get(RotaModelo, p2).is_active is False


def test_planilha_como_na_tela_antiga(app_module, cena):
    from facilities.rotas.models import Rota
    c = cena['gerente']
    a = cena['local']
    url = f'/rotas/locais/{a}/importar-plano'
    antigo = c.post(url, data={'arquivo': (io.BytesIO(_planilha()), 'PLA_TF.xlsx')},
                    content_type='multipart/form-data')
    assert antigo.status_code == 200
    antigo = _texto(antigo.get_data(as_text=True))
    r, j = _nova(c, '/api/v1' + url, data={'arquivo': (io.BytesIO(_planilha()), 'PLA_TF.xlsx')},
                 content_type='multipart/form-data')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    p = j['previa']
    assert j['chave'].startswith(f'planos/{a}/') and j['ja_existem'] == []
    assert f"Blocos ({len(p['blocos'])})" in antigo and f"Rotas ({len(p['rotas'])})" in antigo
    assert f"O que não entendi ou ajustei ({len(p['avisos'])})" in antigo
    assert [x['nome'] for x in p['rotas']] == re.findall(r'<div class="fw-semibold">([^<]+?)(?: <span|</div>)', antigo)
    assert 'Responsável: ROSA' in antigo and any(x['responsavel'] == 'ROSA' for x in p['rotas'])
    # A recusa: a mesma frase.
    _, d1, rec = _antiga(c, url, data={})
    r, j2 = _nova(c, '/api/v1' + url, data={})
    assert r.status_code == 400 and j2['error'] == rec[0]['texto'] and j2['destino'] == '/novo' + d1
    # Criar: o mesmo recado e as mesmas rotas.
    r, j3 = _nova(c, '/api/v1' + url + '/criar', data={'chave': j['chave']})
    assert j3['recados'][0]['texto'].startswith('Plano importado: 8 rota(s)')
    assert j3['destino'] == f'/novo/rotas/locais/{a}'
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=a).count() == 9
    r, j3 = _nova(c, '/api/v1' + url + '/criar', data={'chave': j['chave']})
    _, _, rec = _antiga(c, url + '/criar', data={'chave': j['chave']})
    assert r.status_code == 400 and j3['error'] == rec[0]['texto'] and 'Já existe neste local' in j3['error']
    r, j3 = _nova(c, '/api/v1' + url + '/criar', data={'chave': 'xpto'})
    assert r.status_code == 400 and j3['error'] == 'A prévia venceu. Envie a planilha de novo.'


def test_rota_escala_e_feriados_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.rotas.models import Feriado, Rota, RotaEscala, RotaItem
    c = auth_client
    a = cena['local']
    form = {'turno': '1º Turno', 'hora_inicio': '06:00', 'hora_fim': '14:00', 'tolerancia_min': '20',
            'dias_semana': ['1', '3'], 'feriado_no_form': '1'}
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/rotas', data={**form, 'nome': 'Rota antiga'})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/rotas', json={**form, 'nome': 'Rota nova'})
    _mesmo_recado(rec, j['recados'])
    with app_module.app.app_context():
        x, y = (Rota.query.filter_by(client_id=a, nome=n).one() for n in ('Rota antiga', 'Rota nova'))
        campos = ('turno', 'hora_inicio', 'hora_fim', 'tolerancia_min', 'dias_semana', 'funciona_em_feriado')
        assert [getattr(x, k) for k in campos] == [getattr(y, k) for k in campos]
        assert y.funciona_em_feriado is False
        r1, r2 = x.id, y.id
    assert d1 == f'/rotas/{r1}' and j['destino'] == f'/novo/rotas/{r2}'
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/rotas', data={**form, 'nome': 'Sem dia', 'dias_semana': []})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/rotas', data={**form, 'nome': 'Sem dia', 'dias_semana': []})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == '/novo' + d1
    # Editar a rota.
    _, _, rec = _antiga(c, f'/rotas/{r1}', data={**form, 'nome': 'Rota antiga', 'tolerancia_min': '45'})
    r, j = _nova(c, f'/api/v1/rotas/{r2}', data={**form, 'nome': 'Rota nova', 'tolerancia_min': '45'})
    _mesmo_recado(rec, j['recados'])
    # Atividades: uma, várias e editar; tirar e voltar.
    with app_module.app.app_context():
        from facilities.cadastros import servico as cad
        from facilities.cadastros.models import Ambiente
        amb = db.session.get(Ambiente, cena['ambiente'])
        outro = cad.salvar_ponto(fabrica.local(), None, {'nome': 'Pia', 'ambiente_id': amb.id}, None)
        db.session.commit()
        outro = outro.id
    item = {'modelo_id': str(cena['modelo']), 'horarios': '07:00, 09:00', 'tempo_previsto_min': '15'}
    _, _, rec = _antiga(c, f'/rotas/{r1}/itens', data={**item, 'ponto_id': [str(cena['ponto']), str(outro)]})
    r, j = _nova(c, f'/api/v1/rotas/{r2}/itens', data={**item, 'ponto_id': [str(cena['ponto']), str(outro)]})
    _mesmo_recado(rec, j['recados'])
    assert j['recados'][0]['texto'].startswith('2 pontos incluídos')
    _, _, rec = _antiga(c, f'/rotas/{r1}/itens', data={**item, 'ponto_id': str(cena['ponto']), 'horarios': '99:99'})
    r, j = _nova(c, f'/api/v1/rotas/{r2}/itens', data={**item, 'ponto_id': str(cena['ponto']), 'horarios': '99:99'})
    assert r.status_code == 400 and j['error'] == rec[0]['texto']
    with app_module.app.app_context():
        i1, i2 = (RotaItem.query.filter_by(rota_id=x).order_by(RotaItem.id).first().id for x in (r1, r2))
    _, _, rec = _antiga(c, f'/rotas/{r1}/itens/{i1}', data={**item, 'ponto_id': str(cena['ponto']), 'horarios': '08:00'})
    r, j = _nova(c, f'/api/v1/rotas/{r2}/itens/{i2}', data={**item, 'ponto_id': str(cena['ponto']), 'horarios': '08:00'})
    _mesmo_recado(rec, j['recados'])
    for ativo in ('0', '1', '0'):
        _, _, rec = _antiga(c, f'/rotas/{r1}/itens/{i1}', data={'ativo': ativo})
        r, j = _nova(c, f'/api/v1/rotas/{r2}/itens/{i2}', data={'ativo': ativo})
        _mesmo_recado(rec, j['recados'])
    assert c.post(f'/api/v1/rotas/{r2}/itens/{i1}', data={'ativo': '1'}).status_code == 404 == \
        c.post(f'/rotas/{r2}/itens/{i1}', data={'ativo': '1'}).status_code
    # Escala: escalar e encerrar.
    esc = {'user_id': str(cena['enc']), 'data_inicio': tempo.hoje().isoformat(), 'dias_semana': ['1']}
    _, _, rec = _antiga(c, f'/rotas/{r1}/escalas', data=esc)
    r, j = _nova(c, f'/api/v1/rotas/{r2}/escalas', data=esc)
    _mesmo_recado(rec, j['recados'])
    assert j['recados'][0]['texto'] == 'Encarregada Rotina escalado(a) nesta rota.'
    with app_module.app.app_context():
        e1, e2 = (RotaEscala.query.filter_by(rota_id=x).one().id for x in (r1, r2))
    _, _, rec = _antiga(c, f'/rotas/{r1}/escalas/{e1}/encerrar')
    r, j = _nova(c, f'/api/v1/rotas/{r2}/escalas/{e2}/encerrar')
    _mesmo_recado(rec, j['recados'])
    # Desativar a rota.
    _, _, rec = _antiga(c, f'/rotas/{r1}/ativo', data={'ativo': '0'})
    r, j = _nova(c, f'/api/v1/rotas/{r2}/ativo', data={'ativo': '0'})
    _mesmo_recado(rec, j['recados'])
    with app_module.app.app_context():
        def retrato(rid):
            rr = db.session.get(Rota, rid)
            return (rr.is_active, rr.tolerancia_min,
                    sorted((i.ponto_id, i.horarios, i.is_active, i.tempo_previsto_min) for i in rr.itens),
                    [(e.user_id, e.is_active, e.dias_semana) for e in rr.escalas])
        assert retrato(r1) == retrato(r2) and retrato(r2)[0] is False
    # Feriados: cadastrar, recusar repetido, remover.
    ano = tempo.hoje().year + 1
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/feriados', data={'data': f'{ano}-03-10', 'nome': 'Fer antigo'})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/feriados', data={'data': f'{ano}-03-11', 'nome': 'Fer novo'})
    assert [x['texto'].split(' (')[0] for x in j['recados']] == ['Fer novo'] and rec[0]['texto'].startswith('Fer antigo (10/03/')
    assert j['destino'] == '/novo' + d1 == f'/novo/rotas/locais/{a}/feriados?ano={ano}'
    _, _, rec = _antiga(c, f'/rotas/locais/{a}/feriados', data={'data': f'{ano}-03-11', 'nome': 'X'})
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/feriados', data={'data': f'{ano}-03-11', 'nome': 'X'})
    assert r.status_code == 400 and j['error'] == rec[0]['texto']
    with app_module.app.app_context():
        f1, f2 = (Feriado.query.filter_by(client_id=a, nome=n).one().id for n in ('Fer antigo', 'Fer novo'))
    _, d1, rec = _antiga(c, f'/rotas/locais/{a}/feriados/{f1}/remover')
    r, j = _nova(c, f'/api/v1/rotas/locais/{a}/feriados/{f2}/remover')
    _mesmo_recado(rec, j['recados'])
    assert j['destino'] == '/novo' + d1
    with app_module.app.app_context():
        assert not Feriado.query.filter(Feriado.id.in_((f1, f2))).count()


def test_acompanhamento_como_na_tela_antiga(app_module, cena, auth_client):
    from app import db
    from facilities.rotas.models import Execucao, NaoConformidade, OcorrenciaPublica
    c = auth_client
    ex = cena['execucao']
    codigo = c.get(f'/api/v1/rotas/execucoes/{ex}').get_json()['itens'][0]['codigo']
    # Corrigir: a recusa (motivo curto) e a correção.
    _, d1, rec = _antiga(c, f'/rotas/execucoes/{ex}/corrigir', data={f'r_{codigo}': 'sim', 'motivo': 'x'})
    r, j = _nova(c, f'/api/v1/rotas/execucoes/{ex}/corrigir', data={f'r_{codigo}': 'sim', 'motivo': 'x'})
    assert r.status_code == 400 and j['error'] == rec[0]['texto'] and j['destino'] == '/novo' + d1
    r, j = _nova(c, f'/api/v1/rotas/execucoes/{ex}/corrigir', json={f'r_{codigo}': 'sim', 'motivo': 'Errei a resposta'})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Correção registrada. A resposta original continua na trilha.'}]
    d = c.get(f'/api/v1/rotas/execucoes/{ex}').get_json()
    assert d['respostas'][0] == {'codigo': codigo, 'texto': f'Pergunta {SEGREDO}', 'resposta': 'sim',
                                 'corrigida': True, 'original': 'nao'}
    assert d['correcoes'][0]['motivo'] == 'Errei a resposta'
    antigo = _texto(c.get(f'/rotas/execucoes/{ex}').get_data(as_text=True))
    assert '(corrigido; original: nao)' in antigo and d['correcoes'][0]['quando'] in antigo
    # A não conformidade vira chamado: o destino é o chamado (na tela nova
    # desde a Fase 4a; a antiga continua indo à antiga).
    r, j = _nova(c, f"/api/v1/rotas/nao-conformidades/{cena['nc']}/chamado")
    with app_module.app.app_context():
        ch = db.session.get(NaoConformidade, cena['nc']).chamado_id
    assert ch and j['destino'] == f'/novo/chamados/{ch}' and j['recados'] == []
    d = c.get(f'/api/v1/rotas/execucoes/{ex}').get_json()
    assert d['nao_conformidades'][0]['chamado'] == f'/novo/chamados/{ch}'
    assert f'href="/chamados/{ch}"' in c.get(f'/rotas/execucoes/{ex}').get_data(as_text=True)
    # A ocorrência do público: resolvida pelo site (a volta é o dia de hoje,
    # como na antiga).
    r, j = _nova(c, f"/api/v1/rotas/ocorrencias/{cena['ocorrencia']}/resolver", data={'resolucao': 'Feito'})
    assert j['recados'] == [{'tipo': 'success', 'texto': 'Ocorrência resolvida.'}]
    assert j['destino'] == f"/novo/rotas/locais/{cena['local']}/dia"
    _, _, rec = _antiga(c, f"/rotas/ocorrencias/{cena['ocorrencia']}/resolver", data={'resolucao': 'x'})
    r, j = _nova(c, f"/api/v1/rotas/ocorrencias/{cena['ocorrencia']}/resolver", data={'resolucao': 'x'})
    _mesmo_recado(rec, j['recados'])
    with app_module.app.app_context():
        oc = db.session.get(OcorrenciaPublica, cena['ocorrencia'])
        assert oc.status == 'resolvida' and oc.resolucao == 'Feito'
        assert db.session.get(Execucao, ex).correcoes


def test_quem_e_de_outro_local_nao_ve_nem_altera_a(app_module, cena):
    from app import db
    from facilities.rotas.models import ChecklistModelo, Rota
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'rot.plenob@trino.com', 'pleno', locais=[LOCAL_B])
    c = fabrica.entrar(app_module, 'rot.plenob@trino.com')
    a = cena['local']
    for url in (f'/api/v1/rotas/locais/{a}', f'/api/v1/rotas/locais/{a}/dia',
                f'/api/v1/rotas/locais/{a}/feriados', f'/api/v1/rotas/locais/{a}/rota-pronta',
                f'/api/v1/rotas/locais/{a}/importar-plano', f"/api/v1/rotas/{cena['rota']}",
                f"/api/v1/rotas/modelos/{cena['modelo']}", f"/api/v1/rotas/execucoes/{cena['execucao']}"):
        r = c.get(url)
        assert r.status_code in (403, 404) and r.is_json and SEGREDO not in r.get_data(as_text=True), url
    for url, dados in ((f"/api/v1/rotas/{cena['rota']}/ativo", {'ativo': '0'}),
                       (f"/api/v1/rotas/{cena['rota']}", {'nome': 'Invasão', 'turno': 'x'}),
                       (f'/api/v1/rotas/locais/{a}/modelos', {'nome': 'Invasão'}),
                       (f"/api/v1/rotas/modelos/{cena['modelo']}", {'texto': ['Invasão']}),
                       (f"/api/v1/rotas/documentos/{cena['documento']}/retirar", {}),
                       (f"/api/v1/rotas/locais/{a}/feriados/{cena['feriado']}/remover", {}),
                       (f"/api/v1/rotas/execucoes/{cena['execucao']}/corrigir", {'motivo': 'Invasão!'}),
                       (f"/api/v1/rotas/ocorrencias/{cena['ocorrencia']}/resolver", {'resolucao': 'x'})):
        r = c.post(url, data=dados)
        assert r.status_code in (403, 404) and r.is_json, url
    d = c.get('/api/v1/rotas/inicio').get_json()
    assert a not in [x['id'] for x in d['locais']]
    with app_module.app.app_context():
        assert db.session.get(Rota, cena['rota']).is_active
        assert not ChecklistModelo.query.filter_by(nome='Invasão').count()


def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):
    c = auth_client
    from facilities.telas.cadastros import nova
    assert nova('/rotas/locais/1') == '/novo/rotas/locais/1'
    assert nova('/rotas/documentos/1') == '/rotas/documentos/1'
    assert nova('/rotas/fotos/1') == '/rotas/fotos/1'
    assert nova('/rotas/referencias/1/abc') == '/rotas/referencias/1/abc'
    # Fase 4a: os chamados, as demandas e a preventiva também; as fotos e os
    # PDFs dos chamados continuam no servidor.
    assert nova('/chamados/1') == '/novo/chamados/1'
    assert nova('/chamados/anexos/1') == '/chamados/anexos/1'
    assert nova('/preventiva/locais/1') == '/novo/preventiva/locais/1'
    # Fase 4b: a equipe, os materiais e as visitas do local; a foto do pedido
    # de insumo e o aplicativo do supervisor continuam onde estão.
    assert nova('/equipes/locais/1') == '/novo/equipes/locais/1'
    assert nova('/equipes/locais/1/mes?m=2026-10') == '/novo/equipes/locais/1/mes?m=2026-10'
    assert nova('/visitas/locais/1') == '/novo/visitas/locais/1'
    assert nova('/materiais/') == '/novo/materiais/'
    assert nova('/materiais/pedidos') == '/novo/materiais/pedidos'
    assert nova('/materiais/pedidos/1/foto') == '/materiais/pedidos/1/foto'
    assert nova('/app/visitas/1') == '/app/visitas/1'
    assert nova('/app/materiais') == '/app/materiais'
    assert nova('/app/equipe') == '/app/equipe'
    # As telas antigas e o menu não mudam.
    assert 'href="/rotas/locais/' in c.get('/rotas/').get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert not any(u.startswith('/novo/rotas') for u in menu)
    # Os cadastros novos levam à rotina nova.
    a = cena['local']
    d = c.get(f'/api/v1/cadastros/novo-contrato/{a}/estrutura').get_json()
    assert d['links']['rotas'] == f'/novo/rotas/locais/{a}'
    assert d['links']['importar'] == f'/novo/rotas/locais/{a}/importar-plano'


# ── Correções dos defeitos da tela antiga achados na Fase 3b ─────────────

def _campos(html, acao):
    """Os campos do formulário que posta em ``acao``, como o navegador manda
    (nome → lista de valores, na ordem; caixa desmarcada não vai)."""
    from html.parser import HTMLParser

    class Leitor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.dentro, self.campos, self.select, self.opcao = False, {}, None, None

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == 'form' and a.get('action') == acao:
                self.dentro = True
            elif not self.dentro or 'disabled' in a:
                return
            elif tag == 'input' and a.get('name'):
                if a.get('type') in ('checkbox', 'radio') and 'checked' not in a:
                    return
                self.campos.setdefault(a['name'], []).append(a.get('value', ''))
            elif tag == 'textarea' and a.get('name'):
                self.campos.setdefault(a['name'], []).append('')
            elif tag == 'select' and a.get('name'):
                self.select, self.opcao = a['name'], None
            elif tag == 'option' and self.select:
                if self.opcao is None or 'selected' in a:
                    self.opcao = a.get('value', '')

        def handle_endtag(self, tag):
            if tag == 'form':
                self.dentro = False
            elif tag == 'select' and self.select:
                self.campos.setdefault(self.select, []).append(self.opcao or '')
                self.select = None

    leitor = Leitor()
    leitor.feed(html)
    assert leitor.campos, acao
    leitor.campos.pop('csrf_token', None)
    return leitor.campos


def test_salvar_e_aplicar_rota_pronta_mantem_o_tempo_previsto(app_module, cena, auth_client):
    """O formulário da rota pronta não tem campo para o tempo previsto: antes,
    salvar (ou aplicar no local) devolvia cada linha ao padrão do tipo de
    ambiente. Agora o tempo vai junto, nas duas telas."""
    from app import db
    from facilities.rotas.models import Rota, RotaModelo
    c, rmid = auth_client, cena['pronta']
    with app_module.app.app_context():
        db.session.get(RotaModelo, rmid).itens[0].tempo_previsto_min = 47
        db.session.commit()
    url = f'/rotas/biblioteca/rotas/{rmid}'
    form = _campos(c.get(url).get_data(as_text=True), url)
    assert form['tempo_previsto_min'][0] == '47'
    _antiga(c, url, data=form)
    with app_module.app.app_context():
        assert db.session.get(RotaModelo, rmid).itens[0].tempo_previsto_min == 47
    # A tela nova recebe o tempo nas linhas e manda de volta do mesmo jeito.
    d = c.get(f'/api/v1{url}').get_json()
    assert d['linhas'][0]['tempo_previsto_min'] == 47
    _nova(c, f'/api/v1{url}', data=form)
    with app_module.app.app_context():
        assert db.session.get(RotaModelo, rmid).itens[0].tempo_previsto_min == 47
    # Aplicar no local: a rota criada leva o tempo da linha.
    pagina = f"/rotas/locais/{cena['local']}/rota-pronta?modelo={rmid}"
    acao = f"/rotas/locais/{cena['local']}/rota-pronta/{rmid}"
    html = c.get(pagina).get_data(as_text=True)
    form = _campos(html, acao)
    assert form['tempo_previsto_min'] == ['47', '47']          # quantidade 2
    assert c.get(f'/api/v1{pagina}').get_json()['linhas'][0]['tempo_previsto_min'] == 47
    form['nome'] = ['Rota aplicada com tempo']
    _antiga(c, acao, data=form)
    with app_module.app.app_context():
        rota = Rota.query.filter_by(nome='Rota aplicada com tempo').one()
        assert [i.tempo_previsto_min for i in rota.itens] == [47, 47]


def test_resolver_ocorrencia_volta_para_o_dia_que_estava_aberto(app_module, cena, auth_client):
    """A ocorrência em aberto aparece em todos os dias; resolvida a partir de
    um dia passado, a tela volta para aquele dia (antes, ia para hoje)."""
    c, cid, oid = auth_client, cena['local'], cena['ocorrencia']
    ontem = (tempo.hoje() - timedelta(days=1)).isoformat()
    pagina = f'/rotas/locais/{cid}/dia?data={ontem}'
    acao = f'/rotas/ocorrencias/{oid}/resolver'
    form = _campos(c.get(pagina).get_data(as_text=True), acao)
    assert form['data'] == [ontem]
    _, destino, _ = _antiga(c, acao, data={**form, 'resolucao': 'Feito'})
    assert destino == f'/rotas/locais/{cid}/dia?data={ontem}'
    r, j = _nova(c, f'/api/v1{acao}', json={'resolucao': 'x', 'data': ontem})
    assert j['destino'] == f'/novo/rotas/locais/{cid}/dia?data={ontem}'
    # Sem o dia, ou com um dia que não é data: hoje, como antes.
    _, destino, _ = _antiga(c, acao, data={'resolucao': 'x', 'data': 'ontem'})
    assert destino == f'/rotas/locais/{cid}/dia'


def test_copiar_com_id_que_nao_e_numero_e_nao_encontrado(app_module, cena, auth_client):
    """Antes, ``modelo_id`` que não é número dava erro do servidor (500)."""
    for url in (f"/rotas/locais/{cena['local']}/copiar", f"/api/v1/rotas/locais/{cena['local']}/copiar"):
        assert auth_client.post(url, data={'modelo_id': 'abc'}).status_code == 404
