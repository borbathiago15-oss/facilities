"""Chamados / ordens de serviço — o ciclo, quem pode o quê, o prazo e os avisos.

Cada regra com o seu contraexemplo:

* abrir vale para quem age no módulo, só no contrato da carteira, só com área
  do próprio contrato; a diretoria lê e não abre;
* o ciclo aberto → em atendimento → aguardando → resolvido → fechado grava a
  trilha e avisa a pessoa certa em cada passo (e só ela);
* atribuir é do gestor, e só a quem atende o contrato; resolver é do
  responsável (ou do gestor); confirmar e reabrir são de quem pediu;
* o prazo sai da prioridade, recalcula da ABERTURA quando a prioridade muda,
  e "atrasado" não conta o que já foi resolvido;
* foto com conteúdo que não confere é recusada; anexo de contrato alheio, 403.
"""
import io
import struct
import zlib
from datetime import datetime, timedelta

import pytest

from facilities.chamados import servico
from facilities.chamados.models import Chamado, ChamadoAnexo, ChamadoEvento
from facilities.core.models import Notification


def _pessoa(app_module, email, papel, contratos, nome=None):
    from app import Client, User, db
    u = User.query.filter_by(email=email).first()
    if u is None:
        u = User(name=nome or email.split('@')[0].title(), email=email)
        db.session.add(u)
    u.role = papel
    u.is_active = True
    u.is_deleted = False
    u.all_clients = False
    u.must_change_password = False
    u.permissions_json = '[]'
    u.set_password('senha12345')
    db.session.flush()
    u.clients = [db.session.get(Client, c) for c in contratos]
    return u


@pytest.fixture()
def cena(app_module):
    with app_module.app.app_context():
        from app import Client, db
        c1, c2 = Client.query.order_by(Client.id).limit(2).all()
        gestora = _pessoa(app_module, 'gestora.ch@trino.com', 'pleno', [c1.id], 'Gestora Ana')
        enc = _pessoa(app_module, 'enc.ch@trino.com', 'encarregado', [c1.id], 'Encarregado Bia')
        tec = _pessoa(app_module, 'tec.ch@trino.com', 'tecnico', [c1.id], 'Técnico Caio')
        tec2 = _pessoa(app_module, 'tec2.ch@trino.com', 'tecnico', [c1.id], 'Técnico Davi')
        fora = _pessoa(app_module, 'tec.fora@trino.com', 'tecnico', [c2.id], 'Técnico de Fora')
        dir_ = _pessoa(app_module, 'dir.ch@trino.com', 'visualizador', [c1.id], 'Diretora Eva')
        gestor_outro = _pessoa(app_module, 'gestor.outro@trino.com', 'pleno', [c2.id], 'Gestor Outro')
        c1.responsible_user_id = gestora.id
        db.session.commit()
        ids = {'c1': c1.id, 'c2': c2.id, 'gestora': gestora.id, 'enc': enc.id,
               'tec': tec.id, 'tec2': tec2.id, 'fora': fora.id, 'dir': dir_.id,
               'gestor_outro': gestor_outro.id}
    yield ids
    with app_module.app.app_context():
        from app import Client, db
        db.session.get(Client, ids['c1']).responsible_user_id = None
        db.session.commit()


def _entrar(app_module, email):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': email, 'password': 'senha12345'})
    assert r.status_code == 302, r.get_data(as_text=True)
    return c


def _abrir(cliente, cena, **kw):
    dados = {'client_id': cena['c1'], 'titulo': 'Torneira vazando no banheiro',
             'local': 'Bloco B, 2º andar', 'categoria': 'hidraulica', 'prioridade': 'media'}
    dados.update(kw)
    return cliente.post('/chamados/', data=dados)


def _ultimo():
    return Chamado.query.order_by(Chamado.id.desc()).first()


def _acao(cliente, ch_id, acao, **kw):
    return cliente.post(f'/chamados/{ch_id}/acao', data=dict(acao=acao, **kw))


def _avisos(uid):
    return [n.title for n in Notification.query.filter_by(user_id=uid,
                                                          notification_type='chamado')]


def _png():
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', ihdr)
            + bloco(b'IDAT', zlib.compress(b'\x00\x10\x20\x30')) + bloco(b'IEND', b''))


# ── Abrir ────────────────────────────────────────────────────────────────

def test_encarregado_abre_e_os_gestores_do_contrato_sao_avisados(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    r = _abrir(enc, cena)
    assert r.status_code == 302
    with app_module.app.app_context():
        ch = _ultimo()
        assert r.headers['Location'].endswith(f'/chamados/{ch.id}')
        assert (ch.status, ch.solicitante_id, ch.client_id) == ('aberto', cena['enc'], cena['c1'])
        assert ch.numero == f'OS-{ch.id:05d}'
        # Prazo da prioridade média: 72h a partir da abertura.
        assert abs((ch.prazo - ch.aberto_em) - timedelta(hours=72)) < timedelta(seconds=2)
        assert [e.tipo for e in ch.eventos] == ['aberto']
        assert len(_avisos(cena['gestora'])) == 1
        # O gestor de OUTRO contrato e o técnico não recebem.
        assert _avisos(cena['gestor_outro']) == []
        assert _avisos(cena['tec']) == []
        # Quem abriu não é avisado do próprio chamado.
        assert _avisos(cena['enc']) == []


@pytest.mark.parametrize('prioridade,horas', [('urgente', 4), ('alta', 24), ('baixa', 168)])
def test_o_prazo_sai_da_prioridade(app_module, cena, prioridade, horas):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena, prioridade=prioridade)
    with app_module.app.app_context():
        ch = _ultimo()
        assert abs((ch.prazo - ch.aberto_em) - timedelta(hours=horas)) < timedelta(seconds=2)


def test_nao_abre_em_contrato_fora_da_carteira(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    r = _abrir(enc, cena, client_id=cena['c2'])
    assert r.status_code == 302 and '/chamados/novo' in r.headers['Location']
    with app_module.app.app_context():
        assert Chamado.query.count() == 0


def test_nao_aceita_area_de_outro_contrato(app_module, cena):
    from facilities.passagem.models import DiarioArea
    with app_module.app.app_context():
        from app import db
        area = DiarioArea(client_id=cena['c2'], nome='Portaria', ativo=True)
        db.session.add(area)
        db.session.commit()
        area_id = area.id
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena, area_id=area_id)
    with app_module.app.app_context():
        assert Chamado.query.count() == 0


def test_sem_titulo_nao_abre(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena, titulo='   ')
    with app_module.app.app_context():
        assert Chamado.query.count() == 0


def test_a_diretoria_le_mas_nao_abre(app_module, cena):
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(gestora, cena)
    diretora = _entrar(app_module, 'dir.ch@trino.com')
    assert diretora.get('/chamados/').status_code == 200
    with app_module.app.app_context():
        ch_id = _ultimo().id
    assert diretora.get(f'/chamados/{ch_id}').status_code == 200
    assert 'Abrir chamado' not in diretora.get('/chamados/').get_data(as_text=True)
    assert _abrir(diretora, cena).status_code == 403
    assert _acao(diretora, ch_id, 'comentar', texto='Oi').status_code == 403


# ── O ciclo ──────────────────────────────────────────────────────────────

def test_o_ciclo_completo_grava_a_trilha_e_avisa_quem_precisa(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id

    assert _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec']).status_code == 302
    with app_module.app.app_context():
        assert _ultimo().responsavel_id == cena['tec']
        assert len(_avisos(cena['tec'])) == 1

    _acao(tec, ch_id, 'iniciar')
    # Esperar exige dizer o quê.
    _acao(tec, ch_id, 'aguardar', texto='')
    with app_module.app.app_context():
        assert _ultimo().status == 'em_atendimento'
    _acao(tec, ch_id, 'aguardar', texto='Peça de reposição chega amanhã')
    with app_module.app.app_context():
        assert _ultimo().status == 'aguardando'
        assert _ultimo().motivo_espera == 'Peça de reposição chega amanhã'
    _acao(tec, ch_id, 'retomar')
    _acao(tec, ch_id, 'resolver', texto='')            # sem dizer o que fez: recusa
    with app_module.app.app_context():
        assert _ultimo().status == 'em_atendimento'
    _acao(tec, ch_id, 'resolver', texto='Troquei o reparo da torneira')
    with app_module.app.app_context():
        ch = _ultimo()
        assert ch.status == 'resolvido' and ch.solucao == 'Troquei o reparo da torneira'
        assert ch.resolvido_em is not None
        assert len(_avisos(cena['enc'])) == 1          # quem pediu confere

    _acao(enc, ch_id, 'confirmar')
    with app_module.app.app_context():
        ch = _ultimo()
        assert ch.status == 'fechado' and ch.fechado_em is not None
        assert [e.tipo for e in ch.eventos] == [
            'aberto', 'atribuido', 'iniciado', 'aguardando', 'retomado', 'resolvido', 'fechado']
    # Fechado: mais nada se faz, nem comentar.
    assert _acao(enc, ch_id, 'comentar', texto='Obrigado').status_code == 302
    with app_module.app.app_context():
        assert ChamadoEvento.query.filter_by(chamado_id=ch_id, tipo='comentario').count() == 0


def test_quem_pediu_reabre_e_o_responsavel_e_avisado(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    _acao(tec, ch_id, 'resolver', texto='Apertei a conexão')
    _acao(enc, ch_id, 'reabrir', texto='Continua pingando')
    with app_module.app.app_context():
        ch = _ultimo()
        assert ch.status == 'em_atendimento' and ch.resolvido_em is None
        assert any('reaberto' in t for t in _avisos(cena['tec']))


def test_tecnico_que_inicia_sem_atribuicao_vira_responsavel(app_module, cena):
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(gestora, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'iniciar')
    with app_module.app.app_context():
        assert _ultimo().responsavel_id == cena['gestora']


# ── Quem pode o quê ──────────────────────────────────────────────────────

def test_so_o_gestor_atribui_e_so_a_quem_atende_o_contrato(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(tec, ch_id, 'atribuir', responsavel_id=cena['tec'])        # técnico não atribui
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['fora'])   # de outro contrato
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['enc'])    # encarregado não atende
    with app_module.app.app_context():
        assert _ultimo().responsavel_id is None


def test_tecnico_que_nao_e_o_responsavel_nao_resolve(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    outro = _entrar(app_module, 'tec2.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(outro, ch_id, 'iniciar')
    _acao(outro, ch_id, 'resolver', texto='Fiz eu')
    with app_module.app.app_context():
        assert _ultimo().status == 'aberto'


def test_so_quem_pediu_ou_o_gestor_confirma(app_module, cena):
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(gestora, cena)                       # quem pediu foi a gestora
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    _acao(tec, ch_id, 'resolver', texto='Feito')
    _acao(tec, ch_id, 'confirmar')              # o técnico não confirma o próprio serviço
    _acao(enc, ch_id, 'confirmar')              # nem um encarregado que não pediu
    with app_module.app.app_context():
        assert _ultimo().status == 'resolvido'
    _acao(gestora, ch_id, 'confirmar')
    with app_module.app.app_context():
        assert _ultimo().status == 'fechado'


def test_cancelar_e_do_gestor_e_exige_motivo(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(enc, ch_id, 'cancelar', texto='Abri errado')
    _acao(gestora, ch_id, 'cancelar', texto='')
    with app_module.app.app_context():
        assert _ultimo().status == 'aberto'
    _acao(gestora, ch_id, 'cancelar', texto='Duplicado da OS anterior')
    with app_module.app.app_context():
        assert _ultimo().status == 'cancelado'
        assert any('cancelado' in t for t in _avisos(cena['enc']))


def test_contrato_alheio_nao_abre_o_chamado(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    fora = _entrar(app_module, 'tec.fora@trino.com')
    assert fora.get(f'/chamados/{ch_id}').status_code == 403
    assert _acao(fora, ch_id, 'comentar', texto='x').status_code == 403
    assert 'Torneira' not in fora.get('/chamados/?visao=todos').get_data(as_text=True)
    assert fora.get(f'/chamados/?client_id={cena["c1"]}').status_code == 403


# ── Prazo e números ──────────────────────────────────────────────────────

def test_mudar_prioridade_recalcula_o_prazo_desde_a_abertura(app_module, cena):
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(gestora, cena, prioridade='baixa')
    with app_module.app.app_context():
        from app import db
        ch = _ultimo()
        ch.aberto_em = datetime.utcnow() - timedelta(days=3)
        ch.prazo = servico.prazo_para('baixa', ch.aberto_em)
        db.session.commit()
        ch_id = ch.id
        assert not _ultimo().atrasado()
    _acao(gestora, ch_id, 'prioridade', prioridade='urgente', texto='Vazamento aumentou')
    with app_module.app.app_context():
        ch = _ultimo()
        assert ch.prioridade == 'urgente'
        assert abs((ch.prazo - ch.aberto_em) - timedelta(hours=4)) < timedelta(seconds=2)
        assert ch.atrasado()


def test_indicadores_e_atrasado_nao_conta_o_resolvido(app_module, cena):
    from app import db
    agora = datetime.utcnow()
    with app_module.app.app_context():
        def novo(status, aberto_ha_h, prazo_h, resolvido_ha_h=None):
            ch = Chamado(client_id=cena['c1'], titulo='x', status=status,
                         solicitante_id=cena['enc'], prioridade='media',
                         aberto_em=agora - timedelta(hours=aberto_ha_h),
                         prazo=agora - timedelta(hours=aberto_ha_h) + timedelta(hours=prazo_h))
            if resolvido_ha_h is not None:
                ch.resolvido_em = agora - timedelta(hours=resolvido_ha_h)
            db.session.add(ch)
        novo('aberto', 10, 4)                    # atrasado
        novo('em_atendimento', 1, 24)            # no prazo
        novo('resolvido', 30, 24, resolvido_ha_h=2)   # resolvido depois do prazo (28h)
        novo('fechado', 50, 72, resolvido_ha_h=40)    # resolvido no prazo (10h)
        db.session.commit()
        n = servico.indicadores([cena['c1']], agora=agora)
        assert (n['em_aberto'], n['atrasados'], n['aguardando_confirmacao']) == (2, 1, 1)
        assert n['resolvidos'] == 2
        assert n['pct_no_prazo'] == 50.0
        assert n['horas_medias'] == 19.0
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    html = gestora.get('/chamados/?visao=atrasados').get_data(as_text=True)
    assert html.count('class="ch-item atrasado"') == 1


def test_visao_comigo_mostra_o_que_eu_pedi_ou_atendo(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena, titulo='Lâmpada queimada no hall')
    _abrir(gestora, cena, titulo='Portão emperrado')
    with app_module.app.app_context():
        portao = Chamado.query.filter_by(titulo='Portão emperrado').one().id
    _acao(gestora, portao, 'atribuir', responsavel_id=cena['tec'])
    tec = _entrar(app_module, 'tec.ch@trino.com')
    html = tec.get('/chamados/?visao=meus').get_data(as_text=True)
    assert 'Portão emperrado' in html and 'Lâmpada queimada' not in html
    html = enc.get('/chamados/?visao=meus').get_data(as_text=True)
    assert 'Lâmpada queimada' in html and 'Portão emperrado' not in html


# ── Anexos ───────────────────────────────────────────────────────────────

def test_foto_valida_entra_e_falsa_e_recusada(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    r = enc.post('/chamados/', data={
        'client_id': cena['c1'], 'titulo': 'Infiltração no teto', 'prioridade': 'alta',
        'arquivo': [(io.BytesIO(_png()), 'teto.png'),
                    (io.BytesIO(b'MZ\x90\x00 executavel'), 'falsa.png')]},
        content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        ch = _ultimo()
        anexos = ChamadoAnexo.query.filter_by(chamado_id=ch.id).all()
        assert [a.nome for a in anexos] == ['teto.png']
        assert anexos[0].momento == 'antes'
        anexo_id = anexos[0].id
    assert enc.get(f'/chamados/anexos/{anexo_id}').data == _png()
    fora = _entrar(app_module, 'tec.fora@trino.com')
    assert fora.get(f'/chamados/anexos/{anexo_id}').status_code == 403


def test_foto_do_servico_feito_entra_como_depois(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    tec.post(f'/chamados/{ch_id}/acao', data={
        'acao': 'resolver', 'texto': 'Reparo trocado',
        'arquivo': (io.BytesIO(_png()), 'depois.png')}, content_type='multipart/form-data')
    with app_module.app.app_context():
        a = ChamadoAnexo.query.filter_by(chamado_id=ch_id).one()
        assert a.momento == 'depois'
