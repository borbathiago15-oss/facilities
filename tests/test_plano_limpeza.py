"""Plano de limpeza do cliente (decisões do dono, 22/10/2026): a planilha
"PLANO DE LIMPEZA E CONSERVAÇÃO" da Trino Frio vira blocos, checklists e
rotas.

* ``ler``: 8 rotas; a Rota 2 é noturna (22:00–05:20, domingo a sexta); a
  Rota 3 tem sábado com horário diferente; a Rota 1 tem atividades só de
  segunda a sexta; intervalo e observações lidos; "1600h" vira 16:00 com
  aviso.
* ``planejar``: os blocos esperados, um checklist por atividade distinta,
  "Continuação" no mesmo bloco/checklist, perguntas quebradas pelos
  dois-pontos.
* ``aplicar``: setores, pontos, checklists (com materiais e EPI), rotas e
  itens com tempo; ``gerar`` numa segunda, num sábado e num domingo respeita
  dias, horários por dia e intervalo; registra na trilha.
* Idempotência: de novo recusa; ``substituir`` desativa a antiga; o
  ``flask rotas importar-plano --dry-run`` não grava; a tela só para a gestão.
"""
import io
from datetime import date, time

import pytest

from tests import fabrica

SEGUNDA = date(2026, 10, 19)
SABADO = date(2026, 10, 24)
DOMINGO = date(2026, 10, 25)


def _pl():
    from facilities.rotas import plano_limpeza
    return plano_limpeza


def _planilha():
    with open(_pl().caminho_da_planilha_trino_frio(), 'rb') as f:
        return f.read()


@pytest.fixture(scope='module')
def plano():
    return _pl().ler(_pl().caminho_da_planilha_trino_frio())


@pytest.fixture()
def contexto(app_module):
    with app_module.app.app_context():
        yield


# ── Leitura ───────────────────────────────────────────────────────────────

def test_le_as_oito_rotas_da_planilha_real(plano):
    assert [r.numero for r in plano.rotas] == [1, 2, 3, 4, 5, 6, 7, 8]
    r1 = plano.rotas[0]
    assert (r1.responsavel, r1.entrada, r1.largada) == ('ROSA', time(6, 0), time(15, 0))
    assert r1.intervalo == (time(11, 0), time(12, 0)) and r1.dias == '123456'
    assert r1.atividades[0].descricao.startswith('Recolhe e abastece as garrafas de café')
    assert r1.atividades[0].material.startswith('Cafeteira')
    assert r1.atividades[0].horarios_por_dia['1'] == (time(6, 0), time(6, 30))
    # Rota 2: noturna, domingo a sexta, intervalo na virada do dia.
    r2 = plano.rotas[1]
    assert (r2.entrada, r2.largada, r2.dias) == (time(22, 0), time(5, 20), '123457')
    assert r2.intervalo == (time(0, 0), time(1, 0))
    assert r2.atividades[2].horarios_por_dia['7'] == (time(23, 40), time(0, 0))
    # Rota 3: o sábado começa no mesmo horário mas a segunda atividade é mais cedo.
    r3 = plano.rotas[2]
    assert r3.atividades[1].horarios_por_dia['1'] == (time(10, 30), time(11, 30))
    assert r3.atividades[1].horarios_por_dia['6'] == (time(9, 30), time(10, 30))
    # A tarde da Rota 1 não existe no sábado ("x").
    tarde = r1.atividades[4]
    assert set(tarde.horarios_por_dia) == {'1', '2', '3', '4', '5'}
    assert tarde.turno_bloco == '2° TURNO' and r1.atividades[0].turno_bloco == '1° TURNO'
    # Observações e a frequência.
    assert 'gaiola amarela' in plano.rotas[4].observacoes and not r1.observacoes
    assert r1.atividades[0].frequencia == 'DIÁRIA'
    # "1600h" (erro de digitação) virou 16:00, com aviso; o resto sem aviso de leitura.
    assert plano.rotas[4].atividades[-1].horarios_por_dia['2'] == (time(15, 50), time(16, 0))
    assert any('1600h' in a and '16:00' in a for a in plano.avisos)
    assert plano.revisoes >= 20
    # "xx" no material/EPI é vazio.
    assert plano.rotas[7].atividades[2].material == '' and plano.rotas[7].atividades[2].epi == ''


def test_planilha_que_nao_e_plano_e_recusada(tmp_path):
    import openpyxl
    from facilities.rotas.servico import RegraDaRota
    wb = openpyxl.Workbook()
    wb.active.title = 'Dados'
    wb.active['A1'] = 'nada'
    caminho = tmp_path / 'outra.xlsx'
    wb.save(caminho)
    with pytest.raises(RegraDaRota, match='nenhuma aba'):
        _pl().ler(str(caminho))
    with pytest.raises(RegraDaRota, match='abrir a planilha'):
        _pl().ler(b'isto nao e um xlsx')


# ── Planejamento ──────────────────────────────────────────────────────────

def test_planejar_decide_blocos_checklists_e_rotas(plano):
    previa = _pl().planejar(plano)
    blocos = {(b.setor, b.nome) for b in previa.blocos}
    assert {('GALPÃO FRIO', 'Andar administrativo'), ('GALPÃO FRIO', 'Térreo'),
            ('GALPÃO FRIO', 'Mezanino'), ('GALPÃO FRIO', 'Galpão Frio'),
            ('PÁTIO EXTERNO', 'Pátio Externo'), ('LACTALIS', 'Lactalis'),
            ('Operação', 'DML (guarda de utensílios)'),
            ('Operação', 'Doca 09 / triagem de resíduos'), ('Operação', 'Central de resíduos'),
            ('Operação', 'Câmaras D1'), ('Operação', 'Câmaras D2')} == blocos
    # Um checklist por atividade distinta: "guarda dos utensílios" está em 7 rotas.
    nomes = [c.nome for c in previa.checklists]
    assert len(nomes) == len({n.lower() for n in nomes})
    assert nomes.count('Limpeza e guarda dos utensílios de limpeza') == 1
    utens = next(c for c in previa.checklists if c.nome.startswith('Limpeza e guarda'))
    assert utens.materiais == 'água, pano, sanitizante, detergente'
    assert [i['texto'] for i in utens.itens] == ['Feito conforme o plano']
    adm = next(c for c in previa.checklists
               if c.nome == 'Andar administrativo: Limpeza de WCs, corredor e salas, copa e degelo')
    assert [i['texto'] for i in adm.itens] == ['WCs', 'Corredor e salas', 'Copa e degelo']
    assert all(i['tipo'] == 'sim_nao' and i['obrigatorio'] and i['problema_se'] == 'nao'
               for i in adm.itens)
    assert adm.itens[0]['problema'] == 'WCs com problema'
    assert adm.descricao.startswith('GALPÃO FRIO - Andar administrativo')
    # Rotas: nome pelo bloco principal, turno, dias, intervalo, observações.
    r1, r2, r3, r5, r8 = (previa.rotas[i] for i in (0, 1, 2, 4, 7))
    assert r1.nome == 'Rota 1 — GALPÃO FRIO — Andar administrativo'
    assert (r1.hora_inicio, r1.hora_fim, r1.dias_semana) == ('06:00', '15:00', '123456')
    assert (r1.intervalo_inicio, r1.intervalo_fim, r1.tolerancia_min) == ('11:00', '12:00', 15)
    assert r1.responsavel == 'ROSA'
    assert (r2.turno, r2.hora_inicio, r2.hora_fim, r2.dias_semana) == \
        ('Noturno', '22:00', '05:20', '123457')
    assert r5.nome == 'Rota 5 — Operação — Câmaras D1' and 'gaiola' in r5.observacoes
    # Itens: horário = início, tempo = fim − início, dias e horários por dia.
    assert [(it.horario, it.tempo_previsto_min) for it in r1.itens[:3]] == \
        [('06:00', 30), ('06:30', 90), ('08:00', 90)]
    assert r1.itens[4].dias_semana == '12345' and r1.itens[0].dias_semana is None
    assert r3.itens[1].horarios_por_dia == {'6': '09:30'} and r3.itens[0].horarios_por_dia == {}
    assert r2.itens[2].tempo_previsto_min == 20          # 23:40 → 00:00 cruza a meia-noite
    assert r2.itens[3].horario == '01:00'
    # Continuação: mesmo bloco e checklist da atividade de referência.
    assert r5.itens[2].bloco is r5.itens[1].bloco and r5.itens[2].checklist is r5.itens[1].checklist
    assert r5.itens[2].tempo_previsto_min == 170
    assert r8.itens[5].bloco.nome == 'Câmaras D2' and r8.itens[5].checklist is r8.itens[1].checklist
    # Avisos: intervalo da grade vence o do cabeçalho; horário fora do turno é dito.
    assert any('Rota 3: o intervalo' in a for a in previa.avisos)
    assert any('Rota 7' in a and 'fora do turno' in a for a in previa.avisos)
    assert (previa.rotas[2].intervalo_inicio, previa.rotas[2].intervalo_fim) == ('12:00', '13:00')
    assert previa.responsaveis[0] == (1, 'ROSA')
    texto = _pl().descrever(previa)
    assert 'BLOCOS (11)' in texto and 'Responsável: ROSA (escalar depois)' in texto


# ── Aplicação ─────────────────────────────────────────────────────────────

def _aplicar(app_module, substituir=False, pular=False):
    from app import db
    loc = fabrica.local()
    previa = _pl().planejar(_pl().ler(_pl().caminho_da_planilha_trino_frio()), loc)
    r = _pl().aplicar(previa, loc, None, substituir=substituir, pular_existentes=pular)
    db.session.commit()
    return previa, r


def test_aplicar_cria_tudo_e_o_agendador_respeita_dias_horarios_e_intervalo(app_module,
                                                                               contexto):
    from app import db
    from facilities.cadastros.models import Ambiente, CadastroEvento, PontoInspecao, Setor
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistModelo, Rota, RotaItem, TarefaDia
    loc = fabrica.local()
    previa, r = _aplicar(app_module)
    assert (r['rotas'], r['substituidas'], r['puladas']) == (8, 0, 0)
    assert r['itens'] == sum(len(x.itens) for x in previa.rotas) == 52
    assert r['setores'] == 4 and r['ambientes'] == r['pontos'] == len(previa.blocos) == 11
    assert r['checklists'] == len(previa.checklists) and r['checklists_atualizados'] == 0
    assert Setor.query.filter_by(client_id=loc.id).count() == 4
    assert Ambiente.query.join(Setor).filter(Setor.client_id == loc.id).count() == 11
    assert PontoInspecao.query.filter_by(client_id=loc.id).count() == 11
    assert ChecklistModelo.query.filter_by(client_id=loc.id).count() == len(previa.checklists)
    assert Rota.query.filter_by(client_id=loc.id, is_active=True).count() == 8
    assert CadastroEvento.query.filter_by(entidade='rota', acao='importada',
                                          client_id=loc.id).count() == 8
    # Materiais e EPI estão na versão publicada; a tela do técnico recebe os dois.
    utens = ChecklistModelo.query.filter_by(
        client_id=loc.id, nome='Limpeza e guarda dos utensílios de limpeza').one()
    v = utens.versao_atual
    assert v.materiais == 'água, pano, sanitizante, detergente' and v.epi is None
    assert s.dados_da_versao(v) == {'materiais': v.materiais, 'epi': ''}
    rota1 = Rota.query.filter_by(client_id=loc.id, nome=previa.rotas[0].nome).one()
    assert (rota1.intervalo_inicio, rota1.intervalo_fim) == (time(11, 0), time(12, 0))
    assert rota1.presencas_por_turno == 0 and rota1.tolerancia_min == 15
    rota5 = Rota.query.filter_by(client_id=loc.id, nome=previa.rotas[4].nome).one()
    assert 'gaiola amarela' in rota5.observacoes
    tempos = [it.tempo_previsto_min for it in rota1.itens]
    assert tempos == [30, 90, 90, 90, 30, 60, 60, 20, 10]
    assert rota1.itens[4].dias_semana == '12345' and rota1.itens[0].dias_semana is None
    rota3 = Rota.query.filter_by(client_id=loc.id, nome=previa.rotas[2].nome).one()
    assert rota3.itens[1].horarios_por_dia_dict == {'6': '09:30'}
    assert RotaItem.query.filter(RotaItem.horarios_por_dia.isnot(None)).count() >= 4

    # O agendador: segunda, sábado e domingo.
    s.gerar(SEGUNDA, [loc.id])
    s.gerar(SABADO, [loc.id])
    s.gerar(DOMINGO, [loc.id])
    db.session.commit()

    def horas(rota, dia):
        from facilities import tempo
        return [tempo.fmt(t.previsto_para, '%H:%M') for t in TarefaDia.query.filter_by(
            rota_id=rota.id, data=dia).order_by(TarefaDia.previsto_para)]
    assert horas(rota1, SEGUNDA) == ['06:00', '06:30', '08:00', '09:30', '12:00', '12:30',
                                     '13:30', '14:30', '14:50']
    assert horas(rota1, SABADO) == ['06:00', '06:30', '08:00', '09:30']
    assert horas(rota1, DOMINGO) == []
    assert horas(rota3, SEGUNDA)[:3] == ['07:00', '10:30', '11:30']
    assert horas(rota3, SABADO) == ['07:00', '09:30', '10:30']
    rota2 = Rota.query.filter_by(client_id=loc.id, nome=previa.rotas[1].nome).one()
    assert horas(rota2, SABADO) == []
    assert horas(rota2, DOMINGO) == ['22:00', '23:20', '23:40', '01:00', '01:30', '02:00',
                                     '03:00', '03:30', '04:50', '05:10']
    # A tarefa das 01:00 de domingo é na segunda de madrugada, UTC; a das
    # 22:00 começa no domingo mesmo.
    t = TarefaDia.query.filter_by(rota_id=rota2.id, data=DOMINGO).order_by(
        TarefaDia.previsto_para).all()
    assert t[0].previsto_para.date() == date(2026, 10, 26) and t[0].previsto_para.hour == 1
    assert t[3].previsto_para.date() == date(2026, 10, 26) and t[3].previsto_para.hour == 4


def test_intervalo_da_rota_tira_as_tarefas_de_dentro_dele(app_module, contexto):
    """Regra do intervalo em separado: o agendador não cria tarefa cujo
    horário caia dentro dele (início incluído, fim excluído)."""
    from app import db
    from facilities.rotas import servico as s
    from tests.test_rotas_servico import montar_cena
    cena = montar_cena(app_module)
    loc = fabrica.local()
    rota = db.session.get(s.Rota, cena['rota'])
    item = rota.itens[0]
    s.salvar_item(rota, item, {'ponto_id': item.ponto_id, 'modelo_id': item.modelo_id,
                               'horarios': '08:00, 09:00, 10:30, 11:00', 'frequencia_min': ''})
    s.salvar_rota(loc, rota, {'nome': rota.nome, 'turno': rota.turno, 'hora_inicio': '07:00',
                              'hora_fim': '15:00', 'dias_semana': '12345',
                              'intervalo_inicio': '09:00', 'intervalo_fim': '11:00'})
    db.session.commit()
    assert [m.strftime('%H:%M') for m in s.horarios_do_item(rota, item, SEGUNDA)] == \
        ['08:00', '11:00']
    # Intervalo que vira a noite, num turno noturno.
    rota.hora_inicio, rota.hora_fim = time(22, 0), time(5, 20)
    rota.intervalo_inicio, rota.intervalo_fim = time(0, 0), time(1, 0)
    item.horarios = '23:40, 00:00, 00:30, 01:00'
    assert [m.strftime('%H:%M') for m in s.horarios_do_item(rota, item, SEGUNDA)] == \
        ['23:40', '01:00']
    db.session.rollback()


def test_validacoes_de_intervalo_dias_e_horarios_por_dia(app_module, contexto):
    from app import db
    from facilities.rotas import servico as s
    from tests.test_rotas_servico import montar_cena
    cena = montar_cena(app_module)
    loc = fabrica.local()
    rota = db.session.get(s.Rota, cena['rota'])
    base = {'nome': rota.nome, 'turno': rota.turno, 'hora_inicio': '07:00', 'hora_fim': '15:00',
            'dias_semana': '12345'}
    with pytest.raises(s.RegraDaRota, match='caber no turno'):
        s.salvar_rota(loc, rota, dict(base, intervalo_inicio='16:00', intervalo_fim='17:00'))
    with pytest.raises(s.RegraDaRota, match='início e o fim'):
        s.salvar_rota(loc, rota, dict(base, intervalo_inicio='11:00', intervalo_fim=''))
    with pytest.raises(s.RegraDaRota, match='duração'):
        s.salvar_rota(loc, rota, dict(base, intervalo_inicio='11:00', intervalo_fim='11:00'))
    s.salvar_rota(loc, rota, dict(base, intervalo_inicio='11:00', intervalo_fim='12:00'))
    assert (rota.intervalo_inicio, rota.intervalo_fim) == (time(11, 0), time(12, 0))
    # Sem as chaves no formulário, o intervalo fica como está.
    s.salvar_rota(loc, rota, base)
    assert rota.intervalo_inicio == time(11, 0)
    s.salvar_rota(loc, rota, dict(base, intervalo_inicio='', intervalo_fim=''))
    assert rota.intervalo_inicio is None
    item = rota.itens[0]
    dados = {'ponto_id': item.ponto_id, 'modelo_id': item.modelo_id, 'horarios': '09:00'}
    with pytest.raises(s.RegraDaRota, match='não roda em sáb'):
        s.salvar_item(rota, item, dict(dados, dias_semana='126'))
    with pytest.raises(s.RegraDaRota, match='não acontece nesse dia'):
        s.salvar_item(rota, item, dict(dados, dias_semana='12', horarios_por_dia='sex: 08:00'))
    with pytest.raises(s.RegraDaRota, match='fora do turno'):
        s.salvar_item(rota, item, dict(dados, horarios_por_dia='sex: 18:00'))
    with pytest.raises(s.RegraDaRota, match='não é um dia'):
        s.salvar_item(rota, item, dict(dados, horarios_por_dia='feriado: 08:00'))
    s.salvar_item(rota, item, dict(dados, dias_semana='12', horarios_por_dia='ter: 08:00; 1: 10:00'))
    assert item.dias_semana == '12' and item.horarios_por_dia_dict == {'1': '10:00', '2': '08:00'}
    # Todos os dias da rota marcados = sem restrição.
    s.salvar_item(rota, item, dict(dados, dias_semana='12345', horarios_por_dia=''))
    assert item.dias_semana is None and item.horarios_por_dia is None
    db.session.rollback()


def test_publicar_com_materiais_e_epi_cria_versao_nova_e_a_copia_leva(app_module, contexto):
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistModelo
    loc = fabrica.local()
    m = s.criar_modelo(None, {'nome': 'Checklist com materiais'}, None)
    itens = s.normalizar_itens([{'texto': 'Feito?', 'tipo': 'sim_nao'}])
    v1, _ = s.publicar(m, itens, {}, None)
    v2, publicou = s.publicar(m, itens, {'materiais': 'Vassoura, pá', 'epi': 'Luva'}, None)
    assert publicou and v2.numero == 2 and (v2.materiais, v2.epi) == ('Vassoura, pá', 'Luva')
    _v, publicou = s.publicar(m, itens, {'materiais': 'Vassoura, pá', 'epi': 'Luva'}, None)
    assert not publicou
    # Sem as chaves no formulário, continuam os da versão atual.
    _v, publicou = s.publicar(m, itens, {}, None)
    assert not publicou
    copia = s.copiar_da_biblioteca(m, loc.id, None)
    assert copia.versao_atual.materiais == 'Vassoura, pá' and copia.versao_atual.epi == 'Luva'
    db.session.commit()
    assert ChecklistModelo.query.filter_by(client_id=loc.id, nome=m.nome).one().id == copia.id
    db.session.rollback()


def test_aplicar_de_novo_recusa_pula_ou_substitui(app_module, contexto):
    from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
    from facilities.rotas.models import ChecklistModelo, ChecklistVersao, Rota
    from facilities.rotas.servico import RegraDaRota
    loc = fabrica.local()
    previa, _r = _aplicar(app_module)

    def contar():
        return (Setor.query.filter_by(client_id=loc.id).count(),
                Ambiente.query.join(Setor).filter(Setor.client_id == loc.id).count(),
                PontoInspecao.query.filter_by(client_id=loc.id).count(),
                ChecklistModelo.query.filter_by(client_id=loc.id).count(),
                ChecklistVersao.query.join(ChecklistModelo).filter(
                    ChecklistModelo.client_id == loc.id).count())
    antes = contar()
    assert _pl().rotas_que_ja_existem(previa, loc) == [r.nome for r in previa.rotas]
    with pytest.raises(RegraDaRota, match='Já existe neste local'):
        _aplicar(app_module)
    assert Rota.query.filter_by(client_id=loc.id).count() == 8 and contar() == antes
    _p, r = _aplicar(app_module, pular=True)
    assert (r['rotas'], r['puladas']) == (0, 8) and contar() == antes
    assert r['checklists'] == 0 and r['checklists_atualizados'] == len(previa.checklists)
    _p, r = _aplicar(app_module, substituir=True)
    assert (r['rotas'], r['substituidas']) == (8, 8) and contar() == antes
    assert Rota.query.filter_by(client_id=loc.id).count() == 16
    assert Rota.query.filter_by(client_id=loc.id, is_active=True).count() == 8
    antiga = Rota.query.filter(Rota.client_id == loc.id, Rota.is_active.is_(False)).first()
    assert 'substituída em' in antiga.nome


def test_cli_dry_run_mostra_a_previa_sem_gravar(app_module, contexto):
    from facilities.rotas.models import Rota
    loc = fabrica.local()
    runner = app_module.app.test_cli_runner()
    caminho = _pl().caminho_da_planilha_trino_frio()
    r = runner.invoke(args=['rotas', 'importar-plano', caminho, '--local', str(loc.id),
                            '--dry-run'])
    assert r.exit_code == 0, r.output
    assert 'BLOCOS (11)' in r.output and 'Rota 2 — ' in r.output and '270 min' in r.output
    assert 'nada foi gravado' in r.output and 'AVISOS (' in r.output
    assert Rota.query.filter_by(client_id=loc.id).count() == 0
    r = runner.invoke(args=['rotas', 'importar-plano', caminho, '--local', str(loc.id)])
    assert r.exit_code == 0, r.output
    assert '8 rota(s) criada(s)' in r.output
    assert Rota.query.filter_by(client_id=loc.id).count() == 8
    r = runner.invoke(args=['rotas', 'importar-plano', caminho, '--local', str(loc.id)])
    assert r.exit_code != 0 and 'Já existe' in r.output
    r = runner.invoke(args=['rotas', 'importar-plano', caminho, '--local', '999999'])
    assert r.exit_code != 0 and 'não encontrado' in r.output


# ── Tela ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def pessoas(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'coord.plano@trino.com', 'pleno', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'fora.plano@trino.com', 'pleno', locais=['Hospital Norte'])
        fabrica.pessoa(app_module, 'asg.plano@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
        return fabrica.local().id


def test_tela_envia_mostra_a_previa_e_cria(app_module, pessoas):
    import re
    from facilities.rotas.models import Rota
    cid = pessoas
    c = fabrica.entrar(app_module, 'coord.plano@trino.com')
    url = f'/rotas/locais/{cid}/importar-plano'
    assert 'Importar plano (planilha)' in c.get(f'/rotas/locais/{cid}').get_data(as_text=True)
    assert c.get(url).status_code == 200
    r = c.post(url, data={'arquivo': (io.BytesIO(_planilha()), 'PLA_TF.xlsx')},
               content_type='multipart/form-data')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Rota 1 — GALPÃO FRIO — Andar administrativo' in html
    assert 'Responsável: ROSA' in html and 'Câmaras D2' in html
    chave = re.search(r'name="chave" value="([^"]+)"', html).group(1)
    assert chave.startswith(f'planos/{cid}/')
    r = c.post(f'{url}/criar', data={'chave': chave}, follow_redirects=True)
    assert 'Plano importado: 8 rota(s)' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cid).count() == 8
    # De novo: a prévia avisa que já existe; sem "substituir", recusa.
    html = c.post(url, data={'arquivo': (io.BytesIO(_planilha()), 'PLA_TF.xlsx')},
                  content_type='multipart/form-data').get_data(as_text=True)
    assert 'Substituir as rotas que já existem' in html
    chave = re.search(r'name="chave" value="([^"]+)"', html).group(1)
    r = c.post(f'{url}/criar', data={'chave': chave}, follow_redirects=True)
    assert 'Já existe neste local' in r.get_data(as_text=True)
    r = c.post(f'{url}/criar', data={'chave': chave, 'substituir': '1'}, follow_redirects=True)
    assert 'Plano importado: 8 rota(s)' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cid, is_active=True).count() == 8
        assert Rota.query.filter_by(client_id=cid).count() == 16
    # A rota importada mostra as observações e o intervalo.
    with app_module.app.app_context():
        rota5 = Rota.query.filter(Rota.client_id == cid, Rota.is_active.is_(True),
                                  Rota.nome.like('Rota 5%')).one()
    html = c.get(f'/rotas/{rota5.id}').get_data(as_text=True)
    assert 'Observações do plano' in html and 'intervalo 12:00 às 13:00' in html


def test_tela_recusa_quem_nao_monta_e_arquivo_que_nao_e_planilha(app_module, pessoas):
    from facilities.rotas.models import Rota
    cid = pessoas
    dados = lambda: {'arquivo': (io.BytesIO(_planilha()), 'PLA_TF.xlsx')}   # noqa: E731
    url = f'/rotas/locais/{cid}/importar-plano'
    for email in ('asg.plano@trino.com', 'fora.plano@trino.com'):
        c = fabrica.entrar(app_module, email)
        assert c.get(url).status_code == 403
        assert c.post(url, data=dados(), content_type='multipart/form-data').status_code == 403
        assert c.post(f'{url}/criar', data={'chave': f'planos/{cid}/' + 'a' * 32 + '.xlsx'}
                      ).status_code == 403
    c = fabrica.entrar(app_module, 'coord.plano@trino.com')
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 100
    r = c.post(url, data={'arquivo': (io.BytesIO(png), 'plano.xlsx')},
               content_type='multipart/form-data', follow_redirects=True)
    assert 'Envie o plano em Excel' in r.get_data(as_text=True)
    r = c.post(url, data={'arquivo': (io.BytesIO(_planilha()), 'plano.xls')},
               content_type='multipart/form-data', follow_redirects=True)
    assert 'Envie o plano em Excel' in r.get_data(as_text=True)
    r = c.post(url, data={}, follow_redirects=True)
    assert 'Escolha o arquivo' in r.get_data(as_text=True)
    # Chave inventada (ou de outro local) não cria nada.
    r = c.post(f'{url}/criar', data={'chave': f'planos/{cid + 1}/' + 'a' * 32 + '.xlsx'},
               follow_redirects=True)
    assert 'A prévia venceu' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert Rota.query.filter_by(client_id=cid).count() == 0


# ── Cadastro de teste da Trino Frio ───────────────────────────────────────

def test_semear_trino_frio_cria_o_cliente_e_as_rotas_sem_pessoas(app_module, contexto):
    from app import User, db
    from facilities.cadastros.models import Contratante, Empresa
    from facilities.core.models import Client
    from facilities.rotas.models import Rota
    pessoas_antes = User.query.count()
    loc, r = _pl().semear_trino_frio()
    db.session.commit()
    assert loc.name == 'Galpão Frio — Trino Frio' and loc.cost_center == 'TF-01'
    cli = Contratante.query.filter_by(nome='Trino Frio').one()
    assert cli.centro_custo == 'TF' and loc.contratante_id == cli.id
    assert Empresa.query.count() == 1
    assert (r['rotas'], r['puladas']) == (8, 0)
    assert Rota.query.filter_by(client_id=loc.id, is_active=True).count() == 8
    assert User.query.count() == pessoas_antes
    assert not any(e.is_active for rota in Rota.query.filter_by(client_id=loc.id)
                   for e in rota.escalas)
    # De novo: nada duplica.
    loc2, r = _pl().semear_trino_frio()
    db.session.commit()
    assert loc2.id == loc.id and (r['rotas'], r['puladas']) == (0, 8)
    assert Client.query.filter_by(name='Galpão Frio — Trino Frio').count() == 1
    assert Contratante.query.filter_by(nome='Trino Frio').count() == 1
    runner = app_module.app.test_cli_runner()
    out = runner.invoke(args=['semear-trino-frio'])
    assert out.exit_code == 0 and '8 já existia(m)' in out.output, out.output
