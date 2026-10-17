"""O piso no Diário Operacional: perfil, régua congelada e prova anexada.

Três coisas se provam aqui, e as três nasceram de um pedido de quem usa:

* **"Vamos criar usuários que terão exclusividade de acesso a esse módulo."**
  O perfil Encarregado alcança a passagem de turno e nada mais — e isso não
  pode depender de quem cadastra lembrar de não marcar as outras caixas.
* **"Cada cliente um estilo de passagem."** Mesma lógica da régua do SLA
  Contratual, com a consequência que ela ensinou: o passado é julgado pelo
  passado. Editar o checklist hoje NÃO pode reescrever o turno de ontem.
* **"Ele poderá anexar imagens ou PDF no campo de observação."** Com a
  validação de sempre: extensão na lista e assinatura de bytes conferida.
"""
import io
import json
import struct
import zlib
from datetime import timedelta

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import (DiarioAnexo, DiarioConfiguracao, DiarioOcorrencia,
                          DiarioPendencia, DiarioTurno)
from facilities.passagem import analitico as an

ATIVIDADES = [
    {'nome': 'DTS direcionados', 'codigo': 'dts', 'obrigatorio': True},
    {'nome': '5S da área', 'codigo': 'cinco_s', 'obrigatorio': True},
]


def _png(cor=(200, 30, 30)):
    """Um PNG de 1x1 de verdade — assinatura e CRC corretos."""
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n'
            + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00' + bytes(cor)))
            + bloco(b'IEND', b''))


@pytest.fixture()
def operacao(app_module):
    """Um contrato com modelo de passagem e um encarregado ligado a ele."""
    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != cliente.id).first())
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Operação CDV',
            turnos_json=json.dumps([{'nome': 'T1'}, {'nome': 'T2'}]),
            campos_json=json.dumps([{'nome': 'Pedidos', 'codigo': 'pedidos',
                                     'tipo': 'numero'}]),
            atividades_json=json.dumps(ATIVIDADES),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)

        # A limpeza entre testes não apaga usuários (o seed estrutural fica
        # de pé), então o encarregado é reaproveitado em vez de recriado —
        # senão o segundo teste do arquivo esbarra no e-mail único.
        enc = app_module.User.query.filter_by(
            email='encarregado.diario@teste.com').first()
        if enc is None:
            enc = app_module.User(name='Encarregado do T1',
                                  email='encarregado.diario@teste.com',
                                  is_active=True)
            app_module.db.session.add(enc)
        enc.role = 'encarregado'
        enc.is_active = True
        enc.is_deleted = False
        enc.must_change_password = False
        enc.permissions_json = json.dumps([])
        enc.set_password('senha12345')
        enc.clients = [cliente]
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'outro_id': outro.id,
                'config_id': cfg.id, 'email': enc.email, 'senha': 'senha12345',
                'enc_id': enc.id, 'admin_id': admin.id}


def _outro_encarregado(app_module, client_ids):
    """Um segundo encarregado, em test_client PRÓPRIO.

    ``/login`` redireciona quem já está autenticado: reaproveitar o cliente
    do primeiro usuário deixaria a sessão dele de pé, e o teste mediria a
    pessoa errada — passando por engano.
    """
    from tests.test_authz import _make_user
    with app_module.app.app_context():
        _uid, email = _make_user(app_module, role='encarregado',
                                 client_ids=client_ids)
    novo = app_module.app.test_client()
    novo.post('/login', data={'email': email, 'password': 'senha12345'})
    return novo, email


@pytest.fixture()
def piso(client, operacao):
    """Cliente HTTP logado como o encarregado."""
    client.post('/login', data={'email': operacao['email'],
                                'password': operacao['senha']})
    return client


@pytest.fixture()
def mestre(app_module):
    """O Master, em test_client PRÓPRIO — nunca o mesmo do encarregado.

    Usar o ``auth_client`` ao lado do ``piso`` não funciona: os dois são o
    MESMO test_client, e ``/login`` redireciona quem já está autenticado.
    O segundo login não acontecia e o teste seguia medindo o primeiro
    usuário — dois testes deste arquivo passaram assim, por engano, antes
    desta fixture existir.
    """
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _salvar(cl, operacao, **extra):
    corpo = {'client_id': operacao['client_id'],
             'configuracao_id': operacao['config_id'],
             'data_turno': tempo.hoje().isoformat(), 'turno': 'T1'}
    corpo.update(extra)
    return cl.post('/passagem-de-turno/api/turnos', json=corpo)


# ── O perfil ─────────────────────────────────────────────────────────────

def test_o_encarregado_alcanca_o_diario_e_nada_mais(app_module, operacao):
    with app_module.app.app_context():
        u = app_module.User.query.get(operacao['enc_id'])
        assert u.can_view('diario_operacional') is True
        assert u.can_access('diario_operacional') is True
        assert u.e_encarregado() is True
        for modulo in ('sla', 'upload', 'absenteismo', 'action_plans',
                       'onepage', 'audit', 'team', 'projects'):
            assert u.can_access(modulo) is False, modulo
            assert u.can_view(modulo) is False, modulo


def test_marcar_modulo_no_cadastro_nao_abre_porta_para_o_encarregado(
        app_module, operacao):
    """O perfil É a permissão: caixa marcada não vale para ele.

    Sem isto, um clique errado no cadastro abriria o custo do contrato para
    o piso — e o Master veria "concedido" o que a régua nega.
    """
    with app_module.app.app_context():
        u = app_module.User.query.get(operacao['enc_id'])
        u.permissions_json = json.dumps(['sla', 'upload', 'action_plans'])
        app_module.db.session.commit()
        assert u.can_access('sla') is False
        assert u.can_access('upload') is False
        assert u.can_access('action_plans') is False
        assert u.can_access('diario_operacional') is True


def test_as_portas_fechadas_respondem_de_verdade(piso, operacao):
    """Esconder o menu não basta: a rota tem de recusar."""
    assert piso.get('/passagem-de-turno/').status_code == 200
    assert piso.get('/passagem-de-turno/turno').status_code == 200
    # Os cadastros são do administrador.
    for rota in ('/admin/usuarios', '/admin/contratos'):
        assert piso.get(rota).status_code in (302, 403), rota
    assert piso.post('/admin/contratos', data={'name': 'X'}).status_code in (302, 403)
    # A configuração do modelo é do administrador e do gestor.
    assert piso.get('/passagem-de-turno/configuracao').status_code == 302


def test_o_encarregado_ve_a_passagem_e_os_chamados_no_inicio(piso):
    """No Facilities o encarregado faz a passagem E abre chamados: o início
    mostra os dois, e nada de cadastro."""
    html = piso.get('/').get_data(as_text=True)
    assert '/passagem-de-turno/' in html and '/chamados/' in html
    assert '/admin/usuarios' not in html


def test_ele_so_ve_o_contrato_dele(piso, operacao):
    html = piso.get('/passagem-de-turno/turno').data.decode('utf8')
    assert f'value="{operacao["client_id"]}"' in html
    assert f'value="{operacao["outro_id"]}"' not in html
    # E o relatório do contrato alheio é 403, não uma tela vazia.
    assert piso.get('/passagem-de-turno/relatorio-mensal'
                    f'?client_id={operacao["outro_id"]}').status_code == 403


def test_um_contrato_so_nao_e_escolha_e_sim_informacao(piso, app_module,
                                                       operacao):
    """Menos escolha é menos erro para quem lança no fim do turno."""
    html = piso.get('/passagem-de-turno/turno').data.decode('utf8')
    with app_module.app.app_context():
        nome = app_module.Client.query.get(operacao['client_id']).name
    assert nome in html
    assert 'type="hidden" id="diario-client"' in html


def test_o_encarregado_nao_deixa_pendencia_para_a_operacao(piso, operacao):
    """Deixar pendência é do gestor; o piso resolve e registra."""
    r = piso.post('/passagem-de-turno/api/pendencias',
                  json={'client_id': operacao['client_id'], 'titulo': 'X'})
    assert r.status_code == 403


# ── A régua congelada ────────────────────────────────────────────────────

def test_editar_o_checklist_nao_reescreve_o_turno_ja_encerrado(
        piso, app_module, operacao, mestre):
    """O defeito que motivou o congelamento, em forma de teste.

    Antes: acrescentar duas rotinas derrubava um turno passado, que cumpriu
    tudo o que lhe foi pedido, de 100% para 50% — sem ninguém tocar nele.
    """
    ontem = tempo.hoje() - timedelta(days=1)
    r = piso.post('/passagem-de-turno/api/turnos', json={
        'client_id': operacao['client_id'],
        'configuracao_id': operacao['config_id'],
        'data_turno': ontem.isoformat(), 'turno': 'T1', 'finalizar': True,
        'dados': {'atividade:dts': {'concluido': True},
                  'atividade:cinco_s': {'concluido': True}}})
    assert r.status_code == 201

    with app_module.app.app_context():
        antes = an.painel(operacao['client_id'], periodo='7d')['aderencia']
    assert antes['pct'] == 100.0 and antes['exigidas'] == 2

    # O Master evolui o checklist da operação.
    assert mestre.put(f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
                    json={'atividades': ATIVIDADES + [
                        {'nome': 'Formulário Q', 'codigo': 'form_q', 'obrigatorio': True},
                        {'nome': 'Ronda', 'codigo': 'ronda', 'obrigatorio': True}]}
                      ).status_code == 200

    with app_module.app.app_context():
        depois = an.painel(operacao['client_id'], periodo='7d')['aderencia']
    assert depois['pct'] == 100.0, 'o passado foi reescrito'
    assert depois['exigidas'] == 2


def test_o_turno_novo_ja_nasce_com_a_regua_nova(piso, app_module, operacao,
                                                mestre):
    assert mestre.put(
        f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
        json={'atividades': ATIVIDADES + [
            {'nome': 'Ronda', 'codigo': 'ronda', 'obrigatorio': True}]}
    ).status_code == 200
    _salvar(piso, operacao, finalizar=True,
            dados={'atividade:dts': {'concluido': True},
                   'atividade:cinco_s': {'concluido': True}})
    with app_module.app.app_context():
        hoje = an.painel(operacao['client_id'], periodo='hoje')['aderencia']
    assert (hoje['cumpridas'], hoje['exigidas']) == (2, 3)


def test_rascunho_nao_congela_regua(piso, app_module, operacao):
    """Só o encerramento decide o que valia — o rascunho ainda vai mudar."""
    _salvar(piso, operacao, finalizar=False,
            dados={'atividade:dts': {'concluido': True}})
    with app_module.app.app_context():
        t = DiarioTurno.query.first()
        assert an.CHAVE_EXIGIDAS not in json.loads(t.dados_json)


def test_o_navegador_nao_forja_a_propria_exigencia(piso, app_module, operacao):
    """Mandar a lista vazia daria 100% de aderência de graça."""
    _salvar(piso, operacao, finalizar=True,
            dados={'atividade:dts': {'concluido': True},
                   an.CHAVE_EXIGIDAS: []})
    with app_module.app.app_context():
        t = DiarioTurno.query.first()
        congelado = json.loads(t.dados_json)[an.CHAVE_EXIGIDAS]
        assert len(congelado) == 2
        assert an.painel(operacao['client_id'], periodo='hoje')['aderencia']['pct'] == 50.0


def test_turno_antigo_sem_congelamento_ainda_e_lido(app_module, operacao):
    """Quem já estava no banco antes desta mudança não pode sumir da conta."""
    with app_module.app.app_context():
        app_module.db.session.add(DiarioTurno(
            client_id=operacao['client_id'], configuracao_id=operacao['config_id'],
            data_turno=tempo.hoje(), turno='T2', status='encerrado',
            dados_json=json.dumps({'atividade:dts': {'concluido': True}}),
            created_by=operacao['admin_id']))
        app_module.db.session.commit()
        ader = an.painel(operacao['client_id'], periodo='hoje')['aderencia']
        assert (ader['cumpridas'], ader['exigidas']) == (1, 2)


# ── Um turno por dia e por nome ──────────────────────────────────────────

def test_salvar_rascunho_e_depois_encerrar_e_o_mesmo_turno(piso, app_module,
                                                           operacao):
    """Antes isto deixava para trás um turno aberto que nunca fechava."""
    r1 = _salvar(piso, operacao, finalizar=False,
                 dados={'atividade:dts': {'concluido': True}})
    r2 = _salvar(piso, operacao, finalizar=True,
                 dados={'atividade:dts': {'concluido': True},
                        'atividade:cinco_s': {'concluido': True}})
    assert r1.get_json()['id'] == r2.get_json()['id']
    with app_module.app.app_context():
        assert DiarioTurno.query.count() == 1
        assert DiarioTurno.query.first().status == 'encerrado'


def test_reenviar_nao_duplica_pendencia_nem_ocorrencia(piso, app_module,
                                                       operacao):
    carga = {'pendencias': [{'titulo': 'Repor etiquetas', 'prioridade': 'alta'}],
             'ocorrencias': [{'tipo': 'Avaria', 'referencia': 'NF 1',
                              'descricao': 'Pallet quebrado.'}]}
    _salvar(piso, operacao, finalizar=False, dados={}, **carga)
    _salvar(piso, operacao, finalizar=True, dados={}, **carga)
    with app_module.app.app_context():
        assert DiarioPendencia.query.count() == 1
        assert DiarioOcorrencia.query.count() == 1


def test_turno_ja_encerrado_nao_e_reaberto_por_reenvio(piso, operacao):
    _salvar(piso, operacao, finalizar=True, dados={})
    r = _salvar(piso, operacao, finalizar=True, dados={})
    assert r.status_code == 409
    erro = r.get_json()['error']
    assert 'já foi encerrada' in erro
    # A recusa nomeia o MODELO, não só o turno: um contrato tem várias áreas
    # lançando o mesmo turno no mesmo dia, e "o T1 de hoje já foi encerrado"
    # não diria a qual delas a recusa se refere.
    assert 'Operação CDV' in erro and 'T1' in erro


# ── O anexo da atividade ─────────────────────────────────────────────────

def test_anexa_foto_na_observacao_da_atividade(piso, app_module, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'atividade': 'cinco_s',
                        'arquivo': (io.BytesIO(_png()), 'rua-12.png')},
                  content_type='multipart/form-data')
    assert r.status_code == 201
    anexo = r.get_json()['anexos'][0]
    assert anexo['nome'] == 'rua-12.png'
    assert anexo['atividade'] == 'cinco_s'
    assert anexo['e_imagem'] is True
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 1


def test_anexo_sem_atividade_e_da_observacao_geral(piso, app_module, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
              data={'atividade': '', 'arquivo': (io.BytesIO(_png()), 'geral.png')},
              content_type='multipart/form-data')
    with app_module.app.app_context():
        assert DiarioAnexo.query.first().atividade_codigo is None


def test_executavel_renomeado_para_pdf_e_recusado(piso, app_module, operacao):
    """A extensão é o que está escrito; a assinatura é o que o arquivo É."""
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'arquivo': (io.BytesIO(b'MZ\x90\x00executavel'), 'nota.pdf')},
                  content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'não é um PDF de verdade' in r.get_json()['error']
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 0


def test_tipo_fora_da_lista_e_recusado(piso, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'arquivo': (io.BytesIO(b'#!/bin/sh\n'), 'script.sh')},
                  content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'Tipo não aceito' in r.get_json()['error']


def test_arquivo_vazio_e_recusado(piso, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'arquivo': (io.BytesIO(b''), 'vazio.png')},
                  content_type='multipart/form-data')
    assert r.status_code == 400


def test_envio_sem_arquivo_nenhum(piso, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={}, content_type='multipart/form-data')
    assert r.status_code == 400


def test_varios_anexos_de_uma_vez(piso, app_module, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'atividade': 'cinco_s',
                        'arquivo': [(io.BytesIO(_png()), 'a.png'),
                                    (io.BytesIO(_png((9, 9, 9))), 'b.png')]},
                  content_type='multipart/form-data')
    assert r.status_code == 201
    assert len(r.get_json()['anexos']) == 2
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 2


def test_o_bom_entra_e_o_ruim_e_listado(piso, app_module, operacao):
    """Numa leva mista o que presta é gravado e o resto volta nomeado."""
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    r = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                  data={'arquivo': [(io.BytesIO(_png()), 'boa.png'),
                                    (io.BytesIO(b'MZ'), 'ruim.pdf')]},
                  content_type='multipart/form-data')
    assert r.status_code == 201
    corpo = r.get_json()
    assert [a['nome'] for a in corpo['anexos']] == ['boa.png']
    assert corpo['recusados'][0]['nome'] == 'ruim.pdf'
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 1


def test_anexo_de_turno_alheio_e_403(app_module, operacao, piso):
    """A carteira manda aqui como manda no resto."""
    from tests.test_authz import _cleanup_users

    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    forasteiro, email = _outro_encarregado(app_module, [operacao['outro_id']])
    r = forasteiro.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                    data={'arquivo': (io.BytesIO(_png()), 'x.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 403
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 0
        _cleanup_users(app_module, email)


def test_baixar_e_excluir_o_anexo(piso, app_module, operacao):
    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    aid = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                    data={'arquivo': (io.BytesIO(_png()), 'foto.png')},
                    content_type='multipart/form-data').get_json()['anexos'][0]['id']

    r = piso.get(f'/passagem-de-turno/anexos/{aid}')
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('image/png')
    # Imagem abre no navegador; não desce como anexo.
    assert 'attachment' not in r.headers.get('Content-Disposition', '')

    assert piso.delete(f'/passagem-de-turno/anexos/{aid}').status_code == 200
    with app_module.app.app_context():
        assert DiarioAnexo.query.count() == 0


def test_so_quem_anexou_ou_o_master_exclui(piso, app_module, operacao):
    from tests.test_authz import _cleanup_users

    tid = _salvar(piso, operacao, finalizar=False, dados={}).get_json()['id']
    aid = piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
                    data={'arquivo': (io.BytesIO(_png()), 'foto.png')},
                    content_type='multipart/form-data').get_json()['anexos'][0]['id']

    colega, email = _outro_encarregado(app_module, [operacao['client_id']])
    assert colega.delete(f'/passagem-de-turno/anexos/{aid}').status_code == 403
    # O Master pode.
    mestre = app_module.app.test_client()
    mestre.post('/login', data={'email': 'admin@grupotrino.com.br',
                                'password': TEST_ADMIN_PASSWORD})
    assert mestre.delete(f'/passagem-de-turno/anexos/{aid}').status_code == 200
    with app_module.app.app_context():
        _cleanup_users(app_module, email)


# ── A tela de leitura do turno ───────────────────────────────────────────

def test_a_tela_do_turno_mostra_a_prova(piso, operacao):
    """Sem esta tela o anexo entra e ninguém nunca mais o vê."""
    tid = _salvar(piso, operacao, finalizar=True,
                  dados={'atividade:dts': {'concluido': True},
                         'atividade:cinco_s': {'concluido': False,
                                               'observacao': 'Rua 12 sem organizar.'},
                         'pedidos': '312'}).get_json()['id']
    piso.post(f'/passagem-de-turno/api/turnos/{tid}/anexos',
              data={'atividade': 'cinco_s',
                    'arquivo': (io.BytesIO(_png()), 'rua-12.png')},
              content_type='multipart/form-data')

    html = piso.get(f'/passagem-de-turno/turno/{tid}').data.decode('utf8')
    assert 'rua-12.png' in html
    assert 'Rua 12 sem organizar.' in html
    assert 'Não concluído' in html and 'Concluído' in html
    assert '312' in html          # o campo numérico do turno


def test_a_tela_do_turno_respeita_a_carteira(app_module, operacao, piso):
    from tests.test_authz import _cleanup_users

    tid = _salvar(piso, operacao, finalizar=True, dados={}).get_json()['id']
    forasteiro, email = _outro_encarregado(app_module, [operacao['outro_id']])
    assert forasteiro.get(f'/passagem-de-turno/turno/{tid}').status_code == 403
    with app_module.app.app_context():
        _cleanup_users(app_module, email)


# ── O cadastro do modelo ─────────────────────────────────────────────────

def test_o_cadastro_resolve_o_contrato_sozinho(mestre):
    """Antes a tela abria vazia e o seletor de contrato não fazia nada."""
    r = mestre.get('/passagem-de-turno/configuracao')
    assert r.status_code == 200
    assert 'Modelos deste contrato' in r.data.decode('utf8')


def test_dois_modelos_no_mesmo_contrato_aparecem_na_lista(mestre, operacao):
    """Antes só o PRIMEIRO modelo de cada contrato era editável."""
    r = mestre.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': operacao['client_id'], 'nome': 'Operação Cross-docking',
        'turnos': [{'nome': 'T1'}], 'atividades': [], 'campos': [],
        'tipos_ocorrencia': []})
    assert r.status_code == 201
    html = mestre.get('/passagem-de-turno/configuracao'
                      f'?client_id={operacao["client_id"]}').data.decode('utf8')
    assert 'Operação CDV' in html and 'Operação Cross-docking' in html
    assert html.count('cf-item') >= 2


def test_modelo_desativado_some_da_tela_de_passagem(piso, mestre, operacao):
    assert mestre.put(
        f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
        json={'ativo': False}).status_code == 200
    html = piso.get('/passagem-de-turno/turno').data.decode('utf8')
    # O payload de configs vai vazio: a tela avisa em vez de oferecer o modelo.
    assert "data-configs='[]'" in html


def test_a_lista_mostra_quantos_turnos_cada_modelo_ja_amparou(piso, mestre,
                                                              operacao):
    """É o que diz se mexer naquele modelo encosta em histórico."""
    _salvar(piso, operacao, finalizar=True, dados={})
    html = mestre.get('/passagem-de-turno/configuracao'
                      f'?client_id={operacao["client_id"]}').data.decode('utf8')
    # Plural certo, e o número também vai num atributo (`data-usos`), que é
    # de onde o aviso "já foi usado em N turnos" o lê.
    assert '1 turno lançado' in html
    assert 'data-usos="1"' in html


# ── A passagem no molde do SLA Contratual ────────────────────────────────

def test_o_cabecalho_vem_preenchido_com_quem_e_onde(piso, app_module, operacao):
    """Não se pergunta o que o sistema já sabe.

    Encarregado, operação e centro de custo vêm escritos; a pessoa só decide
    data, turno e as respostas.
    """
    with app_module.app.app_context():
        cliente = app_module.Client.query.get(operacao['client_id'])
        cliente.cost_center = 'CC-TESTE-9'
        app_module.db.session.commit()
        nome_cliente = cliente.name

    html = piso.get('/passagem-de-turno/turno').data.decode('utf8')
    assert 'Nova passagem de turno' in html
    assert 'Encarregado do T1' in html      # o nome de quem está lançando
    assert nome_cliente in html
    assert 'CC-TESTE-9' in html
    assert 'Centro de custo' in html


def test_contrato_sem_centro_de_custo_mostra_travessao(piso, app_module,
                                                       operacao):
    """Campo vazio no cadastro não pode virar um rótulo solto na tela."""
    with app_module.app.app_context():
        cliente = app_module.Client.query.get(operacao['client_id'])
        cliente.cost_center = None
        app_module.db.session.commit()
    html = piso.get('/passagem-de-turno/turno').data.decode('utf8')
    assert 'Centro de custo' in html and '—' in html


def test_as_perguntas_saem_numa_lista_so_e_na_ordem_do_modelo(mestre, operacao):
    """Sim/Não e número intercalados, na ordem em que o modelo os define.

    Para quem preenche não existe "atividade" e "campo": existe a pergunta.
    A distinção segue por baixo porque tem consequência — número não é
    cumprido nem descumprido, e não entra na aderência.
    """
    r = mestre.put(f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
                   json={'perguntas': [
                       {'nome': 'O 5S foi feito?', 'codigo': 'cinco_s',
                        'tipo': 'sim_nao', 'obrigatorio': True},
                       {'nome': 'Quantos pedidos?', 'codigo': 'pedidos',
                        'tipo': 'numero', 'obrigatorio': False},
                       {'nome': 'Reconferência feita?', 'codigo': 'reconf',
                        'tipo': 'sim_nao', 'obrigatorio': True},
                       {'nome': 'Placa da carreta', 'codigo': 'placa',
                        'tipo': 'texto', 'obrigatorio': False},
                   ]})
    assert r.status_code == 200
    perguntas = r.get_json()['perguntas']
    assert [p['codigo'] for p in perguntas] == ['cinco_s', 'pedidos',
                                                'reconf', 'placa']
    assert [p['tipo'] for p in perguntas] == ['sim_nao', 'numero',
                                              'sim_nao', 'texto']


def test_a_ordem_sobrevive_a_ida_e_volta_no_banco(app_module, mestre, operacao):
    """A ordem viaja dentro do JSON — sem coluna nova, sem migração."""
    from facilities.passagem.rotas import perguntas_do_modelo
    mestre.put(f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
               json={'perguntas': [
                   {'nome': 'A', 'codigo': 'a', 'tipo': 'sim_nao'},
                   {'nome': 'B', 'codigo': 'b', 'tipo': 'numero'},
                   {'nome': 'C', 'codigo': 'c', 'tipo': 'sim_nao'},
               ]})
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.get(operacao['config_id'])
        atividades = json.loads(cfg.atividades_json)
        campos = json.loads(cfg.campos_json)
        # Guardadas separadas, como o banco sempre guardou…
        assert [x['codigo'] for x in atividades] == ['a', 'c']
        assert [x['codigo'] for x in campos] == ['b']
        # …mas remontadas na ordem em que foram cadastradas.
        assert [x['codigo'] for x in
                perguntas_do_modelo(atividades, campos)] == ['a', 'b', 'c']


def test_so_a_pergunta_de_sim_nao_entra_na_aderencia(piso, mestre, app_module,
                                                     operacao):
    """"Quantos pedidos separou" não é cumprido nem descumprido."""
    mestre.put(f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
               json={'perguntas': [
                   {'nome': 'O 5S foi feito?', 'codigo': 'cinco_s',
                    'tipo': 'sim_nao', 'obrigatorio': True},
                   {'nome': 'Reconferência feita?', 'codigo': 'reconf',
                    'tipo': 'sim_nao', 'obrigatorio': True},
                   {'nome': 'Quantos pedidos?', 'codigo': 'pedidos',
                    'tipo': 'numero', 'obrigatorio': False},
               ]})
    _salvar(piso, operacao, finalizar=True,
            dados={'atividade:cinco_s': {'concluido': True},
                   'atividade:reconf': {'concluido': False},
                   'pedidos': '287'})
    with app_module.app.app_context():
        ader = an.painel(operacao['client_id'], periodo='hoje')['aderencia']
    assert (ader['cumpridas'], ader['exigidas']) == (1, 2)


def test_o_modelo_antigo_sem_ordem_continua_sendo_lido(app_module, operacao):
    """Modelo cadastrado antes desta mudança não tem `ordem` no JSON."""
    from facilities.passagem.rotas import perguntas_do_modelo
    antigas = [{'nome': 'DTS', 'codigo': 'dts', 'obrigatorio': True},
               {'nome': '5S', 'codigo': 'cinco_s', 'obrigatorio': True}]
    campos = [{'nome': 'Pedidos', 'codigo': 'pedidos', 'tipo': 'numero'}]
    lista = perguntas_do_modelo(antigas, campos)
    assert [p['codigo'] for p in lista] == ['dts', 'cinco_s', 'pedidos']
    assert [p['tipo'] for p in lista] == ['sim_nao', 'sim_nao', 'numero']


def test_o_par_antigo_ainda_e_aceito_ao_salvar(mestre, operacao):
    """Quem já chamava com `atividades`/`campos` não quebra."""
    r = mestre.put(f'/passagem-de-turno/api/configuracoes/{operacao["config_id"]}',
                   json={'atividades': [{'nome': 'X', 'codigo': 'x',
                                         'obrigatorio': True}],
                         'campos': []})
    assert r.status_code == 200
    assert [p['codigo'] for p in r.get_json()['perguntas']] == ['x']


def test_o_dashboard_chama_a_acao_pelo_nome_certo(piso, operacao):
    """A ação primária diz "passagem", e leva à tela de passar o turno.

    O rótulo encurtou de "Nova passagem de turno" para "Nova passagem"
    quando o módulo passou a se chamar Passagem de Turno: o título da tela
    já diz "de turno", e repetir custava duas linhas no celular. O que o
    teste garante é o que importa — que o encarregado vê a ação, que ela usa
    a palavra da operação (ninguém diz "novo registro") e que ela vai para o
    lugar certo. Casar a string inteira fazia o teste reprovar uma melhora
    de rótulo.
    """
    html = piso.get('/passagem-de-turno/').data.decode('utf8')
    assert 'Nova passagem' in html
    assert '/passagem-de-turno/turno' in html
