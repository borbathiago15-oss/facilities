"""Nova passagem por ÁREA, e a leitura da passagem completa.

Três defeitos da tela de passagem, os três achados no uso:

* **"O turno anterior deixou" era do contrato inteiro.** O encarregado do
  Almoxarifado chegava e lia, como sendo o turno anterior DELE, a doca
  travada da Expedição — e a passagem do Almoxarifado ficava escondida atrás
  da outra. Agora cada área tem o seu bloco (``data-area``), e a tela mostra
  o da área escolhida. Área = ``DiarioConfiguracao.area_id``; os modelos
  sem área são, juntos, a área do contrato.
* **O turno pré-selecionado era sempre o 1º do modelo.** O encarregado do
  2º Turno abria a passagem no 1º — já encerrado pelo colega —, preenchia
  tudo e levava 409 no envio. O servidor passa a dizer, por modelo e por
  data, o que já fechou, e a tela abre no primeiro turno em aberto.
* **A leitura da passagem escondia a rotina opcional.** Só a régua
  congelada (as obrigatórias) aparecia; a rotina opcional marcada, e a foto
  presa a ela, sumiam. Agora aparecem, marcadas como "opcional", sem mudar a
  aderência.
"""
import io
import json
import re
import struct
import zlib
from datetime import timedelta

import pytest

from facilities import tempo
from facilities.passagem.models import (DiarioAnexo, DiarioArea, DiarioConfiguracao,
                          DiarioTurno)
from facilities.passagem import analitico as an

TURNOS = [{'nome': '1º Turno'}, {'nome': '2º Turno'}]


def _png(cor=(30, 120, 200)):
    """Um PNG de 1x1 de verdade — o upload confere assinatura e CRC."""
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n'
            + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00' + bytes(cor)))
            + bloco(b'IEND', b''))


@pytest.fixture()
def recife(app_module):
    """Um contrato com DUAS áreas (um modelo cada) e um encarregado.

    Expedição e Almoxarifado, como na PepsiCo Fábrica Recife: mesmo
    contrato, mesmos turnos, passagens diferentes.
    """
    with app_module.app.app_context():
        db = app_module.db
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        ids = {}
        for nome_area in ('Expedição', 'Almoxarifado'):
            area = DiarioArea(client_id=cliente.id, nome=nome_area,
                              ativo=True, created_by=admin.id)
            db.session.add(area)
            db.session.flush()
            cfg = DiarioConfiguracao(
                client_id=cliente.id, area_id=area.id,
                nome=f'Passagem {nome_area}',
                turnos_json=json.dumps(TURNOS),
                campos_json=json.dumps([{'nome': 'Pedidos', 'codigo': 'pedidos',
                                         'tipo': 'numero'}]),
                atividades_json=json.dumps([
                    {'nome': 'DTS direcionados', 'codigo': 'dts',
                     'obrigatorio': True},
                    {'nome': 'Limpeza extra da doca', 'codigo': 'limpeza',
                     'obrigatorio': False}]),
                tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id)
            db.session.add(cfg)
            db.session.flush()
            ids[nome_area] = {'area': area.id, 'cfg': cfg.id}

        enc = app_module.User.query.filter_by(
            email='enc.porarea@teste.com').first()
        if enc is None:
            enc = app_module.User(name='Jefferson do Almoxarifado',
                                  email='enc.porarea@teste.com', is_active=True)
            db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = '[]'
        enc.set_password('senha12345')
        enc.clients = [cliente]
        db.session.commit()
        return {'client_id': cliente.id, 'areas': ids, 'email': enc.email,
                'admin_id': admin.id, 'enc_id': enc.id}


@pytest.fixture()
def piso(client, recife):
    client.post('/login', data={'email': recife['email'],
                                'password': 'senha12345'})
    return client


def _lancar(cl, recife, area, dia, turno='1º Turno', finalizar=True, **extra):
    corpo = {'client_id': recife['client_id'],
             'configuracao_id': recife['areas'][area]['cfg'],
             'data_turno': dia.isoformat(), 'turno': turno,
             'finalizar': finalizar}
    corpo.update(extra)
    r = cl.post('/passagem-de-turno/api/turnos', json=corpo)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['id']


def _tela(cl, recife):
    r = cl.get(f"/passagem-de-turno/turno?client_id={recife['client_id']}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _bloco(tela, chave):
    """O HTML do bloco "o turno anterior deixou" de UMA área.

    Cada bloco é um elemento ``.dt-anterior`` com ``data-area``; a fatia vai
    do atributo até o próximo bloco (ou até as pendências, depois do último).
    """
    marca = f'data-area="{chave}"'
    assert tela.count(marca) == 1, f'esperava um bloco {chave}'
    ini = tela.index(marca)
    fins = [i for i in (tela.find('class="dt-anterior', ini),
                        tela.find('Pendências em aberto', ini),
                        tela.find('dt-sem-pend', ini)) if i != -1]
    return tela[ini:min(fins)]


def _abre_visivel(tela, chave):
    """O bloco sai do servidor à vista (sem ``hidden``)?"""
    m = re.search(r'<(details|div) class="dt-anterior mb-3" data-area="%s"(.*?)>'
                  % re.escape(chave), tela, re.S)
    assert m, f'bloco {chave} não encontrado'
    return 'hidden' not in m.group(2)


def _encerrados(tela):
    m = re.search(r'<script type="application/json" id="dt-turnos-encerrados">'
                  r'(.*?)</script>', tela, re.S)
    assert m, 'a tela não trouxe os turnos encerrados'
    return json.loads(m.group(1))


# ── 1. O bloco "o turno anterior deixou" é da área ───────────────────────

def test_cada_area_ve_a_sua_ultima_passagem(app_module, piso, recife):
    """O defeito: a Expedição de ontem tapava o Almoxarifado de anteontem."""
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Almoxarifado', hoje - timedelta(days=2),
            observacao='Inventário do corredor B conferido.')
    _lancar(piso, recife, 'Expedição', hoje - timedelta(days=1),
            observacao='Doca 3 travada a tarde inteira.',
            ocorrencias=[{'tipo': 'Avaria', 'referencia': 'NF 9912',
                          'descricao': 'Pallet amassado na rua 12.'}])
    tela = _tela(piso, recife)
    alm = _bloco(tela, f"area-{recife['areas']['Almoxarifado']['area']}")
    exp = _bloco(tela, f"area-{recife['areas']['Expedição']['area']}")

    assert 'Inventário do corredor B' in alm
    assert 'Doca 3 travada' not in alm
    assert 'NF 9912' not in alm
    assert 'Doca 3 travada' in exp and 'NF 9912' in exp
    assert 'Inventário do corredor B' not in exp
    # O nome da área no cabeçalho confirma de quem é o bloco.
    assert 'Almoxarifado' in alm and 'Expedição' in exp


def test_area_sem_passagem_diz_que_ainda_nao_tem(app_module, piso, recife):
    _lancar(piso, recife, 'Expedição', tempo.hoje() - timedelta(days=1),
            observacao='Doca 3 travada.')
    tela = _tela(piso, recife)
    alm = _bloco(tela, f"area-{recife['areas']['Almoxarifado']['area']}")
    assert 'O turno anterior deixou' in alm
    assert 'Nenhuma passagem encerrada nesta área ainda.' in alm
    assert 'Doca 3 travada' not in alm


def test_contrato_sem_passagem_nenhuma_nao_desenha_o_bloco(piso, recife):
    """Contrato novo continua sem bloco — nada a dizer em área nenhuma."""
    tela = _tela(piso, recife)
    assert 'O turno anterior deixou' not in tela
    assert 'class="dt-anterior' not in tela


def test_rascunho_nao_e_turno_anterior(app_module, piso, recife):
    """Só passagem ENCERRADA é o que o turno de trás deixou."""
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Expedição', hoje - timedelta(days=3),
            observacao='Encerrada de verdade.')
    _lancar(piso, recife, 'Expedição', hoje, finalizar=False,
            observacao='Rascunho ainda sendo escrito.')
    exp = _bloco(_tela(piso, recife),
                 f"area-{recife['areas']['Expedição']['area']}")
    assert 'Encerrada de verdade.' in exp
    assert 'Rascunho ainda sendo escrito.' not in exp


def test_no_mesmo_dia_vale_o_ultimo_lancado_da_area(app_module, piso, recife):
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Expedição', hoje, turno='1º Turno',
            observacao='Manhã tranquila.')
    _lancar(piso, recife, 'Expedição', hoje, turno='2º Turno',
            observacao='Tarde com fila de carretas.')
    exp = _bloco(_tela(piso, recife),
                 f"area-{recife['areas']['Expedição']['area']}")
    assert 'Tarde com fila de carretas.' in exp
    assert 'Manhã tranquila.' not in exp


def test_modelo_inativo_da_area_continua_contando(app_module, piso, recife):
    """O modelo que a Expedição usava até o mês passado é da Expedição."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        velho = DiarioConfiguracao(
            client_id=recife['client_id'],
            area_id=recife['areas']['Expedição']['area'],
            nome='Passagem Expedição (antigo)',
            turnos_json=json.dumps(TURNOS), campos_json='[]',
            atividades_json='[]', tipos_ocorrencia_json='[]', ativo=False,
            created_by=recife['admin_id'])
        app_module.db.session.add(velho)
        app_module.db.session.flush()
        app_module.db.session.add(DiarioTurno(
            client_id=recife['client_id'], configuracao_id=velho.id,
            data_turno=hoje - timedelta(days=1), turno='1º Turno',
            status='encerrado', dados_json='{}',
            observacao='Lançada no modelo antigo.',
            created_by=recife['enc_id']))
        app_module.db.session.commit()
    tela = _tela(piso, recife)
    exp = _bloco(tela, f"area-{recife['areas']['Expedição']['area']}")
    assert 'Lançada no modelo antigo.' in exp
    # E o modelo inativo não vira um bloco próprio: ele não é escolhível.
    assert 'data-area="modelo-' not in tela


def test_modelos_sem_area_sao_a_area_do_contrato(app_module, client):
    """Contrato que nunca dividiu em áreas, com um modelo por turno.

    No CD de um modelo por turno, o turno anterior do T2 é o T1 — que
    lançou noutro modelo. Com cada modelo como área própria, o encarregado
    do T2 lia a passagem do T2 de ontem como "o turno anterior deixou".
    Sem área cadastrada, os modelos são, juntos, a área do contrato.
    """
    with app_module.app.app_context():
        db = app_module.db
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        ids = {}
        for nome, turno in (('Modelo T1', 'T1'), ('Modelo T3', 'T3')):
            cfg = DiarioConfiguracao(
                client_id=cliente.id, nome=nome,
                turnos_json=json.dumps([{'nome': turno}]), campos_json='[]',
                atividades_json='[]', tipos_ocorrencia_json='[]', ativo=True,
                created_by=admin.id)
            db.session.add(cfg)
            db.session.flush()
            ids[turno] = cfg.id
        db.session.add(DiarioTurno(
            client_id=cliente.id, configuracao_id=ids['T1'],
            data_turno=tempo.hoje(), turno='T1', status='encerrado',
            dados_json='{}', observacao='Formulários Q conferidos.',
            created_by=admin.id))
        db.session.commit()
        cid = cliente.id
    from tests.conftest import TEST_ADMIN_PASSWORD
    client.post('/login', data={'email': 'admin@grupotrino.com.br',
                                'password': TEST_ADMIN_PASSWORD})
    tela = client.get(f'/passagem-de-turno/turno?client_id={cid}').get_data(
        as_text=True)
    assert 'Formulários Q conferidos.' in _bloco(tela, 'contrato-0')
    # Um bloco só: nenhum modelo sem área vira "área" à parte.
    assert 'data-area="modelo-' not in tela


def test_so_o_bloco_da_area_inicial_sai_a_vista(app_module, piso, recife):
    """O seletor abre na primeira área (ordem de nome): Almoxarifado.

    Os outros blocos vêm escondidos; o JS troca quando a área muda.
    """
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Almoxarifado', hoje - timedelta(days=1))
    _lancar(piso, recife, 'Expedição', hoje - timedelta(days=1))
    tela = _tela(piso, recife)
    assert _abre_visivel(tela, f"area-{recife['areas']['Almoxarifado']['area']}")
    assert not _abre_visivel(tela, f"area-{recife['areas']['Expedição']['area']}")


def test_o_bloco_custa_consultas_fixas(app_module, piso, recife):
    """Dez áreas não podem virar trinta idas ao banco na abertura da tela."""
    from sqlalchemy import event

    from facilities.passagem import rotas
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Almoxarifado', hoje - timedelta(days=1),
            ocorrencias=[{'tipo': 'Avaria', 'descricao': 'Caixa molhada.'}])
    _lancar(piso, recife, 'Expedição', hoje - timedelta(days=1),
            ocorrencias=[{'tipo': 'Avaria', 'descricao': 'Pallet amassado.'}])
    with app_module.app.app_context():
        configs = DiarioConfiguracao.query.filter_by(
            client_id=recife['client_id'], ativo=True).all()
        motor = app_module.db.engine
        contagem = []

        def conta(*_a, **_k):
            contagem.append(1)

        event.listen(motor, 'before_cursor_execute', conta)
        try:
            blocos = rotas._o_que_o_turno_anterior_deixou(
                recife['client_id'], configs)
        finally:
            event.remove(motor, 'before_cursor_execute', conta)
        assert len(blocos) == 2
        assert all(b['turno'] is not None for b in blocos)
        # Modelos, último dia, candidatos, ocorrências, anexos, autores e
        # nomes de área — sete, tenha o contrato duas áreas ou dez.
        assert len(contagem) <= 7


# ── 2. O servidor diz o que já fechou, para a pré-seleção do turno ───────

def test_a_tela_informa_os_turnos_ja_encerrados_por_modelo(app_module, piso,
                                                           recife):
    hoje = tempo.hoje()
    _lancar(piso, recife, 'Expedição', hoje, turno='1º Turno')
    tela = _tela(piso, recife)
    mapa = _encerrados(tela)
    exp = str(recife['areas']['Expedição']['cfg'])
    alm = str(recife['areas']['Almoxarifado']['cfg'])
    assert mapa[exp][hoje.isoformat()] == ['1º Turno']
    # É por MODELO: o 1º Turno fechado da Expedição não fecha o do
    # Almoxarifado, que continua podendo lançar.
    assert alm not in mapa


def test_rascunho_nao_conta_como_encerrado(app_module, piso, recife):
    """Rascunho ainda pode ser retomado — a tela não deve pular por ele."""
    _lancar(piso, recife, 'Expedição', tempo.hoje(), finalizar=False)
    assert _encerrados(_tela(piso, recife)) == {}


def test_turnos_encerrados_cobrem_a_janela_e_nao_o_historico(app_module, piso,
                                                             recife):
    """Ontem entra (o 3º turno que vira a meia-noite); o mês passado, não."""
    hoje = tempo.hoje()
    ontem = hoje - timedelta(days=1)
    antigo = hoje - timedelta(days=30)
    _lancar(piso, recife, 'Expedição', ontem, turno='2º Turno')
    _lancar(piso, recife, 'Expedição', antigo, turno='1º Turno')
    mapa = _encerrados(_tela(piso, recife))
    exp = mapa[str(recife['areas']['Expedição']['cfg'])]
    assert exp[ontem.isoformat()] == ['2º Turno']
    assert antigo.isoformat() not in exp


def test_o_js_le_o_que_a_tela_escreve(app_module):
    """Template e JS combinam pelo nome: se um muda sozinho, a pré-seleção
    e a troca do bloco por área param em silêncio — nenhum erro aparece."""
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'facilities', 'static', 'js', 'diario_operacional.js'),
              encoding='utf-8') as f:
        js = f.read()
    assert "getElementById('dt-turnos-encerrados')" in js
    assert ".dt-anterior[data-area]" in js
    # A chave da área tem o mesmo formato dos dois lados.
    assert "'area-' + cfg.area_id" in js and "'contrato-0'" in js
    from facilities.passagem.rotas import _chave_da_area
    assert _chave_da_area(7, 3) == 'area-3'
    assert _chave_da_area(7, None) == 'contrato-0'
    # E a pré-seleção não é mais "sempre o primeiro".
    assert 'primeiroEmAberto(disponiveis)' in js


# ── 3. A leitura mostra a rotina opcional e a foto dela ──────────────────

def test_a_leitura_mostra_a_rotina_opcional_e_a_foto(app_module, piso, recife):
    tid = _lancar(piso, recife, 'Expedição', tempo.hoje(), dados={
        'atividade:dts': {'concluido': True},
        'atividade:limpeza': {'concluido': True,
                              'observacao': 'Doca lavada depois da avaria.'},
        'pedidos': '87'})
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'atividade': 'limpeza',
                        'arquivo': (io.BytesIO(_png()), 'doca-lavada.png')},
                  content_type='multipart/form-data')
    assert r.status_code == 201

    html = piso.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'Limpeza extra da doca' in html
    assert 'Doca lavada depois da avaria.' in html
    assert 'doca-lavada.png' in html
    assert '>opcional</span>' in html
    # A obrigatória continua lá, e vem antes da opcional.
    assert html.index('DTS direcionados') < html.index('Limpeza extra da doca')


def test_a_rotina_opcional_nao_mexe_na_aderencia(app_module, piso, recife):
    """Aparece na leitura, mas a régua continua sendo só o que era exigido."""
    tid = _lancar(piso, recife, 'Expedição', tempo.hoje(), dados={
        'atividade:dts': {'concluido': True},
        'atividade:limpeza': {'concluido': False}})
    with app_module.app.app_context():
        t = DiarioTurno.query.get(tid)
        pct, cumpridas, exigidas = an.aderencia([t], {})
        assert (pct, cumpridas, exigidas) == (100.0, 1, 1)
    html = piso.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    # Opcional não feita não é falha: sem o "Não concluído" vermelho.
    assert 'Não feita' in html
    assert 'Não concluído' not in html


def test_rotina_obrigatoria_nao_vira_opcional(app_module, piso, recife):
    tid = _lancar(piso, recife, 'Expedição', tempo.hoje(), dados={
        'atividade:dts': {'concluido': False},
        'atividade:limpeza': {'concluido': True}})
    html = piso.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert html.count('>opcional</span>') == 1
    assert 'Não concluído' in html          # a obrigatória que faltou


def test_foto_do_campo_e_foto_orfa_tambem_aparecem(app_module, piso, recife):
    """A tela oferece foto em TODA pergunta. Nenhuma pode sumir da leitura —
    nem a do campo numérico, nem a de uma pergunta que saiu do modelo."""
    tid = _lancar(piso, recife, 'Expedição', tempo.hoje(), dados={
        'atividade:dts': {'concluido': True}, 'pedidos': '87'})
    with app_module.app.app_context():
        for codigo, nome in (('pedidos', 'mapa-de-pedidos.png'),
                             ('pergunta_que_saiu', 'foto-antiga.png')):
            app_module.db.session.add(DiarioAnexo(
                turno_id=tid, atividade_codigo=codigo,
                storage_key=f'diario/anexos/teste-{codigo}.png', nome=nome,
                mime='image/png', tamanho=10, uploaded_by=recife['enc_id']))
        app_module.db.session.commit()
    html = piso.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'mapa-de-pedidos.png' in html
    assert 'foto-antiga.png' in html


def test_regua_congelada_vazia_nao_poe_o_checklist_de_hoje(app_module, piso,
                                                           recife):
    """Modelo sem rotina obrigatória no dia: a régua congelada é VAZIA.

    Antes a tela tratava isso como "turno antigo" e punha o checklist de
    hoje, com o aviso de régua não congelada. A aderência mede esse turno
    como "nada exigido" — a leitura tem de dizer a mesma coisa.
    """
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.get(recife['areas']['Expedição']['cfg'])
        cfg.atividades_json = json.dumps([
            {'nome': 'Limpeza extra da doca', 'codigo': 'limpeza',
             'obrigatorio': False}])
        app_module.db.session.commit()
    tid = _lancar(piso, recife, 'Expedição', tempo.hoje(), dados={
        'atividade:limpeza': {'concluido': True}})
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.get(recife['areas']['Expedição']['cfg'])
        # Depois do turno, a gestão torna obrigatória uma rotina nova.
        cfg.atividades_json = json.dumps([
            {'nome': 'Rotina nova', 'codigo': 'nova', 'obrigatorio': True},
            {'nome': 'Limpeza extra da doca', 'codigo': 'limpeza',
             'obrigatorio': False}])
        app_module.db.session.commit()
    html = piso.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'Rotina nova' not in html
    assert 'antes de o sistema passar a congelar' not in html
    assert 'Limpeza extra da doca' in html and '>opcional</span>' in html
