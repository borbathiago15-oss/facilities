"""Fase 7 — materiais e custo operacional.

O caso: o Shopping Centro e o Hospital Norte são do mesmo cliente (Grupo GL).
A coordenação (gestora dos dois contratos) dá entrada de detergente; a Ana
(encarregada) lança o consumo no aplicativo e avisa que acabou o saco de
lixo; o supervisor vê o custo; a Ana e o técnico, não.
"""
import io
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from facilities import tempo
from tests import fabrica
from tests.conftest import CONTRATOS_SEMEADOS


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        hosp = fabrica.local(CONTRATOS_SEMEADOS[1])
        cad.vincular_local(hosp, {'contratante_id': ids['cliente'], 'estado_id': ids['estado']},
                           None)
        ids['hosp'] = hosp.id
        ids['ana'] = fabrica.pessoa(app_module, 'ana.mat@trino.com', 'encarregado',
                                    locais=['Shopping Centro'], nome='Ana')
        ids['tec'] = fabrica.pessoa(app_module, 'tec.mat@trino.com', 'tecnico',
                                    locais=['Shopping Centro'])
        ids['sup'] = fabrica.pessoa(app_module, 'sup.mat@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.mat@trino.com', 'pleno',
                                      locais=['Shopping Centro', CONTRATOS_SEMEADOS[1]],
                                      nome='Coordenação')
        ids['fora'] = fabrica.pessoa(app_module, 'fora.mat@trino.com', 'encarregado',
                                     locais=[CONTRATOS_SEMEADOS[2]])
        det = mat.salvar_material(None, {'nome': 'Detergente neutro', 'unidade': 'L',
                                         'preco_unitario': '12,90'})
        pano = mat.salvar_material(None, {'nome': 'Pano de chão', 'unidade': 'un'})
        db.session.commit()
        ids.update(det=det.id, pano=pano.id)
    return ids


def _u(uid):
    from app import User, db
    return db.session.get(User, uid)


def _loc(cid):
    from app import Client, db
    return db.session.get(Client, cid)


def _entrada(cena, material, qtd, local=None):
    from app import db
    from facilities.materiais import servico as mat
    m = mat.movimentar(_u(cena['coord']), _loc(local or cena['local']),
                       {'material_id': str(material), 'quantidade': qtd}, 'entrada')
    db.session.commit()
    return m


# ── Números ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('bruto, esperado', [
    ('1,5', Decimal('1.500')), ('1.234,56', Decimal('1234.560')), ('0.25', Decimal('0.250')),
    (' 3 ', Decimal('3.000')),
])
def test_quantidade_aceita_virgula(bruto, esperado):
    from facilities.materiais.servico import decimal_de
    assert decimal_de(bruto, 'a quantidade') == esperado


@pytest.mark.parametrize('bruto', ['abc', '0', '-1', '', 'NaN', 'inf'])
def test_quantidade_invalida(bruto):
    from facilities.materiais.servico import RegraDoMaterial, decimal_de
    with pytest.raises(RegraDoMaterial):
        decimal_de(bruto, 'a quantidade')


def test_reais():
    from facilities.materiais.servico import reais
    assert reais(Decimal('1234.5')) == 'R$ 1.234,50'
    assert reais(Decimal('0.3')) == 'R$ 0,30'


# ── Estoque e saldo ───────────────────────────────────────────────────────

def test_entrada_e_da_gestao_consumo_de_quem_executa(app_module, cena):
    from app import db
    from facilities.materiais import servico as mat
    from facilities.materiais.servico import RegraDoMaterial
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '10')
        with pytest.raises(RegraDoMaterial) as e:
            mat.movimentar(_u(cena['ana']), _loc(cena['local']),
                           {'material_id': str(cena['det']), 'quantidade': '5'}, 'entrada')
        assert e.value.codigo == 403
        mat.consumir(_u(cena['ana']), _loc(cena['local']),
                     {'material_id': str(cena['det']), 'quantidade': '1,5'})
        db.session.commit()
        assert mat.saldo(cena['local'], cena['det']) == Decimal('8.500')
        with pytest.raises(RegraDoMaterial) as e:
            mat.consumir(_u(cena['fora']), _loc(cena['local']),
                         {'material_id': str(cena['det']), 'quantidade': '1'})
        assert e.value.codigo == 403


def test_saldo_negativo_so_com_o_gestor_do_contrato(app_module, cena):
    from app import db
    from facilities.materiais import servico as mat
    from facilities.materiais.servico import RegraDoMaterial
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '2')
        dados = {'material_id': str(cena['det']), 'quantidade': '3'}
        with pytest.raises(RegraDoMaterial, match='Saldo insuficiente: há 2 L') as e:
            mat.consumir(_u(cena['ana']), _loc(cena['local']), dados)
        assert e.value.codigo == 409
        with pytest.raises(RegraDoMaterial, match='gestor do contrato') as e:
            mat.consumir(_u(cena['sup']), _loc(cena['local']),
                         dict(dados, autorizar_negativo='1', motivo='urgência'))
        assert e.value.codigo == 403
        with pytest.raises(RegraDoMaterial, match='justificativa'):
            mat.consumir(_u(cena['coord']), _loc(cena['local']),
                         dict(dados, autorizar_negativo='1'))
        mov = mat.consumir(_u(cena['coord']), _loc(cena['local']),
                           dict(dados, autorizar_negativo='1', motivo='vazamento no 2º andar'))
        db.session.commit()
        assert mov.autorizado_por == cena['coord']
        assert mat.saldo(cena['local'], cena['det']) == Decimal('-1.000')


def test_saida_e_ajuste_pedem_motivo(app_module, cena):
    from facilities.materiais import servico as mat
    from facilities.materiais.servico import RegraDoMaterial
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '5')
        for tipo, qtd in (('saida', '1'), ('ajuste', '-1')):
            with pytest.raises(RegraDoMaterial, match='motivo'):
                mat.movimentar(_u(cena['coord']), _loc(cena['local']),
                               {'material_id': str(cena['det']), 'quantidade': qtd}, tipo)
        m = mat.movimentar(_u(cena['coord']), _loc(cena['local']),
                           {'material_id': str(cena['det']), 'quantidade': '-2',
                            'motivo': 'inventário'}, 'ajuste')
        assert m.quantidade == Decimal('-2.000')


# ── Custo ─────────────────────────────────────────────────────────────────

def test_preco_do_dia_e_centavos_sem_perda(app_module, cena):
    from app import db
    from facilities.materiais import servico as mat
    from facilities.materiais.models import Material
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '100')
        m1 = mat.consumir(_u(cena['ana']), _loc(cena['local']),
                          {'material_id': str(cena['det']), 'quantidade': '1,5'})
        assert m1.valor == Decimal('19.35')
        m = db.session.get(Material, cena['det'])
        mat.salvar_material(m, {'nome': m.nome, 'unidade': 'L', 'preco_unitario': '0,10'})
        for _ in range(3):
            mat.consumir(_u(cena['ana']), _loc(cena['local']),
                         {'material_id': str(cena['det']), 'quantidade': '1'})
        db.session.commit()
        db.session.refresh(m1)
        assert m1.valor == Decimal('19.35')          # mudar o preço não reescreve o passado
        hoje = tempo.hoje()
        r = mat.custo([cena['local']], hoje, hoje)
        assert r['total'] == Decimal('19.65')


def test_soma_por_local_igual_a_soma_por_cliente(app_module, cena):
    from app import db
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        for cid in (cena['local'], cena['hosp']):
            _entrada(cena, cena['det'], '10', cid)
            mat.consumir(_u(cena['coord']), _loc(cid),
                         {'material_id': str(cena['det']), 'quantidade': '0,333'})
        _entrada(cena, cena['pano'], '10')
        mat.consumir(_u(cena['coord']), _loc(cena['local']),
                     {'material_id': str(cena['pano']), 'quantidade': '2'})
        db.session.commit()
        hoje = tempo.hoje()
        r = mat.custo(None, hoje, hoje)
        soma_locais = sum(x['valor'] for x in r['locais'])
        assert soma_locais == r['total'] == sum(r['clientes'].values()) \
            == sum(r['estados'].values())
        assert r['clientes']['Grupo GL'] == Decimal('8.60')     # 2 × 0,333 × 12,90 = 4,30 cada
        assert r['sem_preco'] == 1                              # o pano não tem preço
        assert r['estados'] == {'BA': Decimal('8.60')}


def test_consumo_do_mes(app_module, cena):
    from app import db
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '10')
        _entrada(cena, cena['pano'], '10')
        for qtd in ('1', '2'):
            mat.consumir(_u(cena['ana']), _loc(cena['local']),
                         {'material_id': str(cena['det']), 'quantidade': qtd})
        mat.consumir(_u(cena['ana']), _loc(cena['local']),
                     {'material_id': str(cena['pano']), 'quantidade': '1'})
        db.session.commit()
        hoje = tempo.hoje()
        linhas = {x['material'].nome: x for x in
                  mat.consumo_do_mes(cena['local'], hoje.replace(day=1), hoje)}
        assert linhas['Detergente neutro']['quantidade'] == Decimal('3.000')
        assert linhas['Detergente neutro']['valor'] == Decimal('38.70')
        assert linhas['Detergente neutro']['vezes'] == 2
        assert linhas['Pano de chão']['valor'] is None


# ── Consumo na OS ─────────────────────────────────────────────────────────

def test_consumo_na_ordem_de_servico(app_module, cena):
    from app import db
    from facilities.chamados import servico as chamados
    from facilities.materiais import servico as mat
    from facilities.materiais.servico import RegraDoMaterial
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '10')
        ch = chamados.abrir(_u(cena['coord']), cena['local'], 'Vazamento')
        db.session.commit()
        mat.consumir(_u(cena['tec']), _loc(cena['local']),
                     {'material_id': str(cena['det']), 'quantidade': '2',
                      'chamado_id': str(ch.id)})
        db.session.commit()
        assert [c.movimento.quantidade for c in mat.consumos_do_chamado(ch.id)] == \
            [Decimal('-2.000')]
        with pytest.raises(RegraDoMaterial, match='deste local'):
            mat.consumir(_u(cena['coord']), _loc(cena['hosp']),
                         {'material_id': str(cena['det']), 'quantidade': '1',
                          'chamado_id': str(ch.id)})
        cid = ch.id
    tec = fabrica.entrar(app_module, 'tec.mat@trino.com')
    html = tec.get(f'/chamados/{cid}').get_data(as_text=True)
    assert 'Material usado' in html and 'Detergente neutro' in html and 'R$' not in html
    sup = fabrica.entrar(app_module, 'sup.mat@trino.com')
    assert 'R$ 25,80' in sup.get(f'/chamados/{cid}').get_data(as_text=True)
    r = tec.post(f'/materiais/locais/{cena["local"]}/consumo',
                 data={'material_id': cena['det'], 'quantidade': '1', 'chamado_id': cid,
                       'voltar': 'chamado'})
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/chamados/{cid}')


# ── Pedido de insumo ──────────────────────────────────────────────────────

def _png():
    from tests.test_rotas_servico import _png as png
    return png()


def test_pedido_avisa_o_gestor_que_so_marca_visto(app_module, cena):
    from app import db
    from facilities.core.models import Notification
    from facilities.materiais import servico as mat
    from facilities.materiais.models import PedidoInsumo
    from facilities.materiais.servico import RegraDoMaterial
    with app_module.app.app_context():
        with pytest.raises(RegraDoMaterial, match='Diga o que está faltando'):
            mat.pedir(_u(cena['ana']), _loc(cena['local']), {})
        agora = datetime.utcnow()
        p = mat.pedir(_u(cena['ana']), _loc(cena['local']),
                      {'material_id': str(cena['pano']), 'quantidade': '5',
                       'texto': 'acabou no 2º andar'}, agora_utc=agora)
        db.session.commit()
        assert p.prazo == agora + timedelta(hours=48)
        assert p.resumo == '5 un de Pano de chão · acabou no 2º andar'
        assert Notification.query.filter_by(user_id=cena['coord'],
                                            notification_type='insumo').count() == 1
        with pytest.raises(RegraDoMaterial) as e:
            mat.marcar_visto(_u(cena['sup']), p)
        assert e.value.codigo == 403
        mat.marcar_visto(_u(cena['coord']), p)
        db.session.commit()
        assert PedidoInsumo.query.one().status == 'visto'


def test_prazo_do_pedido_do_cliente(app_module, cena):
    from app import db
    from facilities.cadastros.models import Contratante
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        db.session.get(Contratante, cena['cliente']).prazo_pedido_insumo_horas = 24
        db.session.commit()
        agora = datetime.utcnow()
        p = mat.pedir(_u(cena['ana']), _loc(cena['local']), {'texto': 'luva'}, agora_utc=agora)
        assert p.prazo == agora + timedelta(hours=24)


def test_app_consumo_e_pedido_com_foto(app_module, cena):
    from facilities.materiais.models import PedidoInsumo
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '10')
    ana = fabrica.entrar(app_module, 'ana.mat@trino.com')
    html = ana.get('/app/materiais').get_data(as_text=True)
    assert 'Detergente neutro' in html and 'R$' not in html and '12,90' not in html
    r = ana.post('/app/materiais/consumo', data={'client_id': cena['local'],
                                                 'material_id': cena['det'],
                                                 'quantidade': '20'}, follow_redirects=True)
    assert 'Saldo insuficiente' in r.get_data(as_text=True)
    r = ana.post('/app/materiais/consumo', data={'client_id': cena['local'],
                                                 'material_id': cena['det'],
                                                 'quantidade': '2'}, follow_redirects=True)
    assert 'Consumo registrado' in r.get_data(as_text=True)
    r = ana.post('/app/materiais/pedido', data={
        'client_id': cena['local'], 'texto': 'saco de lixo 100 L',
        'foto': (io.BytesIO(_png()), 'falta.png')}, content_type='multipart/form-data',
        follow_redirects=True)
    assert 'Pedido enviado' in r.get_data(as_text=True)
    with app_module.app.app_context():
        pid = PedidoInsumo.query.one().id
    coord = fabrica.entrar(app_module, 'coord.mat@trino.com')
    assert 'saco de lixo 100 L' in coord.get('/demandas/?tipo=insumo').get_data(as_text=True)
    assert coord.get(f'/materiais/pedidos/{pid}/foto').status_code == 200
    r = coord.post(f'/materiais/pedidos/{pid}/visto', follow_redirects=True)
    assert 'Marcar como visto' not in r.get_data(as_text=True)
    fora = fabrica.entrar(app_module, 'fora.mat@trino.com')
    assert fora.post('/app/materiais/consumo', data={'client_id': cena['local'],
                                                     'material_id': cena['det'],
                                                     'quantidade': '1'}).status_code == 403
    assert fora.get(f'/materiais/pedidos/{pid}/foto').status_code == 403


# ── Quem vê o custo ───────────────────────────────────────────────────────

@pytest.mark.parametrize('email, pode', [
    ('ana.mat@trino.com', False), ('tec.mat@trino.com', False),
    ('sup.mat@trino.com', True), ('coord.mat@trino.com', True),
])
def test_custo_so_para_supervisao_gestao_e_diretoria(app_module, cena, email, pode):
    c = fabrica.entrar(app_module, email)
    for url in ('/materiais/', '/materiais/custo', f'/materiais/locais/{cena["local"]}',
                f'/materiais/locais/{cena["local"]}/mes', '/materiais/pedidos'):
        assert c.get(url).status_code == (200 if pode else 403), url


def test_catalogo_e_da_gestao(app_module, cena):
    sup = fabrica.entrar(app_module, 'sup.mat@trino.com')
    assert sup.post('/materiais/', data={'nome': 'x', 'unidade': 'un'}).status_code == 403
    coord = fabrica.entrar(app_module, 'coord.mat@trino.com')
    r = coord.post('/materiais/', data={'nome': 'Luva nitrílica', 'unidade': 'par',
                                        'preco_unitario': '3,5'}, follow_redirects=True)
    assert 'Luva nitrílica' in r.get_data(as_text=True)
    r = coord.post('/materiais/', data={'nome': 'luva nitrílica', 'unidade': 'par'},
                   follow_redirects=True)
    assert 'Já existe' in r.get_data(as_text=True)


def test_mes_do_estoque_mostra_o_total(app_module, cena):
    with app_module.app.app_context():
        _entrada(cena, cena['det'], '10')
        from app import db
        from facilities.materiais import servico as mat
        mat.consumir(_u(cena['ana']), _loc(cena['local']),
                     {'material_id': str(cena['det']), 'quantidade': '1'})
        db.session.commit()
    sup = fabrica.entrar(app_module, 'sup.mat@trino.com')
    html = sup.get(f'/materiais/locais/{cena["local"]}/mes').get_data(as_text=True)
    assert 'R$ 12,90' in html
