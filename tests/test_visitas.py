"""Fase 6 — visitas de supervisão programadas (D56): a coordenação programa
a visita semanal no Shopping Centro; o agendador abre na data e avisa o
supervisor; ele faz o checklist no aplicativo; o não conforme abre UM
chamado para a gestão (F6-3)."""
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.rotas import servico as rotas
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['sup'] = fabrica.pessoa(app_module, 'sup.vis@trino.com', 'supervisor',
                                    locais=['Shopping Centro'], nome='Sueli')
        ids['sup2'] = fabrica.pessoa(app_module, 'sup2.vis@trino.com', 'supervisor',
                                     locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.vis@trino.com', 'pleno',
                                      locais=['Shopping Centro'])
        ids['enc'] = fabrica.pessoa(app_module, 'enc.vis@trino.com', 'encarregado',
                                    locais=['Shopping Centro'])
        ids['fora'] = fabrica.pessoa(app_module, 'fora.vis@trino.com', 'supervisor',
                                     locais=['Hospital Norte'])
        m = rotas.criar_modelo(loc.id, {'nome': 'Qualidade'}, None)
        rotas.publicar(m, rotas.normalizar_itens([
            {'texto': 'Uniforme completo?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao'},
            {'texto': 'Banheiros', 'tipo': 'conforme', 'obrigatorio': True}]), {}, None)
        foto = rotas.criar_modelo(loc.id, {'nome': 'Com foto'}, None)
        rotas.publicar(foto, rotas.normalizar_itens([{'texto': 'x', 'tipo': 'sim_nao'}]),
                       {'exige_foto_depois': '1'}, None)
        db.session.commit()
        ids.update(modelo=m.id, modelo_foto=foto.id)
    return ids


def _u(uid):
    from app import User, db
    return db.session.get(User, uid)


def _programar(cena, **extra):
    from app import db
    from facilities.visitas import servico
    dados = {'nome': 'Visita semanal', 'modelo_id': str(cena['modelo']), 'intervalo_dias': '7',
             'proxima_em': tempo.hoje().isoformat(), 'supervisor_id': str(cena['sup'])}
    dados.update(extra)
    p = servico.salvar_programada(fabrica.local(), None, dados, _u(cena['coord']))
    db.session.commit()
    return p


def _avisos(uid):
    from facilities.core.models import Notification
    return [n.title for n in Notification.query.filter_by(user_id=uid)]


def test_programacao_valida(app_module, cena):
    from facilities.visitas.servico import RegraDaVisita
    with app_module.app.app_context():
        with pytest.raises(RegraDaVisita, match='foto'):
            _programar(cena, modelo_id=str(cena['modelo_foto']))
        with pytest.raises(RegraDaVisita, match='não atende'):
            _programar(cena, supervisor_id=str(cena['fora']))
        with pytest.raises(RegraDaVisita, match='365'):
            _programar(cena, intervalo_dias='0')
        with pytest.raises(RegraDaVisita, match='checklist'):
            _programar(cena, modelo_id='abc')


def test_agendador_abre_uma_por_data_e_avisa_o_supervisor(app_module, cena):
    from app import db
    from facilities.visitas import servico
    from facilities.visitas.models import Visita
    with app_module.app.app_context():
        p = _programar(cena, proxima_em=(tempo.hoje() - timedelta(days=20)).isoformat())
        hoje = tempo.hoje()
        assert servico.gerar_visitas(hoje) == 1
        assert servico.gerar_visitas(hoje) == 0
        db.session.commit()
        assert Visita.query.count() == 1          # perdeu datas: abre uma só
        assert p.proxima_em > hoje
        assert any('Visita de supervisão' in t for t in _avisos(cena['sup']))
        assert not any('Visita' in t for t in _avisos(cena['sup2']))


def _visita(cena):
    from app import db
    from facilities.visitas import servico
    from facilities.visitas.models import Visita
    _programar(cena)
    servico.gerar_visitas(tempo.hoje())
    db.session.commit()
    return Visita.query.one()


def test_nao_conforme_abre_um_chamado_para_a_gestao(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_VISITA, Chamado
    from facilities.visitas import servico
    from facilities.visitas.servico import RegraDaVisita
    with app_module.app.app_context():
        v = _visita(cena)
        with pytest.raises(RegraDaVisita, match='Responda'):
            servico.registrar(_u(cena['sup']), v, {'uniforme_completo': 'sim'})
        servico.registrar(_u(cena['sup']), v, {'uniforme_completo': 'nao',
                                               'banheiros': 'nao_conforme'}, 'Faltou papel')
        db.session.commit()
        assert v.status == 'feita' and v.n_nao_conformes == 2
        ch = Chamado.query.filter_by(origem=ORIGEM_VISITA, origem_id=v.id).one()
        assert v.chamado_id == ch.id and 'Uniforme completo?' in ch.descricao
        assert any(ch.numero in t for t in _avisos(cena['coord']))
        with pytest.raises(RegraDaVisita) as e:
            servico.registrar(_u(cena['sup']), v, {'uniforme_completo': 'sim',
                                                   'banheiros': 'conforme'})
        assert e.value.codigo == 409


def test_tudo_conforme_nao_abre_chamado(app_module, cena):
    from app import db
    from facilities.chamados.models import Chamado
    from facilities.visitas import servico
    with app_module.app.app_context():
        v = _visita(cena)
        servico.registrar(_u(cena['coord']), v, {'uniforme_completo': 'sim',
                                                 'banheiros': 'conforme'})
        db.session.commit()
        assert v.chamado_id is None and Chamado.query.count() == 0


def test_so_quem_foi_designado_ou_a_gestao_faz(app_module, cena):
    from facilities.visitas import servico
    with app_module.app.app_context():
        v = _visita(cena)
        assert servico.pode_fazer(_u(cena['sup'] ), v)
        assert servico.pode_fazer(_u(cena['coord']), v)
        assert not servico.pode_fazer(_u(cena['sup2']), v)
        assert not servico.pode_fazer(_u(cena['enc']), v)
        assert not servico.pode_fazer(_u(cena['fora']), v)


def test_telas_da_visita(app_module, cena):
    with app_module.app.app_context():
        vid = _visita(cena).id
    cid = cena['local']
    coord = fabrica.entrar(app_module, 'coord.vis@trino.com')
    assert 'Visita semanal' in coord.get(f'/visitas/locais/{cid}').get_data(as_text=True)
    sup = fabrica.entrar(app_module, 'sup.vis@trino.com')
    assert sup.post(f'/visitas/locais/{cid}', data={'nome': 'x'}).status_code == 403
    assert 'Visita semanal' in sup.get('/app/visitas').get_data(as_text=True)
    assert 'Registrar a visita' in sup.get(f'/app/visitas/{vid}').get_data(as_text=True)
    assert 'Visita de supervisão' in sup.get('/demandas/?tipo=visita').get_data(as_text=True)
    r = sup.post(f'/app/visitas/{vid}', data={'r_uniforme_completo': 'nao',
                                              'r_banheiros': 'conforme'}, follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert 'não conforme(s): o chamado' in texto and 'Feita por' in texto
    fora = fabrica.entrar(app_module, 'fora.vis@trino.com')
    assert fora.get(f'/app/visitas/{vid}').status_code == 403
    assert 'Visita semanal' not in fora.get('/app/visitas').get_data(as_text=True)
    enc = fabrica.entrar(app_module, 'enc.vis@trino.com')
    assert enc.get('/app/visitas').status_code == 403
    # O encarregado vê o chamado aberto pela visita, mas não a visita em si.
    assert '/app/visitas/' not in enc.get('/demandas/').get_data(as_text=True)
