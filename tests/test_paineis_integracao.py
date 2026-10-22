"""Fase 8 — nota por local, painel por perfil e a API só de leitura para o
Trino Intelligence.

O caso: ontem, no Shopping Centro, a rota teve 2 tarefas (uma no prazo, uma
perdida) e dois chamados foram resolvidos (um no prazo, um atrasado). Sem
visita nem ocorrência do QR no período: esses dois indicadores ficam fora
da média. Nota = (50 + 50) / 2 = 50 → crítica.
"""
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS


@pytest.fixture()
def cena(app_module):
    from app import User, db
    from facilities.chamados import servico as chamados
    from facilities.rotas import servico as rotas
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, PERDIDA, NaoConformidade
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['hosp'] = fabrica.local(CONTRATOS_SEMEADOS[1]).id
        ids['sup'] = fabrica.pessoa(app_module, 'sup.pn@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.pn@trino.com', 'pleno',
                                      locais=['Shopping Centro'])
        ids['enc'] = fabrica.pessoa(app_module, 'enc.pn@trino.com', 'encarregado',
                                    locais=['Shopping Centro'])
        coord = db.session.get(User, ids['coord'])
        ontem = tempo.hoje() - timedelta(days=1)
        m = rotas.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        rotas.publicar(m, rotas.normalizar_itens([{'texto': 'Limpo?', 'tipo': 'sim_nao'}]),
                       {}, None)
        rota = rotas.salvar_rota(loc, None, {'nome': 'Manhã', 'turno': 'T1',
                                             'hora_inicio': '07:00', 'hora_fim': '15:00',
                                             'tolerancia_min': '15', 'dias_semana': '1234567',
                                             'presencas_por_turno': '0'})
        rotas.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                       'horarios': '08:00, 10:00'})
        rotas.gerar(ontem, [loc.id])
        t1, t2 = rotas.tarefas_do_dia([loc.id], ontem)
        t1.status, t2.status = CONCLUIDA_NO_PRAZO, PERDIDA
        agora = tempo.para_utc(ontem, __import__('datetime').time(18, 0))
        for atrasado in (False, True):
            ch = chamados.abrir(coord, loc.id, f'Chamado {atrasado}')
            ch.aberto_em = agora - timedelta(hours=10)
            ch.prazo = agora - timedelta(hours=5)
            ch.status = 'resolvido'
            ch.resolvido_em = agora if atrasado else agora - timedelta(hours=6)
        db.session.commit()
        from app import User as U
        dono = db.session.get(U, ids['coord'])
        ex, _ = rotas.registrar_execucao(dono, {
            'envio_id': 'envio-painel-1', 'ponto': ids['qr'], 'versao_id': m.versao_atual.id,
            'respostas': {}, 'sem_sinal': True,
            'lido_em': (agora - timedelta(hours=1)).isoformat()}, {}, agora_utc=agora)
        db.session.add(NaoConformidade(execucao_id=ex.id, client_id=loc.id,
                                       item_codigo='limpo', item_texto='Limpo?', resposta='nao'))
        db.session.commit()
        ids.update(ontem=ontem.isoformat())
    return ids


# ── A nota ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('nota, faixa', [(None, None), (0, 'critica'), (69.9, 'critica'),
                                         (70, 'atencao'), (84.9, 'atencao'), (85, 'boa'),
                                         (100, 'boa')])
def test_faixas(nota, faixa):
    from facilities.paineis.servico import faixa as f
    assert f(nota) == faixa


def test_nota_media_dos_indicadores_com_dado(app_module, cena):
    from facilities.paineis import servico
    with app_module.app.app_context():
        hoje = tempo.hoje()
        x = servico.nota_do_local(fabrica.local(), hoje - timedelta(days=7), hoje)
        assert x['indicadores']['aderencia'] == {'bom': 1, 'base': 2, 'pct': 50.0}
        assert x['indicadores']['chamados'] == {'bom': 1, 'base': 2, 'pct': 50.0}
        assert x['indicadores']['visitas']['pct'] is None
        assert x['indicadores']['ocorrencias']['pct'] is None
        assert x['nota'] == 50.0 and x['faixa'] == 'critica'
        vazio = servico.nota_do_local(fabrica.local(CONTRATOS_SEMEADOS[1]),
                                      hoje - timedelta(days=7), hoje)
        assert vazio['nota'] is None and vazio['faixa'] is None


def test_painel_por_perfil(app_module, cena):
    coord = fabrica.entrar(app_module, 'coord.pn@trino.com')
    html = coord.get('/painel').get_data(as_text=True)
    assert 'Grupo GL' in html and '50,0 · Crítica' in html      # agrupado por cliente
    sup = fabrica.entrar(app_module, 'sup.pn@trino.com')
    html = sup.get('/painel').get_data(as_text=True)
    assert '50,0 · Crítica' in html and 'nota média 50' not in html
    assert 'Hospital Norte' not in html
    enc = fabrica.entrar(app_module, 'enc.pn@trino.com')
    assert enc.get('/painel').status_code == 403
    assert 'Painel' in coord.get('/').get_data(as_text=True)


# ── A API ─────────────────────────────────────────────────────────────────

def _chave(app_module, cena, todos=False, locais=None):
    from app import User, db
    from facilities.integracao import servico
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        ch, texto = servico.criar_chave('Intelligence', locais or [cena['local']], todos, admin)
        db.session.commit()
        return ch.id, texto


def _get(app_module, rota, texto=None, **params):
    c = app_module.app.test_client()
    h = {'Authorization': f'Bearer {texto}'} if texto else {}
    return c.get(f'/api/integracao/v1/{rota}', query_string=params, headers=h)


def _acessos(app_module):
    from facilities.integracao.models import IntegracaoAcesso
    with app_module.app.app_context():
        return [(a.chave_id, a.rota, a.status, a.parametros)
                for a in IntegracaoAcesso.query.order_by(IntegracaoAcesso.id)]


def test_sem_chave_ou_chave_errada_nao_entra_e_fica_registrado(app_module, cena):
    _kid, texto = _chave(app_module, cena)
    assert _get(app_module, 'locais').status_code == 401
    assert _get(app_module, 'locais', texto[:-2] + 'xx').status_code == 401
    assert _get(app_module, 'locais', 'fac_naoexiste_abc').status_code == 401
    # Um registro por endereço por hora: a tabela não cresce por tentativa
    # (auditoria N-03); os três pedidos vieram do mesmo endereço.
    assert [a[2] for a in _acessos(app_module)] == [401]


def test_chave_de_um_local_nao_le_outro(app_module, cena):
    kid, texto = _chave(app_module, cena)
    r = _get(app_module, 'locais', texto)
    assert r.status_code == 200
    assert [x['id'] for x in r.get_json()['itens']] == [cena['local']]
    r = _get(app_module, 'chamados', texto, de=cena['ontem'], ate=cena['ontem'],
             local=cena['hosp'])
    assert r.status_code == 403
    r = _get(app_module, 'chamados', texto, de=cena['ontem'], ate=cena['ontem'])
    assert {x['local_id'] for x in r.get_json()['itens']} == {cena['local']}
    assert {x['no_prazo'] for x in r.get_json()['itens']} == {True, False}
    todos_kid, todos = _chave(app_module, cena, todos=True)
    ids = {x['id'] for x in _get(app_module, 'locais', todos).get_json()['itens']}
    assert {cena['local'], cena['hosp']} <= ids


def test_repetir_da_o_mesmo_resultado_e_o_registro_nao_tem_segredo(app_module, cena):
    from facilities.integracao.models import IntegracaoAcesso, IntegracaoChave
    kid, texto = _chave(app_module, cena)
    args = dict(de=cena['ontem'], ate=cena['ontem'])
    respostas = [_get(app_module, rota, texto, **args).get_data()
                 for rota in ('aderencia', 'aderencia')]
    assert respostas[0] == respostas[1]
    with app_module.app.app_context():
        segredo = texto.split('_', 2)[2]
        for a in IntegracaoAcesso.query:
            assert segredo not in repr([a.rota, a.parametros, a.ip])
        ch = IntegracaoChave.query.get(kid)
        assert segredo not in ch.hash_chave and ch.prefixo in texto
        assert ch.ultimo_uso_em is not None
    assert _acessos(app_module)[-1] == (kid, 'aderencia', 200,
                                        f'ate={cena["ontem"]}&de={cena["ontem"]}')


def test_numeros_da_api_iguais_aos_da_tela(app_module, cena):
    from facilities.paineis import servico
    _kid, texto = _chave(app_module, cena)
    args = dict(de=cena['ontem'], ate=cena['ontem'])
    nota = _get(app_module, 'nota', texto, **args).get_json()['itens'][0]
    from datetime import date
    with app_module.app.app_context():
        tela = servico.nota_do_local(fabrica.local(), date.fromisoformat(cena['ontem']),
                                     date.fromisoformat(cena['ontem']))
    assert nota['nota'] == tela['nota'] == 50.0 and nota['faixa'] == 'critica'
    assert nota['indicadores'] == tela['indicadores']
    ad = _get(app_module, 'aderencia', texto, **args).get_json()['itens']
    assert ad == [dict(ad[0], previstas=2, no_prazo=1, perdidas=1, aderencia_pct=50.0)]


def test_nao_conformidade_sai_com_a_referencia_do_plano_de_acao(app_module, cena):
    from facilities.rotas.models import NaoConformidade
    _kid, texto = _chave(app_module, cena)
    itens = _get(app_module, 'nao-conformidades', texto, de=cena['ontem'],
                 ate=cena['ontem']).get_json()['itens']
    with app_module.app.app_context():
        nc = NaoConformidade.query.one()
        assert itens[0]['referencia'] == f'NC-{nc.id}' and itens[0]['item'] == 'Limpo?'
    coord = fabrica.entrar(app_module, 'coord.pn@trino.com')
    with app_module.app.app_context():
        eid = NaoConformidade.query.one().execucao_id
    assert f'NC-{nc.id}' in coord.get(f'/rotas/execucoes/{eid}').get_data(as_text=True)


def test_periodo_validado_e_chave_revogada(app_module, cena):
    from app import db
    from facilities.integracao import servico
    from facilities.integracao.models import IntegracaoChave
    kid, texto = _chave(app_module, cena)
    assert _get(app_module, 'chamados', texto).status_code == 400
    assert _get(app_module, 'chamados', texto, de='2026-01-01',
                ate='2026-06-01').status_code == 400
    assert _get(app_module, 'chamados', texto, de=cena['ontem'], ate=cena['ontem'],
                local='abc').status_code == 400
    with app_module.app.app_context():
        servico.revogar(db.session.get(IntegracaoChave, kid))
        db.session.commit()
    assert _get(app_module, 'locais', texto).status_code == 401


def test_custo_de_material_nao_sai_pela_api(app_module):
    rotas = {r.rule for r in app_module.app.url_map.iter_rules()
             if r.rule.startswith('/api/integracao/')}
    assert not any('custo' in r or 'material' in r for r in rotas)


def test_tela_de_chaves_so_do_administrador(app_module, cena, auth_client):
    r = auth_client.post('/admin/integracao/', data={'nome': 'Intelligence', 'todos': '1'})
    texto = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Copie agora' in texto
    import re
    chave = re.search(r'fac_[0-9a-f]{8}_[A-Za-z0-9_-]+', texto).group(0)
    assert _get(app_module, 'locais', chave).status_code == 200
    lista = auth_client.get('/admin/integracao/').get_data(as_text=True)
    assert chave not in lista and chave.split('_')[1] in lista
    coord = fabrica.entrar(app_module, 'coord.pn@trino.com')
    assert coord.get('/admin/integracao/').status_code in (302, 403)
    assert coord.post('/admin/integracao/', data={'nome': 'x', 'todos': '1'}).status_code \
        in (302, 403)
