"""O analítico do Diário Operacional — as contas, e o que elas se recusam a dizer.

A Fase 1 mostrava três contadores. O que se testa aqui é a camada que os
substituiu: aderência ao checklist, eficácia da fila de pendências, o que está
vencido, o índice de desvio por turno, o Pareto, o comparativo entre turnos e
o burn-down.

Cada bloco cobre tanto o número quanto a REGRA que o número carrega — turno
aberto não conta, a exigência vem da configuração do próprio turno, e zero de
zero é "não se aplica", não 0%.
"""
import json
from datetime import date, datetime, timedelta

import pytest

from facilities import tempo
from facilities.passagem import analitico as an


# ── Cenário ──────────────────────────────────────────────────────────────

ATIVIDADES = [
    {'nome': 'DTS direcionados', 'codigo': 'dts', 'obrigatorio': True},
    {'nome': 'Reconferência', 'codigo': 'reconf', 'obrigatorio': True},
    {'nome': 'Abastecimento PVV', 'codigo': 'pvv', 'obrigatorio': True},
    {'nome': '5S', 'codigo': 'cinco_s', 'obrigatorio': True},
    # Opcional: não entra em exigência nenhuma.
    {'nome': 'Café do turno', 'codigo': 'cafe', 'obrigatorio': False},
]


@pytest.fixture()
def cenario(app_module):
    """Um contrato com configuração ativa, e nada lançado ainda."""
    from facilities.passagem.models import DiarioConfiguracao

    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Operação CDV',
            turnos_json=json.dumps([{'nome': 'T1'}, {'nome': 'T2'},
                                    {'nome': 'T3'}]),
            campos_json='[]',
            atividades_json=json.dumps(ATIVIDADES),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Devolução'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'config_id': cfg.id,
                'user_id': admin.id, 'cliente': cliente.name}


def _turno(app_module, cenario, dia, nome, concluidas, status='encerrado',
           observacao=None, config_id=None):
    from facilities.passagem.models import DiarioTurno
    t = DiarioTurno(
        client_id=cenario['client_id'],
        configuracao_id=config_id or cenario['config_id'],
        data_turno=dia, turno=nome, status=status,
        dados_json=json.dumps({f'atividade:{c}': {'concluido': True}
                               for c in concluidas}),
        observacao=observacao, created_by=cenario['user_id'],
        submitted_at=datetime.utcnow() if status == 'encerrado' else None)
    app_module.db.session.add(t)
    app_module.db.session.flush()
    return t


def _pendencia(app_module, cenario, titulo, criada_ha_horas=1,
               prioridade='media', resolvida=False, turno_id=None):
    from facilities.passagem.models import DiarioPendencia
    criada = datetime.utcnow() - timedelta(hours=criada_ha_horas)
    p = DiarioPendencia(
        client_id=cenario['client_id'], turno_id=turno_id, titulo=titulo,
        status='resolvida' if resolvida else 'aberta', prioridade=prioridade,
        created_by=cenario['user_id'], created_at=criada,
        resolved_at=criada + timedelta(hours=1) if resolvida else None)
    app_module.db.session.add(p)
    app_module.db.session.flush()
    return p


def _ocorrencia(app_module, cenario, tipo, turno_id=None, dias_atras=0):
    from facilities.passagem.models import DiarioOcorrencia
    o = DiarioOcorrencia(
        client_id=cenario['client_id'], turno_id=turno_id, tipo=tipo,
        descricao=f'Ocorrência de {tipo}.', status='aberta',
        created_by=cenario['user_id'],
        created_at=datetime.utcnow() - timedelta(days=dias_atras))
    app_module.db.session.add(o)
    app_module.db.session.flush()
    return o


# ── Aderência às atividades obrigatórias ─────────────────────────────────

def test_aderencia_conta_so_o_obrigatorio(app_module, cenario):
    """A atividade opcional não entra no denominador nem quando é cumprida."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _turno(app_module, cenario, hoje, 'T1', ['dts', 'reconf', 'cafe'])
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        # 4 obrigatórias exigidas; 'cafe' cumprida não conta em lugar nenhum.
        assert p['aderencia']['exigidas'] == 4
        assert p['aderencia']['cumpridas'] == 2
        assert p['aderencia']['pct'] == 50.0


def test_turno_aberto_nao_entra_na_conta(app_module, cenario):
    """Rascunho não é reprovação: o turno aberto fica fora do indicador."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _turno(app_module, cenario, hoje, 'T1', ['dts', 'reconf', 'pvv', 'cinco_s'])
        _turno(app_module, cenario, hoje, 'T2', [], status='aberto')
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['aderencia']['exigidas'] == 4      # só o turno encerrado
        assert p['aderencia']['pct'] == 100.0
        assert p['n_turnos'] == 1


def test_sem_rotina_cadastrada_a_aderencia_e_none_e_nao_zero(app_module, cenario):
    """Zero de zero não é 0% — mostrar 0% acenderia alarme falso."""
    from facilities.passagem.models import DiarioConfiguracao
    hoje = tempo.hoje()
    with app_module.app.app_context():
        vazia = DiarioConfiguracao(
            client_id=cenario['client_id'], nome='Sem rotina',
            turnos_json='[]', campos_json='[]', atividades_json='[]',
            tipos_ocorrencia_json='[]', ativo=True,
            created_by=cenario['user_id'])
        app_module.db.session.add(vazia)
        app_module.db.session.flush()
        _turno(app_module, cenario, hoje, 'T1', [], config_id=vazia.id)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['aderencia']['pct'] is None
        assert p['aderencia']['faixa'] == 'neutro'


def test_exigencia_vem_da_configuracao_daquele_turno(app_module, cenario):
    """Mudar o checklist hoje não reescreve o que o turno de ontem cobrava.

    A mesma regra que o SLA Contratual aplica à medição congelada: o passado
    é julgado pelo passado.
    """
    from facilities.passagem.models import DiarioConfiguracao
    hoje = tempo.hoje()
    with app_module.app.app_context():
        # Configuração enxuta: uma obrigatória só.
        enxuta = DiarioConfiguracao(
            client_id=cenario['client_id'], nome='Enxuta',
            turnos_json='[]', campos_json='[]',
            atividades_json=json.dumps(
                [{'nome': 'DTS', 'codigo': 'dts', 'obrigatorio': True}]),
            tipos_ocorrencia_json='[]', ativo=True,
            created_by=cenario['user_id'])
        app_module.db.session.add(enxuta)
        app_module.db.session.flush()
        # Turno antigo pela enxuta (1 exigida, cumprida) e turno de hoje pela
        # completa (4 exigidas, 1 cumprida).
        _turno(app_module, cenario, hoje - timedelta(days=1), 'T1', ['dts'],
               config_id=enxuta.id)
        _turno(app_module, cenario, hoje, 'T1', ['dts'])
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['aderencia']['exigidas'] == 5      # 1 da enxuta + 4 da completa
        assert p['aderencia']['cumpridas'] == 2


def test_faixa_da_aderencia_segue_o_semaforo_da_casa():
    assert an.faixa_aderencia(95.0) == 'ok'
    assert an.faixa_aderencia(99.9) == 'ok'
    assert an.faixa_aderencia(94.9) == 'alerta'
    assert an.faixa_aderencia(85.0) == 'alerta'
    assert an.faixa_aderencia(84.9) == 'critico'
    assert an.faixa_aderencia(None) == 'neutro'


def test_raio_x_das_rotinas_poe_o_gargalo_primeiro(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        for _ in range(3):
            _turno(app_module, cenario, hoje, 'T1', ['dts', 'reconf'])
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        nomes = [r['nome'] for r in p['rotinas']]
        assert len(p['rotinas']) == 4
        # Abandonadas (0%) primeiro; cumpridas (100%) por último.
        assert p['rotinas'][0]['pct'] == 0.0
        assert p['rotinas'][-1]['pct'] == 100.0
        assert 'Café do turno' not in nomes      # opcional não vira linha
        cinco_s = next(r for r in p['rotinas'] if r['nome'] == '5S')
        assert (cinco_s['exigida'], cinco_s['cumprida']) == (3, 0)
        assert cinco_s['faixa'] == 'critico'


def test_atividade_gravada_como_booleano_solto_tambem_conta(app_module, cenario):
    """Formato antigo em banco não pode virar "não cumpriu"."""
    from facilities.passagem.models import DiarioTurno
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = DiarioTurno(client_id=cenario['client_id'],
                        configuracao_id=cenario['config_id'],
                        data_turno=hoje, turno='T1', status='encerrado',
                        dados_json=json.dumps({'atividade:dts': True,
                                               'atividade:reconf': False}),
                        created_by=cenario['user_id'])
        app_module.db.session.add(t)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['aderencia']['cumpridas'] == 1


def test_json_corrompido_nao_derruba_a_tela(app_module, cenario):
    from facilities.passagem.models import DiarioTurno
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = DiarioTurno(client_id=cenario['client_id'],
                        configuracao_id=cenario['config_id'],
                        data_turno=hoje, turno='T1', status='encerrado',
                        dados_json='{isto não é json',
                        created_by=cenario['user_id'])
        app_module.db.session.add(t)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['aderencia']['exigidas'] == 4
        assert p['aderencia']['cumpridas'] == 0


# ── Pendências: safra, vencidas e críticas ───────────────────────────────

def test_resolucao_e_medida_por_safra(app_module, cenario):
    """Denominador = o que nasceu na janela. Nunca passa de 100%."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        for i in range(4):
            _pendencia(app_module, cenario, f'P{i}', criada_ha_horas=2,
                       resolvida=i < 3)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['resolucao'] == {'pct': 75.0, 'abertas': 4, 'resolvidas': 3,
                                  'faixa': 'critico'}


def test_mutirao_de_backlog_antigo_nao_infla_a_taxa(app_module, cenario):
    """Baixar pendência velha hoje não faz a janela passar de 100%."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        # Nasceu há 60 dias (fora da janela de 7), baixada agora.
        _pendencia(app_module, cenario, 'Velha', criada_ha_horas=24 * 60,
                   resolvida=True)
        _pendencia(app_module, cenario, 'Nova', criada_ha_horas=2)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='7d', hoje=hoje)
        assert p['resolucao']['abertas'] == 1
        assert p['resolucao']['resolvidas'] == 0
        assert p['resolucao']['pct'] == 0.0


def test_sem_pendencia_na_janela_a_taxa_e_none(app_module, cenario):
    with app_module.app.app_context():
        p = an.painel(cenario['client_id'], periodo='7d', hoje=tempo.hoje())
        assert p['resolucao']['pct'] is None
        assert p['resolucao']['abertas'] == 0


def test_pendencia_vencida_passa_de_24h(app_module, cenario):
    """O corte é 24h: 23h ainda está no prazo, 25h já é cobrança."""
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'No prazo', criada_ha_horas=23)
        _pendencia(app_module, cenario, 'Vencida', criada_ha_horas=25)
        app_module.db.session.commit()

        fila = an.criticas_e_vencidas(cenario['client_id'])
        assert [f['pendencia'].titulo for f in fila] == ['Vencida']
        assert fila[0]['vencida'] is True
        assert fila[0]['alta'] is False


def test_prioridade_alta_entra_mesmo_recem_aberta(app_module, cenario):
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'Urgente', criada_ha_horas=1,
                   prioridade='alta')
        app_module.db.session.commit()

        fila = an.criticas_e_vencidas(cenario['client_id'])
        assert len(fila) == 1
        assert fila[0]['alta'] is True and fila[0]['vencida'] is False


def test_pendencia_resolvida_nunca_e_cobrada(app_module, cenario):
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'Antiga resolvida',
                   criada_ha_horas=24 * 30, prioridade='alta', resolvida=True)
        app_module.db.session.commit()

        assert an.criticas_e_vencidas(cenario['client_id']) == []


def test_criticas_ignoram_o_filtro_de_periodo(app_module, cenario):
    """Pendência velha em aberto é problema de HOJE, não do recorte."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'Arrastando', criada_ha_horas=24 * 45)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='hoje', hoje=hoje)
        assert p['n_criticas'] == 1          # apesar do recorte "Hoje"
        assert p['resolucao']['abertas'] == 0  # mas fora da safra do dia


def test_a_fila_de_criticas_vem_da_mais_velha_para_a_mais_nova(app_module, cenario):
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'Média idade', criada_ha_horas=48)
        _pendencia(app_module, cenario, 'A mais velha', criada_ha_horas=200)
        _pendencia(app_module, cenario, 'Recente alta', criada_ha_horas=2,
                   prioridade='alta')
        app_module.db.session.commit()

        fila = an.criticas_e_vencidas(cenario['client_id'])
        assert [f['pendencia'].titulo for f in fila] == [
            'A mais velha', 'Média idade', 'Recente alta']
        assert fila[0]['dias'] == 8


# ── Ocorrências: índice, Pareto e agrupamento por turno ──────────────────

def test_indice_de_ocorrencias_por_turno(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t1 = _turno(app_module, cenario, hoje, 'T1', ['dts'])
        _turno(app_module, cenario, hoje, 'T2', ['dts'])
        for _ in range(3):
            _ocorrencia(app_module, cenario, 'Devolução', turno_id=t1.id)
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['indice_ocorrencias']['valor'] == 1.5      # 3 ÷ 2 turnos


def test_sem_turno_encerrado_nao_ha_indice(app_module, cenario):
    """Dividir por zero turno não é 0 ocorrências/turno, é "não se aplica"."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _ocorrencia(app_module, cenario, 'Devolução')
        app_module.db.session.commit()

        p = an.painel(cenario['client_id'], periodo='30d', hoje=hoje)
        assert p['indice_ocorrencias']['valor'] is None
    assert an.indice_de_ocorrencias(5, 0) is None


def test_pareto_ordena_e_marca_os_vitais(app_module, cenario):
    """Vital é quem entra antes de o acumulado alcançar 80%."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        for _ in range(8):
            _ocorrencia(app_module, cenario, 'Devolução')
        for _ in range(4):
            _ocorrencia(app_module, cenario, 'Retrabalho')
        for _ in range(2):
            _ocorrencia(app_module, cenario, 'Falha WMS')
        _ocorrencia(app_module, cenario, 'Avaria')
        app_module.db.session.commit()

        linhas = an.painel(cenario['client_id'], periodo='30d',
                           hoje=hoje)['pareto']
        assert [l['tipo'] for l in linhas] == [
            'Devolução', 'Retrabalho', 'Falha WMS', 'Avaria']
        assert [l['qtd'] for l in linhas] == [8, 4, 2, 1]
        # 8/15 = 53,3% → acumulado 80,0% com Retrabalho. Falha WMS entra
        # depois de os 80% já terem sido alcançados: cauda.
        assert [l['vital'] for l in linhas] == [True, True, False, False]
        assert linhas[1]['acumulado'] == 80.0


def test_pareto_vazio_nao_quebra(app_module, cenario):
    with app_module.app.app_context():
        assert an.pareto([]) == []


def test_comparativo_de_turnos_separa_o_gargalo(app_module, cenario):
    """A pergunta "o problema é a noite?" respondida com número."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t1 = _turno(app_module, cenario, hoje, 'T1',
                    ['dts', 'reconf', 'pvv', 'cinco_s'])
        t3 = _turno(app_module, cenario, hoje, 'T3', ['dts'])
        _ocorrencia(app_module, cenario, 'Devolução', turno_id=t1.id)
        for _ in range(4):
            _ocorrencia(app_module, cenario, 'Retrabalho', turno_id=t3.id)
        app_module.db.session.commit()

        linhas = an.painel(cenario['client_id'], periodo='30d',
                           hoje=hoje)['turnos_comparativo']
        por_nome = {l['turno']: l for l in linhas}
        assert por_nome['T1']['pct'] == 100.0
        assert por_nome['T1']['ocorrencias'] == 1
        assert por_nome['T3']['pct'] == 25.0
        assert por_nome['T3']['ocorrencias'] == 4
        assert por_nome['T3']['faixa'] == 'critico'
        # T2 está na configuração mas não teve lançamento: aparece vazio em
        # vez de sumir, senão a ausência do turno inteiro passa despercebida.
        assert por_nome['T2']['turnos'] == 0
        assert por_nome['T2']['pct'] is None


def test_filtro_por_turno_recorta_tudo(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t1 = _turno(app_module, cenario, hoje, 'T1',
                    ['dts', 'reconf', 'pvv', 'cinco_s'])
        t3 = _turno(app_module, cenario, hoje, 'T3', ['dts'])
        _ocorrencia(app_module, cenario, 'Devolução', turno_id=t1.id)
        _ocorrencia(app_module, cenario, 'Retrabalho', turno_id=t3.id)
        app_module.db.session.commit()

        so_t3 = an.painel(cenario['client_id'], periodo='30d', turno='T3',
                          hoje=hoje)
        assert so_t3['aderencia']['pct'] == 25.0
        assert so_t3['n_turnos'] == 1
        assert [o.tipo for o in so_t3['ocorrencias']] == ['Retrabalho']


# ── Janela de datas ──────────────────────────────────────────────────────

def test_janelas_nomeadas():
    hoje = date(2026, 9, 21)
    assert an.janela('hoje', hoje=hoje) == (hoje, hoje, 'Hoje')
    assert an.janela('7d', hoje=hoje)[:2] == (date(2026, 9, 15), hoje)
    assert an.janela('30d', hoje=hoje)[:2] == (date(2026, 8, 23), hoje)
    assert an.janela('mes', hoje=hoje)[:2] == (date(2026, 9, 1), hoje)


def test_janela_personalizada_e_a_inversao_silenciosa():
    hoje = date(2026, 9, 21)
    de, ate, rotulo = an.janela('custom', date(2026, 9, 3), date(2026, 9, 10),
                                hoje=hoje)
    assert (de, ate) == (date(2026, 9, 3), date(2026, 9, 10))
    assert rotulo == '03/09/2026 a 10/09/2026'
    # De depois de Até é erro de digitação, não motivo para negar a tela.
    de2, ate2, _ = an.janela('custom', date(2026, 9, 10), date(2026, 9, 3),
                             hoje=hoje)
    assert (de2, ate2) == (date(2026, 9, 3), date(2026, 9, 10))


def test_periodo_desconhecido_cai_nos_7_dias():
    hoje = date(2026, 9, 21)
    assert an.janela('mes-que-vem', hoje=hoje)[:2] == (date(2026, 9, 15), hoje)


def test_a_janela_recorta_de_verdade(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _turno(app_module, cenario, hoje, 'T1', ['dts'])
        _turno(app_module, cenario, hoje - timedelta(days=20), 'T1', ['dts'])
        app_module.db.session.commit()

        assert an.painel(cenario['client_id'], periodo='hoje',
                         hoje=hoje)['n_turnos'] == 1
        assert an.painel(cenario['client_id'], periodo='30d',
                         hoje=hoje)['n_turnos'] == 2


# ── Burn-down ────────────────────────────────────────────────────────────

def test_burndown_separa_o_que_entra_do_que_sai(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _pendencia(app_module, cenario, 'Hoje 1', criada_ha_horas=1)
        _pendencia(app_module, cenario, 'Hoje 2', criada_ha_horas=2,
                   resolvida=True)
        app_module.db.session.commit()

        curva = an.burndown(cenario['client_id'], hoje, dias=7)
        assert len(curva['labels']) == 7
        assert len(curva['criadas']) == 7 and len(curva['resolvidas']) == 7
        assert sum(curva['criadas']) == 2
        assert sum(curva['resolvidas']) == 1


def test_burndown_sem_pendencia_devolve_a_curva_zerada(app_module, cenario):
    with app_module.app.app_context():
        curva = an.burndown(cenario['client_id'], tempo.hoje(), dias=14)
        assert curva['criadas'] == [0] * 14
        assert curva['resolvidas'] == [0] * 14


# ── Isolamento entre contratos ───────────────────────────────────────────

# ── A rota do dashboard ──────────────────────────────────────────────────

def test_o_dashboard_responde_aos_filtros(auth_client, app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _turno(app_module, cenario, hoje, 'T1', ['dts', 'reconf', 'pvv', 'cinco_s'])
        _turno(app_module, cenario, hoje - timedelta(days=20), 'T3', ['dts'])
        app_module.db.session.commit()

    cid = cenario['client_id']
    hoje_only = auth_client.get(f'/passagem-de-turno/?client_id={cid}&periodo=hoje')
    trinta = auth_client.get(f'/passagem-de-turno/?client_id={cid}&periodo=30d')
    assert hoje_only.status_code == 200 and trinta.status_code == 200
    # O plural sai certo: "1 turno encerrado", "2 turnos encerrados".
    assert '<strong>1</strong> turno encerrado no recorte' in hoje_only.data.decode('utf8')
    assert '<strong>2</strong> turnos encerrados no recorte' in trinta.data.decode('utf8')


def test_o_dashboard_mostra_os_quatro_indicadores(auth_client, app_module,
                                                  cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _turno(app_module, cenario, hoje, 'T1', ['dts', 'reconf'])
        app_module.db.session.commit()

    html = auth_client.get('/passagem-de-turno/'
                           f'?client_id={cenario["client_id"]}').data.decode('utf8')
    for rotulo in ('Aderência às rotinas obrigatórias',
                   'Taxa de resolução de pendências',
                   'Pendências críticas e vencidas',
                   'Índice de ocorrências por turno'):
        assert rotulo in html, rotulo
    assert 'Pareto de ocorrências por categoria' in html
    assert 'Eficiência entre turnos' in html
    assert 'Evolução diária de pendências' in html
    assert 'Raio-X do checklist' in html
    assert '50,0%' in html          # 2 de 4 obrigatórias


def test_periodo_invalido_na_url_cai_no_padrao(auth_client, cenario):
    r = auth_client.get('/passagem-de-turno/'
                        f'?client_id={cenario["client_id"]}&periodo=ontem')
    assert r.status_code == 200
    assert 'Últimos 7 dias' in r.data.decode('utf8')


def test_data_personalizada_invalida_nao_derruba_a_tela(auth_client, cenario):
    r = auth_client.get('/passagem-de-turno/'
                        f'?client_id={cenario["client_id"]}'
                        '&periodo=custom&de=31/02/2026&ate=xxx')
    assert r.status_code == 200


# ── Ocorrência → chamado de manutenção ───────────────────────────────────

def _chamados_de(oid):
    from facilities.chamados.models import Chamado
    return Chamado.query.filter_by(origem='ocorrencia', origem_id=oid)


def test_abrir_chamado_cria_com_a_origem_certa(auth_client, app_module, cenario):
    with app_module.app.app_context():
        o = _ocorrencia(app_module, cenario, 'Devolução')
        app_module.db.session.commit()
        oid = o.id

    r = auth_client.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    assert r.status_code == 201
    corpo = r.get_json()
    assert corpo['criado'] is True
    assert corpo['url'] == f'/chamados/{corpo["id"]}'
    assert corpo['numero'].startswith('OS-')

    with app_module.app.app_context():
        ch = _chamados_de(oid).one()
        assert ch.client_id == cenario['client_id']
        assert 'Devolução' in ch.titulo
        assert 'Ocorrência de Devolução.' in ch.descricao
        assert ch.prioridade == 'media'
        assert ch.status == 'aberto'
        assert [e.tipo for e in ch.eventos] == ['aberto']


def test_ocorrencia_critica_vira_chamado_de_prioridade_alta(auth_client, app_module,
                                                            cenario):
    with app_module.app.app_context():
        o = _ocorrencia(app_module, cenario, 'Vazamento')
        o.gravidade = 'critica'
        app_module.db.session.commit()
        oid = o.id
    assert auth_client.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado'
                            ).status_code == 201
    with app_module.app.app_context():
        assert _chamados_de(oid).one().prioridade == 'alta'


def test_abrir_chamado_duas_vezes_nao_duplica(auth_client, app_module, cenario):
    """O botão fica numa lista relida todo dia: clicar de novo não duplica."""
    with app_module.app.app_context():
        o = _ocorrencia(app_module, cenario, 'Retrabalho')
        app_module.db.session.commit()
        oid = o.id

    primeiro = auth_client.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    segundo = auth_client.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    assert (primeiro.status_code, segundo.status_code) == (201, 200)
    assert segundo.get_json()['criado'] is False
    assert primeiro.get_json()['id'] == segundo.get_json()['id']
    with app_module.app.app_context():
        assert _chamados_de(oid).count() == 1


def test_abrir_chamado_de_contrato_alheio_da_403(app_module, client, cenario):
    from tests.test_authz import _cleanup_users, _login, _make_user

    with app_module.app.app_context():
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != cenario['client_id']).first())
        o = _ocorrencia(app_module, cenario, 'Devolução')
        app_module.db.session.commit()
        oid = o.id
        _uid, email = _make_user(app_module, role='pleno', client_ids=[outro.id])

    _login(client, email)
    assert client.post(
        f'/passagem-de-turno/api/ocorrencias/{oid}/chamado').status_code == 403
    with app_module.app.app_context():
        assert _chamados_de(oid).count() == 0
        _cleanup_users(app_module, email)


def test_quem_so_le_nao_abre_chamado(app_module, client, cenario):
    """Esconder o botão não basta — a rota também precisa recusar."""
    from tests.test_authz import _cleanup_users, _login, _make_user

    with app_module.app.app_context():
        o = _ocorrencia(app_module, cenario, 'Devolução')
        app_module.db.session.commit()
        oid = o.id
        _uid, email = _make_user(app_module, role='visualizador',
                                 client_ids=[cenario['client_id']])

    _login(client, email)
    html = client.get(f'/passagem-de-turno/?client_id={cenario["client_id"]}'
                      ).get_data(as_text=True)
    assert 'data-acao="dopAbrirChamado"' not in html
    r = client.post(f'/passagem-de-turno/api/ocorrencias/{oid}/chamado')
    assert r.status_code == 403
    with app_module.app.app_context():
        assert _chamados_de(oid).count() == 0
        _cleanup_users(app_module, email)


# ── Isolamento entre contratos ───────────────────────────────────────────

def test_contrato_nao_ve_o_dado_do_outro(app_module, cenario):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != cenario['client_id']).first())
        assert outro, 'o seed precisa de ao menos dois clientes'
        _turno(app_module, cenario, hoje, 'T1', ['dts'])
        _pendencia(app_module, cenario, 'Do primeiro', criada_ha_horas=48)
        app_module.db.session.commit()

        p = an.painel(outro.id, periodo='30d', hoje=hoje)
        assert p['n_turnos'] == 0
        assert p['n_criticas'] == 0
        assert p['aderencia']['pct'] is None
