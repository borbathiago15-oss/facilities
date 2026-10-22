"""Fase 4B — o QR público (D47, Q1 a Q3).

* sem login, o QR abre o formulário; enviar cria a ocorrência sem dado
  pessoal e leva ao acompanhamento;
* vai para quem está na rota do ponto agora (e o supervisor); sem ninguém
  escalado, para supervisor e coordenador;
* prazo só quando o cliente configurou;
* a equipe atende e resolve; quem é de fora não mexe;
* robô (campo-isca), tipo inventado e foto falsa são recusados.
"""
import io

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import _png


@pytest.fixture()
def cena(app_module):
    from app import db
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ids['ana'] = fabrica.pessoa(app_module, 'ana.qr@trino.com', 'encarregado',
                                    locais=['Shopping Centro'])
        ids['sup'] = fabrica.pessoa(app_module, 'sup.qr@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.qr@trino.com', 'pleno',
                                      locais=['Shopping Centro'])
        db.session.commit()
    return ids


def _avisos(app_module, uid):
    from facilities.core.models import Notification
    with app_module.app.app_context():
        return [n.title for n in Notification.query.filter_by(user_id=uid)]


def _enviar(app_module, qr, **campos):
    c = app_module.app.test_client()
    dados = {'tipo': 'sujo', 'texto': 'piso molhado'}
    dados.update(campos)
    return c, c.post(f'/q/{qr}/ocorrencia', data=dados, content_type='multipart/form-data')


def test_publico_abre_sem_login_e_acompanha(app_module, cena):
    c = app_module.app.test_client()
    html = c.get(f"/q/{cena['qr']}").get_data(as_text=True)
    assert 'É aqui?' in html and 'Não pedimos seu nome' in html
    c, r = _enviar(app_module, cena['qr'])
    assert r.status_code == 302 and '/acompanhar/' in r.headers['Location']
    html = c.get(r.headers['Location']).get_data(as_text=True)
    assert 'Recebida' in html and 'Local sujo' in html
    with app_module.app.app_context():
        from facilities.rotas.models import OcorrenciaPublica
        oc = OcorrenciaPublica.query.one()
        cols = {col.name for col in OcorrenciaPublica.__table__.columns}
        assert not cols & {'nome', 'email', 'telefone', 'contato', 'ip'}
        assert oc.prazo is None                  # o cliente não configurou prazo
    # Token errado ou de outro QR não mostra nada.
    assert c.get(f"/q/{cena['qr']}/acompanhar/inventado").status_code == 404


def test_sem_escalado_avisa_supervisor_e_coordenador(app_module, cena):
    _enviar(app_module, cena['qr'])
    assert _avisos(app_module, cena['sup']) == ['Ocorrência: Local sujo']
    assert _avisos(app_module, cena['coord']) == ['Ocorrência: Local sujo']
    assert _avisos(app_module, cena['ana']) == []


def test_com_rota_agora_avisa_quem_esta_nela_e_o_supervisor(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        loc = fabrica.local()
        m = s.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Ok?'}]), {}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'R', 'turno': 'T', 'hora_inicio': '00:00',
                                         'hora_fim': '23:59', 'dias_semana': '1234567',
                                         'presencas_por_turno': '0'})
        s.salvar_item(rota, None, {'ponto_id': cena['ponto'], 'modelo_id': m.id,
                                   'horarios': '23:00'})
        s.salvar_escala(rota, {'user_id': cena['ana'], 'dias_semana': '1234567',
                               'data_inicio': tempo.hoje().isoformat()})
        s.garantir_hoje([loc.id])
        db.session.commit()
    _enviar(app_module, cena['qr'])
    assert _avisos(app_module, cena['ana']) == ['Ocorrência: Local sujo']
    assert _avisos(app_module, cena['sup']) == ['Ocorrência: Local sujo']
    assert _avisos(app_module, cena['coord']) == []


def test_prazo_vem_do_cliente(app_module, cena, auth_client):
    with app_module.app.app_context():
        from facilities.cadastros.models import Contratante
        cli = Contratante.query.one()
        cid, eid, nome = cli.id, cli.empresa_id, cli.nome
    r = auth_client.post(f'/cadastros/clientes/{cid}', data={'nome': nome, 'empresa_id': eid,
                                                             'prazo_sujo': '30'})
    assert r.status_code == 302
    _enviar(app_module, cena['qr'])
    with app_module.app.app_context():
        from facilities.rotas.models import OcorrenciaPublica
        oc = OcorrenciaPublica.query.one()
        assert round((oc.prazo - oc.criada_em).total_seconds() / 60) == 30
    r = auth_client.post(f'/cadastros/clientes/{cid}', data={'nome': nome, 'empresa_id': eid,
                                                             'prazo_sujo': '1'},
                         follow_redirects=True)
    assert 'de 5 a 10080' in r.get_data(as_text=True)


def test_equipe_atende_e_resolve_e_quem_e_de_fora_nao(app_module, cena):
    _c, r = _enviar(app_module, cena['qr'])
    link = r.headers['Location']
    with app_module.app.app_context():
        from facilities.rotas.models import OcorrenciaPublica
        oid = OcorrenciaPublica.query.one().id
        fabrica.pessoa(app_module, 'fora.qr@trino.com', 'encarregado', locais=['Hospital Norte'])
    fora = fabrica.entrar(app_module, 'fora.qr@trino.com')
    assert fora.post(f'/app/api/ocorrencias/{oid}/resolver', json={}).status_code == 403
    ana = fabrica.entrar(app_module, 'ana.qr@trino.com')
    assert ana.post(f'/app/api/ocorrencias/{oid}/atender', json={}).get_json()['status'] == \
        'em_atendimento'
    assert ana.post(f'/app/api/ocorrencias/{oid}/resolver',
                    json={'resolucao': 'secado'}).get_json()['status'] == 'resolvida'
    assert ana.post(f'/app/api/ocorrencias/{oid}/resolver', json={}).status_code == 409
    html = app_module.app.test_client().get(link).get_data(as_text=True)
    assert 'Resolvida' in html and 'Ana' not in html          # sem nome de ninguém


def test_ocorrencia_aparece_no_app_e_no_site(app_module, cena, auth_client):
    _enviar(app_module, cena['qr'], tipo='lixo', texto='')
    ana = fabrica.entrar(app_module, 'ana.qr@trino.com')
    assert 'Lixeira cheia' in ana.get('/app/').get_data(as_text=True)
    assert 'Lixeira cheia' in ana.get('/app/turno').get_data(as_text=True)
    assert 'Lixeira cheia' in auth_client.get(f"/rotas/locais/{cena['local']}/dia").get_data(
        as_text=True)


def test_robos_e_lixo_sao_recusados(app_module, cena):
    _c, r = _enviar(app_module, cena['qr'], site='http://spam')
    assert r.status_code == 400
    _c, r = _enviar(app_module, cena['qr'], tipo='hack')
    assert r.status_code == 400
    _c, r = _enviar(app_module, cena['qr'], tipo='outro', texto='')
    assert r.status_code == 400 and 'poucas palavras' in r.get_data(as_text=True)
    _c, r = _enviar(app_module, cena['qr'], foto=(io.BytesIO(b'<script>'), 'x.png'))
    assert r.status_code == 400
    _c, r = _enviar(app_module, cena['qr'], foto=(io.BytesIO(_png()), 'foto.png'))
    assert r.status_code == 302
    with app_module.app.app_context():
        from facilities.rotas.models import OcorrenciaPublica
        assert OcorrenciaPublica.query.count() == 1
    assert app_module.app.test_client().post('/q/naoexiste1234/ocorrencia',
                                             data={'tipo': 'sujo'}).status_code == 404


def test_limite_de_envios_esta_declarado(app_module):
    from facilities.extensions import limiter
    import inspect
    from facilities.rotas import publico
    fonte = inspect.getsource(publico.abrir_ocorrencia)
    assert "@limiter.limit('5 per hour')" in fonte
    assert "@limiter.limit('30 per hour', key_func=_chave_do_qr)" in fonte
    assert limiter is not None


def test_ponto_desativado_nao_recebe(app_module, cena):
    from app import db
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        db.session.get(PontoInspecao, cena['ponto']).is_active = False
        db.session.commit()
    c = app_module.app.test_client()
    assert 'não está mais em uso' in c.get(f"/q/{cena['qr']}").get_data(as_text=True)
    _c, r = _enviar(app_module, cena['qr'])
    assert r.status_code == 409
