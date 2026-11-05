"""Auditoria da Fase 1 (permissões: perfil x rota), 05/11/2026.

Cada teste com ``xfail(strict=True)`` documenta um DEFEITO contra a régua
confirmada pelo dono (R1, R3, R4, R5, R6, R9, R10 e as regras gerais). A
suíte fica verde enquanto o defeito existir; quando for corrigido, o xfail
vira "XPASS" e falha: aí é só tirar a marca. Os testes sem marca guardam o
que a auditoria conferiu e está CERTO (R7, R8 e a carteira entre locais).

A cena: o local A (Shopping Centro) é do cliente "Grupo GL", cujo gerente
responde pelo cliente SEM vínculo direto ao local. Abaixo dele, na cadeia:
coordenador (vinculado a A) › supervisor (vinculado a A) › encarregado e
técnico (vinculados a A). Um segundo cliente do MESMO gerente, "Grupo HN",
tem o local Hospital Norte, fora da carteira do coordenador.
"""
import os
from datetime import datetime, timedelta

import pytest

from tests import fabrica
from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ger = fabrica.pessoa(app_module, 'aud.gerente@trino.com', 'gerente')
        gl = db.session.get(Contratante, ids['cliente'])
        gl.gerente_id = ger
        hn = cad.salvar_contratante(None, {'nome': 'Grupo HN', 'empresa_id': ids['empresa'],
                                           'gerente_id': str(ger)}, None)
        db.session.flush()
        fabrica.local('Hospital Norte').contratante_id = hn.id
        fabrica.local('Hospital Norte').estado_id = ids['estado']
        db.session.commit()
        ple = fabrica.pessoa(app_module, 'aud.pleno@trino.com', 'pleno',
                             locais=['Shopping Centro'], superior_id=ger)
        sup = fabrica.pessoa(app_module, 'aud.supervisor@trino.com', 'supervisor',
                             locais=['Shopping Centro'], superior_id=ple)
        enc = fabrica.pessoa(app_module, 'aud.encarregado@trino.com', 'encarregado',
                             locais=['Shopping Centro'], superior_id=sup)
        tec = fabrica.pessoa(app_module, 'aud.tecnico@trino.com', 'tecnico',
                             locais=['Shopping Centro'], superior_id=sup)
        ids.update(ger=ger, ple=ple, sup=sup, enc=enc, tec=tec, hn=hn.id,
                   local_b=fabrica.local('Hospital Norte').id)
    return ids


def _abrir_chamado(app_module, email, client_id, titulo='Lâmpada queimada no hall'):
    c = fabrica.entrar(app_module, email)
    r = c.post('/api/v1/chamados/', json={'client_id': client_id, 'titulo': titulo,
                                          'prioridade': 'media', 'categoria': 'eletrica'})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        from facilities.chamados.models import Chamado
        return Chamado.query.filter_by(titulo=titulo).one().id


def _avisos(app_module, uid):
    with app_module.app.app_context():
        from facilities.core.models import Notification
        return [n.title for n in Notification.query.filter_by(user_id=uid)]


# ── R4: o gerente que responde pelo cliente (sem vínculo direto ao local) ──

@pytest.mark.xfail(strict=True, reason='BUG R4: chamados.servico.gestores_do_contrato conta só '
                   'quem está vinculado ao local; o gerente pelo cliente não é avisado')
def test_r4_gerente_pelo_cliente_recebe_aviso_de_chamado_novo(app_module, cena):
    _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    assert any('Novo chamado' in t for t in _avisos(app_module, cena['ger']))


@pytest.mark.xfail(strict=True, reason='BUG R4: chamados.servico.tecnicos_do_contrato '
                   '(pessoas_do_contrato) ignora o gerente pelo cliente')
def test_r4_gerente_pelo_cliente_esta_na_lista_de_quem_recebe_chamado(app_module, cena):
    with app_module.app.app_context():
        from facilities.chamados.servico import tecnicos_do_contrato
        assert cena['ger'] in {u.id for u in tecnicos_do_contrato(cena['local'])}


@pytest.mark.xfail(strict=True, reason='BUG R4: o coordenador que vê o local pela cadeia '
                   '(sem vínculo direto) também não é avisado do chamado novo')
def test_r4_coordenador_pela_cadeia_recebe_aviso_de_chamado_novo(app_module, cena):
    with app_module.app.app_context():
        from app import User, db
        db.session.get(User, cena['ple']).clients = []
        db.session.commit()
    _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    assert any('Novo chamado' in t for t in _avisos(app_module, cena['ple']))


@pytest.mark.xfail(strict=True, reason='BUG: a tela diz "Os gestores do contrato foram '
                   'avisados" mesmo quando ninguém recebeu o aviso (chamados/rotas.py:192)')
def test_aviso_de_chamado_nao_promete_o_que_nao_fez(app_module, cena):
    with app_module.app.app_context():
        from app import User, db
        db.session.get(User, cena['ple']).clients = []
        db.session.commit()
    c = fabrica.entrar(app_module, 'aud.encarregado@trino.com')
    r = c.post('/chamados/', data={'client_id': cena['local'], 'titulo': 'Vazamento',
                                   'prioridade': 'media', 'categoria': 'hidraulica'})
    assert r.status_code == 302
    with c.session_transaction() as s:
        recados = ' '.join(t for _, t in s.get('_flashes', []))
    ninguem = not any(_avisos(app_module, u) for u in (cena['ger'], cena['ple']))
    assert not (ninguem and 'foram avisados' in recados)


@pytest.mark.xfail(strict=True, reason='BUG R4: materiais.servico.e_gestor_do_contrato usa '
                   'gestores_do_contrato; o gerente pelo cliente vê o pedido e não marca visto')
def test_r4_gerente_pelo_cliente_marca_pedido_de_insumo_como_visto(app_module, cena):
    from app import User, db
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        p = mat.pedir(db.session.get(User, cena['enc']), fabrica.local(),
                      {'texto': 'Faltou papel toalha'})
        db.session.commit()
        pid = p.id
    c = fabrica.entrar(app_module, 'aud.gerente@trino.com')
    assert c.get('/api/v1/materiais/pedidos').status_code == 200
    r = c.post(f'/api/v1/materiais/pedidos/{pid}/visto', json={})
    assert r.status_code == 200, r.get_data(as_text=True)


@pytest.mark.xfail(strict=True, reason='BUG R4: o pedido de insumo avisa gestores_do_contrato; '
                   'o gerente pelo cliente não recebe')
def test_r4_gerente_pelo_cliente_recebe_aviso_de_pedido_de_insumo(app_module, cena):
    from app import User, db
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        mat.pedir(db.session.get(User, cena['enc']), fabrica.local(),
                  {'texto': 'Faltou sabonete'})
        db.session.commit()
    assert _avisos(app_module, cena['ger'])


# ── R3: o supervisor distribui, muda prioridade, cancela e atende ────────

def _acao(app_module, email, chamado_id, **corpo):
    c = fabrica.entrar(app_module, email)
    return c.post(f'/api/v1/chamados/{chamado_id}/acao', json=corpo)


@pytest.mark.xfail(strict=True, reason='BUG R3: chamados.servico.pode_gerir exige e_gestao(); '
                   'o supervisor não atribui o técnico')
def test_r3_supervisor_atribui_o_tecnico(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    r = _acao(app_module, 'aud.supervisor@trino.com', cid, acao='atribuir',
              responsavel_id=cena['tec'])
    assert r.status_code == 200, r.get_data(as_text=True)


@pytest.mark.xfail(strict=True, reason='BUG R3: pode_gerir barra o supervisor na prioridade')
def test_r3_supervisor_muda_a_prioridade(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    r = _acao(app_module, 'aud.supervisor@trino.com', cid, acao='prioridade',
              prioridade='alta')
    assert r.status_code == 200, r.get_data(as_text=True)


@pytest.mark.xfail(strict=True, reason='BUG R3: pode_gerir barra o supervisor no cancelamento')
def test_r3_supervisor_cancela(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    r = _acao(app_module, 'aud.supervisor@trino.com', cid, acao='cancelar',
              texto='Aberto em duplicidade')
    assert r.status_code == 200, r.get_data(as_text=True)


@pytest.mark.xfail(strict=True, reason='BUG R3: tecnicos_do_contrato só aceita técnico, '
                   'coordenador e gerente; o supervisor não pode ser o responsável')
def test_r3_supervisor_pode_ser_o_responsavel(app_module, cena):
    with app_module.app.app_context():
        from facilities.chamados.servico import tecnicos_do_contrato
        assert cena['sup'] in {u.id for u in tecnicos_do_contrato(cena['local'])}


@pytest.mark.xfail(strict=True, reason='BUG R3: pode_atender exige gestão ou ser o '
                   'responsável; o supervisor não inicia o atendimento')
def test_r3_supervisor_assume_e_atende(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    r = _acao(app_module, 'aud.supervisor@trino.com', cid, acao='iniciar')
    assert r.status_code == 200, r.get_data(as_text=True)


# ── R1: "acesso a todos" de quem não é gestão nem diretoria ──────────────

@pytest.mark.xfail(strict=True, reason='BUG R1: core/hierarquia.carteira devolve None (tudo) '
                   'para qualquer perfil com all_clients')
@pytest.mark.parametrize('papel', ['supervisor', 'encarregado', 'tecnico'])
def test_r1_acesso_a_todos_fica_na_cadeia(app_module, cena, papel):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'aud.{papel}.todos@trino.com', papel, all_clients=True)
    c = fabrica.entrar(app_module, f'aud.{papel}.todos@trino.com')
    assert c.get(f'/api/v1/chamados/{cid}').status_code == 403
    assert c.get(f"/api/v1/passagem/turno?client_id={cena['local']}").status_code == 403


@pytest.mark.xfail(strict=True, reason='BUG R1: pessoas_do_contrato soma todo técnico com '
                   'all_clients à lista de quem pode receber chamado de qualquer local')
def test_r1_tecnico_com_todos_fora_da_cadeia_nao_recebe_chamado(app_module, cena):
    with app_module.app.app_context():
        tt = fabrica.pessoa(app_module, 'aud.tecnico.volante@trino.com', 'tecnico',
                            all_clients=True)
        from facilities.chamados.servico import tecnicos_do_contrato
        assert tt not in {u.id for u in tecnicos_do_contrato(cena['local'])}


@pytest.mark.xfail(strict=True, reason='BUG R1: passagem/rotas._time_do_piso avisa todo '
                   'encarregado/técnico com all_clients, de qualquer local')
def test_r1_piso_com_todos_fora_da_cadeia_nao_recebe_aviso_do_local(app_module, cena):
    with app_module.app.app_context():
        et = fabrica.pessoa(app_module, 'aud.enc.volante@trino.com', 'encarregado',
                            all_clients=True)
        from facilities.passagem.rotas import _time_do_piso
        assert et not in _time_do_piso(cena['local'])


# ── R5: a diretoria vê todos os locais, venha de onde vier ───────────────

@pytest.mark.xfail(strict=True, reason='BUG R5: diretoria criada em "Pessoas e acessos" sem a '
                   'caixinha fica com carteira vazia (core/admin._aplicar_formulario + '
                   'hierarquia.carteira)')
def test_r5_diretoria_criada_pelo_administrador_ve_todos_os_locais(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    adm = fabrica.entrar(app_module, ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    r = adm.post('/admin/usuarios', data={'name': 'Diretora', 'email': 'aud.dir@trino.com',
                                          'role': 'visualizador'})
    assert r.status_code == 200
    with app_module.app.app_context():
        from app import User, db
        u = User.query.filter(User.email == 'aud.dir@trino.com').one()
        u.set_password(fabrica.SENHA)
        u.must_change_password = False
        db.session.commit()
        fabrica.CRIADAS.add('aud.dir@trino.com')
    c = fabrica.entrar(app_module, 'aud.dir@trino.com')
    assert c.get(f'/api/v1/chamados/{cid}').status_code == 200


def test_r5_diretoria_nunca_grava(app_module, cena):
    """Conferido: a diretoria (com todos os locais) lê e não age."""
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'aud.dir2@trino.com', 'visualizador', all_clients=True,
                       permissions_json='["diario_config"]')
    c = fabrica.entrar(app_module, 'aud.dir2@trino.com')
    assert c.get(f'/api/v1/chamados/{cid}').status_code == 200
    assert c.post(f'/api/v1/chamados/{cid}/acao',
                  json={'acao': 'comentar', 'texto': 'x'}).status_code in (400, 403)
    r = c.post('/passagem-de-turno/api/configuracoes',
               json={'client_id': cena['local'], 'nome': 'Modelo'})
    assert r.status_code == 403


# ── R6: o coordenador monta locais só na carteira dele ───────────────────

@pytest.mark.xfail(strict=True, reason='BUG R6: cadastros/montagem.clientes_da_montagem dá ao '
                   'coordenador TODOS os clientes do gerente acima dele')
def test_r6_coordenador_nao_monta_local_em_outro_cliente_do_gerente(app_module, cena):
    c = fabrica.entrar(app_module, 'aud.pleno@trino.com')
    r = c.post(f"/api/v1/cadastros/novo-contrato/cliente/{cena['hn']}/local",
               json={'name': 'Hospital Norte — anexo', 'estado_id': cena['estado']})
    assert r.status_code == 403, r.get_data(as_text=True)


# ── R9: o agendador pela internet fica desligado ─────────────────────────

def test_r9_agendador_pela_internet_nao_existe(app_module, cena, monkeypatch):
    monkeypatch.setitem(os.environ, 'AGENDADOR_TOKEN', 'token-da-auditoria')
    c = app_module.app.test_client()
    r = c.post('/rotas/agendador', headers={'Authorization': 'Bearer token-da-auditoria'})
    assert r.status_code == 404


# ── R10: o coordenador autoriza o encarregado a configurar a passagem ────

@pytest.mark.xfail(strict=True, reason='BUG R10: só o administrador concede diario_config '
                   '(core/admin._aplicar_formulario); o coordenador não tem como autorizar')
def test_r10_coordenador_autoriza_encarregado_a_configurar(app_module, cena):
    from facilities.core.models import User
    rotas_que_concedem = [r for r in app_module.app.url_map.iter_rules()
                          if 'POST' in r.methods and r.endpoint not in (
                              'admin.criar_usuario', 'admin.editar_usuario',
                              'api_v1.api_admin_criar_usuario', 'api_v1.api_admin_editar_usuario')]
    c = fabrica.entrar(app_module, 'aud.pleno@trino.com')
    for regra in rotas_que_concedem:
        if 'permiss' in regra.rule or 'autoriz' in regra.rule:
            c.post(regra.rule.replace('<int:uid>', str(cena['enc'])),
                   json={'permissao': 'diario_config', 'user_id': cena['enc']})
    with app_module.app.app_context():
        from app import db
        assert db.session.get(User, cena['enc']).pode('diario_config')


def test_r10_encarregado_sem_autorizacao_nao_configura(app_module, cena):
    """Conferido: não é automático para o encarregado."""
    c = fabrica.entrar(app_module, 'aud.encarregado@trino.com')
    r = c.post('/passagem-de-turno/api/configuracoes',
               json={'client_id': cena['local'], 'nome': 'Modelo'})
    assert r.status_code == 403


# ── Desativar quem é responsável ─────────────────────────────────────────

def _desativar(app_module, uid):
    adm = fabrica.entrar(app_module, ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    with app_module.app.app_context():
        from app import User, db
        u = db.session.get(User, uid)
        dados = {'name': u.name, 'email': u.email, 'role': u.role,
                 'clients': [str(c) for c in u.client_ids],
                 'superior_id': str(u.superior_id or '')}
    r = adm.post(f'/admin/usuarios/{uid}', data=dados)
    assert r.status_code == 302
    with app_module.app.app_context():
        from app import User, db
        assert not db.session.get(User, uid).is_active


@pytest.mark.xfail(strict=True, reason='BUG: desativar o técnico responsável de um plano '
                   'preventivo não transfere nada; a ordem nova nasce com ele e ninguém '
                   'ativo é avisado (preventiva/servico._abrir_ordem)')
def test_desativar_responsavel_do_plano_nao_deixa_a_ordem_sem_ninguem(app_module, cena):
    from app import User, db
    from facilities import tempo
    from facilities.preventiva import servico as prev
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        m = s.criar_modelo(cena['local'], {'nome': 'Checklist do ar'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Filtro limpo?', 'tipo': 'sim_nao'}]), {},
                   None)
        prev.salvar_plano(fabrica.local(), None, {
            'nome': 'Filtro do ar', 'ponto_id': cena['ponto'], 'modelo_id': m.id,
            'intervalo_dias': '30', 'proxima_em': tempo.hoje().isoformat(),
            'responsavel_id': str(cena['tec'])}, db.session.get(User, cena['ple']))
        db.session.commit()
    _desativar(app_module, cena['tec'])
    with app_module.app.app_context():
        from facilities.core.models import Notification
        antes = Notification.query.count()
        assert prev.gerar_ordens(tempo.hoje()) == 1
        db.session.commit()
        assert Notification.query.count() > antes


@pytest.mark.xfail(strict=True, reason='BUG: desativar o técnico responsável de um chamado '
                   'aberto não o transfere; o aviso "vence em breve" vai só a ele '
                   '(chamados.servico.avisar_prazos) e ninguém ativo recebe')
def test_desativar_responsavel_do_chamado_nao_deixa_o_prazo_sem_aviso(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    assert _acao(app_module, 'aud.pleno@trino.com', cid, acao='atribuir',
                 responsavel_id=cena['tec']).status_code == 200
    _desativar(app_module, cena['tec'])
    with app_module.app.app_context():
        from app import db
        from facilities.chamados import servico as chs
        from facilities.chamados.models import Chamado
        from facilities.core.models import Notification
        ch = db.session.get(Chamado, cid)
        antes = Notification.query.count()
        chs.avisar_prazos(agora=ch.prazo - timedelta(minutes=10))
        db.session.commit()
        assert Notification.query.count() > antes


# ── O que está CERTO (conferido; sem marca) ──────────────────────────────

def test_r7_supervisor_e_diretoria_veem_custo_e_nao_mexem_no_catalogo(app_module, cena):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'aud.dir3@trino.com', 'visualizador', all_clients=True)
    for email in ('aud.supervisor@trino.com', 'aud.dir3@trino.com'):
        c = fabrica.entrar(app_module, email)
        assert c.get('/api/v1/materiais/custo').status_code == 200
        assert c.post('/api/v1/materiais/', json={'nome': 'Cera', 'unidade': 'L',
                                                  'preco_unitario': '3'}).status_code == 403
    c = fabrica.entrar(app_module, 'aud.pleno@trino.com')
    assert c.post('/api/v1/materiais/', json={'nome': 'Cera', 'unidade': 'L',
                                              'preco_unitario': '3'}).status_code == 200


def test_r8_supervisor_desativado_nao_corta_a_carteira_do_chefe(app_module, cena):
    with app_module.app.app_context():
        from app import User, db
        db.session.get(User, cena['ple']).clients = []
        db.session.get(User, cena['sup']).clients = []
        db.session.commit()
    _desativar(app_module, cena['sup'])
    with app_module.app.app_context():
        from app import User, db
        from facilities.core.hierarquia import carteira
        assert cena['local'] in carteira(db.session.get(User, cena['ple']))


def test_aviso_de_outra_pessoa_nao_abre(app_module, cena):
    with app_module.app.app_context():
        from app import db
        from facilities.core.models import Notification
        n = Notification(user_id=cena['ple'], title='Só do coordenador', link='/chamados/')
        db.session.add(n)
        db.session.commit()
        nid = n.id
    c = fabrica.entrar(app_module, 'aud.encarregado@trino.com')
    assert c.post(f'/avisos/{nid}/abrir').status_code == 404
    with app_module.app.app_context():
        from app import db
        from facilities.core.models import Notification
        assert db.session.get(Notification, nid).status == 'unread'


def test_menu_de_cada_perfil_so_leva_a_tela_que_abre(app_module, cena):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'aud.dir4@trino.com', 'visualizador', all_clients=True)
    for email in ('aud.gerente@trino.com', 'aud.pleno@trino.com', 'aud.supervisor@trino.com',
                  'aud.encarregado@trino.com', 'aud.tecnico@trino.com', 'aud.dir4@trino.com'):
        c = fabrica.entrar(app_module, email)
        for g in c.get('/api/v1/eu').get_json()['menu']:
            for it in g['itens']:
                assert c.get(it['url']).status_code == 200, (email, it['url'])


# ── R2: o supervisor usa a segunda etapa (obrigatória, como a gestão) ────

@pytest.mark.xfail(strict=True, reason='BUG R2: core/models.PERFIS_COM_SEGUNDA_ETAPA não '
                   'inclui o supervisor; ele entra só com a senha')
def test_r2_supervisor_sem_codigo_so_abre_a_tela_de_seguranca(app_module, cena):
    app_module.app.config['MFA_OBRIGATORIO_GESTAO'] = True   # o conftest desliga ao fim
    c = fabrica.entrar(app_module, 'aud.supervisor@trino.com')
    r = c.get('/')
    assert r.status_code == 302 and '/conta/seguranca' in r.headers['Location']
