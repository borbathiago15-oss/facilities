"""O anexo da passagem é do autor; a ocorrência que virou chamado diz qual OS.

**Anexo.** A passagem encerrada é o documento que o autor assina: corrigir é
só dele, com motivo e trilha. Mas qualquer colega do contrato prendia uma
"prova" na passagem de outro — e a tela a mostrava como parte do documento,
sem dizer quem a pôs ali —, e o autor apagava foto da passagem já encerrada
sem deixar rastro. Agora:

* anexa quem lançou a passagem, ou a gestão do contrato (e a tela diz
  "anexado por" quando não foi o autor);
* o autor continua anexando DEPOIS de encerrar — a fila do aparelho sobe as
  fotos depois do encerramento quando não há sinal;
* na passagem encerrada, só o administrador exclui anexo.

**Chamado.** No painel, a ocorrência que já virou chamado mostra "Ver
OS-00012 (situação)" no lugar de "Abrir chamado" — e a rota que abre o
chamado responde SEMPRE em JSON: o botão lia a resposta como JSON e, com um
403 em HTML, ficava travado sem mensagem nenhuma.
"""
import io
import json
import struct
import uuid
import zlib
from datetime import datetime

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import DiarioAnexo, DiarioOcorrencia, DiarioTurno


def _png():
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n'
            + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00' + bytes((10, 120, 30))))
            + bloco(b'IEND', b''))


@pytest.fixture()
def cena(app_module):
    from facilities.passagem.models import DiarioConfiguracao
    with app_module.app.app_context():
        clientes = app_module.Client.query.order_by(app_module.Client.id).all()
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=clientes[0].id, nome='Portaria e segurança — livro do turno',
            turnos_json=json.dumps([{'nome': 'Diurno'}, {'nome': 'Noturno'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Rondas realizadas', 'codigo': 'rondas',
                                         'obrigatorio': True}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Alarme disparado'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'cid': clientes[0].id, 'outro': clientes[1].id, 'cfg': cfg.id}


@pytest.fixture()
def pessoas(app_module):
    criadas = []

    def criar(nome, role, client_ids=()):
        with app_module.app.app_context():
            from app import Client, db
            u = app_module.User(name=nome, email=f'{uuid.uuid4().hex[:10]}@anexo.test',
                                role=role, must_change_password=False)
            u.set_password('senha12345')
            u.clients = [db.session.get(Client, cid) for cid in client_ids]
            db.session.add(u)
            db.session.commit()
            criadas.append(u.id)
            c = app_module.app.test_client()
            c.post('/login', data={'email': u.email, 'password': 'senha12345'})
            return c

    yield criar
    with app_module.app.app_context():
        from app import db
        for uid in criadas:
            u = db.session.get(app_module.User, uid)
            u.is_active, u.is_deleted, u.clients = False, True, []
        db.session.commit()


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _passagem(cliente_http, cena, finalizar, ocorrencias=None):
    r = cliente_http.post('/passagem-de-turno/api/turnos', json={
        'client_id': cena['cid'], 'configuracao_id': cena['cfg'],
        'data_turno': tempo.hoje().isoformat(), 'turno': 'Diurno',
        'dados': {'atividade:rondas': {'concluido': True}},
        'ocorrencias': ocorrencias or [], 'finalizar': finalizar})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['id']


def _anexar(cliente_http, turno_id, nome='foto.png', envio=None):
    dados = {'atividade': 'rondas', 'arquivo': (io.BytesIO(_png()), nome)}
    if envio:
        dados['envio'] = envio
    return cliente_http.post(f'/passagem-de-turno/api/turnos/{turno_id}/anexos',
                             data=dados, content_type='multipart/form-data')


def _n_anexos(app_module):
    with app_module.app.app_context():
        return DiarioAnexo.query.count()


# ── Quem anexa ───────────────────────────────────────────────────────────

def test_colega_do_contrato_nao_anexa_na_passagem_de_outro(app_module, cena, pessoas):
    autora = pessoas('Ana Porteira', 'encarregado', [cena['cid']])
    colega = pessoas('Beto Porteiro', 'encarregado', [cena['cid']])
    for finalizar in (False, True):
        with app_module.app.app_context():
            DiarioTurno.query.delete()
            app_module.db.session.commit()
        tid = _passagem(autora, cena, finalizar)
        r = _anexar(colega, tid, 'prova-falsa.png')
        assert r.status_code == 403
        assert r.is_json and 'Só quem lançou esta passagem' in r.get_json()['error']
        assert _n_anexos(app_module) == 0


def test_o_autor_anexa_depois_de_encerrar_como_a_fila_do_aparelho(app_module, cena,
                                                                   pessoas):
    """Sem sinal, as fotos sobem depois do encerramento — com a marca do envio."""
    autora = pessoas('Ana Porteira', 'encarregado', [cena['cid']])
    tid = _passagem(autora, cena, finalizar=True)
    envio = uuid.uuid4().hex
    assert _anexar(autora, tid, 'ronda.png', envio=envio).status_code == 201
    # O reenvio da fila (a resposta se perdeu) não duplica nem é recusado.
    r = _anexar(autora, tid, 'ronda.png', envio=envio)
    assert r.status_code == 201 and r.get_json()['repetidos'] == 1
    assert _n_anexos(app_module) == 1


def test_a_gestao_anexa_e_a_tela_diz_quem_anexou(app_module, cena, pessoas):
    autora = pessoas('Ana Porteira', 'encarregado', [cena['cid']])
    gestora = pessoas('Gabriela Gestora', 'pleno', [cena['cid']])
    tid = _passagem(autora, cena, finalizar=True)
    assert _anexar(autora, tid, 'da-autora.png').status_code == 201
    assert _anexar(gestora, tid, 'da-gestora.png').status_code == 201
    html = autora.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert 'da-gestora.png' in html and 'da-autora.png' in html
    # Só a foto que NÃO é da autora leva o nome de quem a prendeu.
    assert html.count('anexado por') == 1
    assert 'anexado por Gabriela Gestora' in html


# ── Quem exclui ──────────────────────────────────────────────────────────

def test_na_passagem_encerrada_so_o_administrador_exclui(app_module, cena, pessoas, mestre):
    autora = pessoas('Ana Porteira', 'encarregado', [cena['cid']])
    gestora = pessoas('Gabriela Gestora', 'pleno', [cena['cid']])
    tid = _passagem(autora, cena, finalizar=False)
    aid = _anexar(autora, tid).get_json()['anexos'][0]['id']
    _passagem(autora, cena, finalizar=True)            # encerra a mesma passagem
    for quem in (autora, gestora):
        r = quem.delete(f'/passagem-de-turno/anexos/{aid}')
        assert r.status_code == 403
        assert 'peça ao administrador' in r.get_json()['error']
    assert _n_anexos(app_module) == 1
    assert mestre.delete(f'/passagem-de-turno/anexos/{aid}').status_code == 200
    assert _n_anexos(app_module) == 0


def test_no_rascunho_quem_anexou_exclui_e_a_recusa_fala_administrador(app_module, cena,
                                                                      pessoas):
    autora = pessoas('Ana Porteira', 'encarregado', [cena['cid']])
    gestora = pessoas('Gabriela Gestora', 'pleno', [cena['cid']])
    tid = _passagem(autora, cena, finalizar=False)
    aid = _anexar(autora, tid).get_json()['anexos'][0]['id']
    r = gestora.delete(f'/passagem-de-turno/anexos/{aid}')
    assert r.status_code == 403
    assert r.get_json()['error'] == 'Só quem anexou (ou o administrador) pode excluir.'
    assert autora.delete(f'/passagem-de-turno/anexos/{aid}').status_code == 200


# ── A ocorrência que já virou chamado ────────────────────────────────────

def _ocorrencia_encerrada(app_module, mestre, cena, descricao):
    tid = _passagem(mestre, cena, finalizar=True, ocorrencias=[
        {'tipo': 'Alarme disparado', 'descricao': descricao, 'gravidade': 'critica'}])
    with app_module.app.app_context():
        return DiarioOcorrencia.query.filter_by(turno_id=tid, descricao=descricao).one().id


def test_o_painel_mostra_a_os_no_lugar_do_botao(app_module, mestre, cena):
    com_os = _ocorrencia_encerrada(app_module, mestre, cena, 'Alarme do bloco B às 03h')
    r = mestre.post(f'/passagem-de-turno/api/ocorrencias/{com_os}/chamado')
    assert r.status_code == 201
    numero, chamado_id = r.get_json()['numero'], r.get_json()['id']
    with app_module.app.app_context():
        o = DiarioOcorrencia.query.get(com_os)
        outra = DiarioOcorrencia(client_id=o.client_id, turno_id=o.turno_id,
                                 tipo='Alarme disparado', descricao='Portão da garagem',
                                 status='aberta', created_by=o.created_by)
        app_module.db.session.add(outra)
        app_module.db.session.commit()
        sem_os = outra.id
    html = mestre.get(f'/passagem-de-turno/?client_id={cena["cid"]}').get_data(as_text=True)
    assert f'href="/chamados/{chamado_id}"' in html
    assert f'Ver {numero}' in html
    assert f'dopAbrirChamado({sem_os}, this)' in html
    assert f'dopAbrirChamado({com_os}, this)' not in html

    # Chamado cancelado não prende a ocorrência: o botão volta.
    with app_module.app.app_context():
        from facilities.chamados.models import Chamado
        app_module.db.session.get(Chamado, chamado_id).status = 'cancelado'
        app_module.db.session.commit()
    html = mestre.get(f'/passagem-de-turno/?client_id={cena["cid"]}').get_data(as_text=True)
    assert f'Ver {numero}' not in html
    assert f'dopAbrirChamado({com_os}, this)' in html


def test_a_diretoria_ve_a_os_mas_nao_abre_chamado(app_module, mestre, cena, pessoas):
    com_os = _ocorrencia_encerrada(app_module, mestre, cena, 'Alarme do bloco C')
    numero = mestre.post(f'/passagem-de-turno/api/ocorrencias/{com_os}/chamado'
                         ).get_json()['numero']
    diretora = pessoas('Diretora', 'visualizador', [cena['cid']])
    html = diretora.get(f'/passagem-de-turno/?client_id={cena["cid"]}').get_data(as_text=True)
    assert f'Ver {numero}' in html
    assert 'Abrir chamado</button>' not in html


# ── A rota responde em JSON ──────────────────────────────────────────────

def test_ocorrencia_de_rascunho_e_recusada_em_json_com_o_status_do_servico(
        app_module, mestre, cena):
    tid = _passagem(mestre, cena, finalizar=False, ocorrencias=[
        {'tipo': 'Alarme disparado', 'descricao': 'Ainda no rascunho'}])
    with app_module.app.app_context():
        oid = DiarioOcorrencia.query.filter_by(turno_id=tid).one().id
    r = mestre.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    assert r.status_code == 409
    assert r.is_json and 'ainda não foi encerrada' in r.get_json()['error']


def test_ocorrencia_de_outro_contrato_e_403_em_json(app_module, mestre, cena, pessoas):
    oid = _ocorrencia_encerrada(app_module, mestre, cena, 'Alarme do bloco D')
    de_fora = pessoas('Gestor de outro contrato', 'pleno', [cena['outro']])
    r = de_fora.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    assert r.status_code == 403
    assert r.is_json and r.get_json()['error']


def test_ocorrencia_que_nao_existe_e_404_em_json(mestre):
    r = mestre.post('/passagem-de-turno/api/ocorrencias/987654/chamado')
    assert r.status_code == 404
    assert r.is_json and 'recarregue' in r.get_json()['error']


def test_o_botao_do_painel_nao_trava_sem_resposta_json(mestre, cena):
    html = mestre.get(f'/passagem-de-turno/?client_id={cena["cid"]}').get_data(as_text=True)
    funcao = html[html.index('window.dopAbrirChamado'):]
    funcao = funcao[:funcao.index('if (typeof Chart')]
    # A leitura do JSON tem saída de falha, e a falha de rede também: nos
    # dois casos o botão volta a funcionar e a pessoa lê o que houve.
    assert 'function () { return {ok: false, x: {}}; }' in funcao
    assert 'Sem conexão: o chamado não foi aberto' in funcao
    assert funcao.count('falhou(') >= 3
