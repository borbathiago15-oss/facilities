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
