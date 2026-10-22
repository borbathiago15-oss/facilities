"""Rotas prontas da biblioteca (pedido do dono, 19/10/2026).

* a biblioteca já vem com as rotas de escritório e de centro de distribuição,
  e instalar de novo não duplica;
* só o administrador cria e edita a rota pronta; a gestão vê e aplica;
* aplicar num local cria o que faltar (setor, ambiente, ponto com QR, a cópia
  do checklist) e a rota com os horários, com a presença desligada;
* aplicar de novo reaproveita o que já existe; quem não monta rotas no local
  não aplica; erro no meio não grava nada.
"""
import re

import pytest

from tests import fabrica


@pytest.fixture()
def cena(app_module, auth_client):
    from facilities.rotas.models import RotaModelo
    r = auth_client.post('/rotas/biblioteca/modelos-prontos')
    assert r.status_code == 302
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'coord.rp@trino.com', 'pleno', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'fora.rp@trino.com', 'pleno', locais=['Hospital Norte'])
        fabrica.pessoa(app_module, 'asg.rp@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
        esc = RotaModelo.query.filter_by(nome='Escritório corporativo — turno diurno').one()
        cd = RotaModelo.query.filter_by(nome='Centro de distribuição — turno A (manhã)').one()
        return {'local': fabrica.local().id, 'escritorio': esc.id, 'cd': cd.id}


def _modelo(rmid):
    from app import db
    from facilities.rotas.models import RotaModelo
    return db.session.get(RotaModelo, rmid)


def _form_da_previa(html):
    """Lê a prévia como o navegador mandaria (todas as linhas marcadas)."""
    def valores(nome):
        return re.findall(rf'name="{nome}"[^>]*value="([^"]*)"', html)
    dados = {'incluir': valores('incluir'), 'setor': valores('setor'),
             'ambiente': valores('ambiente'), 'checklist_id': valores('checklist_id'),
             'horarios': valores('horarios')}
    for campo in ('nome', 'turno', 'hora_inicio', 'hora_fim', 'tolerancia_min'):
        dados[campo] = valores(campo)[0]
    dados['dias_semana'] = re.findall(r'name="dias_semana" value="(\d)" checked', html)
    return dados


def test_a_biblioteca_vem_com_as_rotas_e_nao_duplica(app_module, auth_client, cena):
    from facilities.rotas.biblioteca_pronta import ROTAS
    from facilities.rotas.models import RotaModelo
    r = auth_client.post('/rotas/biblioteca/modelos-prontos', follow_redirects=True)
    assert 'já estavam na biblioteca' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert RotaModelo.query.count() == len(ROTAS)
        cd = _modelo(cena['cd'])
        assert cd.segmento == 'Centro de distribuição / galpão'
        assert any(it.quantidade == 2 for it in cd.itens)
        # Toda linha aponta para um checklist publicado da biblioteca.
        assert all(it.checklist.client_id is None and it.checklist.versao_atual
                   for m in RotaModelo.query for it in m.itens)
    tela = auth_client.get('/rotas/biblioteca').get_data(as_text=True)
    assert 'Rotas prontas' in tela and 'Escritório corporativo — turno diurno' in tela


def test_o_administrador_edita_a_rota_pronta(app_module, auth_client, cena):
    url = f"/rotas/biblioteca/rotas/{cena['escritorio']}"
    with app_module.app.app_context():
        ck = _modelo(cena['escritorio']).itens[0].checklist_id
    r = auth_client.post(url, data={
        'nome': 'Escritório — só manhã', 'segmento': 'Escritório / corporativo',
        'turno': 'Manhã', 'hora_inicio': '06:00', 'hora_fim': '12:00', 'tolerancia_min': '20',
        'dias_semana': ['1', '2', '3'],
        'setor': ['Sanitários', ''], 'ambiente': ['Banheiro', ''],
        'checklist_id': [str(ck), ''], 'horarios': ['07:00, 09:00', ''],
        'quantidade': ['3', '1']}, follow_redirects=True)
    assert 'salva' in r.get_data(as_text=True)
    with app_module.app.app_context():
        m = _modelo(cena['escritorio'])
        assert (m.nome, m.dias_semana, m.tolerancia_min) == ('Escritório — só manhã', '123', 20)
        assert [(i.ambiente, i.horarios, i.quantidade) for i in m.itens] == \
            [('Banheiro', '07:00, 09:00', 3)]


@pytest.mark.parametrize('troca, erro', [
    ({'nome': 'Centro de distribuição — turno A (manhã)'}, 'Já existe'),
    ({'horarios': ['25:00']}, 'hor'),
    ({'quantidade': ['11']}, 'Quantidade'),
    ({'checklist_id': ['999999']}, 'checklist publicado'),
    ({'ambiente': ['']}, 'pelo menos um ambiente'),
])
def test_rota_pronta_invalida_nao_grava(app_module, auth_client, cena, troca, erro):
    with app_module.app.app_context():
        antes = _modelo(cena['escritorio'])
        nome, n = antes.nome, len(antes.itens)
        ck = antes.itens[0].checklist_id
    dados = {'nome': 'Outro nome', 'turno': 'Manhã', 'hora_inicio': '06:00',
             'hora_fim': '12:00', 'dias_semana': ['1'], 'setor': ['Sanitários'],
             'ambiente': ['Banheiro'], 'checklist_id': [str(ck)], 'horarios': ['07:00'],
             'quantidade': ['1']}
    dados.update(troca)
    r = auth_client.post(f"/rotas/biblioteca/rotas/{cena['escritorio']}", data=dados,
                         follow_redirects=True)
    assert erro in r.get_data(as_text=True)
    with app_module.app.app_context():
        depois = _modelo(cena['escritorio'])
        assert (depois.nome, len(depois.itens)) == (nome, n)


def test_so_o_administrador_cria_ou_edita(app_module, cena):
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    url = f"/rotas/biblioteca/rotas/{cena['escritorio']}"
    assert c.get(url).status_code == 200            # a gestão vê o modelo
    assert c.get('/rotas/biblioteca/rotas/nova').status_code == 403
    assert c.post(url, data={'nome': 'x'}).status_code == 403
    assert c.post('/rotas/biblioteca/rotas/nova', data={'nome': 'x'}).status_code == 403
    assert c.post(f'{url}/ativo').status_code == 403


def test_aplicar_cria_o_que_falta_e_a_rota(app_module, cena):
    from app import db
    from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
    from facilities.rotas.models import ChecklistModelo, Rota
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    assert 'Usar uma rota pronta' in c.get(f"/rotas/locais/{cena['local']}").get_data(
        as_text=True)
    previa = c.get(f"{base}?modelo={cena['cd']}").get_data(as_text=True)
    assert 'Banheiro da operação 1' in previa and 'Banheiro da operação 2' in previa
    dados = _form_da_previa(previa)
    n = len(dados['ambiente'])
    # O local não tem refeitório: desmarca; e renomeia o armazém.
    i_ref = next(i for i, a in enumerate(dados['ambiente']) if 'Refeitório' in a)
    dados['incluir'] = [str(i) for i in range(n) if i != i_ref]
    i_arm = next(i for i, a in enumerate(dados['ambiente']) if 'Armazém' in a)
    dados['ambiente'][i_arm] = 'Armazém 1 e docas 1 a 6'
    r = c.post(f"{base}/{cena['cd']}", data=dados)
    assert r.status_code == 302 and re.fullmatch(r'/rotas/\d+', r.headers['Location']), \
        r.get_data(as_text=True)[:300]
    with app_module.app.app_context():
        rota = Rota.query.filter_by(client_id=cena['local'],
                                    nome='Centro de distribuição — turno A (manhã)').one()
        assert rota.presencas_por_turno == 0
        assert rota.dias_semana == _modelo(cena['cd']).dias_semana
        assert len(rota.itens) == n - 1
        nomes = {a.nome for a in Ambiente.query.join(Setor).filter(
            Setor.client_id == cena['local'])}
        assert 'Armazém 1 e docas 1 a 6' in nomes
        assert not any('Refeitório' in a for a in nomes)
        # Cada item da rota está num ponto com QR do ambiente e usa a cópia local.
        for it in rota.itens:
            ponto = db.session.get(PontoInspecao, it.ponto_id)
            assert ponto.codigo_qr and ponto.client_id == cena['local']
            ck = db.session.get(ChecklistModelo, it.modelo_id)
            assert ck.client_id == cena['local'] and ck.origem_id is not None
        copias = ChecklistModelo.query.filter_by(client_id=cena['local']).count()
        assert copias == len({it.modelo_id for it in rota.itens})


def test_aplicar_de_novo_reaproveita(app_module, cena):
    from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
    from facilities.rotas.models import ChecklistModelo, Rota
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    dados = _form_da_previa(c.get(f"{base}?modelo={cena['escritorio']}").get_data(as_text=True))
    assert c.post(f"{base}/{cena['escritorio']}", data=dados).status_code == 302

    def contar():
        with app_module.app.app_context():
            return (Setor.query.filter_by(client_id=cena['local']).count(),
                    Ambiente.query.join(Setor).filter(Setor.client_id == cena['local']).count(),
                    PontoInspecao.query.filter_by(client_id=cena['local']).count(),
                    ChecklistModelo.query.filter_by(client_id=cena['local']).count())
    antes = contar()
    dados['nome'] = 'Escritório — sábado'
    r = c.post(f"{base}/{cena['escritorio']}", data=dados, follow_redirects=True)
    assert 'Novos neste local: 0 ambiente(s), 0 ponto(s) com QR e 0 checklist(s)' in \
        r.get_data(as_text=True)
    assert contar() == antes
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cena['local']).count() == 2


def test_erro_no_meio_nao_grava_nada(app_module, cena):
    from facilities.cadastros.models import Setor
    from facilities.rotas.models import Rota
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    dados = _form_da_previa(c.get(f"{base}?modelo={cena['escritorio']}").get_data(as_text=True))
    dados['horarios'][-1] = '23:30'              # fora do turno de 06:00 às 18:00
    with app_module.app.app_context():
        setores = Setor.query.filter_by(client_id=cena['local']).count()
    r = c.post(f"{base}/{cena['escritorio']}", data=dados, follow_redirects=True)
    assert 'alert-danger' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cena['local']).count() == 0
        assert Setor.query.filter_by(client_id=cena['local']).count() == setores


def test_checklist_de_fora_do_modelo_e_recusado(app_module, cena):
    from facilities.rotas.models import ChecklistModelo, Rota
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    dados = _form_da_previa(c.get(f"{base}?modelo={cena['escritorio']}").get_data(as_text=True))
    with app_module.app.app_context():
        do_modelo = {it.checklist_id for it in _modelo(cena['escritorio']).itens}
        outro = ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                             ChecklistModelo.id.notin_(do_modelo)).first()
    dados['checklist_id'][0] = str(outro.id)
    r = c.post(f"{base}/{cena['escritorio']}", data=dados, follow_redirects=True)
    assert 'não é desta rota pronta' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cena['local']).count() == 0


def test_quem_nao_monta_no_local_nao_aplica(app_module, cena):
    from facilities.rotas.models import Rota
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    for email in ('fora.rp@trino.com', 'asg.rp@trino.com'):
        c = fabrica.entrar(app_module, email)
        assert c.get(f"{base}?modelo={cena['escritorio']}").status_code in (403, 404)
        assert c.post(f"{base}/{cena['escritorio']}", data={
            'incluir': ['0'], 'setor': ['S'], 'ambiente': ['A'], 'checklist_id': ['1'],
            'horarios': ['08:00']}).status_code in (403, 404)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cena['local']).count() == 0


def test_rota_pronta_desativada_nao_aparece_nem_aplica(app_module, auth_client, cena):
    r = auth_client.post(f"/rotas/biblioteca/rotas/{cena['cd']}/ativo", follow_redirects=True)
    assert 'desativada' in r.get_data(as_text=True)
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    assert 'turno A (manhã)' not in c.get(base).get_data(as_text=True)
    assert c.post(f"{base}/{cena['cd']}", data={}).status_code == 404


def test_aplicar_reaproveita_setor_e_ambiente_sem_olhar_maiusculas(app_module, cena):
    """Defeito corrigido (21/10/2026): o cadastro recusa "administrativo" quando
    já existe "Administrativo"; a rota pronta precisa reaproveitar, não falhar."""
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Ambiente, Setor
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        loc = fabrica.local()
        s = cad.salvar_setor(loc, None, {'nome': 'ADMINISTRATIVO'}, None)
        db.session.flush()
        cad.salvar_ambiente(loc, None, {'nome': 'copa', 'setor_id': s.id}, None)
        db.session.commit()
    c = fabrica.entrar(app_module, 'coord.rp@trino.com')
    base = f"/rotas/locais/{cena['local']}/rota-pronta"
    dados = _form_da_previa(c.get(f"{base}?modelo={cena['escritorio']}").get_data(as_text=True))
    r = c.post(f"{base}/{cena['escritorio']}", data=dados, follow_redirects=True)
    assert 'alert-danger' not in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cena['local']).count() == 1
        assert Setor.query.filter(Setor.client_id == cena['local'],
                                  db.func.lower(Setor.nome) == 'administrativo').count() == 1
        assert Ambiente.query.filter(db.func.lower(Ambiente.nome) == 'copa').count() == 1
