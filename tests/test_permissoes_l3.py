"""Leva L3 (permissões), 05/11/2026: as regras novas do dono que a auditoria
(``test_auditoria_permissoes.py``) não cobria sozinha.

* R1 do lado positivo: o volante com "todos os locais" sob a gestão vê os
  locais dela (e só os dela); a conta "de baixo para cima"
  (``hierarquia.quem_ve_o_local``) bate com a carteira de cada pessoa.
* R5: a diretoria vê tudo mesmo sem a caixinha.

A cena é a mesma da auditoria: o local A (Shopping Centro) do cliente
"Grupo GL", com o gerente pelo cliente; coordenador › supervisor ›
encarregado e técnico ligados a A; o Hospital Norte, de outro cliente do
mesmo gerente; o Condomínio Sul, de ninguém.
"""
import pytest

from tests import fabrica
from tests.test_auditoria_permissoes import _abrir_chamado, _avisos, cena  # noqa: F401


def _carteira(app_module, uid):
    from app import User, db
    from facilities.core.hierarquia import carteira
    with app_module.app.app_context():
        return carteira(db.session.get(User, uid))


# ── R1: "todos" do piso = os locais da gestão acima ─────────────────────────

@pytest.mark.parametrize('papel', ['supervisor', 'encarregado', 'tecnico'])
def test_r1_volante_ve_os_locais_da_gestao_acima_e_so_eles(app_module, cena, papel):
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, f'l3.{papel}.volante@trino.com', papel,
                             all_clients=True, superior_id=cena['ple'])
    # O coordenador vê A (vinculado) — o volante abaixo dele também; o
    # Hospital Norte é do gerente, não do coordenador: fica de fora.
    assert _carteira(app_module, uid) == {cena['local']}
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    c = fabrica.entrar(app_module, f'l3.{papel}.volante@trino.com')
    assert c.get(f'/api/v1/chamados/{cid}').status_code == 200


def test_r1_volante_sob_o_gerente_ve_todos_os_clientes_dele(app_module, cena):
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'l3.tec.gerente@trino.com', 'tecnico',
                             all_clients=True, superior_id=cena['ger'])
    assert _carteira(app_module, uid) == {cena['local'], cena['local_b']}


def test_r1_tecnico_volante_da_cadeia_pode_receber_o_chamado(app_module, cena):
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'l3.tec.cadeia@trino.com', 'tecnico',
                             all_clients=True, superior_id=cena['ple'])
        from facilities.chamados.servico import tecnicos_do_contrato
        assert uid in {u.id for u in tecnicos_do_contrato(cena['local'])}
        assert uid not in {u.id for u in tecnicos_do_contrato(cena['local_b'])}


def test_r1_gestao_com_todos_ve_o_grupo_mas_nao_recebe_aviso_de_todo_local(app_module, cena):
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'l3.regional@trino.com', 'pleno', all_clients=True)
        from facilities.chamados.servico import gestores_do_contrato
        assert uid not in gestores_do_contrato(cena['local'])
    assert _carteira(app_module, uid) is None


def test_quem_ve_o_local_bate_com_a_carteira_de_cada_pessoa(app_module, cena):
    """A conta de baixo para cima (avisos, quem recebe chamado, escala) e a
    de cima para baixo (o que a pessoa abre) dão o mesmo resultado."""
    from app import Client, User, db
    from facilities.core.hierarquia import carteira, quem_ve_o_local
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'l3.vol.sup@trino.com', 'supervisor', all_clients=True,
                       superior_id=cena['ple'])
        fabrica.pessoa(app_module, 'l3.vol.enc@trino.com', 'encarregado', all_clients=True,
                       superior_id=cena['ger'])
        fabrica.pessoa(app_module, 'l3.vol.solto@trino.com', 'tecnico', all_clients=True)
        locais = [c.id for c in Client.query.all()]
        for loc in locais:
            veem = quem_ve_o_local(loc)
            for u in User.query.filter(User.is_deleted.is_(False)):
                ids = carteira(u)
                if ids is None or u.role == 'cliente':
                    continue
                assert (loc in ids) == (u.id in veem), (u.email, u.role, loc)


# ── R5: a diretoria vê tudo, com ou sem a caixinha ──────────────────────────

def test_r5_diretoria_sem_a_caixinha_ve_tudo(app_module, cena):
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'l3.dir@trino.com', 'visualizador')
    assert _carteira(app_module, uid) is None


def test_r5_editar_a_diretoria_mantem_todos_os_locais(app_module, cena):
    from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'l3.dir2@trino.com', 'visualizador', all_clients=True)
    adm = fabrica.entrar(app_module, ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    r = adm.post(f'/admin/usuarios/{uid}', data={'name': 'Diretora', 'email': 'l3.dir2@trino.com',
                                                 'role': 'visualizador', 'is_active': '1'})
    assert r.status_code == 302
    with app_module.app.app_context():
        from app import User, db
        assert db.session.get(User, uid).all_clients is True


# ── R3 e regra A: o supervisor distribui e é avisado do chamado novo ────────

def test_a_supervisor_recebe_o_aviso_de_chamado_novo_do_local_dele(app_module, cena):
    with app_module.app.app_context():
        fora = fabrica.pessoa(app_module, 'l3.sup.fora@trino.com', 'supervisor',
                              locais=['Hospital Norte'])
    _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    assert any('Novo chamado' in t for t in _avisos(app_module, cena['sup']))
    assert not _avisos(app_module, fora)


def test_r3_o_supervisor_ve_os_controles_de_distribuir_nas_duas_telas(app_module, cena):
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    c = fabrica.entrar(app_module, 'aud.supervisor@trino.com')
    d = c.get(f'/api/v1/chamados/{cid}').get_json()
    assert {'atribuir', 'prioridade', 'cancelar', 'iniciar'} <= set(d['acoes'])
    html = c.get(f'/chamados/{cid}').get_data(as_text=True)
    assert 'name="acao" value="atribuir"' in html and 'Aud.Supervisor' in html.replace(' ', '')


# ── Regra B: o supervisor responde a cobrança do cliente ────────────────────

def _cobranca(app_module, cena):
    from datetime import timedelta
    from app import db
    from facilities import tempo
    from facilities.portal import servico as portal
    with app_module.app.app_context():
        cli = fabrica.cliente(app_module, 'l3.cliente@gl.com', cena['cliente'])
        from app import User
        cob = portal.abrir(db.session.get(User, cli), {
            'client_id': str(cena['local']), 'titulo': 'Vidros', 'texto': 'Limpar os vidros',
            'prazo': (tempo.hoje() + timedelta(days=3)).isoformat()})
        db.session.commit()
        return cob.id


def test_b_supervisor_do_local_responde_a_cobranca_nas_duas_telas(app_module, cena):
    from app import db
    from facilities.portal.models import Cobranca
    cid = _cobranca(app_module, cena)
    c = fabrica.entrar(app_module, 'aud.supervisor@trino.com')
    assert c.get(f'/api/v1/cobrancas/{cid}').get_json()['pode_responder'] is True
    assert 'Resposta para o cliente' in c.get(f'/cobrancas/{cid}').get_data(as_text=True)
    r = c.post(f'/api/v1/cobrancas/{cid}/responder', data={'texto': 'Vidros limpos às 9h.'})
    assert r.status_code == 200, r.get_data(as_text=True)
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'respondida'


def test_b_supervisor_de_outro_local_e_encarregado_nao_respondem(app_module, cena):
    from app import db
    from facilities.portal.models import Cobranca
    cid = _cobranca(app_module, cena)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'l3.sup.hn@trino.com', 'supervisor', locais=['Hospital Norte'])
    for email in ('l3.sup.hn@trino.com', 'aud.encarregado@trino.com'):
        c = fabrica.entrar(app_module, email)
        r = c.post(f'/api/v1/cobrancas/{cid}/responder', data={'texto': 'x'})
        assert r.status_code in (400, 403), email
    with app_module.app.app_context():
        assert db.session.get(Cobranca, cid).status == 'aberta'


# ── D3: sem ninguém para avisar, a tela não promete ─────────────────────────

def test_d3_local_sem_gestao_salva_o_chamado_e_diz_que_ninguem_foi_avisado(app_module, cena):
    """O Condomínio Sul não tem cliente, gerente nem cadeia: só o encarregado."""
    from app import db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'l3.enc.sul@trino.com', 'encarregado',
                       locais=['Condomínio Sul'])
        sul = fabrica.local('Condomínio Sul').id
    c = fabrica.entrar(app_module, 'l3.enc.sul@trino.com')
    r = c.post('/chamados/', data={'client_id': sul, 'titulo': 'Portão travado',
                                   'prioridade': 'urgente', 'categoria': 'outro'})
    assert r.status_code == 302
    with c.session_transaction() as s:
        recados = ' '.join(t for _, t in s.get('_flashes', []))
    assert 'foram avisados' not in recados and 'ninguém foi avisado' in recados
    # A tela nova recebe o mesmo recado.
    r = c.post('/api/v1/chamados/', json={'client_id': sul, 'titulo': 'Luz do hall',
                                          'prioridade': 'media', 'categoria': 'eletrica'})
    assert r.status_code == 200
    assert 'ninguém foi avisado' in r.get_json()['recados'][0]['texto']
    with app_module.app.app_context():
        assert Chamado.query.filter_by(client_id=sul, titulo='Portão travado').count() == 1


def test_d3_com_gestao_avisada_o_recado_segue_o_mesmo(app_module, cena):
    c = fabrica.entrar(app_module, 'aud.encarregado@trino.com')
    r = c.post('/api/v1/chamados/', json={'client_id': cena['local'], 'titulo': 'Torneira',
                                          'prioridade': 'media', 'categoria': 'hidraulica'})
    assert 'Os gestores do contrato foram avisados.' in r.get_json()['recados'][0]['texto']


# ── D7: desativar quem é responsável não deixa o trabalho sem ninguém ───────

def _plano_do_tecnico(app_module, cena):
    from app import User, db
    from facilities import tempo
    from facilities.preventiva import servico as prev
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        m = s.criar_modelo(cena['local'], {'nome': 'Checklist da bomba'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Sem ruído?', 'tipo': 'sim_nao'}]), {},
                   None)
        plano = prev.salvar_plano(fabrica.local(), None, {
            'nome': 'Bomba d’água', 'ponto_id': cena['ponto'], 'modelo_id': m.id,
            'intervalo_dias': '30', 'proxima_em': tempo.hoje().isoformat(),
            'responsavel_id': str(cena['tec'])}, db.session.get(User, cena['ple']))
        db.session.commit()
        return plano.id


def test_d7_ordem_preventiva_nao_nasce_com_o_inativo_e_a_gestao_e_avisada(app_module, cena):
    from app import db
    from facilities import tempo
    from facilities.chamados.models import Chamado
    from facilities.preventiva import servico as prev
    from tests.test_auditoria_permissoes import _desativar
    pid = _plano_do_tecnico(app_module, cena)
    _desativar(app_module, cena['tec'])
    with app_module.app.app_context():
        assert prev.gerar_ordens(tempo.hoje()) == 1
        db.session.commit()
        ch = Chamado.query.filter(Chamado.titulo == 'Preventiva: Bomba d’água').one()
        assert ch.responsavel_id is None
        from facilities.preventiva.models import PlanoPreventivo
        assert db.session.get(PlanoPreventivo, pid).responsavel_id == cena['tec']
    avisos = _avisos(app_module, cena['ple']) + _avisos(app_module, cena['ger'])
    assert any('Preventiva: Bomba' in t for t in avisos)


def test_d7_com_o_responsavel_ativo_a_ordem_segue_com_ele(app_module, cena):
    from app import db
    from facilities import tempo
    from facilities.chamados.models import Chamado
    from facilities.preventiva import servico as prev
    _plano_do_tecnico(app_module, cena)
    with app_module.app.app_context():
        prev.gerar_ordens(tempo.hoje())
        db.session.commit()
        ch = Chamado.query.filter(Chamado.titulo == 'Preventiva: Bomba d’água').one()
        assert ch.responsavel_id == cena['tec']
    assert not any('Preventiva: Bomba' in t for t in _avisos(app_module, cena['ple']))


def test_d7_reabrir_chamado_do_inativo_avisa_a_gestao(app_module, cena):
    from tests.test_auditoria_permissoes import _acao, _desativar
    cid = _abrir_chamado(app_module, 'aud.encarregado@trino.com', cena['local'])
    assert _acao(app_module, 'aud.pleno@trino.com', cid, acao='atribuir',
                 responsavel_id=cena['tec']).status_code == 200
    assert _acao(app_module, 'aud.tecnico@trino.com', cid, acao='iniciar').status_code == 200
    assert _acao(app_module, 'aud.tecnico@trino.com', cid, acao='resolver',
                 texto='Trocada').status_code == 200
    _desativar(app_module, cena['tec'])
    assert _acao(app_module, 'aud.encarregado@trino.com', cid, acao='reabrir',
                 texto='Voltou a queimar').status_code == 200
    assert any('Chamado reaberto' in t for t in _avisos(app_module, cena['ple']))


def test_d7_desativar_avisa_o_administrador_do_que_ficou(app_module, cena):
    from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD
    _plano_do_tecnico(app_module, cena)
    adm = fabrica.entrar(app_module, ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    with app_module.app.app_context():
        from app import User, db
        u = db.session.get(User, cena['tec'])
        dados = {'name': u.name, 'email': u.email, 'role': u.role,
                 'clients': [str(c) for c in u.client_ids]}
    adm.post(f"/admin/usuarios/{cena['tec']}", data=dados)
    with adm.session_transaction() as s:
        recados = ' '.join(t for _, t in s.get('_flashes', []))
    assert '1 plano(s) preventivo(s)' in recados and 'gestão de cada local' in recados


# ── R6: o coordenador monta só na carteira dele ─────────────────────────────

def test_r6_lista_de_clientes_do_coordenador_e_so_a_da_carteira(app_module, cena):
    from app import User, db
    from facilities.cadastros import montagem
    with app_module.app.app_context():
        ple = db.session.get(User, cena['ple'])
        assert [c.id for c in montagem.clientes_da_montagem(ple)] == [cena['cliente']]
        ger = db.session.get(User, cena['ger'])
        assert {c.id for c in montagem.clientes_da_montagem(ger)} == {cena['cliente'], cena['hn']}
    c = fabrica.entrar(app_module, 'aud.pleno@trino.com')
    assert c.get(f"/novo-contrato/cliente/{cena['hn']}/local").status_code == 403
    assert c.get(f"/novo-contrato/cliente/{cena['cliente']}/local").status_code == 200


# ── R10: a gestão autoriza (e retira) o encarregado a configurar a passagem ─

def _pode_configurar(app_module, uid):
    from app import User, db
    with app_module.app.app_context():
        return db.session.get(User, uid).pode('diario_config')


@pytest.mark.parametrize('quem', ['aud.pleno@trino.com', 'aud.gerente@trino.com'])
def test_r10_gestao_autoriza_e_retira_nas_duas_telas(app_module, cena, quem):
    c = fabrica.entrar(app_module, quem)
    d = c.get('/api/v1/cadastros/convites').get_json()
    assert {'id': cena['enc'], 'nome': 'Aud.Encarregado', 'locais': 'Shopping Centro',
            'autorizado': False} in d['encarregados']
    assert 'Quem pode configurar a passagem' in c.get('/convites').get_data(as_text=True)
    r = c.post(f"/convites/pessoas/{cena['enc']}/autorizar-passagem")
    assert r.status_code == 302 and _pode_configurar(app_module, cena['enc'])
    assert any('configurar a passagem' in t for t in _avisos(app_module, cena['enc']))
    # O encarregado entra na configuração do modelo.
    enc = fabrica.entrar(app_module, 'aud.encarregado@trino.com')
    assert enc.post('/passagem-de-turno/api/configuracoes',
                    json={'client_id': cena['local'], 'nome': 'Modelo'}).status_code != 403
    r = c.post(f"/api/v1/cadastros/convites/pessoas/{cena['enc']}/retirar-passagem")
    assert r.status_code == 200 and not _pode_configurar(app_module, cena['enc'])
    assert enc.post('/passagem-de-turno/api/configuracoes',
                    json={'client_id': cena['local'], 'nome': 'Modelo'}).status_code == 403


def test_r10_quem_nao_e_da_carteira_ou_nao_e_encarregado_nao_e_autorizado(app_module, cena):
    with app_module.app.app_context():
        fora = fabrica.pessoa(app_module, 'l3.enc.hn@trino.com', 'encarregado',
                              locais=['Hospital Norte'])
        fabrica.pessoa(app_module, 'l3.ple.hn@trino.com', 'pleno', locais=['Hospital Norte'])
    c = fabrica.entrar(app_module, 'aud.pleno@trino.com')
    ids = {u['id'] for u in c.get('/api/v1/cadastros/convites').get_json()['encarregados']}
    assert fora not in ids and cena['tec'] not in ids and cena['sup'] not in ids
    for uid in (fora, cena['tec'], cena['sup']):
        assert c.post(f'/api/v1/cadastros/convites/pessoas/{uid}/autorizar-passagem'
                      ).status_code == 404
        assert c.post(f'/convites/pessoas/{uid}/autorizar-passagem').status_code == 404
        assert not _pode_configurar(app_module, uid)
    # O coordenador do outro local não autoriza o encarregado de A.
    outro = fabrica.entrar(app_module, 'l3.ple.hn@trino.com')
    assert outro.post(f"/convites/pessoas/{cena['enc']}/autorizar-passagem").status_code == 404
    assert not _pode_configurar(app_module, cena['enc'])


@pytest.mark.parametrize('papel', ['supervisor', 'encarregado', 'tecnico', 'visualizador'])
def test_r10_quem_nao_e_gestao_nao_autoriza_ninguem(app_module, cena, papel):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'l3.{papel}.r10@trino.com', papel, locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, f'l3.{papel}.r10@trino.com')
    for url in (f"/convites/pessoas/{cena['enc']}/autorizar-passagem",
                f"/api/v1/cadastros/convites/pessoas/{cena['enc']}/autorizar-passagem"):
        assert c.post(url).status_code == 403
    assert not _pode_configurar(app_module, cena['enc'])
