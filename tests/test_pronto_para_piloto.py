"""Bloco A — pronto para o piloto (análise de 18/10/2026).

* Item não conforme no checklist da rota ABRE chamado (decisão do dono),
  um por execução, com as fotos.
* Tarefa já feita por outra pessoa ou com turno encerrado: o trabalho vira
  atividade extra, não se perde.
* O agendador registra a rodada que falha; a visita vencida vira perdida.
* Chamado: urgente vai ao celular; resolvido avisa quem abriu e, sem
  confirmação em 24 h, lembra uma vez (não fecha sozinho — decisão do dono);
  reaberto ganha prazo novo e volta a avisar.
* Aviso do núcleo só para quem ainda tem o local na carteira.
"""
from datetime import datetime, timedelta

import pytest

from tests import fabrica
from tests.test_rotas_servico import (SEGUNDA, _executar, _respostas, _s, _tarefas,
                                      cena, utc)  # noqa: F401  (cena é fixture)


# ── Checklist da rota ─────────────────────────────────────────────────────

def test_item_nao_conforme_abre_um_chamado_com_as_fotos(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_EXECUCAO, Chamado, ChamadoAnexo
    from facilities.rotas.models import NaoConformidade
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'),
                          respostas=_respostas(papel_higienico_reposto='nao',
                                               mictorios='nao_conforme'))
        db.session.commit()
        ncs = NaoConformidade.query.filter_by(execucao_id=ex.id).all()
        assert len(ncs) == 2
        # Bloco do técnico (22/10/2026): UM chamado por execução, ligado a ela.
        ch = Chamado.query.filter_by(origem=ORIGEM_EXECUCAO, origem_id=ex.id).one()
        assert {nc.chamado_id for nc in ncs} == {ch.id}
        assert ch.titulo == 'Porta do banheiro · 2 item(ns) com problema'
        assert 'Papel higiênico reposto?' in ch.descricao and 'Mictórios' in ch.descricao
        anexos = ChamadoAnexo.query.filter_by(chamado_id=ch.id).all()
        assert len(anexos) == 1 and anexos[0].momento == 'antes'
        # O botão "abrir chamado" da não conformidade devolve o mesmo.
        assert _s().abrir_chamado_da_nc(ncs[1], ex.pessoa) == ch.id


def test_tudo_conforme_nao_abre_chamado(app_module, cena):
    from app import db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'))
        db.session.commit()
        assert Chamado.query.count() == 0


def test_turno_encerrado_vira_atividade_extra(app_module, cena):
    from app import db
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ex, nova = _executar(cena['ana'], t9, utc(SEGUNDA, '16:00'))
        db.session.commit()
        assert nova and ex.extra and ex.tarefa_id is None
        assert 'turno da tarefa já tinha terminado' in ex.observacao
        with pytest.raises(_s().RegraDaRota, match='Ainda não chegou'):
            _executar(cena['ana'], _tarefas()[1], utc(SEGUNDA, '07:10'))


def test_codigo_invalido_vira_mensagem_e_nao_erro(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        u = db.session.get(User, cena['ana'])
        _s().gerar(SEGUNDA)
        qr = _tarefas()[0].ponto.codigo_qr
        with pytest.raises(_s().RegraDaRota):
            _s().registrar_execucao(u, {'envio_id': 'invalido-0001', 'ponto': qr,
                                        'tarefa_id': 'abc', 'respostas': {}},
                                    {}, agora_utc=utc(SEGUNDA, '09:00'))


# ── Agendador ─────────────────────────────────────────────────────────────

def test_rodada_que_falha_fica_registrada(app_module, cena, monkeypatch):
    from app import db
    from facilities.rotas.models import AgendadorExecucao

    def quebra(*_a, **_k):
        raise RuntimeError('falha de teste')
    monkeypatch.setattr('facilities.rotas.servico.avisar_tarefas', quebra)
    with app_module.app.app_context():
        with pytest.raises(RuntimeError):
            _s().rodar(agora_utc=utc(SEGUNDA, '06:00'))
        db.session.rollback()               # o que quem chama faria
        reg = AgendadorExecucao.query.order_by(AgendadorExecucao.id.desc()).first()
        assert reg is not None and reg.ok is False and 'falha de teste' in reg.erro
        AgendadorExecucao.query.delete()
        db.session.commit()


def test_trava_do_agendador_no_postgres(app_module):
    """Só no Postgres: com a trava tomada por outra conexão, a rodada não faz
    nada (devolve None)."""
    from app import db
    from sqlalchemy import text
    with app_module.app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('a trava existe só no Postgres')
        outra = db.engine.connect()
        tx = outra.begin()
        outra.execute(text('SELECT pg_advisory_xact_lock(:k)'),
                      {'k': _s().TRAVA_DO_AGENDADOR})
        try:
            assert _s().rodar(agora_utc=utc(SEGUNDA, '06:00')) is None
            db.session.rollback()
        finally:
            tx.rollback()
            outra.close()
        reg = _s().rodar(agora_utc=utc(SEGUNDA, '06:00'))
        assert reg is not None and reg.ok
        db.session.rollback()


def test_visita_vencida_vira_perdida_depois_da_folga(app_module):
    from app import User, db
    from facilities import tempo
    from facilities.rotas import servico as rotas
    from facilities.visitas import servico as vis
    from facilities.visitas.models import Visita
    with app_module.app.app_context():
        fabrica.estrutura(app_module)
        loc = fabrica.local()
        coord = fabrica.pessoa(app_module, 'coord.vv@trino.com', 'pleno', locais=['Shopping Centro'])
        m = rotas.criar_modelo(loc.id, {'nome': 'Qualidade'}, None)
        rotas.publicar(m, rotas.normalizar_itens([{'texto': 'Ok?', 'tipo': 'sim_nao'}]), {}, None)
        dia = tempo.hoje() - timedelta(days=10)
        vis.salvar_programada(loc, None, {'nome': 'Semanal', 'modelo_id': str(m.id),
                                          'intervalo_dias': '30', 'proxima_em': dia.isoformat()},
                              db.session.get(User, coord))
        vis.gerar_visitas(dia, tempo.para_utc(dia, datetime.min.time()))
        db.session.commit()
        v = Visita.query.one()
        assert vis.fechar_vencidas(vis.prazo(v) + timedelta(days=1)) == 0
        assert vis.fechar_vencidas(vis.prazo(v) + timedelta(days=3)) == 1
        db.session.commit()
        assert v.status == 'perdida' and v.situacao_rotulo == 'Não feita (venceu)'
        assert vis.abertas([loc.id]) == []


# ── Chamados ──────────────────────────────────────────────────────────────

@pytest.fixture()
def ch_cena(app_module):
    from app import db
    with app_module.app.app_context():
        loc = fabrica.local()
        ids = {'local': loc.id,
               'coord': fabrica.pessoa(app_module, 'coord.pp@trino.com', 'pleno',
                                       locais=['Shopping Centro']),
               'enc': fabrica.pessoa(app_module, 'enc.pp@trino.com', 'encarregado',
                                     locais=['Shopping Centro']),
               'tec': fabrica.pessoa(app_module, 'tec.pp@trino.com', 'tecnico',
                                     locais=['Shopping Centro'])}
        db.session.commit()
    enviados = []
    app_module.app.extensions['facilities_push'] = \
        lambda insc, carga: enviados.append((insc.user_id, carga['titulo'])) or 201
    with app_module.app.app_context():
        from app import User
        from tests.test_push import _celular
        from facilities.core import push
        for uid in ids.values():
            u = db.session.get(User, uid)
            if isinstance(u, User):
                _r, d, _a = _celular()
                d['endpoint'] = d['endpoint'] + str(uid)
                push.inscrever(u, d)
        db.session.commit()
    ids['enviados'] = enviados
    return ids


def _u(uid):
    from app import User, db
    return db.session.get(User, uid)


def test_urgente_vai_ao_celular_da_gestao(app_module, ch_cena):
    from app import db
    from facilities.chamados import servico as chs
    with app_module.app.app_context():
        chs.abrir(_u(ch_cena['enc']), ch_cena['local'], 'Vazamento no teto', prioridade='urgente')
        chs.abrir(_u(ch_cena['enc']), ch_cena['local'], 'Lâmpada', prioridade='baixa')
        db.session.commit()
    titulos = [t for uid, t in ch_cena['enviados'] if uid == ch_cena['coord']]
    assert len(titulos) == 1 and titulos[0].startswith('Urgente:')


def test_resolvido_avisa_quem_abriu_e_lembra_uma_vez(app_module, ch_cena):
    from app import db
    from facilities.chamados import servico as chs
    from facilities.chamados.models import ChamadoEvento
    with app_module.app.app_context():
        ch = chs.abrir(_u(ch_cena['enc']), ch_cena['local'], 'Torneira pingando')
        db.session.flush()
        chs.executar(_u(ch_cena['coord']), ch, 'iniciar', {})
        chs.executar(_u(ch_cena['coord']), ch, 'resolver', {'texto': 'Trocado o reparo'})
        db.session.commit()
        assert (ch_cena['enc'], f'Resolvido: {ch.numero}') in ch_cena['enviados']
        depois = ch.resolvido_em + timedelta(hours=25)
        assert chs.lembrar_confirmacao(ch.resolvido_em + timedelta(hours=2)) == 0
        assert chs.lembrar_confirmacao(depois) == 1
        assert chs.lembrar_confirmacao(depois + timedelta(hours=5)) == 0
        db.session.commit()
        assert ch.status == 'resolvido'           # não fecha sozinho
        assert ChamadoEvento.query.filter_by(chamado_id=ch.id, tipo='lembrete').count() == 1
        assert (ch_cena['enc'], f'Falta confirmar: {ch.numero}') in ch_cena['enviados']


def test_reaberto_ganha_prazo_novo_e_volta_a_avisar(app_module, ch_cena):
    from app import db
    from facilities.chamados import servico as chs
    with app_module.app.app_context():
        ch = chs.abrir(_u(ch_cena['enc']), ch_cena['local'], 'Porta emperrada', prioridade='alta')
        db.session.flush()
        ch.prazo = datetime.utcnow() - timedelta(days=3)
        ch.aviso_vencido_em = ch.aviso_vencendo_em = datetime.utcnow() - timedelta(days=2)
        chs.executar(_u(ch_cena['coord']), ch, 'iniciar', {})
        chs.executar(_u(ch_cena['coord']), ch, 'resolver', {'texto': 'Ajustada'})
        chs.executar(_u(ch_cena['enc']), ch, 'reabrir', {'texto': 'Emperrou de novo'})
        db.session.commit()
        assert ch.prazo > datetime.utcnow() + timedelta(hours=23)
        assert ch.aviso_vencido_em is None and ch.aviso_vencendo_em is None
        assert chs.avisar_prazos(ch.prazo + timedelta(minutes=5)) == 1


# ── Avisos do núcleo ──────────────────────────────────────────────────────

def test_aviso_so_para_quem_ainda_tem_o_local(app_module):
    from app import db
    from facilities.core.models import Notification
    from facilities.core.rotas import avisar
    with app_module.app.app_context():
        loc = fabrica.local()
        dentro = fabrica.pessoa(app_module, 'dentro.av@trino.com', 'supervisor',
                                locais=['Shopping Centro'])
        saiu = fabrica.pessoa(app_module, 'saiu.av@trino.com', 'supervisor',
                              locais=['Hospital Norte'])
        avisados = avisar({dentro, saiu}, 'Teste', 'x', '/', client_id=loc.id)
        db.session.commit()
        assert avisados == {dentro}
        assert Notification.query.filter_by(user_id=saiu).count() == 0
