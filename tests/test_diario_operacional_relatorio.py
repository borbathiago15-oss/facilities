"""O relatório executivo mensal do Diário Operacional.

Duas coisas se provam aqui. A primeira é a CONTA do fechamento: turnos por
nome, aderência global, eficácia da fila e o que sobrou em aberto — incluindo
o arrasto de competência anterior, que é justamente o que um relatório mensal
mal feito esconde.

A segunda é que a TELA e o PDF saem da mesma fonte. Foi por não ter isso que,
no SLA, a tela dizia 93% e o anexo do e-mail dizia 91%: cada um refazia a
conta do seu jeito.
"""
import json
from datetime import date, datetime, time, timedelta

import pytest

from facilities import tempo
from facilities.passagem import analitico as an

ATIVIDADES = [
    {'nome': 'DTS direcionados', 'codigo': 'dts', 'obrigatorio': True},
    {'nome': 'Reconferência de DTS', 'codigo': 'reconf', 'obrigatorio': True},
    {'nome': '5S', 'codigo': 'cinco_s', 'obrigatorio': True},
]


@pytest.fixture()
def contrato(app_module):
    from facilities.passagem.models import DiarioConfiguracao

    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Operação CDV Simões Filho',
            turnos_json=json.dumps([{'nome': 'T1'}, {'nome': 'T2'},
                                    {'nome': 'T3'}]),
            campos_json='[]', atividades_json=json.dumps(ATIVIDADES),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Devolução'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'nome': cliente.name,
                'config_id': cfg.id, 'user_id': admin.id}


def _mes_cheio(app_module, contrato, dias=3, ano=None, mes=None):
    """Semeia ``dias`` dias × 3 turnos numa competência, com desempenho fixo.

    T1 cumpre tudo (3/3), T2 cumpre 2/3 e T3 cumpre 1/3 — 6 de 9 por dia.
    """
    from facilities.passagem.models import DiarioTurno
    hoje = tempo.hoje()
    ano = ano or hoje.year
    mes = mes or hoje.month
    cumpre = {'T1': ['dts', 'reconf', 'cinco_s'], 'T2': ['dts', 'reconf'],
              'T3': ['dts']}
    criados = []
    for d in range(1, dias + 1):
        dia = date(ano, mes, d)
        for nome in ('T1', 'T2', 'T3'):
            t = DiarioTurno(
                client_id=contrato['client_id'],
                configuracao_id=contrato['config_id'], data_turno=dia,
                turno=nome, status='encerrado',
                dados_json=json.dumps({f'atividade:{c}': {'concluido': True}
                                       for c in cumpre[nome]}),
                observacao=('Sem observações' if nome == 'T2'
                            else f'Empilhadeira parada no {nome} em {dia:%d/%m}.'),
                created_by=contrato['user_id'], submitted_at=datetime.utcnow())
            app_module.db.session.add(t)
            criados.append(t)
    app_module.db.session.flush()
    return criados


# ── A conta do fechamento ────────────────────────────────────────────────

def test_turnos_concluidos_saem_quebrados_por_nome(app_module, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=4)
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        assert rel['turnos']['total'] == 12
        assert sorted(rel['turnos']['por_turno']) == [('T1', 4), ('T2', 4),
                                                      ('T3', 4)]
        assert rel['competencia'].endswith(str(hoje.year))


def test_aderencia_global_do_mes(app_module, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=3)
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        # 9 turnos × 3 obrigatórias = 27 exigidas; 6 cumpridas por dia × 3.
        assert rel['aderencia']['exigidas'] == 27
        assert rel['aderencia']['cumpridas'] == 18
        assert rel['aderencia']['pct'] == 66.7
        assert rel['aderencia']['faixa'] == 'critico'


def test_mapa_de_aderencia_tem_uma_linha_por_atividade(app_module, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=3)
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        por_nome = {r['nome']: r for r in rel['rotinas']}
        assert set(por_nome) == {'DTS direcionados', 'Reconferência de DTS', '5S'}
        assert por_nome['DTS direcionados']['pct'] == 100.0
        assert por_nome['Reconferência de DTS']['pct'] == 66.7
        assert por_nome['5S']['pct'] == 33.3
        assert por_nome['5S']['exigida'] == 9


def test_competencia_sem_lancamento_nao_inventa_zero(app_module, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        assert rel['turnos']['total'] == 0
        assert rel['aderencia']['pct'] is None
        assert rel['pendencias']['pct'] is None
        assert rel['ocorrencias']['total'] == 0
        assert rel['bordo'] == []


# ── Pendências: safra, arrasto e responsável ─────────────────────────────

def test_eficacia_da_fila_e_a_safra_do_mes(app_module, contrato):
    from facilities.passagem.models import DiarioPendencia
    hoje = tempo.hoje()
    inicio = date(hoje.year, hoje.month, 1)
    with app_module.app.app_context():
        for i in range(5):
            criada = datetime.combine(inicio, time(12, 0)) + timedelta(days=i)
            app_module.db.session.add(DiarioPendencia(
                client_id=contrato['client_id'], titulo=f'P{i}',
                status='resolvida' if i < 4 else 'aberta', prioridade='media',
                created_by=contrato['user_id'], created_at=criada,
                resolved_at=criada + timedelta(hours=6) if i < 4 else None))
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        assert rel['pendencias']['abertas'] == 5
        assert rel['pendencias']['resolvidas'] == 4
        assert rel['pendencias']['pct'] == 80.0
        assert len(rel['pendencias']['lista_resolvidas']) == 4


def test_arrasto_de_competencia_anterior_aparece_no_em_aberto(app_module, contrato):
    """O que vem de agosto e continua aberto não some do relatório de setembro."""
    from facilities.passagem.models import DiarioPendencia
    hoje = tempo.hoje()
    inicio = date(hoje.year, hoje.month, 1)
    with app_module.app.app_context():
        velha = datetime.combine(inicio, time(12, 0)) - timedelta(days=20)
        app_module.db.session.add(DiarioPendencia(
            client_id=contrato['client_id'], titulo='Arrastando desde antes',
            status='aberta', prioridade='alta',
            created_by=contrato['user_id'], created_at=velha))
        app_module.db.session.add(DiarioPendencia(
            client_id=contrato['client_id'], titulo='Do mês', status='aberta',
            prioridade='media', created_by=contrato['user_id'],
            created_at=datetime.combine(inicio, time(12, 0))))
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        titulos = [l['p'].titulo for l in rel['pendencias']['lista_em_aberto']]
        assert titulos == ['Arrastando desde antes', 'Do mês']
        anterior = rel['pendencias']['lista_em_aberto'][0]
        assert anterior['anterior'] is True
        # ``>= 20``, não ``> 20``: a pendência nasce 20 dias antes do dia 1º,
        # e no próprio dia 1º a idade dela é exatamente 20 — o ``>`` falhava
        # todo começo de mês e passava no resto dele.
        assert anterior['dias'] >= 20
        # Mas a EFICÁCIA do mês só julga a safra do mês.
        assert rel['pendencias']['abertas'] == 1


def test_responsavel_da_pendencia_vem_resolvido(app_module, contrato):
    from facilities.passagem.models import DiarioPendencia
    hoje = tempo.hoje()
    inicio = datetime.combine(date(hoje.year, hoje.month, 1), time(12, 0))
    with app_module.app.app_context():
        app_module.db.session.add(DiarioPendencia(
            client_id=contrato['client_id'], titulo='Com dono',
            status='resolvida', prioridade='media',
            assigned_to=contrato['user_id'], created_by=contrato['user_id'],
            created_at=inicio, resolved_at=inicio + timedelta(hours=2)))
        app_module.db.session.add(DiarioPendencia(
            client_id=contrato['client_id'], titulo='Sem dono',
            status='resolvida', prioridade='media',
            created_by=contrato['user_id'], created_at=inicio,
            resolved_at=inicio + timedelta(hours=2)))
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        nomes = {l['p'].titulo: l['responsavel']
                 for l in rel['pendencias']['lista_resolvidas']}
        assert nomes['Sem dono'] == '—'
        assert nomes['Com dono'] not in ('—', None, '')


# ── Diário de bordo: só o que é fato ─────────────────────────────────────

def test_diario_de_bordo_filtra_o_carimbo_sem_conteudo(app_module, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=3)
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        # T1 e T3 escreveram fato; T2 anotou "Sem observações" nos 3 dias.
        assert len(rel['bordo']) == 6
        assert all('Empilhadeira' in f['texto'] for f in rel['bordo'])
        assert all(f['turno'] in ('T1', 'T3') for f in rel['bordo'])


@pytest.mark.parametrize('texto', [
    '', '   ', '-', 'N/A', 'nada a relatar', 'Sem observações.',
    'sem ocorrências', 'SEM ALTERAÇÕES', 'ok', 'Tudo certo', 'Normal',
])
def test_carimbos_conhecidos_nao_sao_fato(texto):
    assert an._tem_fato(texto) is False


@pytest.mark.parametrize('texto', [
    'Empilhadeira 04 quebrou às 03h e parou a separação da doca 2.',
    'Falta de 3 conferentes no turno.',
])
def test_fato_de_verdade_entra(texto):
    assert an._tem_fato(texto) is True


# ── Matriz de ocorrências ────────────────────────────────────────────────

def test_matriz_de_ocorrencias_liga_cada_desvio_ao_turno(app_module, contrato):
    from facilities.passagem.models import DiarioOcorrencia
    hoje = tempo.hoje()
    with app_module.app.app_context():
        turnos = _mes_cheio(app_module, contrato, dias=2)
        alvo = next(t for t in turnos if t.turno == 'T3')
        base = datetime.combine(date(hoje.year, hoje.month, 1), time(12, 0))
        for i in range(3):
            app_module.db.session.add(DiarioOcorrencia(
                client_id=contrato['client_id'], turno_id=alvo.id,
                tipo='Devolução', referencia=f'NF-{i}',
                descricao='Carga recusada pelo cliente.', status='aberta',
                created_by=contrato['user_id'], created_at=base))
        app_module.db.session.add(DiarioOcorrencia(
            client_id=contrato['client_id'], tipo='Avaria',
            descricao='Avaria sem turno vinculado.', status='aberta',
            created_by=contrato['user_id'], created_at=base))
        app_module.db.session.commit()

        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)
        assert rel['ocorrencias']['total'] == 4
        assert rel['ocorrencias']['pareto'][0]['tipo'] == 'Devolução'
        turnos_na_matriz = {l['turno'] for l in rel['ocorrencias']['lista']}
        assert 'T3' in turnos_na_matriz
        # Ocorrência avulsa não inventa turno: fica com travessão.
        assert '—' in turnos_na_matriz


# ── A rota: RBAC, tela e PDF ─────────────────────────────────────────────

def test_a_tela_do_relatorio_abre_e_mostra_os_numeros(auth_client, app_module,
                                                      contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=3)
        app_module.db.session.commit()

    r = auth_client.get('/passagem-de-turno/relatorio-mensal'
                        f'?client_id={contrato["client_id"]}')
    assert r.status_code == 200
    html = r.data.decode('utf8')
    assert 'Relatório Executivo Mensal' in html
    assert contrato['nome'] in html
    # Os cinco blocos da especificação.
    assert 'Scorecard consolidado do mês' in html
    assert 'Mapa de aderência às rotinas obrigatórias' in html
    assert 'Gestão de pendências da operação' in html
    assert 'Matriz de ocorrências e não conformidades' in html
    assert 'Diário de bordo' in html
    # O número que o fechamento calculou chega à tela.
    assert '66,7%' in html


def test_a_tela_e_o_pdf_contam_a_mesma_historia(auth_client, app_module,
                                                contrato):
    """Anexo do e-mail não pode discordar do que a diretoria viu na tela."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=3)
        app_module.db.session.commit()
        rel = an.fechamento_mensal(contrato['client_id'], hoje.year, hoje.month)

    tela = auth_client.get('/passagem-de-turno/relatorio-mensal'
                           f'?client_id={contrato["client_id"]}')
    pdf = auth_client.get('/passagem-de-turno/relatorio-mensal'
                          f'?client_id={contrato["client_id"]}&format=pdf')
    assert tela.status_code == 200 and pdf.status_code == 200
    assert pdf.data[:4] == b'%PDF'
    assert pdf.headers['Content-Type'].startswith('application/pdf')
    assert 'attachment' in pdf.headers.get('Content-Disposition', '')
    # A mesma aderência aparece nos dois — vinda do mesmo fechamento.
    esperado = f"{rel['aderencia']['pct']:.1f}".replace('.', ',') + '%'
    assert esperado in tela.data.decode('utf8')


def test_pdf_de_competencia_vazia_ainda_e_um_pdf(auth_client, contrato):
    """Mês sem lançamento gera documento, não erro 500."""
    r = auth_client.get('/passagem-de-turno/relatorio-mensal'
                        f'?client_id={contrato["client_id"]}&mes=1&ano=2025'
                        '&format=pdf')
    assert r.status_code == 200
    assert r.data[:4] == b'%PDF'
    assert len(r.data) > 1000


def test_competencia_escolhida_e_respeitada(auth_client, app_module, contrato):
    hoje = tempo.hoje()
    anterior = (date(hoje.year, hoje.month, 1) - timedelta(days=1))
    with app_module.app.app_context():
        _mes_cheio(app_module, contrato, dias=2, ano=anterior.year,
                   mes=anterior.month)
        app_module.db.session.commit()

    r = auth_client.get('/passagem-de-turno/relatorio-mensal'
                        f'?client_id={contrato["client_id"]}'
                        f'&mes={anterior.month}&ano={anterior.year}')
    assert r.status_code == 200
    assert an.MESES[anterior.month - 1] in r.data.decode('utf8')

    # A competência corrente, sem lançamento, não herda os números da outra.
    atual = auth_client.get('/passagem-de-turno/relatorio-mensal'
                            f'?client_id={contrato["client_id"]}')
    assert 'Nenhum turno encerrado na competência' in atual.data.decode('utf8')


def test_competencia_invalida_e_recusada(auth_client, contrato):
    for query in ('&mes=13', '&mes=0', '&ano=1999', '&ano=3000'):
        r = auth_client.get('/passagem-de-turno/relatorio-mensal'
                            f'?client_id={contrato["client_id"]}{query}')
        assert r.status_code == 400, query


def test_sem_contrato_informado_e_recusado(auth_client):
    assert auth_client.get(
        '/passagem-de-turno/relatorio-mensal').status_code == 400


def test_contrato_fora_da_carteira_da_403(app_module, client, contrato):
    """RBAC: quem não tem o contrato não lê o relatório dele.

    O teste prova os DOIS lados de propósito: negar tudo também passaria no
    "403 para o contrato alheio", e aí a régua estaria errada sem ninguém ver.
    """
    from tests.test_authz import _cleanup_users, _login, _make_user

    with app_module.app.app_context():
        outro = (app_module.Client.query
                 .filter(app_module.Client.id != contrato['client_id']).first())
        assert outro, 'o seed precisa de ao menos dois clientes'
        seu = outro.id
        _uid, email = _make_user(app_module, role='pleno',
                                 perms=['diario_operacional'],
                                 client_ids=[seu])
        alvo = contrato['client_id']

    _login(client, email)
    assert client.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={alvo}').status_code == 403
    # No contrato dele, abre normalmente.
    assert client.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={seu}').status_code == 200

    with app_module.app.app_context():
        _cleanup_users(app_module, email)


def test_o_dashboard_oferece_o_atalho_do_relatorio(auth_client, contrato):
    r = auth_client.get('/passagem-de-turno/'
                        f'?client_id={contrato["client_id"]}')
    assert r.status_code == 200
    html = r.data.decode('utf8')
    assert 'Relatório mensal' in html
    assert f'/passagem-de-turno/relatorio-mensal?client_id={contrato["client_id"]}' in html
