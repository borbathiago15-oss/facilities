"""Rota e checklist simples (decisões do dono, 18/10/2026): "como fazer" e
foto de referência em cada pergunta; vários pontos de uma vez na rota;
modelos prontos de limpeza na biblioteca. (O roteiro numerado é do
aplicativo — static/js/rotas-turno.js.)"""
import io

import pytest

from tests import fabrica
from tests.test_rotas_servico import _png


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        pontos = [ids['ponto']]
        for n in (2, 3):
            p = cad.salvar_ponto(loc, None, {'nome': f'Porta do banheiro {n}',
                                             'ambiente_id': ids['ambiente']}, None)
            pontos.append(p.id)
        fabrica.pessoa(app_module, 'coord.rs@trino.com', 'pleno', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'asg.rs@trino.com', 'encarregado', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'fora.rs@trino.com', 'encarregado', locais=['Hospital Norte'])
        m = s.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Papel reposto?', 'tipo': 'sim_nao'}]),
                   {}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'Limpeza', 'turno': 'T1', 'hora_inicio': '07:00',
                                         'hora_fim': '15:00', 'tolerancia_min': '30',
                                         'dias_semana': '1234567'})
        db.session.commit()
        ids.update(pontos=pontos, modelo=m.id, rota=rota.id)
    return ids


def test_como_fazer_e_foto_de_referencia_pelo_editor(app_module, cena):
    from app import db
    from facilities.rotas.models import ChecklistModelo
    from facilities.rotas.servico import itens_da_versao
    c = fabrica.entrar(app_module, 'coord.rs@trino.com')
    r = c.post(f"/rotas/modelos/{cena['modelo']}", data={
        'texto': ['Papel reposto?', ''], 'tipo': ['sim_nao', 'sim_nao'],
        'opcoes': ['', ''], 'minimo': ['', ''], 'maximo': ['', ''],
        'problema_se': ['nao', ''], 'mostrar_se': ['', ''], 'codigo': ['papel_reposto', ''],
        'ordem': ['1', ''], 'como_fazer': ['Deixe 2 rolos por cabine.', ''],
        'foto_ref': ['', ''], 'foto_ref_0': (io.BytesIO(_png()), 'ref.png')},
        content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        m = db.session.get(ChecklistModelo, cena['modelo'])
        it = itens_da_versao(m.versao_atual)[0]
        vid = m.versao_atual.id
        assert m.versao_atual.numero == 2
        assert it['como_fazer'] == 'Deixe 2 rolos por cabine.'
        assert it['foto_ref'].startswith(f"checklists/{m.id}/ref/")
    # Quem é do local vê a foto; de outro local, não.
    asg = fabrica.entrar(app_module, 'asg.rs@trino.com')
    assert asg.get(f'/rotas/referencias/{vid}/papel_reposto').mimetype == 'image/png'
    assert fabrica.entrar(app_module, 'fora.rs@trino.com').get(
        f'/rotas/referencias/{vid}/papel_reposto').status_code == 403
    assert asg.get(f'/rotas/referencias/{vid}/nao_existe').status_code == 404
    # O aplicativo recebe o "como fazer" e o endereço da foto (não a chave).
    pag = asg.get('/app/turno').get_data(as_text=True)
    assert 'Deixe 2 rolos por cabine.' in pag and f'/rotas/referencias/{vid}/papel_reposto' in pag
    assert 'checklists/' not in pag


def test_chave_de_referencia_forjada_e_ignorada():
    from facilities.rotas.servico import normalizar_itens
    it = normalizar_itens([{'texto': 'X', 'foto_ref': '../../etc/passwd'}])[0]
    assert 'foto_ref' not in it


def test_varios_pontos_de_uma_vez(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota
    c = fabrica.entrar(app_module, 'coord.rs@trino.com')
    r = c.post(f"/rotas/{cena['rota']}/itens", data={
        'ponto_id': [str(p) for p in cena['pontos']], 'modelo_id': str(cena['modelo']),
        'horarios': '09:00, 13:00'}, follow_redirects=True)
    assert '3 pontos incluídos' in r.get_data(as_text=True)
    with app_module.app.app_context():
        itens = sorted(db.session.get(Rota, cena['rota']).itens, key=lambda i: i.ordem)
        assert [i.ponto_id for i in itens] == cena['pontos']
        assert [i.ordem for i in itens] == [1, 2, 3]
        assert {i.horarios for i in itens} == {'09:00, 13:00'}


def test_lote_com_horario_fora_do_turno_nao_grava_nada(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota
    c = fabrica.entrar(app_module, 'coord.rs@trino.com')
    c.post(f"/rotas/{cena['rota']}/itens", data={
        'ponto_id': [str(p) for p in cena['pontos']], 'modelo_id': str(cena['modelo']),
        'horarios': '20:00'})
    with app_module.app.app_context():
        assert db.session.get(Rota, cena['rota']).itens == []


def test_modelos_prontos_de_limpeza(app_module, auth_client):
    from facilities.rotas.biblioteca_pronta import MODELOS
    from facilities.rotas.models import ChecklistModelo
    from facilities.rotas.servico import conferir_respostas, itens_da_versao
    r = auth_client.post('/rotas/biblioteca/modelos-prontos', follow_redirects=True)
    from facilities.rotas.biblioteca_pronta import ROTAS
    assert f'{len(MODELOS) + len(ROTAS)} modelo(s) instalado(s)' in r.get_data(as_text=True)
    r = auth_client.post('/rotas/biblioteca/modelos-prontos', follow_redirects=True)
    assert 'já estavam na biblioteca' in r.get_data(as_text=True)
    with app_module.app.app_context():
        banheiro = ChecklistModelo.query.filter_by(
            client_id=None, nome='Limpeza de banheiro — padrão Trino').one()
        itens = itens_da_versao(banheiro.versao_atual)
        assert banheiro.versao_atual.exige_foto_depois
        assert sum(1 for i in itens if i.get('como_fazer')) >= 6
        # A pergunta "O que e onde?" só vale quando há dano.
        base = {i['codigo']: ('conforme' if i['tipo'] == 'conforme' else 'sim')
                for i in itens if i['tipo'] != 'texto'}
        base['dano'] = 'nao'
        _limpas, ncs = conferir_respostas(itens, base, {})
        assert ncs == []
        base['dano'] = 'sim'
        with pytest.raises(Exception, match='O que e onde'):
            conferir_respostas(itens, base, {})
        assert ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None)).count() \
            == len(MODELOS)


def test_so_o_administrador_instala_os_modelos(app_module, cena):
    c = fabrica.entrar(app_module, 'coord.rs@trino.com')
    assert c.post('/rotas/biblioteca/modelos-prontos').status_code == 403
