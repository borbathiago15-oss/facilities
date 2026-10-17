"""Rascunho fora dos indicadores, ocorrência no dia do turno, e o resto da régua.

O que se prova aqui, uma regra por bloco:

* **Rascunho não conta.** Pendência e ocorrência de turno ainda aberto ficam
  fora da taxa de resolução, do cartão de críticas e vencidas, da evolução
  diária, do índice, do Pareto, da lista do painel, dos pontos de atenção
  e do relatório mensal — e passam a contar sozinhas quando o turno
  encerra. A pendência aberta pela gestão, sem turno, conta sempre.
* **Ocorrência é do dia do turno.** O 3º Turno digita depois da meia-noite;
  a ocorrência dele fica no dia (e no mês) do turno, e o cartão, o gráfico
  entre turnos, o Pareto, a coluna "Quando" do painel ("15/09 · 3º Turno")
  e o bloco 4 do relatório contam a mesma coisa.
* **Período apurado.** No mês em curso o relatório diz até hoje, e diz que a
  competência está em andamento — na tela e na capa do PDF.
* **Pareto.** Empate com a última categoria vital também é vital.

Os testes da Torre de Comando (que não existe no Facilities) saíram no
porte; as asserções de PASSAGEM que moravam neles voltaram para cá.
"""
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import (
    OCORRENCIA_CRITICA, OCORRENCIA_NORMAL)
from facilities.passagem import analitico as an


# ── Cenário ──────────────────────────────────────────────────────────────

@pytest.fixture()
def operacao(app_module):
    """Um contrato com um modelo de passagem sem área, e nada lançado."""
    from facilities.passagem.models import DiarioConfiguracao
    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Passagem CD',
            turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'},
                                    {'nome': '3º Turno'}]),
            campos_json='[]', atividades_json='[]',
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'cid': cliente.id, 'cfg': cfg.id, 'user': admin.id}


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _utc(dia, hora, minuto=0):
    """Hora LOCAL (Brasília) → ``datetime`` UTC ingênuo, como o banco grava."""
    local = datetime.combine(dia, time(hora, minuto)).replace(tzinfo=tempo.FUSO)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _turno(app_module, op, dia, nome='1º Turno', status='encerrado', cfg=None):
    from facilities.passagem.models import DiarioTurno
    t = DiarioTurno(client_id=op['cid'], configuracao_id=cfg or op['cfg'],
                    data_turno=dia, turno=nome, status=status,
                    dados_json='{}', created_by=op['user'],
                    submitted_at=datetime.utcnow() if status == 'encerrado' else None)
    app_module.db.session.add(t)
    app_module.db.session.flush()
    return t


def _pendencia(app_module, op, titulo, turno_id=None, criada=None,
               prioridade='media', resolvida=False):
    from facilities.passagem.models import DiarioPendencia
    criada = criada or datetime.utcnow() - timedelta(minutes=1)
    p = DiarioPendencia(client_id=op['cid'], turno_id=turno_id, titulo=titulo,
                        status='resolvida' if resolvida else 'aberta',
                        prioridade=prioridade, created_by=op['user'],
                        created_at=criada,
                        resolved_at=criada + timedelta(minutes=30) if resolvida else None)
    app_module.db.session.add(p)
    app_module.db.session.flush()
    return p


def _ocorrencia(app_module, op, tipo='Avaria', turno_id=None, criada=None,
                gravidade=OCORRENCIA_NORMAL, descricao=None):
    from facilities.passagem.models import DiarioOcorrencia
    o = DiarioOcorrencia(client_id=op['cid'], turno_id=turno_id, tipo=tipo,
                         descricao=descricao or f'Ocorrência de {tipo}.',
                         gravidade=gravidade, status='aberta',
                         created_by=op['user'],
                         created_at=criada or datetime.utcnow())
    app_module.db.session.add(o)
    app_module.db.session.flush()
    return o


def _encerrar(app_module, turno):
    turno.status = 'encerrado'
    turno.submitted_at = datetime.utcnow()
    app_module.db.session.commit()


# ── 1. Rascunho fora dos indicadores ─────────────────────────────────────

def test_pendencia_do_rascunho_nao_entra_na_resolucao_e_entra_ao_encerrar(
        app_module, operacao):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = _turno(app_module, operacao, hoje, status='aberto')
        _pendencia(app_module, operacao, 'Devolução 4471', turno_id=t.id)
        app_module.db.session.commit()

        assert an.resolucao_de_pendencias(operacao['cid'], hoje, hoje)['abertas'] == 0
        assert an.pendencias_da_janela(operacao['cid'], hoje, hoje) == []

        _encerrar(app_module, t)
        assert an.resolucao_de_pendencias(operacao['cid'], hoje, hoje)['abertas'] == 1


def test_evolucao_diaria_ignora_o_rascunho(app_module, operacao):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = _turno(app_module, operacao, hoje, status='aberto')
        _pendencia(app_module, operacao, 'Rascunho', turno_id=t.id,
                   criada=datetime.utcnow() - timedelta(minutes=5))
        app_module.db.session.commit()

        curva = an.burndown(operacao['cid'], hoje, dias=7)
        assert sum(curva['criadas']) == 0

        _encerrar(app_module, t)
        curva = an.burndown(operacao['cid'], hoje, dias=7)
        assert curva['criadas'][-1] == 1


def test_ocorrencia_do_rascunho_fica_fora_do_painel_inteiro(app_module, operacao):
    """Índice, Pareto, gráfico entre turnos e a lista: todos esperam o encerramento."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        fechado = _turno(app_module, operacao, hoje, '1º Turno')
        rascunho = _turno(app_module, operacao, hoje, '2º Turno', status='aberto')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=fechado.id)
        _ocorrencia(app_module, operacao, 'Divergência', turno_id=rascunho.id)
        app_module.db.session.commit()

        p = an.painel(operacao['cid'], periodo='hoje', hoje=hoje)
        assert p['indice_ocorrencias']['ocorrencias'] == 1
        assert [linha['tipo'] for linha in p['pareto']] == ['Avaria']
        assert [o.tipo for o in p['ocorrencias']] == ['Avaria']
        volume = {linha['turno']: linha['ocorrencias']
                  for linha in p['turnos_comparativo']}
        assert volume.get('2º Turno', 0) == 0

        _encerrar(app_module, rascunho)
        p = an.painel(operacao['cid'], periodo='hoje', hoje=hoje)
        assert p['indice_ocorrencias']['ocorrencias'] == 2
        assert sorted(linha['tipo'] for linha in p['pareto']) == ['Avaria', 'Divergência']


def test_relatorio_mensal_ignora_o_rascunho(app_module, operacao):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        fechado = _turno(app_module, operacao, hoje, '1º Turno')
        rascunho = _turno(app_module, operacao, hoje, '2º Turno', status='aberto')
        # Um rascunho esquecido do mês passado, com pendência aberta: não é
        # "arrasto" de competência anterior, é passagem que nunca foi entregue.
        velho = _turno(app_module, operacao, hoje - timedelta(days=40),
                       '3º Turno', status='aberto')
        _pendencia(app_module, operacao, 'Da passagem', turno_id=fechado.id)
        _pendencia(app_module, operacao, 'Do rascunho', turno_id=rascunho.id)
        _pendencia(app_module, operacao, 'Do rascunho velho', turno_id=velho.id,
                   criada=datetime.utcnow() - timedelta(days=40))
        _pendencia(app_module, operacao, 'Da gestão')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=fechado.id)
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=rascunho.id)
        app_module.db.session.commit()

        rel = an.fechamento_mensal(operacao['cid'], hoje.year, hoje.month, hoje=hoje)
        titulos = sorted(linha['p'].titulo
                         for linha in rel['pendencias']['lista_em_aberto'])
        assert titulos == ['Da gestão', 'Da passagem']
        assert rel['pendencias']['abertas'] == 2
        assert rel['ocorrencias']['total'] == 1
        assert len(rel['ocorrencias']['lista']) == 1


# As três de baixo eram asserções de PASSAGEM dentro dos testes da Torre de
# Comando, apagados no porte: sem elas, a regra ficava sem teste nenhum.

def test_critica_do_rascunho_nao_acende_o_cartao(app_module, operacao):
    """A pendência de prioridade alta de um turno em rascunho ainda não foi
    entregue a ninguém: o cartão "Pendências críticas e vencidas" espera o
    encerramento — e acende sozinho quando ele vem."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = _turno(app_module, operacao, hoje, status='aberto')
        _pendencia(app_module, operacao, 'Elevador social parado', turno_id=t.id,
                   prioridade='alta')
        app_module.db.session.commit()

        assert an.criticas_e_vencidas(operacao['cid']) == []
        assert an.painel(operacao['cid'], periodo='hoje', hoje=hoje)['n_criticas'] == 0

        _encerrar(app_module, t)
        assert len(an.criticas_e_vencidas(operacao['cid'])) == 1
        assert an.painel(operacao['cid'], periodo='hoje', hoje=hoje)['n_criticas'] == 1


def test_pendencia_da_gestao_sem_turno_conta_sempre(app_module, operacao):
    """Sem turno de origem não há rascunho a esperar: a pendência que a
    gestão abriu pelo painel entra na taxa e no cartão desde o primeiro
    minuto."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        _pendencia(app_module, operacao, 'Cobrar o conserto do portão da garagem',
                   prioridade='alta')
        app_module.db.session.commit()

        assert an.resolucao_de_pendencias(operacao['cid'], hoje, hoje)['abertas'] == 1
        assert len(an.criticas_e_vencidas(operacao['cid'])) == 1
        assert an.painel(operacao['cid'], periodo='hoje', hoje=hoje)['n_criticas'] == 1


def test_ponto_de_atencao_do_rascunho_nao_sobe(app_module, operacao):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        t = _turno(app_module, operacao, hoje, status='aberto')
        _ocorrencia(app_module, operacao, 'Acidente ou incidente', turno_id=t.id,
                    gravidade=OCORRENCIA_CRITICA,
                    descricao='Colaborador escorregou no piso molhado')
        app_module.db.session.commit()

        assert an.pontos_de_atencao(operacao['cid']) == []

        _encerrar(app_module, t)
        assert len(an.pontos_de_atencao(operacao['cid'])) == 1


# ── 2. Ocorrência no dia do turno ────────────────────────────────────────

def test_ocorrencia_do_3o_turno_fica_no_dia_do_turno(app_module, operacao):
    """Digitada à 01h30 de 16/09, ela é do 3º Turno de 15/09."""
    dia = date(2026, 9, 15)
    with app_module.app.app_context():
        t = _turno(app_module, operacao, dia, '3º Turno')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=t.id,
                    criada=_utc(dia + timedelta(days=1), 1, 30))
        app_module.db.session.commit()

        assert len(an.ocorrencias_da_janela(operacao['cid'], dia, dia)) == 1
        seguinte = dia + timedelta(days=1)
        assert an.ocorrencias_da_janela(operacao['cid'], seguinte, seguinte) == []
        # O recorte por turno usa a mesma régua.
        assert len(an.ocorrencias_da_janela(operacao['cid'], dia, dia,
                                            turno='3º Turno')) == 1


def test_o_painel_diz_o_dia_e_o_nome_do_turno_da_ocorrencia(app_module, operacao,
                                                             mestre):
    """Coluna "Quando" do painel: "15/09 · 3º Turno" — o dia do TURNO (não o
    da digitação, 01h30 de 16/09) e o nome dele. Vinha de um teste da Torre
    apagado no porte; sem ele, tirar o turno da coluna ou trocar o dia pela
    data de digitação passava sem nenhum teste falhar."""
    dia = date(2026, 9, 15)
    with app_module.app.app_context():
        t = _turno(app_module, operacao, dia, '3º Turno')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=t.id,
                    criada=_utc(dia + timedelta(days=1), 1, 30),
                    descricao='Vazamento na casa de bombas')
        app_module.db.session.commit()
    seguinte = dia + timedelta(days=1)
    html = mestre.get(f"/passagem-de-turno/?client_id={operacao['cid']}&periodo=custom"
                      f"&de={dia.isoformat()}&ate={seguinte.isoformat()}"
                      ).get_data(as_text=True)
    assert 'Vazamento na casa de bombas' in html
    assert '15/09 · 3º Turno' in html
    assert '16/09 · 3º Turno' not in html


def test_ocorrencia_da_virada_do_mes_fica_no_mes_do_turno(app_module, operacao):
    """O 3º Turno de 30/09 não aparece em outubro como "01/10 · —"."""
    dia = date(2026, 9, 30)
    with app_module.app.app_context():
        t = _turno(app_module, operacao, dia, '3º Turno')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=t.id,
                    criada=_utc(date(2026, 10, 1), 0, 40))
        app_module.db.session.commit()

        hoje = date(2026, 10, 16)
        outubro = an.fechamento_mensal(operacao['cid'], 2026, 10, hoje=hoje)
        assert outubro['ocorrencias']['total'] == 0
        assert outubro['ocorrencias']['lista'] == []

        setembro = an.fechamento_mensal(operacao['cid'], 2026, 9, hoje=hoje)
        assert setembro['ocorrencias']['total'] == 1
        linha = setembro['ocorrencias']['lista'][0]
        assert linha['data'] == dia
        assert linha['turno'] == '3º Turno'


def test_cartao_grafico_e_pareto_contam_as_mesmas_ocorrencias(app_module, operacao):
    """O caso do 22 contra 21: a da borda da janela entrava num e não no outro."""
    inicio, fim = date(2026, 9, 10), date(2026, 9, 16)
    with app_module.app.app_context():
        for i in range(7):
            dia = inicio + timedelta(days=i)
            t1 = _turno(app_module, operacao, dia, '1º Turno')
            _ocorrencia(app_module, operacao, 'Avaria', turno_id=t1.id,
                        criada=_utc(dia, 10))
        # O 3º Turno do último dia lança depois da meia-noite: é da janela.
        t3 = _turno(app_module, operacao, fim, '3º Turno')
        _ocorrencia(app_module, operacao, 'Divergência', turno_id=t3.id,
                    criada=_utc(fim + timedelta(days=1), 2))
        # O 3º Turno da véspera da janela lança no primeiro dia: não é.
        antes = _turno(app_module, operacao, inicio - timedelta(days=1), '3º Turno')
        _ocorrencia(app_module, operacao, 'Divergência', turno_id=antes.id,
                    criada=_utc(inicio, 1))
        app_module.db.session.commit()

        p = an.painel(operacao['cid'], periodo='custom', de=inicio, ate=fim,
                      hoje=date(2026, 10, 16))
        cartao = p['indice_ocorrencias']['ocorrencias']
        grafico = sum(linha['ocorrencias'] for linha in p['turnos_comparativo'])
        barras = sum(linha['qtd'] for linha in p['pareto'])
        assert cartao == grafico == barras == 8
        assert len(p['ocorrencias']) == 8

        rel = an.fechamento_mensal(operacao['cid'], 2026, 9, hoje=date(2026, 10, 16))
        # No mês, as nove (a da véspera da janela também é de setembro).
        assert rel['ocorrencias']['total'] == 9
        assert sum(linha['qtd'] for linha in rel['ocorrencias']['pareto']) == 9


def test_total_do_mes_bate_com_a_soma_das_areas(app_module, operacao):
    """O caso do 49 contra 33 + 15."""
    from facilities.passagem.models import DiarioArea, DiarioConfiguracao
    with app_module.app.app_context():
        cfgs = {}
        for nome in ('Expedição', 'Almoxarifado'):
            area = DiarioArea(client_id=operacao['cid'], nome=nome, ativo=True,
                              created_by=operacao['user'])
            app_module.db.session.add(area)
            app_module.db.session.flush()
            cfg = DiarioConfiguracao(
                client_id=operacao['cid'], area_id=area.id, nome=f'Passagem {nome}',
                turnos_json=json.dumps([{'nome': '3º Turno'}]), campos_json='[]',
                atividades_json='[]', tipos_ocorrencia_json='[]', ativo=True,
                created_by=operacao['user'])
            app_module.db.session.add(cfg)
            app_module.db.session.flush()
            cfgs[nome] = (area.id, cfg.id)

        exp = _turno(app_module, operacao, date(2026, 9, 30), '3º Turno',
                     cfg=cfgs['Expedição'][1])
        alm = _turno(app_module, operacao, date(2026, 10, 2), '3º Turno',
                     cfg=cfgs['Almoxarifado'][1])
        # A da Expedição de 30/09 digitada em 01/10: é de setembro nas duas
        # visões — antes, outubro a contava no total e não na área.
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=exp.id,
                    criada=_utc(date(2026, 10, 1), 0, 30))
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=alm.id,
                    criada=_utc(date(2026, 10, 3), 1, 0))
        app_module.db.session.commit()

        hoje = date(2026, 10, 16)
        for mes in (9, 10):
            total = an.fechamento_mensal(operacao['cid'], 2026, mes,
                                         hoje=hoje)['ocorrencias']['total']
            por_area = sum(
                an.fechamento_mensal(operacao['cid'], 2026, mes, hoje=hoje,
                                     area_id=area_id)['ocorrencias']['total']
                for area_id, _cfg in cfgs.values())
            assert total == por_area == 1


def test_bloco_4_mostra_o_dia_do_turno_na_tela_e_no_pdf(app_module, operacao,
                                                       mestre):
    from pypdf import PdfReader
    dia = date(2025, 9, 30)
    with app_module.app.app_context():
        t = _turno(app_module, operacao, dia, '3º Turno')
        _ocorrencia(app_module, operacao, 'Avaria', turno_id=t.id,
                    gravidade=OCORRENCIA_CRITICA,
                    criada=_utc(date(2025, 10, 1), 0, 50))
        app_module.db.session.commit()

    url = (f'/passagem-de-turno/relatorio-mensal?client_id={operacao["cid"]}'
           f'&mes=9&ano=2025')
    tela = mestre.get(url).get_data(as_text=True)
    assert re.search(r'30/09/2025\s*·\s*3º Turno', tela)
    assert re.search(r'30/09\s*·\s*3º Turno', tela)        # pontos de atenção
    assert '01/10/2025' not in tela
    assert '01/10' not in re.sub(r'\s+', ' ', tela).split('4. Matriz')[1].split('5. Diário')[0]

    r = mestre.get(url + '&format=pdf')
    assert r.status_code == 200
    texto = '\n'.join(p.extract_text() or ''
                      for p in PdfReader(io.BytesIO(r.data)).pages)
    assert '30/09/2025' in texto
    assert '01/10/2025' not in texto


# ── 3. Período apurado ───────────────────────────────────────────────────

def test_mes_em_curso_vai_ate_hoje_e_mes_fechado_ate_o_ultimo_dia(app_module,
                                                                 operacao):
    hoje = date(2026, 10, 16)
    with app_module.app.app_context():
        corrente = an.fechamento_mensal(operacao['cid'], 2026, 10, hoje=hoje)
        assert corrente['fim_apurado'] == hoje
        assert corrente['em_andamento'] is True
        # A competência continua sendo o mês inteiro.
        assert corrente['fim'] == date(2026, 10, 31)

        fechado = an.fechamento_mensal(operacao['cid'], 2026, 9, hoje=hoje)
        assert fechado['fim_apurado'] == date(2026, 9, 30)
        assert fechado['em_andamento'] is False


def test_tela_e_capa_do_pdf_dizem_competencia_em_andamento(app_module, operacao,
                                                          mestre):
    from pypdf import PdfReader
    hoje = tempo.hoje()
    base = f'/passagem-de-turno/relatorio-mensal?client_id={operacao["cid"]}'

    tela = re.sub(r'\s+', ' ', mestre.get(base).get_data(as_text=True))
    assert (f'Período apurado: {hoje.replace(day=1):%d/%m/%Y} a '
            f'{hoje:%d/%m/%Y} (competência em andamento)') in tela

    pdf = mestre.get(base + '&format=pdf')
    texto = re.sub(r'\s+', ' ', '\n'.join(
        p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf.data)).pages))
    assert f'{hoje.replace(day=1):%d/%m/%Y} a {hoje:%d/%m/%Y}' in texto
    assert 'competência em andamento' in texto

    # Mês fechado: 01 ao último dia, sem o aviso.
    passado = date(hoje.year - 1, 9, 1)
    url = base + f'&mes=9&ano={passado.year}'
    tela = re.sub(r'\s+', ' ', mestre.get(url).get_data(as_text=True))
    assert f'Período apurado: 01/09/{passado.year} a 30/09/{passado.year}' in tela
    assert 'competência em andamento' not in tela


def test_competencia_futura_nao_tem_periodo_apurado(app_module, operacao, mestre):
    """Novembro aberto em outubro: a capa dizia "apurado de 01/11 a 30/11" —
    um mês inteiro que ainda não aconteceu, com tudo zerado como se fosse
    resultado."""
    from pypdf import PdfReader
    with app_module.app.app_context():
        futuro = an.fechamento_mensal(operacao['cid'], 2026, 11, hoje=date(2026, 10, 16))
        assert futuro['fim_apurado'] is None
        assert futuro['em_andamento'] is False

    ano = tempo.hoje().year + 1
    url = (f'/passagem-de-turno/relatorio-mensal?client_id={operacao["cid"]}'
           f'&mes=3&ano={ano}')
    tela = re.sub(r'\s+', ' ', mestre.get(url).get_data(as_text=True))
    assert 'Competência ainda não iniciada' in tela
    assert 'Período apurado' not in tela
    pdf = mestre.get(url + '&format=pdf')
    assert pdf.status_code == 200
    texto = re.sub(r'\s+', ' ', '\n'.join(
        p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf.data)).pages))
    assert 'Competência ainda não iniciada' in texto
    assert 'Período apurado' not in texto


def test_seletor_de_ano_tem_o_ano_pedido(app_module, operacao, mestre):
    """O servidor aceita o ano seguinte, mas o seletor parava no atual: sem a
    opção, a tela mostrava o primeiro ano da lista, e a próxima troca de mês
    — que envia o formulário sozinha — levava o relatório cinco anos atrás."""
    base = f'/passagem-de-turno/relatorio-mensal?client_id={operacao["cid"]}'
    seguinte = tempo.hoje().year + 1
    tela = mestre.get(base + f'&mes=1&ano={seguinte}').get_data(as_text=True)
    assert re.search(rf'<option value="{seguinte}"\s+selected', tela)
    antigo = tempo.hoje().year - 9
    tela = mestre.get(base + f'&mes=1&ano={antigo}').get_data(as_text=True)
    assert re.search(rf'<option value="{antigo}"\s+selected', tela)


# ── 4. Pareto ────────────────────────────────────────────────────────────

def _tipos(**contagem):
    return [SimpleNamespace(tipo=tipo) for tipo, n in contagem.items()
            for _ in range(n)]


def test_empate_com_a_ultima_vital_tambem_e_vital():
    """Avaria e Divergência têm 2 cada; a letra inicial não decide mais."""
    linhas = an.pareto(_tipos(Atraso=14, Divergencia=2, Avaria=2, Outros=1))
    vital = {linha['tipo']: linha['vital'] for linha in linhas}
    assert vital == {'Atraso': True, 'Avaria': True, 'Divergencia': True,
                     'Outros': False}


def test_sem_empate_o_corte_continua_o_mesmo():
    linhas = an.pareto(_tipos(Atraso=6, Avaria=3, Outros=1))
    assert [(linha['tipo'], linha['vital']) for linha in linhas] == [
        ('Atraso', True), ('Avaria', True), ('Outros', False)]
    assert an.pareto([]) == []
