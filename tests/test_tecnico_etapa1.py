"""Bloco do técnico, etapa 1 (decisões do dono, 22/10/2026): banco, regras e
API JSON — sem tela.

* Chegada: só pelo QR da ENTRADA do local; uma por pessoa/local/dia (ler de
  novo devolve a mesma); a gestão libera quando o QR não pôde ser lido.
* Execução: com entrada cadastrada, sem chegada hoje → recusa 'sem_chegada';
  local sem entrada segue como antes.
* Tempo: acima do previsto + 10 min exige o motivo do atraso (422,
  'motivo_atraso'); dentro, não.
* Item 'nao_feito': vira não conformidade com o motivo; 'faltou_material'
  com material abre UM pedido de insumo; os itens com problema de uma
  execução viram UM chamado.
* QR público: itens reportáveis do checklist do ponto, gravados com o autor
  logado.
* Cadastro: tempo previsto 1–480; um ponto de entrada ativo por local.
"""
import json
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_rotas_servico import (SEGUNDA, Arquivo, _executar, _respostas, _s, _tarefas,
                                      montar_cena, utc)


@pytest.fixture()
def cena(app_module):
    """O cenário da Ana (``test_rotas_servico``), com o contexto aberto."""
    with app_module.app.app_context():
        yield montar_cena(app_module)


@pytest.fixture()
def cena_http(app_module):
    """O mesmo cenário, sem deixar o contexto aberto: nos testes por HTTP
    com mais de um login, o ``g`` de um contexto aberto guardaria o primeiro."""
    with app_module.app.app_context():
        return montar_cena(app_module)


def _chegadas():
    from facilities.rotas import chegadas
    return chegadas


def _user(uid):
    from app import User, db
    return db.session.get(User, uid)


def _ponto(pid):
    from app import db
    from facilities.cadastros.models import PontoInspecao
    return db.session.get(PontoInspecao, pid)


def _entrada(app_module, cena, nome='Portaria'):
    """Cria o ponto de ENTRADA do local da cena (um ponto novo, no ambiente)."""
    from app import db
    from facilities.cadastros import servico as cad
    p = cad.salvar_ponto(fabrica.local(), None, {'nome': nome, 'ambiente_id': cena['ambiente'],
                                                 'entrada_do_local': '1'}, None)
    db.session.commit()
    return p


# ── Chegada ───────────────────────────────────────────────────────────────

def test_chegada_so_no_ponto_de_entrada_e_uma_por_dia(app_module, cena):
    from app import db
    with app_module.app.app_context():
        ch = _chegadas()
        ana = _user(cena['ana'])
        with pytest.raises(_s().RegraDaRota) as erro:
            ch.registrar(ana, _ponto(cena['ponto']), utc(SEGUNDA, '07:00'))
        assert erro.value.codigo == 409 and erro.value.codigo_app == 'nao_e_entrada'
        entrada = _entrada(app_module, cena)
        c1, nova = ch.registrar(ana, entrada, utc(SEGUNDA, '07:01'))
        db.session.commit()
        assert nova and c1.com_camera and c1.data == SEGUNDA
        assert tempo.fmt(c1.chegou_em, '%H:%M') == '07:01'
        # Leu de novo no mesmo dia: a mesma chegada, sem duplicar.
        c2, nova = ch.registrar(ana, entrada, utc(SEGUNDA, '12:00'))
        assert not nova and c2.id == c1.id
        assert ch.de_hoje(ana, cena['local'], utc(SEGUNDA, '15:00')).id == c1.id
        # No dia seguinte é outra chegada.
        c3, nova = ch.registrar(ana, entrada, utc(SEGUNDA + timedelta(days=1), '07:00'))
        assert nova and c3.id != c1.id
        assert ch.de_hoje(ana, cena['local'], utc(SEGUNDA + timedelta(days=2), '07:00')) is None


def test_quem_e_de_fora_nao_registra_chegada(app_module, cena):
    with app_module.app.app_context():
        fora = fabrica.pessoa(app_module, 'fora.chegada@trino.com', 'encarregado',
                              locais=['Hospital Norte'])
        entrada = _entrada(app_module, cena)
        with pytest.raises(_s().RegraDaRota) as erro:
            _chegadas().registrar(_user(fora), entrada)
        assert erro.value.codigo == 403


def test_execucao_exige_chegada_so_quando_o_local_tem_entrada(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9, t11 = _tarefas()[:2]
        # Sem ponto de entrada: como hoje, sem exigência.
        ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'))
        db.session.commit()
        assert t9.status == 'concluida_no_prazo'
        # Com entrada e sem chegada: recusa com a marca para o app.
        entrada = _entrada(app_module, cena)
        with pytest.raises(s.RegraDaRota) as erro:
            _executar(cena['ana'], t11, utc(SEGUNDA, '11:00'))
        assert erro.value.codigo == 409 and erro.value.codigo_app == 'sem_chegada'
        assert 'QR da entrada' in erro.value.mensagem
        db.session.rollback()
        # Chegou (leu a entrada): o checklist entra.
        _chegadas().registrar(_user(cena['ana']), entrada, utc(SEGUNDA, '06:55'))
        db.session.commit()
        _executar(cena['ana'], t11, utc(SEGUNDA, '11:00'))
        db.session.commit()
        assert t11.status == 'concluida_no_prazo'


def test_gestor_libera_a_chegada_e_a_execucao_passa(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        ch = _chegadas()
        s.gerar(SEGUNDA)
        t9 = _tarefas()[0]
        local = fabrica.local()
        # Sem entrada no local, não há o que liberar.
        gestor = _user(fabrica.pessoa(app_module, 'coord.chegada@trino.com', 'pleno',
                                      locais=['Shopping Centro']))
        with pytest.raises(s.RegraDaRota, match='não tem ponto de entrada'):
            ch.liberar(gestor, cena['ana'], local, SEGUNDA)
        _entrada(app_module, cena)
        # Quem não é gestão não libera.
        with pytest.raises(s.RegraDaRota) as erro:
            ch.liberar(_user(cena['mariana']), cena['ana'], local, SEGUNDA)
        assert erro.value.codigo == 403
        c, nova = ch.liberar(gestor, cena['ana'], local, SEGUNDA, agora_utc=utc(SEGUNDA, '08:00'))
        db.session.commit()
        assert nova and not c.com_camera and c.liberada_por == gestor.id and c.data == SEGUNDA
        # Liberar de novo devolve a mesma.
        assert ch.liberar(gestor, cena['ana'], local, SEGUNDA)[0].id == c.id
        _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'))
        db.session.commit()
        assert t9.status == 'concluida_no_prazo'


def test_gestao_libera_pela_rota_do_site(app_module, cena_http):
    from facilities.rotas.models import Chegada
    cena = cena_http
    with app_module.app.app_context():
        _entrada(app_module, cena)
        fabrica.pessoa(app_module, 'coord.site@trino.com', 'pleno', locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'coord.site@trino.com')
    r = c.post(f"/rotas/locais/{cena['local']}/chegadas",
               data={'user_id': cena['ana'], 'data': SEGUNDA.isoformat()})
    assert r.status_code == 302 and '/dia' in r.headers['Location']
    with app_module.app.app_context():
        ch = Chegada.query.filter_by(user_id=cena['ana'], data=SEGUNDA).one()
        assert not ch.com_camera
    # Um encarregado não libera (a tela é da gestão).
    enc = fabrica.entrar(app_module, 'ana.rota@trino.com')
    assert enc.post(f"/rotas/locais/{cena['local']}/chegadas",
                    data={'user_id': cena['mariana']}).status_code == 403


def test_api_chegada_e_turno(app_module, cena_http):
    cena = cena_http
    with app_module.app.app_context():
        from app import db
        entrada = _entrada(app_module, cena)
        qr_entrada = entrada.codigo_qr
        _s().gerar(tempo.hoje())
        db.session.commit()
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')
    # Ponto comum não é a entrada: a API diz qual é a marca.
    r = c.post('/app/api/chegada', json={'ponto': cena['qr']})
    assert r.status_code == 409 and r.get_json()['motivo'] == 'nao_e_entrada'
    turno = c.get(f"/app/api/turno?local={cena['local']}").get_json()
    assert turno['entrada'] == qr_entrada and turno['exige_chegada'] and turno['chegada'] is None
    assert turno['data'] == tempo.hoje().isoformat()
    assert 'motivos_atraso' in turno and turno['tolerancia_atraso_min'] == 10
    selo = c.post('/app/api/leitura', json={'ponto': qr_entrada}).get_json()['selo']
    r = c.post('/app/api/chegada', json={'ponto': qr_entrada, 'selo_leitura': selo})
    assert r.status_code == 201 and r.get_json()['nova'] and r.get_json()['chegada']['com_camera']
    r2 = c.post('/app/api/chegada', json={'ponto': qr_entrada})
    assert r2.status_code == 200 and not r2.get_json()['nova']
    assert r2.get_json()['chegada']['id'] == r.get_json()['chegada']['id']
    turno = c.get(f"/app/api/turno?local={cena['local']}").get_json()
    assert turno['chegada']['id'] == r.get_json()['chegada']['id']
    # Local fora da carteira: recusado; sem local: 400.
    with app_module.app.app_context():
        outro = fabrica.local('Hospital Norte').id
    assert c.get(f'/app/api/turno?local={outro}').status_code == 403
    assert c.get('/app/api/turno').status_code == 400


def test_turno_de_hoje_traz_as_tarefas_do_local_com_tempo_e_foto(app_module, cena):
    from app import db
    from facilities.rotas.models import RotaItem
    with app_module.app.app_context():
        s = _s()
        db.session.get(RotaItem, cena['item']).tempo_previsto_min = 30
        db.session.commit()
        dados = s.turno_de_hoje(_user(cena['ana']), cena['local'],
                                agora_utc=utc(tempo.hoje(), '08:00'))
        db.session.commit()
        assert dados['entrada'] is None and not dados['exige_chegada']
        assert dados['local']['id'] == cena['local']
        horas = [t['hora'] for t in dados['tarefas']]
        assert horas == ['09:00', '11:00'] or horas == []     # fim de semana: a rota não roda
        for t in dados['tarefas']:
            assert t['tempo_previsto_min'] == 30 and t['exige_foto'] and t['foto_depois']
            assert t['ponto'] == cena['qr'] and t['minha'] and t['checklist']
        # Outro local da carteira não entra; local de fora é recusado.
        fora = fabrica.local('Hospital Norte').id
        with pytest.raises(s.RegraDaRota) as erro:
            s.turno_de_hoje(_user(cena['ana']), fora)
        assert erro.value.codigo == 403


# ── Tempo previsto e motivo do atraso ─────────────────────────────────────

def test_fora_do_tempo_e_regra_pura():
    s = _s()
    assert s.TOLERANCIA_ATRASO_MIN == 10
    assert not s.fora_do_tempo(None, 90)
    assert not s.fora_do_tempo(30, None)
    assert not s.fora_do_tempo(30, 40)
    assert s.fora_do_tempo(30, 41)


def test_atraso_exige_motivo_acima_do_previsto_mais_tolerancia(app_module, cena):
    from app import db
    from facilities.rotas.models import RotaItem
    with app_module.app.app_context():
        s = _s()
        db.session.get(RotaItem, cena['item']).tempo_previsto_min = 30
        db.session.commit()
        s.gerar(SEGUNDA)
        t9, t11 = _tarefas()[:2]
        # 40 min (= 30 + 10): dentro, sem motivo.
        ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), utc(SEGUNDA, '09:40'))
        db.session.commit()
        assert ex.duracao_min == 40 and ex.motivo_atraso is None
        # 41 min: exige o motivo, com os números para o app.
        with pytest.raises(s.RegraDaRota) as erro:
            _executar(cena['ana'], t11, utc(SEGUNDA, '11:00'), utc(SEGUNDA, '11:41'))
        assert erro.value.codigo == 422 and erro.value.codigo_app == 'motivo_atraso'
        assert erro.value.extra == {'duracao_min': 41, 'previsto_min': 30}
        assert 'levou 41 min; o previsto era 30' in erro.value.mensagem
        db.session.rollback()
        # 'outro' sem texto não vale; motivo inventado também não.
        with pytest.raises(s.RegraDaRota, match='Diga o que aconteceu'):
            _executar_com(cena['ana'], t11, '11:00', '11:41', motivo_atraso='outro')
        db.session.rollback()
        with pytest.raises(s.RegraDaRota, match='motivo do atraso na lista'):
            _executar_com(cena['ana'], t11, '11:00', '11:41', motivo_atraso='dormi')
        db.session.rollback()
        ex, _ = _executar_com(cena['ana'], t11, '11:00', '11:41',
                              motivo_atraso='sujo_acima_do_normal')
        db.session.commit()
        assert ex.motivo_atraso == 'sujo_acima_do_normal' and ex.duracao_min == 41
        assert t11.status == 'concluida_no_prazo'     # começou na hora; só demorou


def _executar_com(uid, tarefa, lido, concluida, respostas=None, fotos=None, **extra):
    """Como ``_executar``, com campos extras no ``dados`` (motivos, atraso)."""
    s = _s()
    lido_utc, concluida_utc = utc(SEGUNDA, lido), utc(SEGUNDA, concluida)
    dados = {'envio_id': f'envio-x-{tarefa.id}-{lido}-{concluida}-{sorted(extra.items())}',
             'ponto': tarefa.ponto.codigo_qr, 'tarefa_id': tarefa.id,
             'respostas': respostas or _respostas(), 'sem_sinal': True,
             'lido_em': lido_utc.isoformat(), 'concluida_em': concluida_utc.isoformat()}
    dados.update(extra)
    return s.registrar_execucao(_user(uid), dados, fotos if fotos is not None
                                else {'depois': [Arquivo()]},
                                agora_utc=concluida_utc + timedelta(minutes=1))


def test_sem_tempo_previsto_nao_pergunta_nada(app_module, cena):
    from app import db
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        ex, _ = _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'), utc(SEGUNDA, '12:00'))
        db.session.commit()
        assert ex.duracao_min == 180 and ex.motivo_atraso is None


def test_tempo_previsto_do_item_vai_de_1_a_480(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        s = _s()
        rota = db.session.get(Rota, cena['rota'])
        base = {'ponto_id': cena['ponto'], 'modelo_id': cena['modelo'], 'horarios': '13:00'}
        for ruim in ('0', '481', 'abc', '-5', '30.5'):
            with pytest.raises(s.RegraDaRota, match='de 1 a 480'):
                s.salvar_item(rota, None, dict(base, tempo_previsto_min=ruim))
        it = s.salvar_item(rota, None, dict(base, tempo_previsto_min='45'))
        assert it.tempo_previsto_min == 45
        it = s.salvar_item(rota, it, dict(base, tempo_previsto_min=''))
        assert it.tempo_previsto_min is None
        db.session.rollback()


# ── Item não feito ────────────────────────────────────────────────────────

def test_item_nao_feito_vira_nc_e_faltou_material_abre_um_pedido(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_EXECUCAO, Chamado
    from facilities.materiais import servico as mat
    from facilities.materiais.models import PedidoInsumo
    from facilities.rotas.models import NaoConformidade
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9, t11 = _tarefas()[:2]
        papel = mat.salvar_material(None, {'nome': 'Papel higiênico (etapa 1)', 'unidade': 'rolo'})
        db.session.commit()
        # Obrigatório sem resposta nem 'nao_feito' continua recusado…
        with pytest.raises(s.RegraDaRota, match='Responda'):
            _executar_com(cena['ana'], t9, '09:00', '09:10', respostas={'mictorios': 'conforme'})
        db.session.rollback()
        # …e 'nao_feito' sem motivo também.
        with pytest.raises(s.RegraDaRota) as erro:
            _executar_com(cena['ana'], t9, '09:00', '09:10',
                          respostas=_respostas(papel_higienico_reposto='nao_feito'))
        assert erro.value.codigo_app == 'motivo_nao_feito'
        assert erro.value.extra == {'item': 'papel_higienico_reposto'}
        db.session.rollback()
        with pytest.raises(s.RegraDaRota, match='por que não foi feito'):
            _executar_com(cena['ana'], t9, '09:00', '09:10',
                          respostas=_respostas(papel_higienico_reposto='nao_feito'),
                          motivos={'papel_higienico_reposto': {'motivo': 'outro'}})
        db.session.rollback()
        ex, _ = _executar_com(
            cena['ana'], t9, '09:00', '09:10',
            respostas=_respostas(papel_higienico_reposto='nao_feito', mictorios='nao_feito'),
            motivos={'papel_higienico_reposto': {'motivo': 'faltou_material',
                                                 'material_id': str(papel.id)},
                     'mictorios': {'motivo': 'equipamento', 'texto': 'descarga quebrada'}})
        db.session.commit()
        ncs = NaoConformidade.query.filter_by(execucao_id=ex.id).order_by(
            NaoConformidade.id).all()
        assert [nc.item_codigo for nc in ncs] == ['papel_higienico_reposto', 'mictorios']
        assert ncs[0].resposta == 'Não feito: faltou material'
        assert ncs[1].resposta == 'Não feito: equipamento com problema — descarga quebrada'
        assert json.loads(ex.respostas_json)['mictorios'] == 'nao_feito'
        # UM pedido de insumo, do material, para o local, por quem executou.
        pedidos = PedidoInsumo.query.filter_by(client_id=cena['local']).all()
        assert len(pedidos) == 1 and pedidos[0].material_id == papel.id
        assert pedidos[0].user_id == cena['ana'] and 'Papel higiênico reposto?' in pedidos[0].texto
        assert [p.id for p in ex.pedidos_de_insumo] == [pedidos[0].id]
        # UM chamado da execução, de equipamento, com os dois itens e o pedido.
        ch = Chamado.query.filter_by(origem=ORIGEM_EXECUCAO, origem_id=ex.id).one()
        assert ch.categoria == 'equipamento' and {nc.chamado_id for nc in ncs} == {ch.id}
        assert 'descarga quebrada' in ch.descricao and 'Pedido de insumo aberto' in ch.descricao
        # Material que não existe: recusado com a pergunta.
        with pytest.raises(s.RegraDaRota, match='Escolha um material'):
            _executar_com(cena['ana'], t11, '11:00', '11:10',
                          respostas=_respostas(papel_higienico_reposto='nao_feito'),
                          motivos={'papel_higienico_reposto': {'motivo': 'faltou_material',
                                                               'material_id': '999999'}})
        db.session.rollback()


def test_um_chamado_por_execucao_com_tres_itens(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_EXECUCAO, Chamado
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        ex, _ = _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'),
                          respostas=_respostas(papel_higienico_reposto='nao',
                                               mictorios='nao_conforme', cloro_ppm='9'))
        db.session.commit()
        assert ex.n_nao_conformes == 3
        chamados = Chamado.query.filter_by(client_id=cena['local']).all()
        assert len(chamados) == 1
        ch = chamados[0]
        assert ch.origem == ORIGEM_EXECUCAO and ch.origem_id == ex.id
        assert ch.titulo == 'Porta do banheiro · 3 item(ns) com problema'
        for texto in ('Papel higiênico reposto?', 'Mictórios', 'Cloro (ppm)'):
            assert texto in ch.descricao
        assert {nc.chamado_id for nc in ex.nao_conformidades} == {ch.id}
        # O botão "abrir chamado" de qualquer NC devolve o mesmo.
        assert _s().abrir_chamado_da_nc(ex.nao_conformidades[2], _user(cena['ana'])) == ch.id


def test_api_de_execucao_devolve_motivo_e_extra(app_module, cena_http):
    cena = cena_http
    from app import db
    from facilities.rotas.models import RotaItem
    with app_module.app.app_context():
        db.session.get(RotaItem, cena['item']).tempo_previsto_min = 30
        _s().gerar(tempo.hoje())
        db.session.commit()
        tarefas = _tarefas(tempo.hoje())
        if not tarefas:
            pytest.skip('a rota da cena não roda no fim de semana')
        t = tarefas[0]
        tid, qr = t.id, t.ponto.codigo_qr
        lido = t.previsto_para
    c = fabrica.entrar(app_module, 'ana.rota@trino.com')

    def enviar(**extra):
        corpo = {'envio_id': f'api-etapa1-{sorted(extra.items())}', 'ponto': qr, 'tarefa_id': tid,
                 'respostas': _respostas(), 'sem_sinal': True,
                 'lido_em': lido.isoformat() + 'Z',
                 'concluida_em': (lido + timedelta(minutes=50)).isoformat() + 'Z'}
        corpo.update(extra)
        from io import BytesIO
        from tests.test_rotas_servico import _png
        return c.post('/app/api/execucoes', data={'corpo': json.dumps(corpo),
                                                  'depois': (BytesIO(_png()), 'd.png')},
                      content_type='multipart/form-data')
    r = enviar()
    assert r.status_code in (422, 409), r.get_data(as_text=True)
    if r.status_code == 409:      # a hora de agora já passou do turno: vira extra… ou é cedo
        pytest.skip('a tarefa de hoje não está na janela agora')
    assert r.get_json() == {'error': 'Esta limpeza levou 50 min; o previsto era 30. Diga o '
                                     'que aconteceu.',
                            'motivo': 'motivo_atraso',
                            'extra': {'duracao_min': 50, 'previsto_min': 30}}
    r = enviar(motivo_atraso='tempo_curto')
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()['duracao_min'] == 50 and r.get_json()['motivo_atraso'] == 'tempo_curto'


# ── QR público com os itens do checklist ──────────────────────────────────

def test_itens_reportaveis_vem_do_checklist_ativo_do_ponto(app_module, cena):
    from app import db
    from facilities.rotas import ocorrencias
    from facilities.rotas.models import ChecklistModelo
    with app_module.app.app_context():
        itens = ocorrencias.itens_reportaveis(_ponto(cena['ponto']))
        # sim/não e conforme entram; texto e número não.
        assert [i['codigo'] for i in itens] == ['papel_higienico_reposto', 'mictorios',
                                                'vazamento']
        assert itens[0]['rotulo_problema'] == 'Problema: Papel higiênico reposto?'
        # O campo "problema" do item dá o rótulo curto.
        m = db.session.get(ChecklistModelo, cena['modelo'])
        s = _s()
        novos = s.normalizar_itens([
            {'texto': 'Papel higiênico reposto?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao', 'problema': 'Falta papel'},
            {'texto': 'Mictórios', 'tipo': 'conforme', 'obrigatorio': True}])
        assert novos[0]['problema'] == 'Falta papel' and 'problema' not in novos[1]
        s.publicar(m, novos, {}, None)
        db.session.commit()
        itens = ocorrencias.itens_reportaveis(_ponto(cena['ponto']))
        assert [(i['codigo'], i['rotulo_problema']) for i in itens] == [
            ('papel_higienico_reposto', 'Falta papel'), ('mictorios', 'Problema: Mictórios')]
        # Ponto sem rota: nada a marcar.
        from facilities.cadastros import servico as cad
        solto = cad.salvar_ponto(fabrica.local(), None, {'nome': 'Copa', 'ambiente_id':
                                                         cena['ambiente']}, None)
        assert ocorrencias.itens_reportaveis(solto) == []


def test_publico_marca_itens_e_o_cliente_logado_fica_como_autor(app_module, cena_http):
    cena = cena_http
    from app import db
    from facilities.rotas.models import OcorrenciaPublica
    html = app_module.app.test_client().get(f"/q/{cena['qr']}").get_data(as_text=True)
    assert 'É aqui?' in html
    # Anônimo, com itens e sem texto (o tipo não é "outro"): aceito.
    c = app_module.app.test_client()
    r = c.post(f"/q/{cena['qr']}/ocorrencia",
               data={'tipo': 'sujo', 'texto': '', 'itens': ['mictorios', 'inventado',
                                                             'papel_higienico_reposto']},
               content_type='multipart/form-data')
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    with app_module.app.app_context():
        oc = OcorrenciaPublica.query.one()
        assert oc.itens == ['mictorios', 'papel_higienico_reposto'] and oc.autor_id is None
        from facilities.rotas import ocorrencias
        # Na tela, sem o "Problema: " da frente (27/10/2026).
        assert ocorrencias.rotulos_dos_itens(oc) == ['Mictórios', 'Papel higiênico reposto?']
        assert oc.resumo == 'Mictórios, Papel higiênico reposto?'
    # "Outro" continua exigindo o texto, mesmo com item marcado.
    r = c.post(f"/q/{cena['qr']}/ocorrencia", data={'tipo': 'outro', 'itens': ['mictorios']},
               content_type='multipart/form-data')
    assert r.status_code == 400 and 'poucas palavras' in r.get_data(as_text=True)
    # O cliente logado (portal) fica registrado como autor.
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cliente.etapa1@gl.com', cena['cliente'])
    cli = fabrica.entrar_com_codigo(app_module, 'cliente.etapa1@gl.com')
    assert 'É aqui?' in cli.get(f"/q/{cena['qr']}").get_data(as_text=True)
    r = cli.post(f"/q/{cena['qr']}/ocorrencia", data={'tipo': 'lixo', 'itens': ['mictorios']},
                 content_type='multipart/form-data')
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    with app_module.app.app_context():
        from app import User
        uid = User.query.filter_by(email='cliente.etapa1@gl.com').one().id
        oc = OcorrenciaPublica.query.filter_by(tipo='lixo').one()
        assert oc.autor_id == uid and oc.itens == ['mictorios']
        db.session.rollback()


# ── Cadastro: um ponto de entrada por local ───────────────────────────────

def test_um_ponto_de_entrada_ativo_por_local(app_module, cena):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.servico import CadastroInvalido
    with app_module.app.app_context():
        loc = fabrica.local()
        entrada = _entrada(app_module, cena)
        assert cad.ponto_de_entrada(loc.id).id == entrada.id
        with pytest.raises(CadastroInvalido, match='já tem um ponto de entrada'):
            cad.salvar_ponto(loc, None, {'nome': 'Outra portaria', 'ambiente_id': cena['ambiente'],
                                         'entrada_do_local': '1'}, None)
        db.session.rollback()
        # Editar o próprio ponto de entrada continua valendo; o formulário
        # sem o campo não desmarca.
        cad.salvar_ponto(loc, entrada, {'nome': 'Portaria principal', 'ambiente_id':
                                        cena['ambiente'], 'entrada_do_local': 'on'}, None)
        cad.salvar_ponto(loc, entrada, {'nome': 'Portaria principal', 'ambiente_id':
                                        cena['ambiente']}, None)
        assert entrada.entrada_do_local
        # Desativada, deixa de contar; reativar com outra ativa é recusado.
        cad.definir_ativo('ponto', entrada, False, None)
        assert cad.ponto_de_entrada(loc.id) is None
        outra = cad.salvar_ponto(loc, None, {'nome': 'Outra portaria', 'ambiente_id':
                                             cena['ambiente'], 'entrada_do_local': '1'}, None)
        with pytest.raises(CadastroInvalido, match='Outra portaria'):
            cad.definir_ativo('ponto', entrada, True, None)
        db.session.rollback()
        # Outro local pode ter a sua.
        outro = fabrica.local('Hospital Norte')
        setor = cad.salvar_setor(outro, None, {'nome': 'Recepção'}, None)
        amb = cad.salvar_ambiente(outro, None, {'nome': 'Hall', 'setor_id': setor.id}, None)
        p = cad.salvar_ponto(outro, None, {'nome': 'Portaria HN', 'ambiente_id': amb.id,
                                           'entrada_do_local': '1'}, None)
        assert p.entrada_do_local and outra.entrada_do_local
        db.session.rollback()


# ── Rotas prontas com tempo previsto ──────────────────────────────────────

def test_rota_pronta_aplica_o_tempo_previsto_por_ambiente(app_module, cena):
    from app import db
    from facilities.rotas import biblioteca_pronta, rotas_prontas
    from facilities.rotas.models import RotaModelo
    assert rotas_prontas.tempo_previsto_padrao('Banheiro feminino') == 30
    assert rotas_prontas.tempo_previsto_padrao('Vestiário') == 30
    assert rotas_prontas.tempo_previsto_padrao('Copa') == 25
    assert rotas_prontas.tempo_previsto_padrao('Recepção') == 20
    assert rotas_prontas.tempo_previsto_padrao('Salas e estações de trabalho') == 40
    assert rotas_prontas.tempo_previsto_padrao('Armazém e docas') == 45
    assert rotas_prontas.tempo_previsto_padrao('Entrada e calçada') == 30
    assert rotas_prontas.tempo_previsto_padrao('Laboratório') is None
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        biblioteca_pronta.semear(admin)
        db.session.commit()
        m = RotaModelo.query.filter_by(nome='Escritório corporativo — turno diurno').one()
        assert {it.ambiente: it.tempo_previsto_min for it in m.itens} == {
            'Banheiro masculino': 30, 'Banheiro feminino': 30, 'Copa': 25, 'Recepção': 20,
            'Salas e estações de trabalho': 40, 'Entrada e calçada': 30}
        linhas = rotas_prontas.linhas_da_previa(m)
        assert linhas[2]['tempo_previsto_min'] == 25
        # A gestão ajusta na prévia: o item da rota recebe o valor; vazio = o padrão.
        linhas[2]['tempo_previsto_min'] = '15'
        linhas[3]['tempo_previsto_min'] = ''
        rota, _r = rotas_prontas.aplicar(m, fabrica.local(), {'nome': 'Escritório (etapa 1)'},
                                         linhas, admin)
        db.session.commit()
        por_ambiente = {it.ponto.ambiente.nome: it.tempo_previsto_min for it in rota.itens}
        assert por_ambiente['Copa'] == 15 and por_ambiente['Recepção'] == 20
        assert por_ambiente['Banheiro masculino'] == 30
        # Os modelos prontos trazem o "problema" curto para o QR público.
        from facilities.rotas.models import ChecklistModelo
        banheiro = ChecklistModelo.query.filter_by(
            nome=biblioteca_pronta._BANHEIRO, client_id=None).one()
        problemas = [i.get('problema') for i in _s().itens_da_versao(banheiro.versao_atual)]
        assert 'Lixeira cheia' in problemas and 'Falta papel ou sabonete' in problemas
