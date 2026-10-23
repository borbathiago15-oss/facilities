"""Ajustes de fluxo (decisões do dono, 23/10/2026).

1. Mudar a rota refaz a agenda que ainda não começou; o que foi feito (ou
   já venceu) fica. Mudar a rota às 14h não faz nascer atrasada a tarefa das 8h.
2. O agendador segue quando uma etapa ou uma rota falha (fica registrado).
3. Feriados: nacionais calculados + os do local; a rota escolhe se funciona.
4. Cliente desativado: a conta do cliente perde o portal na hora.
5. Relatório liberado fica congelado; a gestão vê o que mudou.
6. Tarefa perdida vai para o sino (agrupada), da pessoa e do superior.
"""
from datetime import date, time, timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_relatorio_cliente import SETEMBRO, cena  # noqa: F401 — fixture

TERCA = date(2026, 11, 3)            # dia comum
FINADOS = date(2026, 11, 2)          # feriado nacional, segunda-feira


def _utc(dia, hhmm):
    h, m = map(int, hhmm.split(':'))
    return tempo.para_utc(dia, time(h, m))


def _s():
    from facilities.rotas import servico
    return servico


@pytest.fixture()
def rota_do_dia(app_module):
    """Um local com uma rota (06h–22h, tolerância 30) de 3 horários num ponto,
    escalada para a Ana (que tem um supervisor)."""
    from app import db
    s = _s()
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        sup = fabrica.pessoa(app_module, 'sup.fluxo@trino.com', 'supervisor',
                             locais=[loc.id], nome='Sueli Supervisora')
        ana = fabrica.pessoa(app_module, 'ana.fluxo@trino.com', 'encarregado', locais=[loc.id],
                             nome='Ana Fluxo', superior_id=sup)
        bia = fabrica.pessoa(app_module, 'bia.fluxo@trino.com', 'encarregado', locais=[loc.id],
                             nome='Bia Fluxo')
        m = s.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Piso limpo?', 'tipo': 'sim_nao'}]), {},
                   None)
        rota = s.salvar_rota(loc, None, {'nome': 'Limpeza fluxo', 'turno': 'T1',
                                         'hora_inicio': '06:00', 'hora_fim': '22:00',
                                         'tolerancia_min': '30', 'dias_semana': '1234567'})
        item = s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                          'horarios': '08:00, 16:00, 18:00'})
        s.salvar_escala(rota, {'user_id': ana, 'dias_semana': '1234567',
                               'data_inicio': date(2026, 10, 1).isoformat()})
        db.session.commit()
        ids.update(rota=rota.id, item=item.id, modelo=m.id, ana=ana, bia=bia, sup=sup)
    return ids


def _tarefas(dia):
    from facilities.rotas.models import TarefaDia
    return {tempo.fmt(t.previsto_para, '%H:%M'): t
            for t in TarefaDia.query.filter_by(data=dia).order_by(TarefaDia.previsto_para)}


# ── 1. Mudar a rota refaz a agenda ────────────────────────────────────────

def test_trocar_a_escala_passa_so_o_que_nao_comecou(app_module, rota_do_dia):
    from app import db
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, Rota, RotaEscala
    s = _s()
    with app_module.app.app_context():
        s.gerar(TERCA, agora_utc=_utc(TERCA, '05:00'))
        t = _tarefas(TERCA)
        t['08:00'].status = CONCLUIDA_NO_PRAZO
        db.session.commit()
        rota = db.session.get(Rota, rota_do_dia['rota'])
        RotaEscala.query.filter_by(rota_id=rota.id).one().is_active = False
        s.salvar_escala(rota, {'user_id': rota_do_dia['bia'], 'dias_semana': '1234567',
                               'data_inicio': date(2026, 10, 1).isoformat()})
        removidas, atualizadas, _criadas = s.replanejar(rota, agora_utc=_utc(TERCA, '14:00'))
        db.session.commit()
        t = _tarefas(TERCA)
        assert (removidas, atualizadas) == (0, 2)
        assert t['08:00'].user_id == rota_do_dia['ana']           # já feita: fica
        assert t['16:00'].user_id == t['18:00'].user_id == rota_do_dia['bia']


def test_tirar_a_atividade_tira_so_o_futuro(app_module, rota_do_dia):
    from app import db
    from facilities.rotas.models import Rota, RotaItem
    s = _s()
    with app_module.app.app_context():
        s.gerar(TERCA, agora_utc=_utc(TERCA, '05:00'))
        db.session.get(RotaItem, rota_do_dia['item']).is_active = False
        rota = db.session.get(Rota, rota_do_dia['rota'])
        removidas, _a, _c = s.replanejar(rota, agora_utc=_utc(TERCA, '14:00'))
        db.session.commit()
        # A das 8h já venceu (prazo 8h30) sem registro: fica, e vira perdida no fim.
        assert removidas == 2 and list(_tarefas(TERCA)) == ['08:00']


def test_mudar_a_rota_a_tarde_nao_cria_tarefa_atrasada(app_module, rota_do_dia):
    from app import db
    from facilities.rotas.models import Rota
    s = _s()
    with app_module.app.app_context():
        s.gerar(TERCA, agora_utc=_utc(TERCA, '05:00'))
        rota = db.session.get(Rota, rota_do_dia['rota'])
        s.salvar_item(rota, None, {'ponto_id': rota_do_dia['ponto'],
                                   'modelo_id': rota_do_dia['modelo'],
                                   'horarios': '09:00, 17:00'})
        s.replanejar(rota, agora_utc=_utc(TERCA, '14:00'))
        db.session.commit()
        # E a rede de segurança das telas (garantir_hoje) também não cria a das 9h.
        s.gerar(TERCA, agora_utc=_utc(TERCA, '15:00'))
        db.session.commit()
        assert list(_tarefas(TERCA)) == ['08:00', '16:00', '17:00', '18:00']


def test_editar_pela_tela_refaz_e_avisa(app_module, rota_do_dia, auth_client):
    from app import db
    from facilities.rotas.models import TarefaDia
    s = _s()
    hoje = tempo.hoje()
    with app_module.app.app_context():
        s.garantir_hoje([rota_do_dia['local']])
        db.session.commit()
        antes = TarefaDia.query.filter_by(data=hoje).count()
    r = auth_client.post(f"/rotas/{rota_do_dia['rota']}/itens/{rota_do_dia['item']}",
                         data={'ativo': '0'}, follow_redirects=True)
    pagina = r.get_data(as_text=True)
    with app_module.app.app_context():
        depois = TarefaDia.query.filter_by(data=hoje).count()
    if antes > depois:
        assert 'Agenda de hoje e amanhã refeita' in pagina
    assert depois <= antes


# ── 2. Agendador resiliente ───────────────────────────────────────────────

def test_rota_com_problema_nao_para_as_outras(app_module, rota_do_dia, monkeypatch):
    from app import db
    from facilities.rotas.models import Rota
    s = _s()
    with app_module.app.app_context():
        loc2 = fabrica.local('Hospital Norte')
        outra = s.salvar_rota(loc2, None, {'nome': 'Rota quebrada', 'turno': 'T1',
                                           'hora_inicio': '06:00', 'hora_fim': '22:00',
                                           'dias_semana': '1234567'})
        db.session.commit()
        quebrada = outra.id
        real = s._gerar_rota

        def _quebra(rota, *a, **k):
            if rota.id == quebrada:
                raise RuntimeError('dado estragado')
            return real(rota, *a, **k)
        monkeypatch.setattr(s, '_gerar_rota', _quebra)
        reg = s.rodar(agora_utc=_utc(TERCA, '05:00'))
        db.session.commit()
        assert reg.ok is False and 'Rota quebrada' in reg.erro and 'dado estragado' in reg.erro
        assert len(_tarefas(TERCA)) == 3          # a rota boa gerou
        assert db.session.get(Rota, quebrada) is not None


# ── 3. Feriados ───────────────────────────────────────────────────────────

def test_feriados_nacionais():
    from facilities.rotas.feriados import nacionais, pascoa
    assert pascoa(2025) == date(2025, 4, 20)
    assert pascoa(2026) == date(2026, 4, 5)
    assert pascoa(2027) == date(2027, 3, 28)
    n = nacionais(2026)
    assert n[date(2026, 4, 3)] == 'Sexta-feira Santa'
    assert date(2026, 11, 20) in n and date(2026, 11, 2) in n and len(n) == 10


def test_rota_que_nao_funciona_em_feriado(app_module, rota_do_dia):
    from app import db
    from facilities.rotas import feriados
    from facilities.rotas.models import Rota
    s = _s()
    with app_module.app.app_context():
        rota = db.session.get(Rota, rota_do_dia['rota'])
        assert rota.funciona_em_feriado                     # padrão: como era
        s.gerar(FINADOS, agora_utc=_utc(FINADOS, '05:00'))
        assert len(_tarefas(FINADOS)) == 3
        s.salvar_rota(rota.local, rota, {'nome': rota.nome, 'turno': rota.turno,
                                         'hora_inicio': '06:00', 'hora_fim': '22:00',
                                         'tolerancia_min': '30', 'dias_semana': '1234567',
                                         'feriado_no_form': '1'})
        assert rota.funciona_em_feriado is False
        s.replanejar(rota, agora_utc=_utc(FINADOS, '05:00'))
        db.session.commit()
        assert _tarefas(FINADOS) == {}                     # feriado nacional: saiu
        # Feriado do local (cadastrado), num dia comum.
        feriados.cadastrar(rota.local, {'data': TERCA.isoformat(), 'nome': 'Aniversário da '
                                        'cidade'}, None)
        db.session.commit()
        assert s.gerar(TERCA, agora_utc=_utc(TERCA, '05:00')) == 0
        # Outro local, no mesmo dia, segue normal.
        assert feriados.locais_em_feriado({rota.client_id, rota.client_id + 999}, TERCA) == \
            {rota.client_id}


def test_cadastro_de_feriado_recusa_nacional_e_repetido(app_module, rota_do_dia):
    from facilities.rotas import feriados
    with app_module.app.app_context():
        loc = fabrica.local()
        with pytest.raises(feriados.FeriadoInvalido, match='feriado nacional'):
            feriados.cadastrar(loc, {'data': '2026-12-25', 'nome': 'Natal'}, None)
        feriados.cadastrar(loc, {'data': '2026-07-02', 'nome': 'Independência da Bahia'}, None)
        with pytest.raises(feriados.FeriadoInvalido, match='já está cadastrado'):
            feriados.cadastrar(loc, {'data': '2026-07-02', 'nome': 'Outro'}, None)


def test_tela_de_feriados(app_module, rota_do_dia, auth_client):
    cid = rota_do_dia['local']
    pag = auth_client.get(f'/rotas/locais/{cid}/feriados?ano=2026').get_data(as_text=True)
    assert 'Finados' in pag and 'Sexta-feira Santa' in pag
    r = auth_client.post(f'/rotas/locais/{cid}/feriados',
                         data={'data': '2026-07-02', 'nome': 'Independência da Bahia'},
                         follow_redirects=True)
    assert 'Independência da Bahia' in r.get_data(as_text=True)
    ana = fabrica.entrar(app_module, 'ana.fluxo@trino.com')
    assert ana.post(f'/rotas/locais/{cid}/feriados',
                    data={'data': '2026-08-01', 'nome': 'X'}).status_code == 403


# ── 4. Cliente desativado ─────────────────────────────────────────────────

def test_cliente_desativado_perde_o_portal(app_module, rota_do_dia):
    from app import db
    from facilities.cadastros.models import Contratante
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cli.fluxo@gl.com', rota_do_dia['cliente'])
    cli = fabrica.entrar_com_codigo(app_module, 'cli.fluxo@gl.com')
    assert cli.get('/cliente/').status_code == 200
    with app_module.app.app_context():
        db.session.get(Contratante, rota_do_dia['cliente']).is_active = False
        db.session.commit()
    r = cli.get('/cliente/')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    novo = app_module.app.test_client()
    r = novo.post('/login', data={'email': 'cli.fluxo@gl.com', 'password': fabrica.SENHA})
    assert r.status_code == 401


# ── 5. Relatório congelado ────────────────────────────────────────────────

def test_relatorio_liberado_fica_congelado(app_module, cena):  # noqa: F811
    from app import Client, User, db
    from facilities.chamados.models import Chamado
    from facilities.relatorios import cliente as rel
    from facilities.relatorios.telas import montar
    with app_module.app.app_context():
        coord = db.session.get(User, cena['coord'])
        loc = db.session.get(Client, cena['local'])
        registro = rel.liberar(loc.id, SETEMBRO, coord)
        db.session.commit()
        recebido = montar(loc, SETEMBRO, liberado=True)[0]
        # Uma correção no mês, depois de liberar: o chamado saiu do prazo.
        ch = db.session.get(Chamado, cena['chamado'])
        ch.resolvido_em = ch.prazo + timedelta(days=2)
        db.session.commit()
        agora = rel.dados(loc, SETEMBRO)
        assert agora['nota']['nota'] != recebido['nota']['nota']
        assert montar(loc, SETEMBRO, liberado=True)[0]['nota'] == recebido['nota']
        assert ('Chamados no prazo', 100.0, 0.0) in rel.mudancas(registro, agora)
        # Liberar de novo manda a versão atual.
        rel.liberar(loc.id, SETEMBRO, coord)
        db.session.commit()
        assert rel.mudancas(registro, rel.dados(loc, SETEMBRO)) == []
    gestao = fabrica.entrar(app_module, 'coord.rel@trino.com')
    pag = gestao.get(f"/relatorios/cliente/{cena['local']}/2026-09").get_data(as_text=True)
    assert 'Os números mudaram' not in pag


def test_tela_da_gestao_mostra_o_que_mudou(app_module, cena):  # noqa: F811
    from app import db
    from facilities.chamados.models import Chamado
    gestao = fabrica.entrar(app_module, 'coord.rel@trino.com')
    url = f"/relatorios/cliente/{cena['local']}/2026-09"
    gestao.post(url + '/liberar')
    with app_module.app.app_context():
        ch = db.session.get(Chamado, cena['chamado'])
        ch.resolvido_em = ch.prazo + timedelta(days=2)
        db.session.commit()
    pag = gestao.get(url).get_data(as_text=True)
    assert 'Os números mudaram depois da liberação' in pag and 'Liberar a versão atual' in pag


# ── 6. Tarefa perdida no sino ─────────────────────────────────────────────

def test_tarefas_perdidas_vao_para_o_sino_agrupadas(app_module, rota_do_dia):
    from app import db
    from facilities.core.models import Notification
    s = _s()
    with app_module.app.app_context():
        s.gerar(TERCA, agora_utc=_utc(TERCA, '05:00'))
        db.session.commit()
        n = s.fechar_perdidas(_utc(TERCA + timedelta(days=1), '00:00'))
        db.session.commit()
        assert n == 3
        da_ana = Notification.query.filter_by(user_id=rota_do_dia['ana'],
                                              notification_type='tarefa_perdida').all()
        do_sup = Notification.query.filter_by(user_id=rota_do_dia['sup'],
                                              notification_type='tarefa_perdida').all()
        assert len(da_ana) == 1 and len(do_sup) == 1
        assert '3 tarefa(s) não feita(s)' in da_ana[0].title
        assert 'Ana Fluxo' in do_sup[0].message and '/dia?data=2026-11-03' in do_sup[0].link
