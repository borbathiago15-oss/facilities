"""Fase 9B — portal do cliente e cobrança.

Decisões (F9-1 a F9-4): o cliente vê indicadores, chamados (situação, prazo,
solução, fotos) e as fotos dos checklists — nunca custo, comentário interno
nem a trilha do chamado. A cobrança tem a data escolhida pelo cliente (no
mínimo 24 h), a coordenação responde e só o cliente encerra ou reabre. O nome
de quem fez o checklist só aparece com o interruptor do cliente ligado. Tudo
atrás de ``CLIENTE_EXTERNO_LIBERADO`` (desligado por padrão), com a segunda
etapa obrigatória.
"""
from datetime import datetime, time, timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import Arquivo, _png

COMENTARIO = 'COMENTARIO-INTERNO-DA-EQUIPE'
MATERIAL = 'Detergente-SO-DA-EQUIPE'


@pytest.fixture()
def liberado(app_module):
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    yield
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False


@pytest.fixture()
def cena(app_module):
    """Grupo GL com o Shopping Centro; um coordenador e o gerente do cliente;
    o cliente GL; um coordenador de outro local; um chamado resolvido com foto,
    PDF, comentário e material; um checklist com foto."""
    from app import User, db
    from facilities.chamados import servico as chs
    from facilities.chamados.models import ChamadoAnexo, ChamadoEvento
    from facilities.core.anexos import storage
    from facilities.rotas import servico as rs
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        coord = fabrica.pessoa(app_module, 'coord.gl@trino.com', 'pleno',
                               locais=['Shopping Centro'], nome='Carla Coordenadora')
        ger = fabrica.pessoa(app_module, 'ger.gl@trino.com', 'gerente', nome='Gil Gerente')
        from facilities.cadastros.models import Contratante
        db.session.get(Contratante, ids['cliente']).gerente_id = ger
        outro = fabrica.pessoa(app_module, 'coord.hn@trino.com', 'pleno',
                               locais=['Hospital Norte'])
        sup = fabrica.pessoa(app_module, 'sup.gl@trino.com', 'supervisor',
                             locais=['Shopping Centro'])
        enc = fabrica.pessoa(app_module, 'enc.gl@trino.com', 'encarregado',
                             locais=['Shopping Centro'], nome='Eva Encarregada')
        cli = fabrica.cliente(app_module, 'cliente@gl.com', ids['cliente'])
        db.session.commit()
        u_coord = db.session.get(User, coord)
        ch = chs.abrir(u_coord, ids['local'], 'Lâmpada queimada no hall', local='Hall')
        db.session.flush()
        ch.status = 'resolvido'
        ch.solucao = 'Lâmpada trocada'
        ch.resolvido_em = datetime.utcnow()
        db.session.add(ChamadoEvento(chamado_id=ch.id, tipo='comentario', texto=COMENTARIO,
                                     created_by=coord))
        storage().save('teste/foto.png', _png(), 'image/png')
        storage().save('teste/orcamento.pdf', b'%PDF-1.4 orcamento', 'application/pdf')
        foto = ChamadoAnexo(chamado_id=ch.id, nome='foto.png', mime='image/png',
                            storage_key='teste/foto.png', momento='depois')
        pdf = ChamadoAnexo(chamado_id=ch.id, nome='orcamento.pdf', mime='application/pdf',
                           storage_key='teste/orcamento.pdf', momento='antes')
        db.session.add_all([foto, pdf])
        material = mat.salvar_material(None, {'nome': MATERIAL, 'unidade': 'L',
                                              'preco_unitario': '10'})
        loc = fabrica.local()
        mat.movimentar(u_coord, loc, {'material_id': str(material.id), 'quantidade': '5'},
                       'entrada')
        mat.consumir(u_coord, loc, {'material_id': str(material.id), 'quantidade': '1',
                                    'chamado_id': str(ch.id)})
        m = rs.criar_modelo(ids['local'], {'nome': 'Checklist do banheiro'}, None)
        rs.publicar(m, rs.normalizar_itens([{'texto': 'Piso limpo?', 'tipo': 'sim_nao',
                                             'problema_se': 'nao'}]), {}, None)
        db.session.commit()
        ex, _ = rs.registrar_execucao(db.session.get(User, enc), {
            'envio_id': 'portal-0000001', 'ponto': ids['qr'], 'modelo_id': m.id,
            'respostas': {rs.normalizar_itens([{'texto': 'Piso limpo?'}])[0]['codigo']: 'sim'},
            'sem_sinal': True,
            'lido_em': datetime.utcnow().isoformat()}, {'depois': [Arquivo()]})
        db.session.commit()
        ids.update(coord=coord, ger=ger, outro=outro, sup=sup, enc=enc, cli=cli,
                   chamado=ch.id, foto=foto.id, pdf=pdf.id, execucao=ex.id,
                   foto_checklist=ex.fotos[0].id)
    return ids


def _cliente(app_module):
    return fabrica.entrar_com_codigo(app_module, 'cliente@gl.com')


def _data(dias):
    return (tempo.hoje() + timedelta(days=dias)).isoformat()


# ── A porta: desligado, segunda etapa e só o portal ───────────────────────

def test_desligado_o_cliente_nao_entra_nem_com_a_segunda_etapa(app_module, cena):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': 'cliente@gl.com', 'password': fabrica.SENHA})
    assert r.status_code == 403
    assert 'ainda não foi liberado' in r.get_data(as_text=True)


def test_desligar_o_portal_derruba_a_sessao_aberta(app_module, cena, liberado):
    c = _cliente(app_module)
    assert c.get('/cliente/').status_code == 200
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = False
    r = c.get('/cliente/')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    assert c.get('/cliente/').status_code == 302      # precisa entrar de novo


def test_cliente_sem_cliente_no_cadastro_nao_entra(app_module, cena, liberado):
    from app import User, db
    with app_module.app.app_context():
        db.session.get(User, cena['cli']).cliente_id = None
        db.session.commit()
    r = app_module.app.test_client().post('/login', data={'email': 'cliente@gl.com',
                                                          'password': fabrica.SENHA})
    assert r.status_code == 403


def test_sem_a_segunda_etapa_so_abre_a_tela_de_seguranca(app_module, cena, liberado):
    from facilities.core import totp
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cliente@gl.com', cena['cliente'], segunda_etapa=False)
    c = fabrica.entrar(app_module, 'cliente@gl.com')
    for url in ('/cliente/', '/cliente/cobrancas', '/', '/avisos'):
        r = c.get(url)
        assert r.status_code == 302 and '/conta/seguranca' in r.headers['Location'], url
    assert c.post('/cliente/cobrancas', data={}).status_code == 403
    pagina = c.get('/conta/seguranca')
    assert pagina.status_code == 200
    with c.session_transaction() as s:
        segredo = s['_totp_novo']
    r = c.post('/conta/seguranca/ativar', data={'codigo': totp.codigo(segredo)})
    assert r.status_code == 302
    assert c.get('/cliente/').status_code == 200
    # E não dá para desligar depois.
    c.post('/conta/seguranca/desativar', data={'senha': fabrica.SENHA})
    from app import User, db
    with app_module.app.app_context():
        assert db.session.get(User, cena['cli']).totp_ativo


def test_o_login_leva_ao_portal_e_ignora_destino_de_fora(app_module, cena, liberado):
    from facilities.core import totp
    c = app_module.app.test_client()
    r = c.post('/login?next=/chamados/', data={'email': 'cliente@gl.com',
                                               'password': fabrica.SENHA})
    r = c.post('/login/codigo', data={'codigo': totp.codigo(fabrica.SEGREDO_CLIENTE)})
    assert r.headers['Location'].endswith('/cliente/')
    assert c.get('/').headers['Location'].endswith('/cliente/')


@pytest.mark.parametrize('url', ['/chamados/', '/painel', '/demandas/', '/materiais/custo',
                                 '/app/', '/cadastros/', '/cobrancas/', '/admin/usuarios',
                                 '/passagem-de-turno/', '/app/materiais'])
def test_cliente_nao_abre_nada_da_equipe(app_module, cena, liberado, url):
    c = _cliente(app_module)
    r = c.get(url)
    assert r.status_code == 403, url
    assert COMENTARIO not in r.get_data(as_text=True)


def test_cliente_nao_lanca_nada_pela_equipe(app_module, cena, liberado):
    from app import db
    from facilities.chamados.models import Chamado
    c = _cliente(app_module)
    r = c.post('/chamados/', data={'client_id': cena['local'], 'titulo': 'Do cliente',
                                   'prioridade': 'media', 'categoria': 'outro'})
    assert r.status_code == 403
    r = c.post(f"/chamados/{cena['chamado']}/acao", data={'acao': 'confirmar'})
    assert r.status_code == 403
    r = c.post("/cobrancas/1/responder", data={'texto': 'x'})
    assert r.status_code == 403
    with app_module.app.app_context():
        assert Chamado.query.filter_by(titulo='Do cliente').count() == 0
        assert db.session.get(Chamado, cena['chamado']).status == 'resolvido'


def test_a_equipe_nao_abre_o_portal(app_module, cena):
    c = fabrica.entrar(app_module, 'coord.gl@trino.com')
    assert c.get('/cliente/').status_code == 403
    assert c.post('/cliente/cobrancas', data={'client_id': cena['local']}).status_code == 403


# ── O que o cliente vê ────────────────────────────────────────────────────

def test_o_local_mostra_indicadores_chamados_e_checklists(app_module, cena, liberado):
    c = _cliente(app_module)
    inicio = c.get('/cliente/').get_data(as_text=True)
    assert 'Shopping Centro' in inicio and 'Hospital Norte' not in inicio
    pag = c.get(f"/cliente/locais/{cena['local']}").get_data(as_text=True)
    assert 'Aderência à rota' in pag and 'Chamados no prazo' in pag
    assert 'Lâmpada queimada no hall' in pag
    assert 'Checklist do banheiro' in pag
    assert f"/cliente/fotos/checklist/{cena['foto_checklist']}" in pag
    # R5: a função, não o nome.
    assert 'Encarregado / ASG' in pag and 'Eva Encarregada' not in pag
    for proibido in (MATERIAL, 'R$', COMENTARIO, 'Carla Coordenadora'):
        assert proibido not in pag, proibido


def test_o_chamado_mostra_situacao_solucao_e_so_as_fotos(app_module, cena, liberado):
    c = _cliente(app_module)
    pag = c.get(f"/cliente/chamados/{cena['chamado']}").get_data(as_text=True)
    assert 'Lâmpada trocada' in pag and 'Resolvido' in pag
    assert f"/cliente/fotos/chamado/{cena['foto']}" in pag
    assert f"/cliente/fotos/chamado/{cena['pdf']}" not in pag
    for proibido in (MATERIAL, 'R$', COMENTARIO, 'Carla Coordenadora', 'orcamento'):
        assert proibido not in pag, proibido
    assert c.get(f"/cliente/fotos/chamado/{cena['foto']}").mimetype == 'image/png'
    assert c.get(f"/cliente/fotos/chamado/{cena['pdf']}").status_code == 404
    assert c.get(f"/cliente/fotos/checklist/{cena['foto_checklist']}").status_code == 200


def test_o_nome_de_quem_fez_so_com_o_interruptor(app_module, cena, liberado):
    from app import db
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        db.session.get(Contratante, cena['cliente']).mostrar_nome_executor = True
        db.session.commit()
    pag = _cliente(app_module).get(f"/cliente/locais/{cena['local']}").get_data(as_text=True)
    assert 'Eva Encarregada' in pag


def test_so_o_administrador_liga_o_nome(app_module, cena, auth_client):
    from app import db
    from facilities.cadastros.models import Contratante
    dados = {'nome': 'Grupo GL', 'empresa_id': str(cena['empresa']),
             'mostrar_nome_executor': '1'}
    c = fabrica.entrar(app_module, 'ger.gl@trino.com')
    c.post(f"/cadastros/clientes/{cena['cliente']}", data=dados)
    with app_module.app.app_context():
        from app import User
        from facilities.cadastros import servico as cad
        cad.salvar_contratante(db.session.get(Contratante, cena['cliente']), dados,
                               db.session.get(User, cena['ger']))
        db.session.commit()
    with app_module.app.app_context():
        assert not db.session.get(Contratante, cena['cliente']).mostrar_nome_executor
    auth_client.post(f"/cadastros/clientes/{cena['cliente']}", data=dados)
    with app_module.app.app_context():
        assert db.session.get(Contratante, cena['cliente']).mostrar_nome_executor


def test_local_de_outro_cliente_da_404(app_module, cena, liberado):
    c = _cliente(app_module)
    with app_module.app.app_context():
        hn_id = fabrica.local('Hospital Norte').id
    assert c.get(f'/cliente/locais/{hn_id}').status_code == 404


# ── A cobrança ────────────────────────────────────────────────────────────

def test_prazo_minimo_de_24_horas():
    from facilities.portal.servico import RegraDaCobranca, prazo_escolhido, prazo_minimo
    # 18/10 às 22h em Brasília: amanhã às 23h59 ainda passa das 24 h.
    agora = tempo.para_utc(datetime(2026, 10, 18).date(), time(22, 0))
    assert prazo_minimo(agora).isoformat() == '2026-10-19'
    # 18/10 às 23h59 + 1 min... o fim do dia 19 fica a 24 h exatas: vale.
    agora = tempo.para_utc(datetime(2026, 10, 18).date(), time(23, 59))
    assert prazo_minimo(agora).isoformat() == '2026-10-19'
    agora = tempo.para_utc(datetime(2026, 10, 18).date(), time(8, 0))
    with pytest.raises(RegraDaCobranca):
        prazo_escolhido('2026-10-18', agora)
    p = prazo_escolhido('2026-10-19', agora)
    assert tempo.local(p).strftime('%d/%m %H:%M') == '19/10 23:59'
    with pytest.raises(RegraDaCobranca):
        prazo_escolhido('2027-12-01', agora)
    with pytest.raises(RegraDaCobranca):
        prazo_escolhido('ontem', agora)


def test_cobranca_do_comeco_ao_fim(app_module, cena, liberado):
    from app import db
    from facilities.core.models import Notification
    from facilities.portal.models import Cobranca
    c = _cliente(app_module)
    r = c.post('/cliente/cobrancas', data={'client_id': cena['local'], 'titulo': 'Banheiro sujo',
                                           'texto': 'O 2º andar está sem limpeza.',
                                           'prazo': _data(0)})
    with app_module.app.app_context():
        assert Cobranca.query.count() == 0                  # hoje: menos de 24 h
    r = c.post('/cliente/cobrancas', data={'client_id': cena['local'], 'titulo': 'Banheiro sujo',
                                           'texto': 'O 2º andar está sem limpeza.',
                                           'prazo': _data(3)})
    assert r.status_code == 302
    with app_module.app.app_context():
        cob = Cobranca.query.one()
        cid = cob.id
        avisados = {n.user_id for n in Notification.query.filter_by(notification_type='cobranca')}
    # A coordenação do contrato e o gerente do cliente; ninguém de outro local.
    assert {cena['coord'], cena['ger']} <= avisados
    assert cena['outro'] not in avisados and cena['sup'] not in avisados
    # Aparece em Demandas, com a data escolhida.
    coord = fabrica.entrar(app_module, 'coord.gl@trino.com')
    assert 'Banheiro sujo' in coord.get('/demandas/?tipo=cobranca').get_data(as_text=True)
    # Supervisor vê, mas não responde; coordenador de outro local nem abre.
    sup = fabrica.entrar(app_module, 'sup.gl@trino.com')
    assert sup.get(f'/cobrancas/{cid}').status_code == 200
    sup.post(f'/cobrancas/{cid}/responder', data={'texto': 'do supervisor'})
    assert fabrica.entrar(app_module, 'coord.hn@trino.com').get(
        f'/cobrancas/{cid}').status_code == 403
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'aberta'
    # O cliente ainda não encerra: falta a resposta.
    c.post(f'/cliente/cobrancas/{cid}/confirmar', data={})
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'aberta'
    coord.post(f'/cobrancas/{cid}/responder', data={'texto': 'Limpeza refeita às 14h.'})
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'respondida'
        assert Notification.query.filter_by(user_id=cena['cli'],
                                            notification_type='cobranca').count() == 1
    # Responder de novo não vale.
    coord.post(f'/cobrancas/{cid}/responder', data={'texto': 'segunda'})
    pag = c.get(f'/cliente/cobrancas/{cid}').get_data(as_text=True)
    assert 'Limpeza refeita às 14h.' in pag and 'Coordenação' in pag
    assert 'Carla Coordenadora' not in pag and 'segunda' not in pag
    # A equipe não encerra pelo portal.
    assert coord.post(f'/cliente/cobrancas/{cid}/confirmar').status_code == 403
    # Reabrir pede o que falta e uma data nova (≥ 24 h).
    c.post(f'/cliente/cobrancas/{cid}/reabrir', data={'texto': 'Ainda sujo', 'prazo': _data(0)})
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'respondida'
    c.post(f'/cliente/cobrancas/{cid}/reabrir', data={'texto': 'Ainda sujo', 'prazo': _data(5)})
    with app_module.app.app_context():
        cob = db.session.get(Cobranca, cid)
        assert cob.status == 'aberta' and cob.reaberturas == 1
        assert tempo.local(cob.prazo).date().isoformat() == _data(5)
    coord.post(f'/cobrancas/{cid}/responder', data={'texto': 'Refeito de novo.'})
    c.post(f'/cliente/cobrancas/{cid}/confirmar', data={'texto': 'Agora sim'})
    with app_module.app.app_context():
        cob = db.session.get(Cobranca, cid)
        assert cob.status == 'fechada' and cob.fechada_em is not None
        assert [e.tipo for e in cob.eventos] == ['aberta', 'resposta', 'reaberta', 'resposta',
                                                 'confirmada']
    # Encerrada: sai de Demandas.
    assert 'Banheiro sujo' not in coord.get('/demandas/?tipo=cobranca').get_data(as_text=True)


def test_cobranca_so_nos_locais_do_cliente(app_module, cena, liberado):
    from facilities.portal.models import Cobranca
    with app_module.app.app_context():
        hn_id = fabrica.local('Hospital Norte').id
    c = _cliente(app_module)
    c.post('/cliente/cobrancas', data={'client_id': hn_id, 'titulo': 'Invasão', 'texto': 'x',
                                       'prazo': _data(3)})
    c.post('/cliente/cobrancas', data={'client_id': cena['local'], 'titulo': '', 'texto': 'x',
                                       'prazo': _data(3)})
    with app_module.app.app_context():
        assert Cobranca.query.count() == 0


def test_cobranca_atrasada_aparece_como_atrasada(app_module, cena, liberado):
    from app import User, db
    from facilities import demandas
    from facilities.portal import servico
    with app_module.app.app_context():
        cob = servico.abrir(db.session.get(User, cena['cli']), {
            'client_id': str(cena['local']), 'titulo': 'Vidros', 'texto': 'Limpar',
            'prazo': _data(2)})
        db.session.commit()
        depois = cob.prazo + timedelta(minutes=1)
        itens = [i for i in demandas.demandas([cena['local']], agora=depois)
                 if i['tipo'] == 'cobranca']
        assert itens and itens[0]['situacao'] == 'atrasada'
        assert cob.atrasada(depois)
