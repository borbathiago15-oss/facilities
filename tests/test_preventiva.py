"""Fase 5 — preventiva, prazo parado em "Aguardando" (D8), régua de prazo por
cliente (D9), avisos de prazo e o painel de demandas.

O caso: o secador do banheiro do 2º andar tem limpeza de filtro a cada 30
dias. O plano abre a ordem 2 dias antes; o Caio (técnico) lê o QR da porta e
faz o checklist; a ordem fica resolvida para a coordenação conferir.
"""
import json
from datetime import date, datetime, timedelta

import pytest

from tests import fabrica

HOJE = date(2026, 10, 19)


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.rotas import servico as rotas
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ids['caio'] = fabrica.pessoa(app_module, 'caio.prev@trino.com', 'tecnico',
                                     locais=['Shopping Centro'], nome='Caio')
        ids['coord'] = fabrica.pessoa(app_module, 'coord.prev@trino.com', 'pleno',
                                      locais=['Shopping Centro'], nome='Coordenação')
        ids['fora'] = fabrica.pessoa(app_module, 'fora.prev@trino.com', 'tecnico',
                                     locais=['Hospital Norte'])
        m = rotas.criar_modelo(loc.id, {'nome': 'Limpeza do filtro'}, None)
        v, _ = rotas.publicar(m, rotas.normalizar_itens([
            {'texto': 'Filtro lavado?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao'}]), {}, None)
        db.session.commit()
        ids.update(modelo=m.id, versao=v.id)
    # Fora do contexto: senão as requisições do teste dividem o mesmo ``g``
    # (e a carteira guardada nele) entre pessoas diferentes.
    return ids


def _plano(cena, **extra):
    from app import User, db
    from facilities.preventiva import servico
    dados = {'nome': 'Filtro do secador', 'ponto_id': cena['ponto'],
             'equipamento_id': cena['equipamento'], 'modelo_id': cena['modelo'],
             'intervalo_dias': '30', 'antecedencia_dias': '2',
             'proxima_em': (HOJE + timedelta(days=2)).isoformat(), 'prioridade': 'media',
             'responsavel_id': cena['caio']}
    dados.update(extra)
    p = servico.salvar_plano(fabrica.local(), None, dados, db.session.get(User, cena['coord']))
    db.session.commit()
    return p


def _agora():
    from facilities import tempo
    from datetime import time
    return tempo.para_utc(HOJE, time(8, 0))


def _avisos(uid):
    from facilities.core.models import Notification
    return [n.title for n in Notification.query.filter_by(user_id=uid)]


# ── Plano e geração ───────────────────────────────────────────────────────

def test_plano_valida_local_e_campos(app_module, cena):
    from facilities.preventiva.servico import RegraDaPreventiva
    with app_module.app.app_context():
        with pytest.raises(RegraDaPreventiva, match='antecedência'):
            _plano(cena, antecedencia_dias='30')
        with pytest.raises(RegraDaPreventiva, match='ponto'):
            _plano(cena, ponto_id='abc')
        with pytest.raises(RegraDaPreventiva, match='responsável'):
            _plano(cena, responsavel_id=str(cena['fora']))
        with pytest.raises(RegraDaPreventiva, match='Intervalo'):
            _plano(cena, intervalo_dias='0')


def test_agendador_abre_uma_ordem_por_ciclo_sem_duplicar(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_PREVENTIVA, Chamado
    from facilities.preventiva import servico
    with app_module.app.app_context():
        p = _plano(cena)
        # Ainda faltam 3 dias para abrir (vence em 2 + abre 2 antes = hoje).
        assert servico.gerar_ordens(HOJE - timedelta(days=1), _agora()) == 0
        assert servico.gerar_ordens(HOJE, _agora()) == 1
        assert servico.gerar_ordens(HOJE, _agora()) == 0
        db.session.commit()
        chs = Chamado.query.filter_by(origem=ORIGEM_PREVENTIVA).all()
        assert len(chs) == 1
        assert chs[0].responsavel_id == cena['caio']
        assert p.proxima_em == HOJE + timedelta(days=32)
        assert any('Preventiva' in t for t in _avisos(cena['caio']))
        # O próximo ciclo é outra ordem (outro origem_id), mesmo com a 1ª viva.
        assert servico.gerar_ordens(HOJE + timedelta(days=30), _agora()) == 1
        db.session.commit()
        assert Chamado.query.filter_by(origem=ORIGEM_PREVENTIVA).count() == 2


def test_agendador_parado_abre_uma_so_e_pula_para_o_futuro(app_module, cena):
    from app import db
    from facilities.preventiva import servico
    from facilities.preventiva.models import PreventivaOrdem
    with app_module.app.app_context():
        p = _plano(cena, proxima_em=(HOJE - timedelta(days=95)).isoformat(),
                   antecedencia_dias='0')
        assert servico.gerar_ordens(HOJE, _agora()) == 1
        db.session.commit()
        assert PreventivaOrdem.query.count() == 1
        assert p.proxima_em > HOJE


def test_plano_desativado_nao_abre(app_module, cena):
    from app import db
    from facilities.preventiva import servico
    with app_module.app.app_context():
        p = _plano(cena)
        p.is_active = False
        db.session.commit()
        assert servico.gerar_ordens(HOJE, _agora()) == 0


# ── Execução pelo aplicativo ──────────────────────────────────────────────

def _ordem(app_module, cena):
    from app import db
    from facilities.chamados.models import ORIGEM_PREVENTIVA, Chamado
    from facilities.preventiva import servico
    _plano(cena)
    servico.gerar_ordens(HOJE, _agora())
    db.session.commit()
    return Chamado.query.filter_by(origem=ORIGEM_PREVENTIVA).one()


def _executar(uid, ch, qr, respostas=None, envio='envio-prev-1'):
    from app import User, db
    from facilities.rotas import servico
    dados = {'envio_id': envio, 'ponto': qr, 'chamado_id': ch.id,
             'respostas': respostas or {'filtro_lavado': 'sim'}, 'sem_sinal': True,
             'lido_em': _agora().isoformat(), 'concluida_em': _agora().isoformat()}
    return servico.registrar_execucao(db.session.get(User, uid), dados, {},
                                      agora_utc=_agora() + timedelta(minutes=5))


def test_checklist_da_preventiva_resolve_a_ordem(app_module, cena):
    from app import db
    from facilities.chamados.models import RESOLVIDO
    with app_module.app.app_context():
        ch = _ordem(app_module, cena)
        ex, nova = _executar(cena['caio'], ch, cena['qr'],
                             respostas={'filtro_lavado': 'nao'})
        db.session.commit()
        assert nova and ex.chamado_id == ch.id and not ex.extra
        assert ch.status == RESOLVIDO
        assert '1 item(ns) não conforme(s)' in ch.solucao
        assert any('Preventiva feita' in t for t in _avisos(cena['coord']))
        # Reenviar o mesmo envio não duplica; outro envio dá "já resolvida".
        assert _executar(cena['caio'], ch, cena['qr'])[1] is False
        from facilities.rotas.servico import RegraDaRota
        with pytest.raises(RegraDaRota, match='já foi resolvida'):
            _executar(cena['caio'], ch, cena['qr'], envio='envio-prev-2')


def test_preventiva_recusa_qr_de_outro_ponto_e_quem_nao_atende(app_module, cena):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.rotas.servico import RegraDaRota
    with app_module.app.app_context():
        ch = _ordem(app_module, cena)
        outro = cad.salvar_ponto(fabrica.local(), None, {'nome': 'Pia',
                                                         'ambiente_id': cena['ambiente']}, None)
        db.session.commit()
        with pytest.raises(RegraDaRota, match='outro ponto'):
            _executar(cena['caio'], ch, outro.codigo_qr)
        with pytest.raises(RegraDaRota) as e:
            _executar(cena['fora'], ch, cena['qr'])
        assert e.value.codigo == 403
        with pytest.raises(RegraDaRota, match='não encontrada'):
            from app import User
            from facilities.rotas import servico
            servico.registrar_execucao(
                db.session.get(User, cena['caio']),
                {'envio_id': 'envio-prev-x', 'ponto': cena['qr'], 'chamado_id': 'xyz',
                 'respostas': {}}, {})


def test_app_mostra_a_preventiva_no_turno(app_module, cena):
    with app_module.app.app_context():
        ch = _ordem(app_module, cena)
        numero = ch.numero
    c = fabrica.entrar(app_module, 'caio.prev@trino.com')
    html = c.get('/app/turno').get_data(as_text=True)
    assert numero in html and 'preventivas' in html
    r = c.post('/app/api/execucoes', data={'corpo': json.dumps({
        'envio_id': 'envio-prev-tela', 'ponto': cena['qr'], 'chamado_id': ch.id,
        'versao_id': cena['versao'], 'respostas': {'filtro_lavado': 'sim'},
        'lido_em': datetime.utcnow().isoformat() + 'Z'})})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert 'Preventiva feita' in r.get_json()['situacao']


# ── Telas da gestão ───────────────────────────────────────────────────────

def test_tela_de_planos_gestao_cadastra_tecnico_nao(app_module, cena):
    cid = cena['local']
    coord = fabrica.entrar(app_module, 'coord.prev@trino.com')
    assert coord.get(f'/preventiva/locais/{cid}').status_code == 200
    r = coord.post(f'/preventiva/locais/{cid}', data={
        'nome': 'Filtro do ar', 'ponto_id': cena['ponto'], 'modelo_id': cena['modelo'],
        'intervalo_dias': '15', 'antecedencia_dias': '1', 'proxima_em': '2026-11-01',
        'prioridade': 'alta'})
    assert r.status_code == 302
    assert 'Filtro do ar' in coord.get(f'/preventiva/locais/{cid}').get_data(as_text=True)
    caio = fabrica.entrar(app_module, 'caio.prev@trino.com')
    assert caio.get(f'/preventiva/locais/{cid}').status_code == 403
    assert caio.post(f'/preventiva/locais/{cid}', data={'nome': 'x'}).status_code == 403


def test_plano_de_outro_local_nao_abre(app_module, cena):
    from tests.conftest import CONTRATOS_SEMEADOS
    with app_module.app.app_context():
        outro = fabrica.local(CONTRATOS_SEMEADOS[1]).id
    coord = fabrica.entrar(app_module, 'coord.prev@trino.com')
    assert coord.get(f'/preventiva/locais/{outro}').status_code in (403, 404)


# ── D8: o prazo para em "Aguardando" ──────────────────────────────────────

def _chamado(app_module, cena, prioridade='alta', iniciar=True):
    from app import User, db
    from facilities.chamados import servico
    coord = db.session.get(User, cena['coord'])
    ch = servico.abrir(coord, cena['local'], 'Torneira pingando', prioridade=prioridade)
    if iniciar:
        servico.executar(coord, ch, 'iniciar', {})
    db.session.commit()
    return ch


def test_aguardando_para_o_relogio_e_retomar_empurra_o_prazo(app_module, cena):
    from app import User, db
    from facilities.chamados import servico
    with app_module.app.app_context():
        ch = _chamado(app_module, cena)
        prazo = ch.prazo
        coord = db.session.get(User, cena['coord'])
        servico.executar(coord, ch, 'aguardar', {'texto': 'Esperando a peça'})
        db.session.commit()
        assert ch.pausado_desde is not None
        # Três horas parado não contam como atraso, mesmo depois do prazo.
        ch.pausado_desde -= timedelta(hours=3)
        assert not ch.atrasado(prazo + timedelta(hours=1))
        servico.executar(coord, ch, 'retomar', {'texto': 'A peça chegou'})
        db.session.commit()
        assert ch.pausado_desde is None
        assert 3 * 3600 <= ch.pausa_total_seg < 3 * 3600 + 60
        assert timedelta(hours=3) <= ch.prazo - prazo < timedelta(hours=3, minutes=1)
        # Trocar a prioridade recalcula da abertura, mas a pausa continua valendo.
        servico.executar(coord, ch, 'prioridade', {'prioridade': 'media'})
        assert ch.prazo == ch.aberto_em + timedelta(hours=72, seconds=ch.pausa_total_seg)


def test_resolver_direto_do_aguardando_fecha_a_pausa(app_module, cena):
    from app import User, db
    from facilities.chamados import servico
    with app_module.app.app_context():
        ch = _chamado(app_module, cena)
        coord = db.session.get(User, cena['coord'])
        servico.executar(coord, ch, 'aguardar', {'texto': 'Terceiro'})
        ch.pausado_desde -= timedelta(hours=1)
        servico.executar(coord, ch, 'resolver', {'texto': 'Trocado o reparo'})
        db.session.commit()
        assert ch.pausado_desde is None and ch.pausa_total_seg >= 3600


# ── D9: régua de prazo por cliente ────────────────────────────────────────

def test_regua_do_cliente_vale_para_os_novos_e_nao_muda_os_antigos(app_module, cena):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        antigo = _chamado(app_module, cena, 'alta')
        prazo_antigo = antigo.prazo
        assert prazo_antigo - antigo.aberto_em == timedelta(hours=24)
        cli = db.session.get(Contratante, cena['cliente'])
        cad.salvar_contratante(cli, {'nome': cli.nome, 'empresa_id': cli.empresa_id,
                                     'centro_custo': cli.centro_custo, 'regua_alta': '8',
                                     'regua_urgente': ''}, None)
        db.session.commit()
        novo = _chamado(app_module, cena, 'alta')
        assert novo.prazo - novo.aberto_em == timedelta(hours=8)
        urgente = _chamado(app_module, cena, 'urgente')
        assert urgente.prazo - urgente.aberto_em == timedelta(hours=4)   # padrão
        db.session.refresh(antigo)
        assert antigo.prazo == prazo_antigo


def test_regua_recusa_valor_fora_da_faixa(app_module, cena):
    from app import db
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Contratante
    with app_module.app.app_context():
        cli = db.session.get(Contratante, cena['cliente'])
        with pytest.raises(Exception, match='hora'):
            cad.salvar_contratante(cli, {'nome': cli.nome, 'empresa_id': cli.empresa_id,
                                         'centro_custo': cli.centro_custo,
                                         'regua_alta': '0'}, None)


# ── Avisos de prazo ───────────────────────────────────────────────────────

def test_avisa_antes_e_no_vencimento_uma_vez_so(app_module, cena):
    from app import User, db
    from facilities.chamados import servico
    with app_module.app.app_context():
        enviados = []
        app_module.app.extensions['facilities_push'] = lambda insc, carga: enviados.append(carga) or 201
        ch = _chamado(app_module, cena, 'urgente')          # 4 h → avisa 1 h antes
        servico.executar(db.session.get(User, cena['coord']), ch, 'atribuir',
                         {'responsavel_id': str(cena['caio'])})
        db.session.commit()
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=2)) == 0
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=3, minutes=10)) == 1
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=3, minutes=20)) == 0
        assert any(t.startswith(f'{ch.numero} · Vence às') for t in _avisos(cena['caio']))
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=5)) == 1
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=6)) == 0
        db.session.commit()
        assert any('Prazo vencido' in t for t in _avisos(cena['coord']))


def test_aguardando_nao_avisa_e_chamado_velho_nao_dispara(app_module, cena):
    from app import User, db
    from facilities.chamados import servico
    with app_module.app.app_context():
        ch = _chamado(app_module, cena, 'urgente')
        servico.executar(db.session.get(User, cena['coord']), ch, 'aguardar',
                         {'texto': 'Peça'})
        db.session.commit()
        assert servico.avisar_prazos(ch.aberto_em + timedelta(hours=5)) == 0
        velho = _chamado(app_module, cena, 'urgente')
        antes = len(_avisos(cena['coord']))
        assert servico.avisar_prazos(velho.aberto_em + timedelta(days=3)) == 0
        assert velho.aviso_vencido_em is not None
        assert len(_avisos(cena['coord'])) == antes


# ── Painel de demandas ────────────────────────────────────────────────────

def test_painel_junta_chamados_e_preventivas_atrasado_primeiro(app_module, cena):
    from app import db
    from facilities import demandas
    with app_module.app.app_context():
        _ordem(app_module, cena)
        ch = _chamado(app_module, cena, 'urgente')
        # Bem mais vencido que a ordem preventiva (que vence HOJE, numa data
        # fixa): o teste não pode depender da hora em que roda.
        ch.prazo = datetime.utcnow() - timedelta(days=30)
        db.session.commit()
        itens = demandas.demandas([cena['local']])
        assert itens[0]['situacao'] == 'atrasada' and itens[0]['tipo'] == 'chamado'
        assert {'chamado', 'preventiva'} <= {i['tipo'] for i in itens}
    coord = fabrica.entrar(app_module, 'coord.prev@trino.com')
    html = coord.get('/demandas/?tipo=preventiva').get_data(as_text=True)
    assert 'Preventiva: Filtro do secador' in html and 'Torneira' not in html
    fora = fabrica.entrar(app_module, 'fora.prev@trino.com')
    html = fora.get('/demandas/').get_data(as_text=True)
    assert 'Filtro do secador' not in html and 'Torneira' not in html
