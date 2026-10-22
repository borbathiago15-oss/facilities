"""Concorrência DE VERDADE: duas threads, cada uma com sua própria sessão e
seu próprio app context, contra o Postgres — como dois celulares, ou o
agendador e uma tela aberta, batendo no mesmo registro ao mesmo tempo.

Roda só com ``TEST_DATABASE_URL`` apontando para um Postgres: é lá que valem
as travas de linha (``SELECT … FOR UPDATE`` / ``FOR NO KEY UPDATE``), a
trava consultiva do agendador (``pg_try_advisory_xact_lock``) e a espera na
chave única durante a transação. O SQLite em memória põe toda escrita em fila
e esconderia justamente a corrida que estes testes provocam.

Para cada cenário, o comentário diz QUAL linha do código protege. Onde o
código não protege, o teste fica ``xfail(strict=True)`` descrevendo o defeito
e a correção — sem mexer no código do aplicativo.

Os cenários:

1. mesmo ``envio_id`` enviado duas vezes ao mesmo tempo → uma execução;
2. dois técnicos na mesma tarefa do dia → um vence, o outro vira "extra";
3. ``garantir_hoje`` / ``gerar`` em duas threads → nenhuma tarefa ou pedido
   de presença duplicado;
4. ``rodar()`` (tick do agendador) em duas threads → avisos uma vez só,
   perdidas fechadas uma vez só;
5. a mesma confirmação de presença confirmada por duas threads → uma
   confirmação;
6. consumo de estoque em paralelo → saldo nunca negativo sem autorização,
   nenhum movimento perdido; pedido de insumo em duplicata;
7. chamado: "resolver" × "reabrir" ao mesmo tempo → estado e trilha coerentes.
"""
import os
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from facilities import tempo
from tests import fabrica

pytestmark = pytest.mark.skipif(
    'postgres' not in os.environ.get('TEST_DATABASE_URL', ''),
    reason='corrida de verdade só no Postgres (TEST_DATABASE_URL); o SQLite em '
           'memória serializa as escritas e não reproduz a disputa')

SEXTA = date(2026, 10, 16)
SEGUNDA = date(2026, 10, 19)


def utc(dia, hhmm):
    h, m = map(int, hhmm.split(':'))
    return tempo.para_utc(dia, time(h, m))


def _cedo(dia):
    """Meia-noite local do dia: todos os pedidos de presença ainda no futuro."""
    return tempo.para_utc(dia, time(0, 0))


# ── A ferramenta: N trabalhos soltos juntos, cada um na sua sessão ────────

def _em_paralelo(app, *trabalhos, prazo=60):
    """Roda cada trabalho numa thread com app context PRÓPRIO (logo, sessão
    própria do Flask-SQLAlchemy, que é escopada pelo app context). Uma
    barreira solta todos juntos. Cada thread faz commit do que o trabalho
    deixou pendente, ou rollback se ele levantou, e devolve a conexão ao
    pool (``session.remove``): nada fica aberto para o próximo teste.

    Devolve, na ordem, ``('ok', valor)`` ou ``('erro', excecao)``.
    """
    from app import db
    barreira = threading.Barrier(len(trabalhos))
    saida = [None] * len(trabalhos)

    def rodar(i, trabalho):
        with app.app_context():
            try:
                barreira.wait(10)
                valor = trabalho()
                db.session.commit()
                saida[i] = ('ok', valor)
            except Exception as erro:          # noqa: BLE001 — o teste decide
                db.session.rollback()
                saida[i] = ('erro', erro)
            finally:
                db.session.remove()

    linhas = [threading.Thread(target=rodar, args=(i, t), daemon=True)
              for i, t in enumerate(trabalhos)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join(prazo)
    assert all(s is not None for s in saida), 'uma das threads não voltou (trava presa?)'
    return saida


def _oks(saida):
    return [v for k, v in saida if k == 'ok']


def _erros(saida):
    return [v for k, v in saida if k == 'erro']


def _duplicatas(modelo, *colunas):
    """Grupos de (colunas) com mais de uma linha — deve ser sempre []."""
    from app import db
    cols = [getattr(modelo, c) for c in colunas]
    return (db.session.query(*cols, db.func.count(modelo.id))
            .group_by(*cols).having(db.func.count(modelo.id) > 1).all())


# ── Cenas ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def cena_rota(app_module):
    """Uma rota todos os dias, 07:00–15:00, checklist sem foto obrigatória,
    tarefa às 09:00 e 11:00, a Ana escalada; presença ligada (2 por turno)."""
    from app import db
    from facilities.cadastros.models import PontoInspecao
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ana = fabrica.pessoa(app_module, 'ana.conc@trino.com', 'encarregado',
                             locais=['Shopping Centro'], nome='Ana Concorrente')
        mariana = fabrica.pessoa(app_module, 'mariana.conc@trino.com', 'encarregado',
                                 locais=['Shopping Centro'], nome='Mariana Concorrente')
        m = s.criar_modelo(loc.id, {'nome': 'Checklist da corrida'}, None)
        v, _ = s.publicar(m, s.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]),
                          {}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'Rota da corrida', 'turno': '1º Turno',
                                         'hora_inicio': '07:00', 'hora_fim': '15:00',
                                         'tolerancia_min': '15', 'dias_semana': '1234567',
                                         'presencas_por_turno': '2',
                                         'presenca_prazo_min': '10'})
        item = s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                          'horarios': '09:00, 11:00'})
        s.salvar_escala(rota, {'user_id': ana, 'dias_semana': '1234567',
                               'data_inicio': '2026-10-01'})
        db.session.commit()
        ids.update(modelo=m.id, versao=v.id, rota=rota.id, item=item.id, ana=ana,
                   mariana=mariana, qr=db.session.get(PontoInspecao, ids['ponto']).codigo_qr)
    # Fora do ``with``: um app context vivo na thread principal seria
    # reaproveitado por todos os pedidos do test client (Flask ≥ 2.2), e o
    # ``g._login_user`` do primeiro login contaminaria os logins seguintes.
    return ids


def _tarefa_das(dia, hhmm):
    from facilities.rotas.models import TarefaDia
    return TarefaDia.query.filter_by(data=dia, previsto_para=utc(dia, hhmm)).one()


def _executar(user_id, tarefa_id, qr, lido, envio):
    """Um envio do aplicativo: QR lido, resposta, sem fotos."""
    from app import User, db
    from facilities.rotas import servico as s
    u = db.session.get(User, user_id)
    dados = {'envio_id': envio, 'ponto': qr, 'tarefa_id': tarefa_id,
             'respostas': {'ok': 'sim'}, 'sem_sinal': True,
             'lido_em': lido.isoformat(), 'concluida_em': lido.isoformat()}
    ex, nova = s.registrar_execucao(u, dados, {}, agora_utc=lido + timedelta(minutes=1))
    return ex.id, nova, ex.tarefa_id, ex.extra


# ── 1. Mesmo envio_id, duas threads ───────────────────────────────────────

def test_mesmo_envio_id_em_duas_threads_grava_uma_execucao(app_module, cena_rota):
    """A fila sem sinal reenvia; o clique duplo manda duas vezes. O mesmo
    ``envio_id`` chegando junto grava UMA execução; o outro pedido recebe a
    mesma execução (``nova=False``), nunca 500 nem duplicata.

    Protege: ``Execucao.envio_id`` é ``unique`` (rotas/models.py, classe
    ``Execucao``) e ``registrar_execucao`` trata o ``IntegrityError`` do
    ``flush`` devolvendo a execução já gravada (rotas/servico.py, bloco
    ``except IntegrityError`` logo após ``db.session.add(ex)``). Com
    ``tarefa_id``, a trava ``with_for_update()`` na tarefa (rotas/servico.py,
    ``elif dados.get('tarefa_id')``) já põe o segundo pedido em fila.
    """
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, Execucao, TarefaDia
    with app_module.app.app_context():
        s.gerar(SEGUNDA, agora_utc=_cedo(SEGUNDA))
        db.session.commit()
        tarefa_id = _tarefa_das(SEGUNDA, '09:00').id
    envio = f'corrida-{uuid.uuid4().hex}'
    lido = utc(SEGUNDA, '09:00')
    saida = _em_paralelo(
        app_module.app,
        lambda: _executar(cena_rota['ana'], tarefa_id, cena_rota['qr'], lido, envio),
        lambda: _executar(cena_rota['ana'], tarefa_id, cena_rota['qr'], lido, envio))
    assert not _erros(saida), _erros(saida)
    (id_a, nova_a, _, _), (id_b, nova_b, _, _) = _oks(saida)
    assert id_a == id_b, 'os dois pedidos devem apontar para a MESMA execução'
    assert sorted([nova_a, nova_b]) == [False, True], 'um grava, o outro recebe a existente'
    with app_module.app.app_context():
        assert Execucao.query.filter_by(envio_id=envio).count() == 1
        t = db.session.get(TarefaDia, tarefa_id)
        assert t.status == CONCLUIDA_NO_PRAZO and t.encerrada_por == cena_rota['ana']
        assert len(t.execucoes) == 1


# ── 2. Dois técnicos na mesma tarefa ──────────────────────────────────────

def test_dois_tecnicos_na_mesma_tarefa_um_vence_e_o_outro_vira_extra(app_module, cena_rota):
    """Ana e Mariana leem o mesmo QR e mandam a MESMA tarefa ao mesmo tempo.
    Uma vence; a outra, que também trabalhou, fica registrada como atividade
    extra. A tarefa fica com UM executor.

    Protege: ``SELECT … FOR UPDATE`` na tarefa (rotas/servico.py, em
    ``registrar_execucao``: ``db.select(TarefaDia)…with_for_update()``) — o
    segundo só lê a tarefa depois do commit do primeiro e a vê concluída;
    daí ``virou_extra`` e ``tarefa = None`` (mesma função, bloco
    ``if tarefa.status in (CONCLUIDA_NO_PRAZO, …)``).
    """
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ENCERRADAS, Execucao, TarefaDia
    with app_module.app.app_context():
        s.gerar(SEGUNDA, agora_utc=_cedo(SEGUNDA))
        db.session.commit()
        tarefa_id = _tarefa_das(SEGUNDA, '11:00').id
    lido = utc(SEGUNDA, '11:00')
    saida = _em_paralelo(
        app_module.app,
        lambda: _executar(cena_rota['ana'], tarefa_id, cena_rota['qr'], lido,
                          f'ana-{uuid.uuid4().hex}'),
        lambda: _executar(cena_rota['mariana'], tarefa_id, cena_rota['qr'], lido,
                          f'mariana-{uuid.uuid4().hex}'))
    assert not _erros(saida), _erros(saida)
    resultados = _oks(saida)
    assert all(nova for _, nova, _, _ in resultados), 'as duas execuções são novas'
    assert sorted(extra for _, _, _, extra in resultados) == [False, True]
    with app_module.app.app_context():
        t = db.session.get(TarefaDia, tarefa_id)
        assert t.status in ENCERRADAS
        da_tarefa = Execucao.query.filter_by(tarefa_id=tarefa_id).all()
        assert len(da_tarefa) == 1, 'a tarefa tem UM executor'
        assert t.encerrada_por == da_tarefa[0].user_id
        extra = Execucao.query.filter_by(extra=True).one()
        assert extra.tarefa_id is None and extra.user_id != da_tarefa[0].user_id
        assert extra.observacao.startswith('[Registrada como atividade extra')


# ── 3. garantir_hoje / gerar em duas threads ──────────────────────────────

def test_garantir_hoje_em_duas_threads_nao_duplica_tarefa(app_module, cena_rota):
    """A tela "Meu turno" (``garantir_hoje``) aberta em dois aparelhos, ou a
    tela e o agendador, na mesma virada do dia. Nenhuma tarefa duplicada
    para o mesmo item e horário, e cada tarefa criada por UMA das rodadas.

    Protege: ``uq_tarefas_dia_item_hora`` (rotas/models.py, ``TarefaDia``)
    mais o savepoint por tarefa em ``gerar`` (rotas/servico.py:
    ``with db.session.begin_nested(): db.session.add(t)`` e o
    ``except IntegrityError: pass``). No Postgres o segundo INSERT espera o
    commit do primeiro na chave única e aí falha só naquele savepoint.
    """
    from facilities.rotas import servico as s
    from facilities.rotas.models import ConfirmacaoPresenca, TarefaDia
    local_id = cena_rota['local']
    saida = _em_paralelo(app_module.app,
                         lambda: s.garantir_hoje([local_id]),
                         lambda: s.garantir_hoje([local_id]))
    assert not _erros(saida), _erros(saida)
    with app_module.app.app_context():
        assert _duplicatas(TarefaDia, 'rota_item_id', 'previsto_para') == []
        assert _duplicatas(ConfirmacaoPresenca, 'rota_id', 'user_id', 'pedido_em') == []
        hoje = tempo.hoje()
        assert TarefaDia.query.filter_by(data=hoje).count() == 2
        assert TarefaDia.query.filter_by(data=hoje - timedelta(days=1)).count() == 2
        # Cada tarefa foi contada como criada por exatamente uma rodada.
        assert sum(_oks(saida)) == 4


def test_gerar_com_presenca_em_duas_threads_nao_duplica_pedido(app_module, cena_rota):
    """A mesma disputa num dia fixo, de madrugada (todos os horários de
    presença ainda no futuro): nem tarefa nem pedido de presença duplicado,
    e nenhuma das rodadas estoura.

    Protege: além da chave e do savepoint das tarefas, a chave
    ``uq_confirmacoes_presenca_pedido`` (rotas/models.py,
    ``ConfirmacaoPresenca``) e o savepoint por pedido em ``presenca.gerar``
    (rotas/presenca.py: ``with db.session.begin_nested()`` em volta do
    ``db.session.add(ConfirmacaoPresenca(…))``, com ``except
    IntegrityError``). Sem esse savepoint, o INSERT do pedido falhava fora
    de savepoint e derrubava a rodada inteira (``PendingRollbackError``).
    """
    from facilities.rotas import servico as s
    from facilities.rotas.models import ConfirmacaoPresenca, TarefaDia
    local_id = cena_rota['local']
    saida = _em_paralelo(
        app_module.app,
        lambda: s.gerar(SEGUNDA, [local_id], agora_utc=_cedo(SEGUNDA)),
        lambda: s.gerar(SEGUNDA, [local_id], agora_utc=_cedo(SEGUNDA)))
    assert not _erros(saida), _erros(saida)
    with app_module.app.app_context():
        assert _duplicatas(TarefaDia, 'rota_item_id', 'previsto_para') == []
        assert _duplicatas(ConfirmacaoPresenca, 'rota_id', 'user_id', 'pedido_em') == []
        assert TarefaDia.query.filter_by(data=SEGUNDA).count() == 2
        assert ConfirmacaoPresenca.query.filter_by(data=SEGUNDA).count() == 2
        assert sum(_oks(saida)) == 2


# ── 4. Duas rodadas do agendador ao mesmo tempo ───────────────────────────

def test_duas_rodadas_do_agendador_ao_mesmo_tempo_so_uma_trabalha(app_module, cena_rota):
    """Relógio atrasado + comando manual, ou um deploy no meio: duas rodadas
    de ``rodar()`` juntas. O aviso de presença chega UMA vez, as tarefas
    perdidas de sexta fecham UMA vez, e só uma rodada fica registrada como
    feita (a outra devolve ``None``).

    Protege: ``pg_try_advisory_xact_lock`` em ``_outra_rodada_em_andamento``
    (rotas/servico.py, constante ``TRAVA_DO_AGENDADOR``): a segunda rodada
    não consegue a trava e ``rodar`` devolve ``None`` sem fazer nada. A
    trava cai no commit da primeira.
    """
    from app import db
    from facilities.core.models import Notification
    from facilities.rotas import servico as s
    from facilities.rotas.models import (
        PERDIDA,
        AgendadorExecucao,
        ConfirmacaoPresenca,
        TarefaDia,
    )
    with app_module.app.app_context():
        s.gerar(SEXTA, agora_utc=_cedo(SEXTA))          # vai vencer sem registro
        s.gerar(SEGUNDA, agora_utc=_cedo(SEGUNDA))      # o turno "de agora"
        db.session.commit()
        p1 = (ConfirmacaoPresenca.query.filter_by(data=SEGUNDA)
              .order_by(ConfirmacaoPresenca.pedido_em).first())
        agora = p1.pedido_em + timedelta(minutes=1)     # hora de avisar a presença
        tarefas_sexta = [t.id for t in TarefaDia.query.filter_by(data=SEXTA)]
    assert len(tarefas_sexta) == 2

    def rodada():
        reg = s.rodar(origem='teste', agora_utc=agora)
        return reg.id if reg is not None else None

    saida = _em_paralelo(app_module.app, rodada, rodada)
    assert not _erros(saida), _erros(saida)
    feitas = [r for r in _oks(saida) if r is not None]
    assert len(feitas) == 1, f'só uma rodada trabalha; a outra devolve None: {saida}'
    with app_module.app.app_context():
        assert Notification.query.filter_by(user_id=cena_rota['ana'],
                                            title='Confirme que você está no posto').count() == 1
        for tid in tarefas_sexta:
            t = db.session.get(TarefaDia, tid)
            assert t.status == PERDIDA and t.encerrada_em == agora
        regs = AgendadorExecucao.query.filter_by(origem='teste').all()
        assert len(regs) == 1 and regs[0].ok and regs[0].tarefas_perdidas == 2
        p1 = db.session.get(ConfirmacaoPresenca, p1.id)
        assert p1.avisado_em == agora


# ── 5. A mesma confirmação de presença, duas threads ──────────────────────

def test_confirmar_a_mesma_presenca_em_duas_threads_e_uma_confirmacao(app_module, cena_rota):
    """A Ana toca "Estou no posto" em dois aparelhos (ou duas vezes). Fica
    UMA confirmação: a mesma linha, ``confirmada``, com uma só hora de
    resposta — e os dois pedidos recebem "confirmada", nunca erro.

    Protege: a confirmação é um UPDATE da MESMA linha (``presenca.confirmar``,
    rotas/presenca.py), e não um INSERT; a linha é única por
    ``uq_confirmacoes_presenca_pedido`` (rotas/models.py). O Postgres põe o
    segundo UPDATE em fila atrás do primeiro, e ``confirmar`` é idempotente
    (``if c.status == PRESENCA_CONFIRMADA: return c``).
    """
    from app import db
    from facilities.rotas.models import PRESENCA_CONFIRMADA, ConfirmacaoPresenca, Rota
    with app_module.app.app_context():
        rota = db.session.get(Rota, cena_rota['rota'])
        agora = datetime.now(timezone.utc).replace(tzinfo=None)   # UTC ingênuo, como as colunas
        c = ConfirmacaoPresenca(rota_id=rota.id, client_id=rota.client_id,
                                user_id=cena_rota['ana'], data=tempo.hoje(),
                                pedido_em=agora - timedelta(minutes=1),
                                prazo_ate=agora + timedelta(minutes=9))
        db.session.add(c)
        db.session.commit()
        cid = c.id
    aparelho_a = fabrica.entrar(app_module, 'ana.conc@trino.com')
    aparelho_b = fabrica.entrar(app_module, 'ana.conc@trino.com')
    saida = _em_paralelo(app_module.app,
                         lambda: aparelho_a.post(f'/app/api/presenca/{cid}'),
                         lambda: aparelho_b.post(f'/app/api/presenca/{cid}'))
    assert not _erros(saida), _erros(saida)
    respostas = _oks(saida)
    assert [r.status_code for r in respostas] == [200, 200], \
        [r.get_data(as_text=True) for r in respostas]
    assert all(r.get_json()['status'] == PRESENCA_CONFIRMADA for r in respostas)
    with app_module.app.app_context():
        c = db.session.get(ConfirmacaoPresenca, cid)
        assert c.status == PRESENCA_CONFIRMADA and c.respondida_em is not None
        assert c.pedido_em <= c.respondida_em <= c.prazo_ate
        assert ConfirmacaoPresenca.query.filter_by(rota_id=c.rota_id, user_id=c.user_id,
                                                   pedido_em=c.pedido_em).count() == 1


# ── 6. Estoque: consumo em paralelo e pedido de insumo ────────────────────

@pytest.fixture()
def cena_estoque(app_module):
    """Detergente com 10 L no Shopping Centro; Ana e Mariana consomem."""
    from app import Client, User, db
    from facilities.materiais import servico as mat
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ids['ana'] = fabrica.pessoa(app_module, 'ana.estq@trino.com', 'encarregado',
                                    locais=['Shopping Centro'], nome='Ana')
        ids['mariana'] = fabrica.pessoa(app_module, 'mariana.estq@trino.com', 'encarregado',
                                        locais=['Shopping Centro'], nome='Mariana')
        ids['coord'] = fabrica.pessoa(app_module, 'coord.estq@trino.com', 'pleno',
                                      locais=['Shopping Centro'], nome='Coordenação')
        det = mat.salvar_material(None, {'nome': 'Detergente da corrida', 'unidade': 'L',
                                         'preco_unitario': '12,90'})
        mat.movimentar(db.session.get(User, ids['coord']), db.session.get(Client, ids['local']),
                       {'material_id': str(det.id), 'quantidade': '10'}, 'entrada')
        db.session.commit()
        ids['det'] = det.id
    return ids


def _consumir(user_id, local_id, material_id, qtd):
    from app import Client, User, db
    from facilities.materiais import servico as mat
    mov = mat.consumir(db.session.get(User, user_id), db.session.get(Client, local_id),
                       {'material_id': str(material_id), 'quantidade': qtd})
    return mov.id


def test_dois_consumos_que_estourariam_o_saldo_um_e_recusado(app_module, cena_estoque):
    """Há 10 L; Ana e Mariana lançam 8 L cada ao mesmo tempo. Sem trava os
    dois leriam "10", os dois passariam e o saldo iria a −6 sem autorização.
    Aqui um passa e o outro ouve "saldo insuficiente"; o saldo fica em 2.

    Protege: ``_travar(client_id)`` (materiais/servico.py) — ``SELECT … FOR NO
    KEY UPDATE`` na linha do local (``with_for_update(key_share=True)`` sem
    ``read`` gera FOR NO KEY UPDATE, que conflita consigo mesmo); e o saldo
    é calculado DEPOIS da trava (``movimentar``: ``_travar(local.id)`` e só
    então ``saldo(local.id, mat.id)``). Em READ COMMITTED a soma do segundo
    já enxerga o movimento que o primeiro acabou de gravar.
    """
    from decimal import Decimal

    from facilities.materiais import servico as mat
    from facilities.materiais.models import CONSUMO, MovimentoEstoque
    c = cena_estoque
    saida = _em_paralelo(app_module.app,
                         lambda: _consumir(c['ana'], c['local'], c['det'], '8'),
                         lambda: _consumir(c['mariana'], c['local'], c['det'], '8'))
    assert len(_oks(saida)) == 1 and len(_erros(saida)) == 1, saida
    erro = _erros(saida)[0]
    assert isinstance(erro, mat.RegraDoMaterial) and erro.codigo == 409
    assert 'Saldo insuficiente' in erro.mensagem
    with app_module.app.app_context():
        assert mat.saldo(c['local'], c['det']) == Decimal('2.000')
        assert MovimentoEstoque.query.filter_by(client_id=c['local'], material_id=c['det'],
                                                tipo=CONSUMO).count() == 1
        assert all(m.autorizado_por is None for m in MovimentoEstoque.query.all())


def test_dois_consumos_dentro_do_saldo_nenhum_se_perde(app_module, cena_estoque):
    """Há 10 L; 3 L e 4 L ao mesmo tempo: os dois entram e o saldo é 3.

    Protege: cada consumo é um INSERT próprio em ``movimentos_estoque`` e o
    saldo é a SOMA dos movimentos (``materiais/servico.py``, ``saldo``), não
    um número guardado à parte que uma escrita pudesse sobrescrever. A trava
    de ``_travar`` só põe em fila; não perde nada.
    """
    from decimal import Decimal

    from facilities.materiais import servico as mat
    from facilities.materiais.models import CONSUMO, MovimentoEstoque
    c = cena_estoque
    saida = _em_paralelo(app_module.app,
                         lambda: _consumir(c['ana'], c['local'], c['det'], '3'),
                         lambda: _consumir(c['mariana'], c['local'], c['det'], '4'))
    assert not _erros(saida), _erros(saida)
    with app_module.app.app_context():
        assert mat.saldo(c['local'], c['det']) == Decimal('3.000')
        movs = MovimentoEstoque.query.filter_by(tipo=CONSUMO).all()
        assert sorted(m.quantidade for m in movs) == [Decimal('-4.000'), Decimal('-3.000')]
        assert {m.user_id for m in movs} == {c['ana'], c['mariana']}


# Protege: materiais/servico.py, pedir() — trava a linha do local (_travar) e
# devolve o pedido igual da mesma pessoa aberto nos últimos 2 minutos
# (JANELA_DE_REENVIO), como chamados.abrir_sem_duplicar.
def test_pedido_de_insumo_enviado_duas_vezes_ao_mesmo_tempo_abre_um_pedido(app_module,
                                                                         cena_estoque):
    from facilities.core.models import Notification
    from facilities.materiais.models import PedidoInsumo
    c = cena_estoque

    def pedir():
        from app import Client, User, db
        from facilities.materiais import servico as mat
        p = mat.pedir(db.session.get(User, c['ana']), db.session.get(Client, c['local']),
                      {'material_id': str(c['det']), 'quantidade': '5',
                       'texto': 'Acabou o detergente'})
        return p.id

    saida = _em_paralelo(app_module.app, pedir, pedir)
    assert not _erros(saida), _erros(saida)
    with app_module.app.app_context():
        assert PedidoInsumo.query.filter_by(client_id=c['local'], user_id=c['ana']).count() == 1
        assert Notification.query.filter_by(notification_type='insumo').count() <= 1
    assert len(set(_oks(saida))) == 1, 'os dois envios devem devolver o MESMO pedido'


# ── 7. Chamado: resolver × reabrir ao mesmo tempo ─────────────────────────

@pytest.fixture()
def cena_chamado(app_module):
    """Encarregado abre, gestora atribui ao técnico, técnico inicia e
    resolve. Devolve o chamado em "resolvido — aguardando confirmação"."""
    from app import Client, User, db
    from facilities.chamados import servico as ch_s
    with app_module.app.app_context():
        c1 = fabrica.local()
        ids = {'c1': c1.id}
        ids['enc'] = fabrica.pessoa(app_module, 'enc.conc@trino.com', 'encarregado',
                                    locais=['Shopping Centro'], nome='Encarregado Bia')
        ids['gestora'] = fabrica.pessoa(app_module, 'gestora.conc@trino.com', 'pleno',
                                        locais=['Shopping Centro'], nome='Gestora Ana')
        ids['tec'] = fabrica.pessoa(app_module, 'tec.conc@trino.com', 'tecnico',
                                    locais=['Shopping Centro'], nome='Técnico Caio')
        c1.responsible_user_id = ids['gestora']
        enc, gestora, tec = (db.session.get(User, ids[k]) for k in ('enc', 'gestora', 'tec'))
        ch = ch_s.abrir(enc, c1.id, 'Torneira da corrida', categoria='hidraulica')
        ch_s.executar(gestora, ch, 'atribuir', {'responsavel_id': str(tec.id)})
        ch_s.executar(tec, ch, 'iniciar', {})
        ch_s.executar(tec, ch, 'resolver', {'texto': 'Troquei o reparo'})
        db.session.commit()
        ids['ch'] = ch.id
    yield ids
    with app_module.app.app_context():
        db.session.get(Client, ids['c1']).responsible_user_id = None
        db.session.commit()


def test_resolver_e_reabrir_ao_mesmo_tempo_deixam_estado_e_trilha_coerentes(app_module,
                                                                          cena_chamado):
    """O chamado está "resolvido". O encarregado toca "Reabrir" (não ficou
    bom) no mesmo instante em que o técnico, numa tela velha, toca
    "Resolver" de novo com outro texto. Dois desfechos são aceitáveis, e os
    dois têm trilha coerente:

    * reabrir primeiro → o resolver entra em cima do reaberto: termina
      ``resolvido``, trilha … resolvido, reaberto, resolvido;
    * resolver primeiro → recusado (chamado já resolvido), depois reabrir:
      termina ``em_atendimento``, trilha … resolvido, reaberto.

    O que NÃO pode: os dois gravarem lendo o mesmo estado velho (dois
    "reaberto", ou "resolvido" sem ``resolvido_em``, ou situação diferente
    do último passo da trilha).

    Protege: a rota ``/chamados/<id>/acao`` carrega o chamado com
    ``servico.chamado_para_alterar`` (chamados/rotas.py,
    ``_chamado_autorizado(…, travar=True)``), que faz ``SELECT … FOR NO KEY
    UPDATE`` com ``populate_existing`` (chamados/servico.py,
    ``chamado_para_alterar``); ``executar`` confere ``acoes_disponiveis``
    contra o estado NOVO.
    """
    from app import db
    from facilities.chamados.models import (
        EM_ATENDIMENTO,
        RESOLVIDO,
        Chamado,
        ChamadoEvento,
    )
    c = cena_chamado
    enc = fabrica.entrar(app_module, 'enc.conc@trino.com')
    tec = fabrica.entrar(app_module, 'tec.conc@trino.com')
    saida = _em_paralelo(
        app_module.app,
        lambda: enc.post(f'/chamados/{c["ch"]}/acao',
                         data={'acao': 'reabrir', 'texto': 'Ainda pinga'}),
        lambda: tec.post(f'/chamados/{c["ch"]}/acao',
                         data={'acao': 'resolver', 'texto': 'Apertei de novo'}))
    assert not _erros(saida), _erros(saida)
    assert [r.status_code for r in _oks(saida)] == [302, 302], \
        [r.get_data(as_text=True)[:300] for r in _oks(saida)]
    with app_module.app.app_context():
        ch = db.session.get(Chamado, c['ch'])
        eventos = (ChamadoEvento.query.filter_by(chamado_id=ch.id)
                   .order_by(ChamadoEvento.id).all())
        tipos = [e.tipo for e in eventos]
        assert tipos[:4] == ['aberto', 'atribuido', 'iniciado', 'resolvido']
        assert tipos.count('reaberto') == 1, tipos
        assert tipos[4] == 'reaberto', tipos
        assert tipos[5:] in ([], ['resolvido']), tipos
        esperado = {'reaberto': EM_ATENDIMENTO, 'resolvido': RESOLVIDO}[tipos[-1]]
        assert ch.status == esperado, (ch.status, tipos)
        assert (ch.resolvido_em is not None) == (ch.status == RESOLVIDO)
        if ch.status == RESOLVIDO:
            assert ch.solucao == 'Apertei de novo'
        else:
            assert ch.solucao == 'Troquei o reparo' and ch.responsavel_id == c['tec']




