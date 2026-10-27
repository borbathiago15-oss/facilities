"""Cadastro simplificado: Cliente › Centro de custo › Áreas › Rotas
(decisões do dono, 27/10/2026).

* O gerente abre o cliente, cria o centro de custo e escreve as áreas, uma
  por linha: cada área ganha um QR e o checklist que combina com o nome.
* A rota é digitada em linhas — "06:00 · Banheiro 01" —; o checklist vem da
  área; a mesma área em dois horários fica num item só.
* Quem é do posto não abre; cliente de outro gerente não abre.
* O app usa o checklist da área como escopo da limpeza fora da rota.
"""
import re

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_novo_contrato import _png, base  # noqa: F401  (base é fixture)


@pytest.fixture()
def montado(app_module, base):  # noqa: F811
    """O gerente com um cliente e um centro de custo vazio."""
    import io
    import uuid
    c = fabrica.entrar(app_module, 'gerente.nc@trino.com')
    r = c.post('/novo-contrato/cliente', data={
        'nome': f'Cliente Centros {uuid.uuid4().hex[:4]}', 'empresa_id': str(base['empresa']),
        'logo': (io.BytesIO(_png()), 'logo.png')}, content_type='multipart/form-data')
    ctid = int(re.search(r'/cliente/(\d+)/local', r.headers['Location']).group(1))
    r = c.post(f'/clientes/{ctid}/centros', data={
        'name': f'CD Teste {uuid.uuid4().hex[:6]}', 'cost_center': 'CC-01',
        'estado_id': str(base['ba'])})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    cid = int(re.search(r'/centros/(\d+)$', r.headers['Location']).group(1))
    return {'c': c, 'ctid': ctid, 'cid': cid, **base}


def _areas(app_module, cid):
    from facilities.cadastros.models import PontoInspecao
    with app_module.app.app_context():
        return {p.nome: (p.id, p.checklist.nome if p.checklist else None,
                         p.ambiente.nome, p.ambiente.setor.nome)
                for p in PontoInspecao.query.filter_by(client_id=cid, is_active=True)}


def test_menu_e_lista_de_clientes(app_module, montado):
    c = montado['c']
    html = c.get('/').get_data(as_text=True)
    assert 'Áreas e rotas dos clientes' in html
    html = c.get('/clientes').get_data(as_text=True)
    assert 'Abrir o cliente' in html and 'Centro de custo CC-01' in html
    html = c.get(f"/clientes/{montado['ctid']}").get_data(as_text=True)
    assert '0 área(s) · 0 rota(s)' in html


def test_areas_uma_por_linha_com_qr_e_checklist(app_module, montado):
    c, cid = montado['c'], montado['cid']
    r = c.post(f'/centros/{cid}/areas', data={
        'areas': 'Banheiro 01\nBanheiro 02\n  Recepção  \nCopa\nbanheiro 01\n'})
    assert r.status_code == 302
    areas = _areas(app_module, cid)
    assert set(areas) == {'Banheiro 01', 'Banheiro 02', 'Recepção', 'Copa'}
    assert areas['Banheiro 01'][1] == areas['Banheiro 02'][1] == \
        'Limpeza de banheiro — padrão Trino'
    assert areas['Recepção'][1] == 'Limpeza de recepção e escritório — padrão Trino'
    assert areas['Copa'][1] == 'Limpeza de copa e cozinha — padrão Trino'
    assert areas['Copa'][2:] == ('Copa', 'Geral')         # ambiente = área; setor escondido
    with app_module.app.app_context():
        from facilities.rotas.models import ChecklistModelo
        # Uma cópia por modelo no centro de custo, não uma por área.
        assert ChecklistModelo.query.filter_by(client_id=cid).count() == 3
    html = c.get(f'/centros/{cid}').get_data(as_text=True)
    assert 'QR 001' in html and 'QR 004' in html and 'Imprimir as etiquetas QR' in html
    # Repetida: recusa o lote inteiro, dizendo qual.
    r = c.post(f'/centros/{cid}/areas', data={'areas': 'Vestiário\nCopa'},
               follow_redirects=True)
    assert 'Já existe neste centro de custo: Copa' in r.get_data(as_text=True)
    assert 'Vestiário' not in _areas(app_module, cid)


def test_trocar_o_checklist_da_area(app_module, montado):
    c, cid = montado['c'], montado['cid']
    c.post(f'/centros/{cid}/areas', data={'areas': 'Sala de reunião\nBanheiro'})
    areas = _areas(app_module, cid)
    with app_module.app.app_context():
        from facilities.rotas.models import ChecklistModelo
        banheiro = ChecklistModelo.query.filter_by(
            client_id=cid, nome='Limpeza de banheiro — padrão Trino').one().id
    r = c.post(f"/centros/{cid}/areas/{areas['Sala de reunião'][0]}/checklist",
               data={'checklist_id': str(banheiro)})
    assert r.status_code == 302
    assert _areas(app_module, cid)['Sala de reunião'][1] == 'Limpeza de banheiro — padrão Trino'


def _rota(c, cid, **campos):
    dados = {'nome': 'Banheiros — manhã', 'turno': '1º Turno', 'hora_inicio': '06:00',
             'hora_fim': '14:00', 'dias_semana': list('1234567')}
    dados.update(campos)
    r = c.post(f'/centros/{cid}/rotas', data=dados)
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    return int(re.search(r'/rotas/(\d+)$', r.headers['Location']).group(1))


def test_rota_digitada_em_linhas(app_module, montado):
    from facilities.rotas.models import RotaItem
    c, cid = montado['c'], montado['cid']
    c.post(f'/centros/{cid}/areas', data={'areas': 'Banheiro 01\nBanheiro 02'})
    areas = _areas(app_module, cid)
    b1, b2 = areas['Banheiro 01'][0], areas['Banheiro 02'][0]
    rid = _rota(c, cid)
    r = c.post(f'/centros/{cid}/rotas/{rid}/linhas', data={
        'hora': ['06:00', '06:30', '10:00', '', ''], 'area': [b1, b2, b1, '', '']})
    assert r.status_code == 302
    with app_module.app.app_context():
        itens = {i.ponto_id: i.horarios for i in RotaItem.query.filter_by(rota_id=rid)}
        assert itens == {b1: '06:00, 10:00', b2: '06:30'}
    html = c.get(f'/centros/{cid}/rotas/{rid}').get_data(as_text=True)
    ordem = [m for m in re.findall(r'data-linha="([^"]+)"', html)]
    assert ordem == ['06:00', '06:30', '10:00']
    assert 'Limpeza de banheiro — padrão Trino' in html
    # Fora do turno: a mensagem diz o turno.
    r = c.post(f'/centros/{cid}/rotas/{rid}/linhas', data={'hora': ['15:00'], 'area': [b1]},
               follow_redirects=True)
    assert 'fora do turno' in r.get_data(as_text=True)
    # Linha com horário e sem área: diz qual linha.
    r = c.post(f'/centros/{cid}/rotas/{rid}/linhas', data={'hora': ['07:00'], 'area': ['']},
               follow_redirects=True)
    assert 'Linha 1: escolha a área.' in r.get_data(as_text=True)
    # Tirar um horário: o outro da mesma área fica; tirar o último tira a área.
    with app_module.app.app_context():
        it1 = RotaItem.query.filter_by(rota_id=rid, ponto_id=b1).one().id
        it2 = RotaItem.query.filter_by(rota_id=rid, ponto_id=b2).one().id
    c.post(f'/centros/{cid}/rotas/{rid}/linhas/{it1}/remover', data={'hora': '06:00'})
    c.post(f'/centros/{cid}/rotas/{rid}/linhas/{it2}/remover', data={'hora': '06:30'})
    with app_module.app.app_context():
        from app import db
        assert db.session.get(RotaItem, it1).horarios == '10:00'
        assert db.session.get(RotaItem, it2).is_active is False


def test_escala_e_tarefas_no_app(app_module, montado):
    import json
    from app import Client, db
    c, cid = montado['c'], montado['cid']
    c.post(f'/centros/{cid}/areas', data={'areas': 'Banheiro 01\nAuditório'})
    areas = _areas(app_module, cid)
    rid = _rota(c, cid, hora_inicio='00:00', hora_fim='23:59')
    agora = tempo.agora()
    c.post(f'/centros/{cid}/rotas/{rid}/linhas',
           data={'hora': [agora.strftime('%H:%M')], 'area': [areas['Banheiro 01'][0]]})
    with app_module.app.app_context():
        nome = db.session.get(Client, cid).name
        ana = fabrica.pessoa(app_module, 'ana.centros@trino.com', 'encarregado',
                             locais=[nome], nome='Ana Centros')
    r = c.post(f'/centros/{cid}/rotas/{rid}/escala', data={'user_id': str(ana),
                                                          'data_inicio': agora.date().isoformat()})
    assert r.status_code == 302
    assert 'Ana Centros' in c.get(f'/centros/{cid}/rotas/{rid}').get_data(as_text=True)
    app_ana = fabrica.entrar(app_module, 'ana.centros@trino.com')
    html = app_ana.get(f'/app/turno?local={cid}').get_data(as_text=True)
    dados = json.loads(re.search(r'id="turno-dados">(.*?)</script>', html, re.S).group(1))
    assert [t['ponto_nome'] for t in dados['tarefas'] if t['minha']] == ['Banheiro 01']
    # A área fora da rota (Auditório) tem o checklist dela como escopo.
    with app_module.app.app_context():
        from facilities.cadastros.models import PontoInspecao
        aud = db.session.get(PontoInspecao, areas['Auditório'][0])
        qr, vid = aud.codigo_qr, aud.checklist.versao_atual.id
    assert dados['pontos'][qr]['escopo'] == [vid]


def test_quem_nao_monta_nao_abre(app_module, montado):
    cid, ctid = montado['cid'], montado['ctid']
    from app import Client, db
    with app_module.app.app_context():
        nome = db.session.get(Client, cid).name
        fabrica.pessoa(app_module, 'enc.centros@trino.com', 'encarregado', locais=[nome])
        fabrica.pessoa(app_module, 'outro.gerente@trino.com', 'gerente')
    enc = fabrica.entrar(app_module, 'enc.centros@trino.com')
    for url in ('/clientes', f'/clientes/{ctid}', f'/centros/{cid}'):
        assert enc.get(url).status_code == 403
    assert enc.post(f'/centros/{cid}/areas', data={'areas': 'X'}).status_code == 403
    # Outro gerente: o cliente e o centro não são dele.
    outro = fabrica.entrar(app_module, 'outro.gerente@trino.com')
    assert outro.get(f'/clientes/{ctid}').status_code == 403
    assert outro.get(f'/centros/{cid}').status_code in (403, 404)


def test_copia_desativada_nao_volta_sozinha(app_module, montado):
    """O checklist que a gestão desativou não volta: a área nova fica sem
    checklist, e a rota pede para escolher um."""
    from app import db
    from facilities.rotas.models import ChecklistModelo
    c, cid = montado['c'], montado['cid']
    c.post(f'/centros/{cid}/areas', data={'areas': 'Banheiro 01'})
    with app_module.app.app_context():
        ChecklistModelo.query.filter_by(client_id=cid).one().is_active = False
        db.session.commit()
    r = c.post(f'/centros/{cid}/areas', data={'areas': 'Banheiro 02'})
    assert r.status_code == 302
    areas = _areas(app_module, cid)
    assert areas['Banheiro 02'][1] is None
    rid = _rota(c, cid)
    r = c.post(f'/centros/{cid}/rotas/{rid}/linhas',
               data={'hora': ['06:00'], 'area': [areas['Banheiro 02'][0]]},
               follow_redirects=True)
    assert 'está sem checklist' in r.get_data(as_text=True)
