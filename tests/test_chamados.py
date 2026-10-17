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
* foto com conteúdo que não confere é recusada; anexo de contrato alheio, 403;
  chamado que a ação encerra não recebe anexo; PDF baixa, só foto abre na tela;
* as abas de trabalho mostram TODO o que pede ação, o atrasado primeiro;
* aviso só para quem abre o chamado hoje (ativo, com o contrato) — o
  responsável do contrato só se ainda for gestor dele, e o gestor de "todos
  os contratos" não recebe tudo;
* pedido repetido (duplo clique) não grava duas vezes e confirma na tela;
* a ocorrência vira UM chamado vivo (o cancelado não prende), e a de passagem
  ainda em rascunho não vira.
A corrida de verdade (dois pedidos ao mesmo tempo) está em
``test_chamados_concorrencia.py``, que roda no Postgres.
"""
import io
import re
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


# ── Revisão: listas, avisos, reenvio, anexos e ocorrência ────────────────

def _flashes(cliente, ch_id):
    """As mensagens que a tela do chamado mostra no topo (e consome)."""
    html = cliente.get(f'/chamados/{ch_id}').get_data(as_text=True)
    return re.findall(r'class="alert alert-(\w+) alert-dismissible[^"]*" role="alert">\s*(.*?)\s*<button',
                      html, re.S)


def _eventos(ch_id, tipo):
    return ChamadoEvento.query.filter_by(chamado_id=ch_id, tipo=tipo).count()


def _pdf():
    return b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF'


def _desligar(app_module, *emails):
    """Tira de cena quem o teste criou (sem apagar: os avisos apontam para ele)."""
    from app import User, db
    with app_module.app.app_context():
        for e in emails:
            u = User.query.filter_by(email=e).first()
            if u is not None:
                u.is_active, u.is_deleted, u.all_clients, u.clients = False, True, False, []
        db.session.commit()


def _entrar_admin(app_module):
    from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
    assert r.status_code == 302, r.get_data(as_text=True)
    return c


def test_atrasado_antigo_aparece_mesmo_com_centenas_de_abertos_mais_novos(app_module, cena):
    """A lista era cortada nos 300 mais NOVOS antes de filtrar o atraso: o
    cartão dizia "5 atrasados" e a aba "Atrasados" vinha vazia."""
    from app import db
    agora = datetime.utcnow()
    with app_module.app.app_context():
        for i in range(5):
            aberto = agora - timedelta(days=30, minutes=i)
            db.session.add(Chamado(client_id=cena['c1'], titulo=f'ANTIGO-ATRASADO {i}',
                                   status='aberto', prioridade='urgente',
                                   solicitante_id=cena['enc'], aberto_em=aberto,
                                   prazo=aberto + timedelta(hours=4)))
        for i in range(305):
            aberto = agora - timedelta(minutes=i)
            db.session.add(Chamado(client_id=cena['c1'], titulo=f'novo no prazo {i}',
                                   status='aberto', prioridade='baixa',
                                   solicitante_id=cena['enc'], aberto_em=aberto,
                                   prazo=aberto + timedelta(days=7)))
        db.session.commit()
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    html = gestora.get('/chamados/?visao=atrasados').get_data(as_text=True)
    assert '<b>5</b><span>atrasados</span>' in html
    assert html.count('<a class="ch-item atrasado"') == 5
    assert 'Nenhum chamado atrasado' not in html

    # "Em aberto" mostra TODOS e o atrasado vem primeiro, por mais antigo que seja.
    html = gestora.get('/chamados/?visao=abertos').get_data(as_text=True)
    itens = re.findall(r'<a class="ch-item (atrasado)?"', html)
    assert len(itens) == 310
    assert itens[:5] == ['atrasado'] * 5 and 'atrasado' not in itens[5:]
    assert all(f'ANTIGO-ATRASADO {i}' in html for i in range(5))
    assert 'mais recentes' not in html

    # Só "Todos" é cortado — e avisa que cortou.
    html = gestora.get('/chamados/?visao=todos').get_data(as_text=True)
    assert html.count('<a class="ch-item') == 100
    assert 'Mostrando os 100 chamados mais recentes' in html
    assert 'novo no prazo 0<' in html and 'ANTIGO-ATRASADO' not in html


def test_percentual_no_prazo_mostra_uma_casa_decimal(app_module, cena):
    """7 de 8 no prazo é 87,5% — arredondado para inteiro virava 88%, e 199 de
    200 virava "100%" com chamado atrasado."""
    from app import db
    agora = datetime.utcnow()
    with app_module.app.app_context():
        for i in range(8):
            aberto = agora - timedelta(hours=40)
            db.session.add(Chamado(client_id=cena['c1'], titulo=f'r{i}', status='fechado',
                                   prioridade='alta', solicitante_id=cena['enc'],
                                   aberto_em=aberto, prazo=aberto + timedelta(hours=24),
                                   resolvido_em=aberto + timedelta(hours=30 if i == 0 else 10)))
        db.session.commit()
    html = _entrar(app_module, 'gestora.ch@trino.com').get('/chamados/').get_data(as_text=True)
    assert '<b>87,5%</b>' in html


def test_cada_acao_confirma_na_tela(app_module, cena):
    """Sem a frase, no celular a pessoa tinha de comparar o selo para saber se
    o toque valeu."""
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    passos = [
        (gestora, 'atribuir', {'responsavel_id': cena['tec']}, 'Chamado atribuído a Técnico Caio'),
        (gestora, 'prioridade', {'prioridade': 'alta'}, 'Prioridade alterada para alta'),
        (tec, 'iniciar', {}, 'Atendimento iniciado.'),
        (tec, 'aguardar', {'texto': 'Peça'}, 'Chamado posto em espera.'),
        (tec, 'retomar', {}, 'Atendimento retomado.'),
        (tec, 'comentar', {'texto': 'Chegou a peça'}, 'Comentário registrado.'),
        (tec, 'resolver', {'texto': 'Troquei o reparo'}, 'Chamado marcado como resolvido.'),
        (enc, 'confirmar', {}, 'Chamado fechado.'),
    ]
    for cliente, acao, dados, esperado in passos:
        assert _acao(cliente, ch_id, acao, **dados).status_code == 302
        mensagens = _flashes(cliente, ch_id)
        assert any(cat == 'success' and esperado in txt for cat, txt in mensagens), \
            (acao, mensagens)


# ── Pedido repetido (duplo clique, rede que repete o POST) ───────────────

def test_duplo_clique_em_resolver_grava_uma_vez_e_confirma(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    _flashes(tec, ch_id)
    for _ in range(2):
        tec.post(f'/chamados/{ch_id}/acao', data={
            'acao': 'resolver', 'texto': 'Reparo trocado',
            'arquivo': (io.BytesIO(_png()), 'depois.png')}, content_type='multipart/form-data')
    mensagens = _flashes(tec, ch_id)
    # O segundo envio não vira erro: para quem tocou, o chamado foi resolvido.
    assert mensagens and all(c == 'success' and 'resolvido' in t for c, t in mensagens), mensagens
    with app_module.app.app_context():
        assert _eventos(ch_id, 'resolvido') == 1
        assert sum('resolvido' in t for t in _avisos(cena['enc'])) == 1
        assert ChamadoAnexo.query.filter_by(chamado_id=ch_id).count() == 1


def test_duplo_envio_de_comentario_grava_um_so_e_comentario_novo_entra(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'comentar', texto='Técnico vai amanhã cedo')
    _acao(gestora, ch_id, 'comentar', texto='Técnico vai amanhã cedo')
    with app_module.app.app_context():
        assert _eventos(ch_id, 'comentario') == 1
        assert sum('comentário' in t for t in _avisos(cena['enc'])) == 1
    _acao(gestora, ch_id, 'comentar', texto='Mudou: vai hoje à tarde')
    with app_module.app.app_context():
        assert _eventos(ch_id, 'comentario') == 2


def test_duplo_envio_de_abrir_chamado_abre_uma_os(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    primeiro = _abrir(enc, cena, titulo='Porta da garagem travada')
    segundo = _abrir(enc, cena, titulo='Porta da garagem travada')
    assert primeiro.headers['Location'] == segundo.headers['Location']
    with app_module.app.app_context():
        assert Chamado.query.count() == 1
        assert len(_avisos(cena['gestora'])) == 1
    # Outro problema, mesmo minuto: é outro chamado.
    _abrir(enc, cena, titulo='Lâmpada do hall queimada')
    with app_module.app.app_context():
        assert Chamado.query.count() == 2


def test_acao_le_o_estado_do_banco_e_nao_o_que_ficou_na_sessao(app_module, cena):
    """O pedido que leu "em atendimento" antes de a gestora cancelar não pode
    resolver (e ressuscitar) o chamado: a ação relê o chamado travado."""
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    with app_module.app.app_context():
        from app import User, db
        velho = db.session.get(Chamado, ch_id)
        assert velho.status == 'em_atendimento'
        with db.engine.begin() as con:          # o cancelamento de outro pedido
            con.execute(db.text("UPDATE chamados SET status='cancelado' WHERE id=:i"),
                        {'i': ch_id})
        ch = servico.chamado_para_alterar(ch_id)
        assert ch is velho and ch.status == 'cancelado'
        with pytest.raises(servico.RecusaChamado):
            servico.executar(db.session.get(User, cena['tec']), ch, 'resolver',
                             {'texto': 'Feito'})
        db.session.rollback()


# ── Quem recebe aviso ────────────────────────────────────────────────────

def test_responsavel_do_contrato_fora_da_carteira_nao_e_avisado(app_module, cena):
    """A tela de contratos aceita qualquer gestor como responsável: o que não
    tem o contrato recebia título e local, e o link dava 403."""
    from app import Client, db
    with app_module.app.app_context():
        db.session.get(Client, cena['c1']).responsible_user_id = cena['gestor_outro']
        db.session.commit()
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena, titulo='Vazamento sala do diretor')
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(enc, ch_id, 'comentar', texto='Piorou')
    with app_module.app.app_context():
        assert _avisos(cena['gestor_outro']) == []
        assert len(_avisos(cena['gestora'])) == 2       # a vinculada continua


def test_responsavel_do_contrato_que_nao_e_gestor_ou_saiu_nao_e_avisado(app_module, cena):
    from app import Client, User, db
    with app_module.app.app_context():
        inativo = _pessoa(app_module, 'inativo.ch@trino.com', 'pleno', [cena['c1']], 'Gestor Saiu')
        inativo.is_active = False
        db.session.get(Client, cena['c1']).responsible_user_id = cena['tec']
        db.session.commit()
        inativo_id = inativo.id
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena, titulo='Primeiro')
    with app_module.app.app_context():
        db.session.get(Client, cena['c1']).responsible_user_id = inativo_id
        db.session.commit()
    _abrir(enc, cena, titulo='Segundo')
    with app_module.app.app_context():
        assert not any('Novo chamado' in t for t in _avisos(cena['tec']))
        assert _avisos(inativo_id) == []
        assert len(_avisos(cena['gestora'])) == 2
        assert servico.gestores_do_contrato(cena['c1']) == {cena['gestora']}
        # O administrador como responsável vê o contrato: é avisado.
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        db.session.get(Client, cena['c1']).responsible_user_id = admin.id
        db.session.commit()
        assert servico.gestores_do_contrato(cena['c1']) == {cena['gestora'], admin.id}
    _desligar(app_module, 'inativo.ch@trino.com')


def test_gestor_com_todos_os_contratos_nao_e_avisado_de_tudo(app_module, cena):
    """O regional com "todos os contratos" recebia cada chamado e cada
    comentário da empresa. Avisa só quem é vinculado (e o responsável)."""
    from app import db
    with app_module.app.app_context():
        regional = _pessoa(app_module, 'regional.ch@trino.com', 'pleno', [], 'Gestor Regional')
        regional.all_clients = True
        db.session.commit()
        regional_id = regional.id
    try:
        enc = _entrar(app_module, 'enc.ch@trino.com')
        _abrir(enc, cena)
        with app_module.app.app_context():
            ch_id = _ultimo().id
        _acao(enc, ch_id, 'comentar', texto='Alguém viu?')
        with app_module.app.app_context():
            assert _avisos(regional_id) == []
            assert regional_id not in servico.gestores_do_contrato(cena['c1'])
            # Ver e receber chamado, continua podendo.
            assert regional_id in {u.id for u in servico.tecnicos_do_contrato(cena['c1'])}
    finally:
        _desligar(app_module, 'regional.ch@trino.com')


def test_quem_perdeu_o_contrato_ou_saiu_nao_recebe_aviso_do_chamado(app_module, cena):
    from app import Client, User, db
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    with app_module.app.app_context():
        # O encarregado foi transferido para outro contrato; o técnico saiu.
        db.session.get(User, cena['enc']).clients = [db.session.get(Client, cena['c2'])]
        db.session.get(User, cena['tec']).is_active = False
        db.session.commit()
    _acao(gestora, ch_id, 'comentar', texto='COMENTARIO-INTERNO-C1')
    _acao(gestora, ch_id, 'cancelar', texto='Resolvido pela administração do prédio')
    with app_module.app.app_context():
        assert _avisos(cena['enc']) == []
        assert len(_avisos(cena['tec'])) == 1                # só o "atribuído", de antes
        assert Notification.query.filter(
            Notification.message.contains('COMENTARIO-INTERNO-C1')).count() == 0


def test_mudar_prioridade_e_confirmar_avisam_o_responsavel(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(gestora, ch_id, 'prioridade', prioridade='urgente', texto='Alagando o corredor')
    with app_module.app.app_context():
        avisos = _avisos(cena['tec'])
        assert any('Prioridade mudou' in t for t in avisos), avisos
        n = Notification.query.filter(Notification.user_id == cena['tec'],
                                      Notification.title.contains('Prioridade')).one()
        assert 'urgente' in n.message and 'Alagando o corredor' in n.message
        # Quem pediu também fica sabendo: o prazo prometido a ele mudou.
        assert any('Prioridade mudou' in t for t in _avisos(cena['enc']))
        # E quem mudou não avisa a si mesmo.
        assert not any('Prioridade mudou' in t for t in _avisos(cena['gestora']))
    _acao(tec, ch_id, 'iniciar')
    _acao(tec, ch_id, 'resolver', texto='Troquei o registro')
    _acao(enc, ch_id, 'confirmar')
    with app_module.app.app_context():
        assert any('Chamado fechado' in t for t in _avisos(cena['tec']))


def test_reatribuir_a_mesma_pessoa_nao_grava_nem_avisa_de_novo(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _flashes(gestora, ch_id)
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    assert ('info', 'Técnico Caio já é o responsável por este chamado.') in _flashes(gestora, ch_id)
    with app_module.app.app_context():
        assert _eventos(ch_id, 'atribuido') == 1
        assert len(_avisos(cena['tec'])) == 1


def test_trocar_o_responsavel_avisa_quem_saiu(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec2'])
    with app_module.app.app_context():
        assert _ultimo().responsavel_id == cena['tec2']
        assert any('passou para Técnico Davi' in t for t in _avisos(cena['tec']))
        assert len(_avisos(cena['tec2'])) == 1


# ── Anexos ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('ultima', ['cancelar', 'confirmar'])
def test_anexo_junto_com_acao_que_encerra_nao_entra(app_module, cena, ultima):
    """A rota /anexos recusa chamado fechado/cancelado; um POST montado com
    acao=cancelar (ou confirmar) e um arquivo contornava a regra."""
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    if ultima == 'confirmar':
        _acao(gestora, ch_id, 'iniciar')
        _acao(gestora, ch_id, 'resolver', texto='Feito')
    r = gestora.post(f'/chamados/{ch_id}/acao', data={
        'acao': ultima, 'texto': 'Duplicado',
        'arquivo': (io.BytesIO(_png()), 'x.png')}, content_type='multipart/form-data')
    assert r.status_code == 302
    mensagens = _flashes(gestora, ch_id)
    with app_module.app.app_context():
        assert _ultimo().status in ('cancelado', 'fechado')
        assert ChamadoAnexo.query.filter_by(chamado_id=ch_id).count() == 0
    assert any(c == 'warning' and 'não foram guardados' in t for c, t in mensagens), mensagens


def test_anexo_junto_com_comentario_entra(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    _abrir(enc, cena)
    with app_module.app.app_context():
        ch_id = _ultimo().id
    enc.post(f'/chamados/{ch_id}/acao', data={
        'acao': 'comentar', 'texto': 'Foto de agora',
        'arquivo': (io.BytesIO(_png()), 'agora.png')}, content_type='multipart/form-data')
    with app_module.app.app_context():
        assert ChamadoAnexo.query.filter_by(chamado_id=ch_id).count() == 1


def test_pdf_do_chamado_baixa_como_arquivo_e_foto_abre_na_tela(app_module, cena):
    enc = _entrar(app_module, 'enc.ch@trino.com')
    enc.post('/chamados/', data={
        'client_id': cena['c1'], 'titulo': 'Laudo do elevador', 'prioridade': 'media',
        'arquivo': [(io.BytesIO(_pdf()), 'laudo.pdf'), (io.BytesIO(_png()), 'foto.png')]},
        content_type='multipart/form-data')
    with app_module.app.app_context():
        anexos = {a.nome: a.id for a in ChamadoAnexo.query.filter_by(chamado_id=_ultimo().id)}
    pdf = enc.get(f'/chamados/anexos/{anexos["laudo.pdf"]}')
    assert pdf.headers['Content-Disposition'].startswith('attachment')
    foto = enc.get(f'/chamados/anexos/{anexos["foto.png"]}')
    assert foto.headers['Content-Disposition'].startswith('inline')


# ── Ocorrência da passagem → chamado ─────────────────────────────────────

def _ocorrencia(app_module, cena, status_turno=None, gravidade='normal'):
    """Uma ocorrência no c1 — solta, ou presa a um turno com o status dado."""
    from app import db
    from facilities.passagem.models import DiarioConfiguracao, DiarioOcorrencia, DiarioTurno
    turno_id = None
    if status_turno:
        cfg = DiarioConfiguracao(client_id=cena['c1'], nome='Limpeza', ativo=True,
                                 created_by=cena['gestora'])
        db.session.add(cfg)
        db.session.flush()
        t = DiarioTurno(client_id=cena['c1'], configuracao_id=cfg.id,
                        data_turno=datetime.utcnow().date(), turno='T1', status=status_turno,
                        dados_json='{}', created_by=cena['enc'])
        db.session.add(t)
        db.session.flush()
        turno_id = t.id
    o = DiarioOcorrencia(client_id=cena['c1'], turno_id=turno_id, tipo='Vazamento',
                         descricao='Pia da copa vazando', gravidade=gravidade,
                         created_by=cena['enc'])
    db.session.add(o)
    db.session.commit()
    return o.id


def _abrir_da_ocorrencia(cliente, oid):
    return cliente.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')


def test_ocorrencia_de_passagem_em_rascunho_nao_vira_chamado(app_module, cena):
    with app_module.app.app_context():
        rascunho = _ocorrencia(app_module, cena, status_turno='aberto')
        encerrada = _ocorrencia(app_module, cena, status_turno='encerrado')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    r = _abrir_da_ocorrencia(gestora, rascunho)
    assert r.status_code == 409
    assert 'ainda não foi encerrada' in r.get_json()['error']
    assert _abrir_da_ocorrencia(gestora, encerrada).status_code == 201
    with app_module.app.app_context():
        assert Chamado.query.filter_by(origem='ocorrencia', origem_id=rascunho).count() == 0


def test_ocorrencia_com_chamado_cancelado_vira_chamado_de_novo(app_module, cena):
    with app_module.app.app_context():
        oid = _ocorrencia(app_module, cena)
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    primeiro = _abrir_da_ocorrencia(gestora, oid).get_json()
    with app_module.app.app_context():
        assert {k: c.id for k, c in servico.chamados_das_ocorrencias([oid]).items()} \
            == {oid: primeiro['id']}
    _acao(gestora, primeiro['id'], 'cancelar', texto='Vamos esperar a reforma')
    with app_module.app.app_context():
        assert servico.chamados_das_ocorrencias([oid]) == {}
    r = _abrir_da_ocorrencia(gestora, oid)
    assert r.status_code == 201 and r.get_json()['id'] != primeiro['id']
    with app_module.app.app_context():
        assert servico.chamados_das_ocorrencias([oid, 999999])[oid].id == r.get_json()['id']
        assert servico.chamados_das_ocorrencias([]) == {}


def test_o_banco_aceita_um_chamado_vivo_por_ocorrencia(app_module, cena):
    """O índice único parcial: manual (sem origem_id) à vontade, um vivo por
    ocorrência, e o cancelado não conta."""
    from sqlalchemy.exc import IntegrityError
    from app import db

    def novo(**kw):
        db.session.add(Chamado(client_id=cena['c1'], titulo='x', solicitante_id=cena['enc'],
                               **kw))
        db.session.flush()

    with app_module.app.app_context():
        novo(origem='manual')
        novo(origem='manual')
        novo(origem='ocorrencia', origem_id=41, status='cancelado')
        novo(origem='ocorrencia', origem_id=41)
        with pytest.raises(IntegrityError):
            novo(origem='ocorrencia', origem_id=41)
        db.session.rollback()


def test_ocorrencia_aberta_por_outro_pedido_no_mesmo_instante_devolve_o_mesmo(
        app_module, cena, monkeypatch):
    """Dois cliques ao mesmo tempo: o segundo passa pela consulta antes de o
    primeiro gravar. Aqui a corrida é simulada (a consulta "não vê" o
    chamado que já existe): o índice recusa o segundo INSERT e a resposta é
    o chamado do primeiro, sem segunda OS e sem segundo aviso."""
    with app_module.app.app_context():
        oid = _ocorrencia(app_module, cena)
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    primeiro = _abrir_da_ocorrencia(gestora, oid).get_json()
    with app_module.app.app_context():
        avisos_antes = Notification.query.count()

    verdadeira = servico._chamado_vivo_da_ocorrencia
    chamadas = []

    def cega_na_primeira(ocorrencia_id):
        chamadas.append(ocorrencia_id)
        return None if len(chamadas) == 1 else verdadeira(ocorrencia_id)

    monkeypatch.setattr(servico, '_chamado_vivo_da_ocorrencia', cega_na_primeira)
    admin = _entrar_admin(app_module)
    r = _abrir_da_ocorrencia(admin, oid)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['id'] == primeiro['id'] and r.get_json()['criado'] is False
    with app_module.app.app_context():
        assert Chamado.query.filter_by(origem='ocorrencia', origem_id=oid).count() == 1
        assert Notification.query.count() == avisos_antes
