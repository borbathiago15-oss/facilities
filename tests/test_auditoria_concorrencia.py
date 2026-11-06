"""Auditoria, Fase 3 — corridas que os testes de concorrência ainda não cobriam.

Roda só com ``TEST_DATABASE_URL`` num Postgres (o SQLite serializa as
escritas e esconde a disputa). Cada cenário solta dois (ou mais) pedidos
juntos, cada um no seu cliente de teste e na sua sessão, atrás de uma
barreira, e repete algumas rodadas: a corrida que existe aparece em quase
todas. O que o código não protege fica ``xfail(strict=True)`` com o defeito
descrito em ``reason`` — nada do aplicativo foi alterado.

Já cobertos em ``test_concorrencia.py`` e ``test_chamados_concorrencia.py``
(não repetidos aqui): envio_id da execução, dois técnicos na mesma tarefa,
``garantir_hoje``/``gerar`` em duas threads, duas rodadas do agendador,
presença, estoque, pedido de insumo, resolver × reabrir, duplo resolver,
cancelar × resolver, comentário repetido, abrir chamado duas vezes, ocorrência
que vira OS duas vezes.
"""
import os
import threading
import uuid
from datetime import date

import pytest

from tests import fabrica
from tests.test_chamados import _acao, _entrar, cena  # noqa: F401

pytestmark = pytest.mark.skipif(
    'postgres' not in os.environ.get('TEST_DATABASE_URL', ''),
    reason='corrida de verdade só no Postgres (TEST_DATABASE_URL)')

RODADAS = 4


def _juntos(*pedidos):
    """Solta os pedidos juntos; devolve as respostas (ou a exceção) na ordem."""
    barreira = threading.Barrier(len(pedidos))
    saida = [None] * len(pedidos)

    def rodar(i, pedido):
        barreira.wait(10)
        try:
            saida[i] = pedido()
        except Exception as erro:            # noqa: BLE001 — o teste decide
            saida[i] = erro

    linhas = [threading.Thread(target=rodar, args=(i, p), daemon=True)
              for i, p in enumerate(pedidos)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join(60)
    assert all(r is not None for r in saida), 'um dos pedidos não voltou (trava presa?)'
    return saida


def _status(respostas):
    return [getattr(r, 'status_code', repr(r)) for r in respostas]


# ── Passagem de turno ─────────────────────────────────────────────────────

@pytest.fixture()
def cena_passagem(app_module):
    import json

    from app import db
    from facilities.passagem.models import DiarioArea, DiarioConfiguracao
    with app_module.app.app_context():
        loc = fabrica.local()
        enc = fabrica.pessoa(app_module, 'enc.f3@trino.com', 'encarregado',
                             locais=[loc.name], nome='Encarregada Fase Três')
        area = DiarioArea(client_id=loc.id, nome='Limpeza F3', ativo=True, created_by=enc)
        db.session.add(area)
        db.session.flush()
        cfg = DiarioConfiguracao(
            client_id=loc.id, area_id=area.id, nome='Limpeza — F3',
            turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Banheiros', 'codigo': 'banheiros',
                                         'obrigatorio': False}]),
            tipos_ocorrencia_json='[]', ativo=True, created_by=enc)
        db.session.add(cfg)
        db.session.commit()
        return {'local': loc.id, 'cfg': cfg.id, 'enc': enc}


def _passagem(cena_p, turno, envio, finalizar):
    return {'client_id': cena_p['local'], 'configuracao_id': cena_p['cfg'],
            'data_turno': date(2026, 11, 2).isoformat(), 'turno': turno, 'envio_id': envio,
            'dados': {'banheiros': 'ok'}, 'observacao': 'Sem novidades',
            'pendencias': [{'titulo': 'Repor papel toalha', 'prioridade': 'media'}],
            'ocorrencias': [{'tipo': 'Outros', 'descricao': 'Lâmpada piscando'}],
            'finalizar': finalizar}


@pytest.mark.xfail(strict=True, reason=(
    'BUG: "Encerrar turno" que chega duas vezes ao mesmo tempo (a fila sem sinal '
    'reenviando + o toque na tela) grava DUAS passagens encerradas do mesmo '
    'contrato/modelo/dia/turno, com pendências e ocorrências em dobro. '
    'salvar_turno (facilities/passagem/rotas.py, POST /api/turnos) procura o turno '
    'com SELECT e cria se não achou, sem trava e sem chave única em '
    'diario_operacional_turnos (client_id, configuracao_id, data_turno, turno). '
    'A idempotência por envio_id só vale em sequência. Correção: trava do contrato '
    '(SELECT … FOR NO KEY UPDATE em clients, como chamados._travar_contrato) antes '
    'da busca, e índice único (com migração e quarentena das duplicatas).'))
def test_encerrar_a_mesma_passagem_duas_vezes_ao_mesmo_tempo_grava_uma(app_module,
                                                                    cena_passagem):
    from facilities.passagem.models import DiarioPendencia, DiarioTurno
    a = fabrica.entrar(app_module, 'enc.f3@trino.com')
    b = fabrica.entrar(app_module, 'enc.f3@trino.com')
    url = '/passagem-de-turno/api/turnos'
    for i in range(RODADAS):
        turno, envio = f'Turno corrida {i}', uuid.uuid4().hex
        corpo = _passagem(cena_passagem, turno, envio, finalizar=True)
        respostas = _juntos(lambda: a.post(url, json=corpo), lambda: b.post(url, json=corpo))
        assert all(s in (200, 201) for s in _status(respostas)), _status(respostas)
        with app_module.app.app_context():
            ids = [t.id for t in DiarioTurno.query.filter_by(
                client_id=cena_passagem['local'], configuracao_id=cena_passagem['cfg'],
                turno=turno)]
            assert len(ids) == 1, f'rodada {i}: {len(ids)} passagens encerradas'
            assert DiarioPendencia.query.filter(DiarioPendencia.turno_id.in_(ids)).count() == 1


@pytest.mark.xfail(strict=True, reason=(
    'BUG: o mesmo rascunho salvo em dois aparelhos ao mesmo tempo duplica a pendência '
    '(e a ocorrência). salvar_turno lê as pendências já gravadas do turno (ja_pend) e '
    'só então insere as que faltam, sem trava no turno: as duas requisições leem a '
    'lista vazia e as duas inserem. Correção: SELECT … FOR UPDATE no DiarioTurno '
    'achado (ou a trava do contrato do item anterior) antes de montar ja_pend/ja_ocor.'))
def test_rascunho_salvo_em_dois_aparelhos_ao_mesmo_tempo_nao_duplica_pendencia(
        app_module, cena_passagem):
    from facilities.passagem.models import DiarioOcorrencia, DiarioPendencia, DiarioTurno
    a = fabrica.entrar(app_module, 'enc.f3@trino.com')
    b = fabrica.entrar(app_module, 'enc.f3@trino.com')
    url = '/passagem-de-turno/api/turnos'
    for i in range(RODADAS):
        turno = f'Rascunho corrida {i}'
        vazio = dict(_passagem(cena_passagem, turno, None, False), pendencias=[],
                     ocorrencias=[])
        assert a.post(url, json=vazio).status_code == 201      # o rascunho já existe
        corpo = _passagem(cena_passagem, turno, None, finalizar=False)
        respostas = _juntos(lambda: a.post(url, json=corpo), lambda: b.post(url, json=corpo))
        assert all(s in (200, 201) for s in _status(respostas)), _status(respostas)
        with app_module.app.app_context():
            t = DiarioTurno.query.filter_by(client_id=cena_passagem['local'],
                                            turno=turno).one()
            assert DiarioPendencia.query.filter_by(turno_id=t.id).count() == 1, f'rodada {i}'
            assert DiarioOcorrencia.query.filter_by(turno_id=t.id).count() == 1, f'rodada {i}'


# ── Cadastro de pessoas ───────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=(
    'BUG: duas criações da mesma pessoa ao mesmo tempo (duplo clique em "Criar" '
    'em Pessoas e acessos, ou dois administradores) → a segunda responde 500. '
    'acao_criar_usuario (facilities/core/admin.py) confere o e-mail com '
    'User.por_email e faz commit sem tratar o IntegrityError de users.email_index '
    '(único). O banco não deixa duplicar (nenhum dado perdido), mas a pessoa vê '
    '"erro interno" e não sabe se a conta foi criada. Correção: capturar '
    'IntegrityError no commit → rollback e o recado "Já existe uma pessoa com este '
    'e-mail" (400/409), como já faz o aceite de convite (novo_contrato.aceitar_enviar).'))
def test_mesma_pessoa_criada_duas_vezes_ao_mesmo_tempo_nao_da_500(app_module):
    from app import User, db
    from tests.test_chamados import _entrar_admin
    a = _entrar_admin(app_module)
    b = _entrar_admin(app_module)
    criados = []
    try:
        for i in range(RODADAS):
            email = f'dupla.{i}.{uuid.uuid4().hex[:6]}@trino.com'
            criados.append(email)
            form = {'name': f'Pessoa Dupla {i}', 'email': email, 'role': 'encarregado'}
            respostas = _juntos(lambda: a.post('/admin/usuarios', data=form),
                                lambda: b.post('/admin/usuarios', data=form))
            with app_module.app.app_context():
                assert User.query.filter_by(email_index=User.por_email(email).email_index) \
                    .count() == 1
            assert all(isinstance(s, int) and s < 500 for s in _status(respostas)), \
                f'rodada {i}: {_status(respostas)}'
    finally:
        with app_module.app.app_context():
            for email in criados:
                u = User.por_email(email)
                if u is not None:
                    db.session.delete(u)
            db.session.commit()


# ── Chamados: duas pessoas mexendo no MESMO chamado ───────────────────────

def _chamado_aberto(app_module, cena, enc, titulo):  # noqa: F811
    from facilities.chamados.models import Chamado
    r = enc.post('/chamados/', data={'client_id': cena['c1'], 'titulo': titulo,
                                     'categoria': 'hidraulica', 'prioridade': 'media'})
    assert r.status_code == 302
    with app_module.app.app_context():
        return Chamado.query.filter_by(titulo=titulo).one().id


def test_duas_gestoras_atribuem_tecnicos_diferentes_ao_mesmo_tempo(app_module, cena):  # noqa: F811
    """Uma gestora manda o Caio, outra (em outra aba) manda o Davi, no mesmo
    instante. Os dois pedidos passam (um depois do outro, pela trava de
    ``chamado_para_alterar``), e o responsável final é o do ÚLTIMO evento —
    nunca um responsável que a trilha não mostra."""
    from app import db
    from facilities.chamados.models import Chamado, ChamadoEvento
    enc = _entrar(app_module, 'enc.ch@trino.com')
    g1 = _entrar(app_module, 'gestora.ch@trino.com')
    g2 = _entrar(app_module, 'gestora.ch@trino.com')
    for i in range(RODADAS):
        ch_id = _chamado_aberto(app_module, cena, enc, f'Atribuir junto {i}')
        respostas = _juntos(lambda: _acao(g1, ch_id, 'atribuir', responsavel_id=cena['tec']),
                            lambda: _acao(g2, ch_id, 'atribuir', responsavel_id=cena['tec2']))
        assert _status(respostas) == [302, 302]
        with app_module.app.app_context():
            ch = db.session.get(Chamado, ch_id)
            ev = (ChamadoEvento.query.filter_by(chamado_id=ch_id, tipo='atribuido')
                  .order_by(ChamadoEvento.id).all())
            assert len(ev) == 2, [e.texto for e in ev]
            assert ch.responsavel.name in ev[-1].texto and '(antes:' in ev[-1].texto


def test_atribuir_e_mudar_prioridade_ao_mesmo_tempo_nao_perde_nenhum(app_module, cena):  # noqa: F811
    """Gestora troca o responsável enquanto a outra aba sobe a prioridade:
    as DUAS mudanças ficam (nenhuma escrita sobrescreve a outra com o valor
    velho — o "read-modify-write" perdido)."""
    from app import db
    from facilities.chamados.models import Chamado
    enc = _entrar(app_module, 'enc.ch@trino.com')
    g1 = _entrar(app_module, 'gestora.ch@trino.com')
    g2 = _entrar(app_module, 'gestora.ch@trino.com')
    for i in range(RODADAS):
        ch_id = _chamado_aberto(app_module, cena, enc, f'Prioridade junto {i}')
        _juntos(lambda: _acao(g1, ch_id, 'atribuir', responsavel_id=cena['tec']),
                lambda: _acao(g2, ch_id, 'prioridade', prioridade='alta', texto='Cliente ligou'))
        with app_module.app.app_context():
            ch = db.session.get(Chamado, ch_id)
            assert (ch.responsavel_id, ch.prioridade) == (cena['tec'], 'alta'), f'rodada {i}'


def test_cinco_comentarios_diferentes_ao_mesmo_tempo_nenhum_se_perde(app_module, cena):  # noqa: F811
    from facilities.chamados.models import ChamadoEvento
    enc = _entrar(app_module, 'enc.ch@trino.com')
    pessoas = [_entrar(app_module, e) for e in ('enc.ch@trino.com', 'gestora.ch@trino.com',
                                                 'tec.ch@trino.com', 'tec2.ch@trino.com',
                                                 'gestora.ch@trino.com')]
    ch_id = _chamado_aberto(app_module, cena, enc, 'Comentários juntos')
    respostas = _juntos(*[(lambda p=p, k=k: _acao(p, ch_id, 'comentar', texto=f'Nota {k}'))
                          for k, p in enumerate(pessoas)])
    assert _status(respostas) == [302] * 5
    with app_module.app.app_context():
        textos = sorted(e.texto for e in ChamadoEvento.query.filter_by(chamado_id=ch_id,
                                                                       tipo='comentario'))
        assert textos == [f'Nota {k}' for k in range(5)]


def test_tecnico_inicia_enquanto_a_gestora_passa_para_outro(app_module, cena):  # noqa: F811
    """"Dois técnicos pegando a mesma OS": o Caio toca "Iniciar" no instante
    em que a gestora passa o chamado para o Davi. Ou o Caio iniciou ANTES da
    troca (a trilha mostra iniciado → atribuído), ou foi recusado — nunca o
    Caio atendendo um chamado que já é do Davi."""
    from app import db
    from facilities.chamados.models import Chamado, ChamadoEvento
    enc = _entrar(app_module, 'enc.ch@trino.com')
    g = _entrar(app_module, 'gestora.ch@trino.com')
    caio = _entrar(app_module, 'tec.ch@trino.com')
    for i in range(RODADAS):
        ch_id = _chamado_aberto(app_module, cena, enc, f'Pegar junto {i}')
        _acao(g, ch_id, 'atribuir', responsavel_id=cena['tec'])
        _juntos(lambda: _acao(caio, ch_id, 'iniciar'),
                lambda: _acao(g, ch_id, 'atribuir', responsavel_id=cena['tec2']))
        with app_module.app.app_context():
            ch = db.session.get(Chamado, ch_id)
            tipos = [(e.tipo, e.created_by) for e in ChamadoEvento.query.filter_by(
                chamado_id=ch_id).order_by(ChamadoEvento.id)]
            assert ch.responsavel_id == cena['tec2']
            iniciados = [k for k, (t, _) in enumerate(tipos) if t == 'iniciado']
            ultimo_atrib = max(k for k, (t, _) in enumerate(tipos) if t == 'atribuido')
            assert all(k < ultimo_atrib for k in iniciados), tipos


def test_dez_chamados_abertos_juntos_tem_numeros_diferentes(app_module, cena):  # noqa: F811
    """O número visível (OS-00012) sai do id da linha (sequência do banco):
    abertos ao mesmo tempo nunca repetem número."""
    from facilities.chamados.models import Chamado
    clientes = [_entrar(app_module, 'enc.ch@trino.com') for _ in range(10)]
    respostas = _juntos(*[(lambda c=c, k=k: c.post('/chamados/', data={
        'client_id': cena['c1'], 'titulo': f'Numeração {k}', 'categoria': 'outro',
        'prioridade': 'media'})) for k, c in enumerate(clientes)])
    assert _status(respostas) == [302] * 10
    with app_module.app.app_context():
        numeros = [c.numero for c in Chamado.query.filter(Chamado.titulo.like('Numeração %'))]
        assert len(numeros) == 10 and len(set(numeros)) == 10


# ── Abertura do turno: muita gente abrindo "Meu turno" junto ──────────────

def test_oito_pessoas_abrindo_meu_turno_juntas_nao_dao_500_nem_duplicam(app_module):
    """A virada do turno: oito encarregadas do mesmo local abrem "Meu turno"
    (``garantir_hoje_e_gravar`` grava as tarefas do dia NA requisição GET) no
    mesmo instante, antes de o agendador rodar. Todas recebem a tela, e cada
    tarefa existe uma vez só (chave ``uq_tarefas_dia_item_hora`` + savepoint
    por tarefa em ``rotas.servico.gerar``)."""
    from app import db
    from facilities import tempo
    from facilities.rotas import servico as s
    from facilities.rotas.models import TarefaDia
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        loc_id = loc.id
        emails = [f'turno{k}.f3@trino.com' for k in range(8)]
        pessoas = [fabrica.pessoa(app_module, e, 'encarregado', locais=[loc.name])
                   for e in emails]
        m = s.criar_modelo(loc.id, {'nome': 'Checklist F3'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]), {}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'Rota F3', 'turno': '1º Turno',
                                         'hora_inicio': '00:00', 'hora_fim': '23:59',
                                         'tolerancia_min': '60', 'dias_semana': '1234567'})
        s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                   'horarios': ', '.join(f'{h:02d}:00' for h in range(24))})
        for uid in pessoas:
            s.salvar_escala(rota, {'user_id': uid, 'dias_semana': '1234567',
                                   'data_inicio': '2026-10-01'})
        db.session.commit()
    clientes = [fabrica.entrar(app_module, e) for e in emails]
    respostas = _juntos(*[(lambda c=c: c.get('/app/turno')) for c in clientes])
    assert _status(respostas) == [200] * 8
    with app_module.app.app_context():
        hoje = tempo.hoje()
        assert TarefaDia.query.filter_by(data=hoje, client_id=loc_id).count() == 24
        dup = (db.session.query(TarefaDia.rota_item_id, TarefaDia.previsto_para)
               .group_by(TarefaDia.rota_item_id, TarefaDia.previsto_para)
               .having(db.func.count(TarefaDia.id) > 1).all())
        assert dup == []
