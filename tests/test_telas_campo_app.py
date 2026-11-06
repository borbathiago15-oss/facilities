"""O aplicativo de campo nas telas novas, Fase 1d: a equipe do dia, os
materiais e as visitas de supervisão (``/novo/app/equipe``,
``/novo/app/materiais``, ``/novo/app/visitas`` e ``/novo/app/visitas/<id>``).

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (``contexto_app_*``);
* a mesma porta, perfil a perfil;
* os envios: a MESMA ação da tela antiga — o mesmo estado no banco, o mesmo
  recado e a mesma recusa (400), com o endereço de volta já na tela nova; as
  fotos no próprio formulário;
* quem é de outro local não vê nem altera nada de A (e a varredura de
  isolamento cobre cada rota nova com id);
* dentro das telas novas, o início do campo, o painel de demandas, o chamado
  e as visitas do local levam às telas novas.
"""
import html as html_mod
import io
import re
import struct
import zlib
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS

LOCAL_A, LOCAL_B = CONTRATOS_SEMEADOS[0], CONTRATOS_SEMEADOS[1]
SEGREDO = 'CAMPO-1D-SECRETO-A'
MODULO = 'facilities.telas.campo_app'


def _texto(html):
    return html_mod.unescape(re.sub(r'\s+', ' ', html))


def _png():
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00\x0a\x78\x1e')) + bloco(b'IEND', b''))


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


def _confere(antigo, r, j):
    """O mesmo recado, o mesmo destino (abaixo de /novo) e, na recusa, 400
    com a mesma frase."""
    destino, recados = antigo
    assert j['recados'] == recados
    assert j['destino'] == '/novo' + destino, (j['destino'], destino)
    recusou = any(x['tipo'] == 'danger' for x in recados)
    assert r.status_code == (400 if recusou else 200), recados
    if recusou:
        assert j['error'] == recados[0]['texto']


@pytest.fixture()
def cena(app_module, auth_client):
    """Em A: duas funcionárias escaladas hoje (uma com login), um checklist
    de visita com pergunta condicional, número, escolha e foto no item, duas
    visitas abertas hoje (uma de outra supervisora) e uma feita; dois
    materiais, um chamado aberto e um pedido de insumo. Em B: um local com
    escala própria."""
    from app import Client, User, db
    from facilities.chamados import servico as chs
    from facilities.equipes import servico as eq
    from facilities.materiais import servico as mat
    from facilities.rotas import servico as s
    from facilities.visitas import servico as vis
    from facilities.visitas.models import Visita
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        a = ids['local']
        b = fabrica.local(LOCAL_B).id
        loc = db.session.get(Client, a)
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        enc = fabrica.pessoa(app_module, 'c1d.enc@trino.com', 'encarregado', locais=[LOCAL_A],
                             nome='Encarregada Campo')
        sup = fabrica.pessoa(app_module, 'c1d.sup@trino.com', 'supervisor', locais=[LOCAL_A],
                             nome='Supervisora Campo')
        outra = fabrica.pessoa(app_module, 'c1d.outra@trino.com', 'supervisor',
                               locais=[LOCAL_A], nome='Outra Supervisora')
        m = s.criar_modelo(a, {'nome': f'Checklist {SEGREDO}'}, None)
        s.publicar(m, s.normalizar_itens([
            {'texto': 'Uniforme completo?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao', 'codigo': 'uniforme'},
            {'texto': 'Qual peça faltou?', 'tipo': 'texto', 'codigo': 'peca',
             'mostrar_se': 'uniforme=nao', 'exige_foto': True},
            {'texto': 'Temperatura da câmara', 'tipo': 'numero', 'codigo': 'temp',
             'minimo': '0', 'maximo': '8'},
            {'texto': 'Estado do piso', 'tipo': 'escolha', 'codigo': 'piso',
             'opcoes': 'Limpo;Sujo'},
        ]), {}, None)
        rota = s.salvar_rota(loc, None, {'nome': f'Rota {SEGREDO}', 'turno': 'T1',
                                         'hora_inicio': '00:00', 'hora_fim': '23:59',
                                         'tolerancia_min': '60', 'dias_semana': '1234567'})
        ana = eq.salvar_funcionario(loc, None, {'nome': f'Ana {SEGREDO}', 'funcao': 'ASG',
                                                'user_id': str(enc)}, admin)
        mariana = eq.salvar_funcionario(loc, None, {'nome': 'Mariana Lima'}, admin)
        posto = eq.salvar_posto(loc, None, {'nome': 'Limpeza manhã', 'hora_inicio': '07:00',
                                            'hora_fim': '15:00', 'rota_id': str(rota.id)})
        posto2 = eq.salvar_posto(loc, None, {'nome': 'Portaria', 'hora_inicio': '06:00',
                                             'hora_fim': '18:00'})
        inicio = (tempo.hoje() - timedelta(days=20)).isoformat()
        esc = eq.salvar_escala(loc, {'funcionario_id': ana.id, 'posto_id': posto.id,
                                     'dias_semana': '1234567', 'data_inicio': inicio}, admin)
        esc2 = eq.salvar_escala(loc, {'funcionario_id': mariana.id, 'posto_id': posto2.id,
                                      'dias_semana': '1234567', 'data_inicio': inicio}, admin)
        db.session.flush()
        ontem = eq.registrar_presenca(admin, esc, tempo.hoje() - timedelta(days=1), 'faltou',
                                      '')
        # Em B: uma escala que ninguém de A pode ver.
        loc_b = db.session.get(Client, b)
        bia = eq.salvar_funcionario(loc_b, None, {'nome': 'Bia de B'}, admin)
        pb = eq.salvar_posto(loc_b, None, {'nome': 'Posto B', 'hora_inicio': '07:00',
                                           'hora_fim': '15:00'})
        esc_b = eq.salvar_escala(loc_b, {'funcionario_id': bia.id, 'posto_id': pb.id,
                                         'dias_semana': '1234567', 'data_inicio': inicio}, admin)
        prog = vis.salvar_programada(loc, None, {
            'nome': f'Visita {SEGREDO}', 'modelo_id': str(m.id), 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat(), 'supervisor_id': str(sup)}, admin)
        prog_outra = vis.salvar_programada(loc, None, {
            'nome': 'Visita da outra', 'modelo_id': str(m.id), 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat(), 'supervisor_id': str(outra)}, admin)
        prog_feita = vis.salvar_programada(loc, None, {
            'nome': 'Visita já feita', 'modelo_id': str(m.id), 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat()}, admin)
        db.session.flush()
        vis.gerar_visitas(tempo.hoje())
        feita = Visita.query.filter_by(programada_id=prog_feita.id).one()

        class Arquivo:
            filename = 'foto.png'

            def __init__(self):
                self.stream = io.BytesIO(_png())

            def read(self, *a):
                return self.stream.read(*a)

            def seek(self, *a):
                return self.stream.seek(*a)

            def tell(self):
                return self.stream.tell()
        vis.registrar(db.session.get(User, sup), feita,
                      {'uniforme': 'nao', 'peca': f'Bota {SEGREDO}', 'piso': 'Limpo'},
                      'Obs da visita', fotos={'livre': [Arquivo()], 'item:peca': [Arquivo()]})
        detergente = mat.salvar_material(None, {'nome': 'Detergente neutro', 'unidade': 'L',
                                                'preco_unitario': '12,90'})
        pano = mat.salvar_material(None, {'nome': 'Pano de chão', 'unidade': 'un'})
        mat.movimentar(admin, loc, {'material_id': str(detergente.id), 'quantidade': '10'},
                       'entrada')
        ch = chs.abrir(admin, a, f'Vazamento {SEGREDO}', descricao='Pinga')
        pedido = mat.pedir(db.session.get(User, enc), loc, {
            'material_id': str(pano.id), 'quantidade': '5', 'texto': f'Pedido {SEGREDO}'})
        db.session.commit()
        ids.update(local_b=b, enc=enc, sup=sup, outra=outra, modelo=m.id, rota=rota.id,
                   ana=ana.id, mariana=mariana.id, escala=esc.id, escala2=esc2.id,
                   escala_b=esc_b.id, falta_ontem=ontem.id,
                   visita=Visita.query.filter_by(programada_id=prog.id).one().id,
                   visita_outra=Visita.query.filter_by(programada_id=prog_outra.id).one().id,
                   feita=feita.id, chamado_feita=feita.chamado_id,
                   detergente=detergente.id, pano=pano.id, chamado=ch.id, pedido=pedido.id)
    return ids


# ── Login e porta ─────────────────────────────────────────────────────────

def _rotas_novas(app_module):
    for regra in app_module.app.url_map.iter_rules():
        modulo = getattr(app_module.app.view_functions[regra.endpoint], '__module__', '')
        if modulo != MODULO:
            continue
        caminho = regra.rule
        for arg in regra.arguments:
            caminho = caminho.replace(f'<int:{arg}>', '1')
        for m in sorted(regra.methods - {'HEAD', 'OPTIONS'}):
            yield m, caminho


def test_pede_login(app_module, client):
    rotas = list(_rotas_novas(app_module))
    assert len([1 for m, u in rotas if u.startswith('/api/v1/') and m == 'POST']) == 5
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
    ('/app/equipe', '/api/v1/campo/equipe'),
    ('/app/materiais', '/api/v1/campo/materiais'),
    ('/app/visitas', '/api/v1/campo/visitas'),
    ('/app/visitas/{visita}', '/api/v1/campo/visitas/{visita}'),
    ('/app/visitas/{feita}', '/api/v1/campo/visitas/{feita}'),
    ('/app/visitas/999999', '/api/v1/campo/visitas/999999'),
)

PAPEIS = ['master', 'visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
          'supervisor-de-b']


@pytest.mark.parametrize('papel', PAPEIS)
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):
    """O mesmo código de resposta na tela antiga, na página nova e na API."""
    base = papel.split('-')[0]
    locais = [LOCAL_B] if papel.endswith('de-b') else [LOCAL_A]
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'porta1d.{papel}@trino.com', base, locais=locais)
    c = fabrica.entrar(app_module, f'porta1d.{papel}@trino.com')
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
    de_a = not papel.endswith('de-b')
    gestao = base in ('master', 'gerente', 'pleno')
    assert (codigos['/app/equipe'] == 200) == (gestao or base == 'supervisor'), papel
    assert (codigos['/app/materiais'] == 200) == (base != 'visualizador'), papel
    visita = gestao or base == 'supervisor'
    assert (codigos['/app/visitas'] == 200) == visita, papel
    v = f"/app/visitas/{cena['visita']}"
    assert (codigos[v] == 200) == ((visita or base == 'visualizador') and de_a), papel
    assert codigos['/app/visitas/999999'] == 404


def test_o_cliente_do_portal_nao_entra(app_module, cena):
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    try:
        with app_module.app.app_context():
            fabrica.cliente(app_module, 'cliente.c1d@gl.com', cena['cliente'])
        c = fabrica.entrar_com_codigo(app_module, 'cliente.c1d@gl.com')
        for antiga, api in TELAS:
            antiga, api = antiga.format(**cena), api.format(**cena)
            r_antiga, r_api, r_nova = c.get(antiga), c.get(api), c.get('/novo' + antiga)
            assert r_antiga.status_code == r_api.status_code == r_nova.status_code == 403, antiga
            assert SEGREDO not in r_api.get_data(as_text=True)
    finally:
        app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False


# ── Os dados (os mesmos da tela antiga) ───────────────────────────────────

def test_a_equipe_traz_os_dados_da_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    d = sup.get('/api/v1/campo/equipe').get_json()
    antigo = sup.get('/app/equipe').get_data(as_text=True)
    texto = _texto(antigo)
    assert f"Equipe · {d['dia']}" in texto and d['amanha'] is None
    assert d['ontem'] == '/novo/app/equipe?data=' + (tempo.hoje() - timedelta(days=1)).isoformat()
    assert f'href="{d["ontem"].removeprefix("/novo")}"' in antigo
    assert [x['nome'] for x in d['locais']] == [LOCAL_A]
    [loc] = d['locais']
    assert [x['escala_id'] for x in loc['linhas']] == [
        int(x) for x in re.findall(r'id="escala-(\d+)"', antigo)]
    for linha in loc['linhas']:
        assert linha['detalhe'] in texto and linha['presenca'] is None
    assert d['situacoes'] == [['veio', 'Veio'], ['faltou', 'Faltou'], ['atrasou', 'Atrasou']]
    assert sorted(f['nome'] for f in loc['cobridores']) == sorted(['Mariana Lima', f'Ana {SEGREDO}'])
    # O dia de ontem: a falta, sem cobertura, com o formulário da cobertura.
    ontem = (tempo.hoje() - timedelta(days=1)).isoformat()
    d = sup.get(f'/api/v1/campo/equipe?data={ontem}').get_json()
    antigo = sup.get(f'/app/equipe?data={ontem}').get_data(as_text=True)
    assert d['amanha'] == f'/novo/app/equipe?data={tempo.hoje().isoformat()}'
    [ana] = [x for x in d['locais'][0]['linhas'] if x['escala_id'] == cena['escala']]
    assert ana['presenca'] == {'id': cena['falta_ontem'], 'situacao': 'faltou',
                               'rotulo': 'Faltou', 'cobertura': None}
    assert f'/app/equipe/presencas/{cena["falta_ontem"]}/cobertura' in antigo
    # Fora da janela: hoje, como a antiga.
    d = sup.get('/api/v1/campo/equipe?data=2001-01-01').get_json()
    assert d['data'] == tempo.hoje().isoformat()


def test_os_materiais_trazem_os_dados_da_tela_antiga(app_module, cena):
    enc = fabrica.entrar(app_module, 'c1d.enc@trino.com')
    d = enc.get('/api/v1/campo/materiais').get_json()
    antigo = _texto(enc.get('/app/materiais').get_data(as_text=True))
    assert [x['nome'] for x in d['locais']] == [LOCAL_A]
    assert [f"{m['nome']} ({m['unidade']})" for m in d['materiais']] == [
        'Detergente neutro (L)', 'Pano de chão (un)']
    for m in d['materiais']:
        assert f"{m['nome']} ({m['unidade']})" in antigo
    html = enc.get('/app/materiais').get_data(as_text=True)
    opcoes = html.split('id="cc"')[1].split('</select>')[0]
    assert [c['id'] for c in d['chamados']] == [int(x) for x in re.findall(r'value="(\d+)"', opcoes)]
    assert cena['chamado'] in [c['id'] for c in d['chamados']]
    for ch in d['chamados']:
        assert ch['rotulo'] in antigo
    assert [r['rotulo'] for r in d['rotas']] == [f'{LOCAL_A} · Rota {SEGREDO}']
    [p] = d['meus']
    assert p['resumo'] in antigo and p['detalhe'] in antigo
    assert '12,90' not in str(d)                       # quem consome não vê preço


def test_as_visitas_trazem_os_dados_da_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    d = sup.get('/api/v1/campo/visitas').get_json()
    antigo = sup.get('/app/visitas').get_data(as_text=True)
    # Só as que esperam por ela (a da outra supervisora não), na ordem da antiga.
    assert [v['url'] for v in d['visitas']] == [
        '/novo' + u for u in re.findall(r'href="(/app/visitas/\d+)"', antigo)]
    [v] = d['visitas']
    assert v['id'] == cena['visita'] and v['selo'] == 'hoje'
    assert f"{v['local']} · até {v['ate']}" in _texto(antigo)


def test_a_visita_aberta_traz_o_checklist_da_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    vid = cena['visita']
    d = sup.get(f'/api/v1/campo/visitas/{vid}').get_json()
    antigo = sup.get(f'/app/visitas/{vid}').get_data(as_text=True)
    texto = _texto(antigo)
    assert d['pode_fazer'] is True and d['visita']['ate'] in texto
    assert [i['codigo'] for i in d['itens']] == ['uniforme', 'peca', 'temp', 'piso']
    nomes = set(re.findall(r'name="(r_[^"]+|f_[^"]+|observacao)"', antigo))
    assert nomes == {'r_uniforme', 'r_peca', 'r_temp', 'r_piso', 'f_item:peca', 'f_livre',
                     'observacao'}
    peca = d['itens'][1]
    assert peca['mostrar_se'] == {'codigo': 'uniforme', 'valor': 'nao',
                                  'texto': 'Uniforme completo?'}
    assert 'Responda só se "Uniforme completo?" for "nao".' in texto
    assert peca['exige_foto'] is True and d['itens'][0]['obrigatorio'] is True
    temp = d['itens'][2]
    assert f"Aceitável: de {temp['minimo']} até {temp['maximo']}" in texto
    assert d['itens'][3]['opcoes'] == ['Limpo', 'Sujo']
    assert not d['exige_foto_antes'] and not d['exige_foto_depois']
    assert d['respostas'] == [] and d['fotos'] == []
    # A visita de outra supervisora: o aviso, sem o checklist.
    d = sup.get(f"/api/v1/campo/visitas/{cena['visita_outra']}").get_json()
    antigo = _texto(sup.get(f"/app/visitas/{cena['visita_outra']}").get_data(as_text=True))
    assert d['pode_fazer'] is False and d['itens'] == []
    assert f"Esta visita é de {d['visita']['supervisor']}." in antigo


def test_a_visita_feita_traz_as_respostas_e_as_fotos_da_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    d = sup.get(f"/api/v1/campo/visitas/{cena['feita']}").get_json()
    antigo = sup.get(f"/app/visitas/{cena['feita']}").get_data(as_text=True)
    texto = _texto(antigo)
    v = d['visita']
    assert v['status'] == 'feita' and v['quem_fez'] == 'Supervisora Campo'
    assert f"Feita por</b> {v['quem_fez']} · {v['feita_em']}</p>" in antigo
    assert v['n_nao_conformes'] == 1 and v['chamado']['numero'] in texto
    assert v['chamado']['url'] == f"/novo/chamados/{cena['chamado_feita']}"
    assert v['observacao'] == 'Obs da visita'
    assert [f['url'] for f in d['fotos']] == list(dict.fromkeys(
        re.findall(r'src="(/app/visitas/fotos/\d+)"', antigo)))
    assert d['fotos'][0]['legenda'] in texto
    for r in d['respostas']:
        assert r['texto'] in texto and r['valor'] in texto
    assert {r['codigo']: r['valor'] for r in d['respostas']}['temp'] == '—'
    assert d['itens'] == [] and d['pode_fazer'] is False


# ── Os envios (a MESMA ação da tela antiga) ───────────────────────────────

def _estado_da_equipe(app_module):
    from app import db
    from facilities.equipes.models import Cobertura, Presenca
    with app_module.app.app_context():
        db.session.expire_all()
        return (sorted((p.funcionario_id, p.data.isoformat(), p.situacao, p.observacao)
                       for p in Presenca.query.all()),
                sorted((c.presenca_id, c.funcionario_id, c.motivo) for c in Cobertura.query.all()))


def _apagar_presencas(app_module):
    from app import db
    from facilities.equipes.models import Cobertura, Presenca
    with app_module.app.app_context():
        Cobertura.query.delete()
        Presenca.query.delete()
        db.session.commit()


def test_presenca_e_cobertura_como_na_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    hoje = tempo.hoje().isoformat()
    casos = [{'escala_id': cena['escala'], 'data': hoje, 'situacao': 'faltou'},
             {'escala_id': cena['escala2'], 'data': hoje, 'situacao': 'atrasou',
              'observacao': 'ônibus'},
             {'escala_id': cena['escala'], 'data': hoje, 'situacao': 'xpto'},       # recusa
             {'escala_id': cena['escala'], 'data': '2001-01-01', 'situacao': 'veio'}]
    for dados in casos:
        _apagar_presencas(app_module)
        antigo = _antiga(sup, '/app/equipe/presenca', data=dados)
        estado = _estado_da_equipe(app_module)
        _apagar_presencas(app_module)
        r, j = _nova(sup, '/api/v1/campo/equipe/presenca', data=dados)
        _confere(antigo, r, j)
        assert _estado_da_equipe(app_module) == estado, dados
        assert j['destino'].startswith('/novo/app/equipe?data=') and '#escala-' in j['destino']
    # Escala que não existe: 404, como a antiga.
    assert sup.post('/app/equipe/presenca', data={'escala_id': '999999'}).status_code == 404
    r = sup.post('/api/v1/campo/equipe/presenca', data={'escala_id': '999999'})
    assert r.status_code == 404 and r.is_json
    # A cobertura (e a recusa: motivo curto; quem faltou cobre a si).
    from app import User, db
    from facilities.equipes import servico as eq
    from facilities.equipes.models import EscalaTrabalho
    for dados in ({'funcionario_id': cena['ana'], 'motivo': 'atestado'},
                  {'funcionario_id': cena['mariana'], 'motivo': 'x'},
                  {'funcionario_id': cena['mariana'], 'motivo': 'atestado médico'}):
        resultados = []
        for url in ('/app/equipe/presencas/{}/cobertura', '/api/v1/campo/equipe/presencas/{}/cobertura'):
            _apagar_presencas(app_module)
            with app_module.app.app_context():
                p = eq.registrar_presenca(db.session.get(User, cena['sup']),
                                          db.session.get(EscalaTrabalho, cena['escala']),
                                          tempo.hoje(), 'faltou', '')
                db.session.commit()
                prid = p.id
            if url.startswith('/app'):
                resultados.append(_antiga(sup, url.format(prid), data=dados))
            else:
                resultados.append(_nova(sup, url.format(prid), data=dados))
            estado = _estado_da_equipe(app_module)
            resultados.append([(c[1], c[2]) for c in estado[1]])
        (destino, recados), cob_antiga, (r, j), cob_nova = resultados
        assert j['recados'] == recados and cob_antiga == cob_nova, dados
        assert j['destino'].removeprefix('/novo') == destino
        assert r.status_code == (400 if recados[0]['tipo'] == 'danger' else 200)


def _estado_dos_materiais(app_module):
    from app import db
    from facilities.materiais.models import MovimentoEstoque, PedidoInsumo
    with app_module.app.app_context():
        db.session.expire_all()
        return (sorted((m.client_id, m.material_id, m.tipo, str(m.quantidade), m.user_id)
                       for m in MovimentoEstoque.query.all()),
                sorted((p.client_id, p.material_id or 0, p.texto or '', p.status,
                        bool(p.foto_key)) for p in PedidoInsumo.query.all()))


def _apagar_lancamentos(app_module, antes):
    """Volta o estoque e os pedidos ao que eram (o consumo e o pedido novos saem)."""
    from app import db
    from facilities.materiais.models import Consumo, MovimentoEstoque, PedidoInsumo
    with app_module.app.app_context():
        movs, peds = antes
        for m in MovimentoEstoque.query.filter(MovimentoEstoque.id.notin_(movs)).all():
            Consumo.query.filter_by(movimento_id=m.id).delete()
            db.session.delete(m)
        PedidoInsumo.query.filter(PedidoInsumo.id.notin_(peds)).delete(synchronize_session=False)
        db.session.commit()


def _ids_dos_materiais(app_module):
    from facilities.materiais.models import MovimentoEstoque, PedidoInsumo
    with app_module.app.app_context():
        return ([m.id for m in MovimentoEstoque.query.all()],
                [p.id for p in PedidoInsumo.query.all()])


def test_consumo_e_pedido_como_na_tela_antiga(app_module, cena):
    enc = fabrica.entrar(app_module, 'c1d.enc@trino.com')
    a = cena['local']
    antes = _ids_dos_materiais(app_module)
    casos = [
        ('/app/materiais/consumo', '/api/v1/campo/materiais/consumo',
         {'client_id': a, 'material_id': cena['detergente'], 'quantidade': '1,5',
          'chamado_id': cena['chamado'], 'rota_id': cena['rota']}),
        ('/app/materiais/consumo', '/api/v1/campo/materiais/consumo',
         {'client_id': a, 'material_id': cena['detergente'], 'quantidade': 'abc'}),
        ('/app/materiais/pedido', '/api/v1/campo/materiais/pedido',
         {'client_id': a, 'material_id': '', 'texto': 'saco de lixo 100 L'}),
        ('/app/materiais/pedido', '/api/v1/campo/materiais/pedido',
         {'client_id': a, 'material_id': '', 'texto': ''}),
    ]
    for antiga, nova, dados in casos:
        _apagar_lancamentos(app_module, antes)
        antigo = _antiga(enc, antiga, data=dados)
        estado = _estado_dos_materiais(app_module)
        _apagar_lancamentos(app_module, antes)
        r, j = _nova(enc, nova, data=dados)
        _confere(antigo, r, j)
        assert j['destino'] == '/novo/app/materiais'
        assert _estado_dos_materiais(app_module) == estado, dados
    # O pedido com foto, no próprio formulário.
    _apagar_lancamentos(app_module, antes)
    r, j = _nova(enc, '/api/v1/campo/materiais/pedido', data={
        'client_id': str(a), 'texto': 'papel toalha', 'foto': (io.BytesIO(_png()), 'f.png')},
        content_type='multipart/form-data')
    assert r.status_code == 200 and j['recados'][0]['texto'] == 'Pedido enviado ao gestor do contrato.'
    assert (a, 0, 'papel toalha', 'aberto', True) in _estado_dos_materiais(app_module)[1]
    # O perfil que não lança material: 403, nas duas.
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'c1d.dir@trino.com', 'visualizador', locais=[LOCAL_A])
    d = fabrica.entrar(app_module, 'c1d.dir@trino.com')
    dados = casos[0][2]
    assert d.post('/app/materiais/consumo', data=dados).status_code == 403
    r = d.post('/api/v1/campo/materiais/consumo', data=dados)
    assert r.status_code == 403 and r.is_json


def _estado_da_visita(app_module, vid):
    from app import db
    from facilities.visitas.models import Visita, VisitaFoto
    with app_module.app.app_context():
        db.session.expire_all()
        v = db.session.get(Visita, vid)
        return (v.status, v.feita_por, v.respostas_json, v.observacao, v.n_nao_conformes,
                bool(v.chamado_id),
                sorted((f.momento, f.item_codigo) for f in VisitaFoto.query.filter_by(visita_id=vid)))


def _reabrir(app_module, vid):
    from app import db
    from facilities.chamados.models import Chamado, ChamadoAnexo
    from facilities.visitas.models import PREVISTA, Visita, VisitaFoto
    with app_module.app.app_context():
        v = db.session.get(Visita, vid)
        VisitaFoto.query.filter_by(visita_id=vid).delete()
        if v.chamado_id:
            ch = db.session.get(Chamado, v.chamado_id)
            v.chamado_id = None
            db.session.flush()
            ChamadoAnexo.query.filter_by(chamado_id=ch.id).delete()
            for rel in ('historico', 'eventos'):
                for x in list(getattr(ch, rel, []) or []):
                    db.session.delete(x)
            db.session.delete(ch)
        v.status, v.feita_por, v.feita_em, v.versao_id = PREVISTA, None, None, None
        v.respostas_json, v.observacao, v.n_nao_conformes = None, None, 0
        db.session.commit()


def test_registrar_a_visita_como_na_tela_antiga(app_module, cena):
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    vid = cena['visita']
    casos = [
        ({'r_uniforme': 'sim', 'r_temp': '5', 'r_piso': 'Limpo', 'observacao': 'ok'}, {}),
        ({'r_temp': '5'}, {}),                                          # recusa: obrigatória
        ({'r_uniforme': 'nao', 'r_peca': 'bota'}, {'f_item:peca': 1, 'f_livre': 2}),
    ]
    for dados, fotos in casos:
        resultados = []
        for url in (f'/app/visitas/{vid}', f'/api/v1/campo/visitas/{vid}'):
            _reabrir(app_module, vid)
            corpo = dict(dados)
            for campo, n in fotos.items():
                corpo[campo] = [(io.BytesIO(_png()), f'{campo}{i}.png') for i in range(n)]
            kw = {'data': corpo, 'content_type': 'multipart/form-data'}
            resultados.append(_antiga(sup, url, **kw) if url.startswith('/app')
                              else _nova(sup, url, **kw))
            estado = _estado_da_visita(app_module, vid)
            resultados.append(estado[:2] + estado[2:3] + estado[3:])
        (destino, recados), e_antiga, (r, j), e_nova = resultados
        # O número do chamado aberto muda (cada envio abre o seu; no Postgres a
        # sequência não reaproveita o número do apagado): o resto é igual.
        def sem_numero(xs):
            return [{**x, 'texto': re.sub(r'OS-\d+', 'OS-N', x['texto'])} for x in xs]
        assert sem_numero(j['recados']) == sem_numero(recados), dados
        assert j['destino'] == f'/novo/app/visitas/{vid}' == '/novo' + destino
        assert e_antiga == e_nova, dados
        assert r.status_code == (400 if recados[0]['tipo'] == 'danger' else 200)
    # A última foi não conforme, com o chamado aberto e as fotos.
    assert e_nova[0] == 'feita' and e_nova[4] == 1 and e_nova[5]
    assert e_nova[6] == [('item', 'peca'), ('livre', None), ('livre', None)]
    # Já registrada: a recusa, igual nas duas.
    antigo = _antiga(sup, f'/app/visitas/{vid}', data={'r_uniforme': 'sim'})
    r, j = _nova(sup, f'/api/v1/campo/visitas/{vid}', data={'r_uniforme': 'sim'})
    _confere(antigo, r, j)
    assert 'já foi registrada' in j['error']


# ── Isolamento ────────────────────────────────────────────────────────────

def test_quem_e_de_outro_local_nao_ve_nem_altera_a(app_module, cena):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'c1d.supb@trino.com', 'supervisor', locais=[LOCAL_B])
        fabrica.pessoa(app_module, 'c1d.encb@trino.com', 'encarregado', locais=[LOCAL_B])
    supb = fabrica.entrar(app_module, 'c1d.supb@trino.com')
    encb = fabrica.entrar(app_module, 'c1d.encb@trino.com')
    for c, url in ((supb, '/api/v1/campo/equipe'), (supb, '/api/v1/campo/visitas'),
                   (encb, '/api/v1/campo/materiais')):
        r = c.get(url)
        assert r.status_code == 200 and SEGREDO not in r.get_data(as_text=True), url
        assert LOCAL_A not in r.get_data(as_text=True), url
    d = supb.get('/api/v1/campo/equipe').get_json()
    assert [x['nome'] for x in d['locais']] == [LOCAL_B]
    for vid in (cena['visita'], cena['feita']):
        r = supb.get(f'/api/v1/campo/visitas/{vid}')
        assert r.status_code == 403 and SEGREDO not in r.get_data(as_text=True)
    antes = (_estado_da_equipe(app_module), _estado_dos_materiais(app_module),
             _estado_da_visita(app_module, cena['visita']))
    assert supb.post('/api/v1/campo/equipe/presenca', data={
        'escala_id': cena['escala'], 'situacao': 'veio'}).status_code == 403
    assert supb.post(f"/api/v1/campo/equipe/presencas/{cena['falta_ontem']}/cobertura", data={
        'funcionario_id': cena['mariana'], 'motivo': 'atestado'}).status_code == 403
    assert supb.post(f"/api/v1/campo/visitas/{cena['visita']}",
                     data={'r_uniforme': 'sim'}).status_code == 403
    for url in ('/api/v1/campo/materiais/consumo', '/api/v1/campo/materiais/pedido'):
        r = encb.post(url, data={'client_id': cena['local'], 'material_id': cena['detergente'],
                                 'quantidade': '1', 'texto': 'x'})
        assert r.status_code == 403 and r.is_json, url
    assert (_estado_da_equipe(app_module), _estado_dos_materiais(app_module),
            _estado_da_visita(app_module, cena['visita'])) == antes


# ── Os endereços dentro das telas novas ───────────────────────────────────

def test_dentro_das_telas_novas_os_links_sao_os_novos(app_module, cena, auth_client):
    from facilities.telas.cadastros import nova
    assert nova('/app/equipe') == '/novo/app/equipe'
    assert nova('/app/equipe?data=2026-11-01') == '/novo/app/equipe?data=2026-11-01'
    assert nova('/app/materiais') == '/novo/app/materiais'
    assert nova('/app/visitas') == '/novo/app/visitas'
    assert nova('/app/visitas/7') == '/novo/app/visitas/7'
    # A foto da visita e o resto do aplicativo continuam onde estão.
    assert nova('/app/visitas/fotos/7') == '/app/visitas/fotos/7'
    for url in ('/app/', '/app/api/execucoes', '/app/instalar', '/app/materiais/pedidos/1/foto'):
        assert nova(url) in (url, '/novo' + url) and not nova(url).startswith('/novo/app/api')
    sup = fabrica.entrar(app_module, 'c1d.sup@trino.com')
    d = sup.get('/api/v1/campo/inicio').get_json()
    assert d['equipe'] == '/novo/app/equipe' and d['material'] == '/novo/app/materiais'
    assert d['visitas']['url'] == '/novo/app/visitas' and d['visitas']['abertas'] == 1
    # A tela antiga continua com os endereços de sempre.
    html = sup.get('/app/').get_data(as_text=True)
    assert 'href="/app/equipe"' in html and 'href="/app/visitas"' in html
    a = cena['local']
    # As visitas do local, o chamado aberto pela visita e o painel de demandas.
    d = auth_client.get(f'/api/v1/visitas/locais/{a}').get_json()
    assert all(v['url'].startswith('/novo/app/visitas/') for v in d['recentes'])
    d = auth_client.get(f"/api/v1/chamados/{cena['chamado_feita']}").get_json()
    assert d['chamado']['visita'] == f"/novo/app/visitas/{cena['feita']}"
    itens = auth_client.get('/api/v1/demandas/').get_json()['itens']
    assert [i['link'] for i in itens if i['tipo'] == 'visita'] and all(
        i['link'].startswith('/novo/app/visitas/') for i in itens if i['tipo'] == 'visita')
    # O menu não muda.
    menu = [i['url'] for g in auth_client.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert not any(u.startswith('/novo/app') for u in menu)
