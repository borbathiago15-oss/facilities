"""Fase 10 — fotos na visita de supervisão.

Decisões do dono: a visita obedece ao que o checklist pede (antes, depois,
por item) e aceita até 5 fotos livres; com não conformidade, as fotos vão
para o chamado como foto de "antes"; o cliente vê as visitas feitas, com as
fotos, no portal (o nome de quem fez segue o interruptor R5).
"""
import io

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import Arquivo, _png


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.rotas import servico as rotas
    from facilities.visitas import servico
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['sup'] = fabrica.pessoa(app_module, 'sup.foto@trino.com', 'supervisor',
                                    locais=['Shopping Centro'], nome='Sueli Supervisora')
        ids['fora'] = fabrica.pessoa(app_module, 'fora.foto@trino.com', 'supervisor',
                                     locais=['Hospital Norte'])
        coord = fabrica.pessoa(app_module, 'coord.foto@trino.com', 'pleno',
                               locais=['Shopping Centro'])
        m = rotas.criar_modelo(loc.id, {'nome': 'Qualidade com foto'}, None)
        rotas.publicar(m, rotas.normalizar_itens([
            {'texto': 'Extintor no lugar?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao', 'exige_foto': True}]), {'exige_foto_depois': '1'}, None)
        from app import User
        servico.salvar_programada(loc, None, {
            'nome': 'Visita com foto', 'modelo_id': str(m.id), 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat(), 'supervisor_id': str(ids['sup'])},
            db.session.get(User, coord))
        servico.gerar_visitas(tempo.hoje())
        db.session.commit()
        from facilities.visitas.models import Visita
        ids['visita'] = Visita.query.one().id
        ids['item'] = rotas.normalizar_itens([{'texto': 'Extintor no lugar?'}])[0]['codigo']
    return ids


def _registrar(app_module, cena, resposta='sim', fotos=None):
    from app import User, db
    from facilities.visitas import servico
    from facilities.visitas.models import Visita
    with app_module.app.app_context():
        v = db.session.get(Visita, cena['visita'])
        servico.registrar(db.session.get(User, cena['sup']), v, {cena['item']: resposta},
                          fotos=fotos)
        db.session.commit()
        return v.id


def test_foto_que_o_checklist_pede_e_obrigatoria(app_module, cena):
    from facilities.visitas.servico import RegraDaVisita
    item = f"item:{cena['item']}"
    with pytest.raises(RegraDaVisita, match='foto'):
        _registrar(app_module, cena, fotos={'depois': [Arquivo()]})
    with pytest.raises(RegraDaVisita, match='DEPOIS'):
        _registrar(app_module, cena, fotos={item: [Arquivo()]})
    with pytest.raises(RegraDaVisita, match='não é imagem'):
        _registrar(app_module, cena, fotos={item: [Arquivo(b'nao sou foto', 'x.png')],
                                            'depois': [Arquivo()]})
    with pytest.raises(RegraDaVisita, match='5 fotos'):
        _registrar(app_module, cena, fotos={item: [Arquivo()], 'depois': [Arquivo()],
                                            'livre': [Arquivo() for _ in range(6)]})
    from app import db
    from facilities.visitas.models import Visita, VisitaFoto
    with app_module.app.app_context():
        assert db.session.get(Visita, cena['visita']).status == 'prevista'
        assert VisitaFoto.query.count() == 0
    _registrar(app_module, cena, fotos={item: [Arquivo()], 'depois': [Arquivo()],
                                        'livre': [Arquivo(), Arquivo()]})
    with app_module.app.app_context():
        assert sorted(f.momento for f in VisitaFoto.query) == ['depois', 'item', 'livre',
                                                                'livre']


def test_nao_conforme_leva_as_fotos_ao_chamado(app_module, cena):
    from app import db
    from facilities.chamados.models import ChamadoAnexo
    from facilities.visitas.models import Visita
    item = f"item:{cena['item']}"
    _registrar(app_module, cena, 'nao', fotos={item: [Arquivo()], 'depois': [Arquivo()],
                                               'livre': [Arquivo()]})
    with app_module.app.app_context():
        v = db.session.get(Visita, cena['visita'])
        anexos = ChamadoAnexo.query.filter_by(chamado_id=v.chamado_id).all()
        assert len(anexos) == 3 and {a.momento for a in anexos} == {'antes'}
        assert {a.storage_key for a in anexos} == {f.storage_key for f in v.fotos}
        aid = anexos[0].id
    coord = fabrica.entrar(app_module, 'coord.foto@trino.com')
    r = coord.get(f'/chamados/anexos/{aid}')
    assert r.status_code == 200 and r.mimetype == 'image/png'


def test_a_foto_da_visita_segue_a_carteira(app_module, cena):
    from facilities.visitas.models import VisitaFoto
    item = f"item:{cena['item']}"
    _registrar(app_module, cena, fotos={item: [Arquivo()], 'depois': [Arquivo()]})
    with app_module.app.app_context():
        fid = VisitaFoto.query.first().id
    sup = fabrica.entrar(app_module, 'sup.foto@trino.com')
    pag = sup.get(f"/app/visitas/{cena['visita']}").get_data(as_text=True)
    assert f'/app/visitas/fotos/{fid}' in pag
    assert sup.get(f'/app/visitas/fotos/{fid}').mimetype == 'image/png'
    assert fabrica.entrar(app_module, 'fora.foto@trino.com').get(
        f'/app/visitas/fotos/{fid}').status_code == 403


def test_tela_manda_as_fotos_pelo_formulario(app_module, cena):
    from app import db
    from facilities.visitas.models import Visita
    sup = fabrica.entrar(app_module, 'sup.foto@trino.com')
    pag = sup.get(f"/app/visitas/{cena['visita']}").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in pag
    assert f"f_item:{cena['item']}" in pag and 'f_depois' in pag and 'f_livre' in pag
    r = sup.post(f"/app/visitas/{cena['visita']}", data={
        f"r_{cena['item']}": 'sim', f"f_item:{cena['item']}": (io.BytesIO(_png()), 'a.png'),
        'f_depois': (io.BytesIO(_png()), 'b.png'),
        'f_livre': [(io.BytesIO(_png()), 'c.png'), (io.BytesIO(_png()), 'd.png')]},
        content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        v = db.session.get(Visita, cena['visita'])
        assert v.status == 'feita' and len(v.fotos) == 4


def test_cliente_ve_a_visita_com_fotos_no_portal(app_module, cena):
    from app import db
    from facilities.cadastros.models import Contratante
    from facilities.visitas.models import VisitaFoto
    item = f"item:{cena['item']}"
    _registrar(app_module, cena, fotos={item: [Arquivo()], 'depois': [Arquivo()]})
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cli.foto@gl.com', cena['cliente'])
        fid = VisitaFoto.query.first().id
    c = fabrica.entrar_com_codigo(app_module, 'cli.foto@gl.com')
    pag = c.get(f"/cliente/locais/{cena['local']}").get_data(as_text=True)
    assert 'Visita com foto' in pag and f'/cliente/fotos/visita/{fid}' in pag
    assert 'Supervisor' in pag and 'Sueli Supervisora' not in pag
    assert c.get(f'/cliente/fotos/visita/{fid}').mimetype == 'image/png'
    with app_module.app.app_context():
        db.session.get(Contratante, cena['cliente']).mostrar_nome_executor = True
        db.session.commit()
    assert 'Sueli Supervisora' in c.get(f"/cliente/locais/{cena['local']}").get_data(
        as_text=True)


def test_cliente_de_outro_contratante_nao_ve_a_foto(app_module, cena):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.visitas.models import VisitaFoto
    item = f"item:{cena['item']}"
    _registrar(app_module, cena, fotos={item: [Arquivo()], 'depois': [Arquivo()]})
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        emp = cad.salvar_empresa(None, {'nome': 'Outra'}, None)
        hn = cad.salvar_contratante(None, {'nome': 'Grupo HN', 'empresa_id': emp.id}, None)
        db.session.commit()
        fabrica.cliente(app_module, 'cli.hn@hn.com', hn.id)
        fid = VisitaFoto.query.first().id
    c = fabrica.entrar_com_codigo(app_module, 'cli.hn@hn.com')
    assert c.get(f'/cliente/fotos/visita/{fid}').status_code == 404
