"""Chamados com dois pedidos AO MESMO TEMPO — o que só aparece em corrida.

Roda só contra Postgres (``TEST_DATABASE_URL``, como no CI): é lá que valem
a trava de linha (``SELECT … FOR NO KEY UPDATE``) e o índice único parcial
de origem. O SQLite dos testes locais põe toda escrita em fila e esconderia
justamente a corrida que estes testes provocam.

Cada cenário roda algumas rodadas: sem a correção, a corrida aparecia em
praticamente todas (dois "resolvido", duas OS da mesma ocorrência); com ela,
o resultado é um só em todas.
"""
import os
import threading

import pytest

from facilities.chamados.models import Chamado, ChamadoEvento
from tests.test_chamados import _abrir, _acao, _avisos, _entrar, cena  # noqa: F401

pytestmark = pytest.mark.skipif(
    'postgres' not in os.environ.get('TEST_DATABASE_URL', ''),
    reason='corrida de verdade só no Postgres (TEST_DATABASE_URL)')

RODADAS = 4


def _ao_mesmo_tempo(*pedidos):
    """Solta os pedidos juntos (cada um no seu cliente/sessão) e devolve as
    respostas na mesma ordem."""
    barreira = threading.Barrier(len(pedidos))
    saida = [None] * len(pedidos)

    def rodar(i, pedido):
        barreira.wait(10)
        saida[i] = pedido()

    linhas = [threading.Thread(target=rodar, args=(i, p)) for i, p in enumerate(pedidos)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join(60)
    assert all(r is not None for r in saida), 'um dos pedidos não voltou'
    return saida


def _eventos(ch_id, *tipos):
    return ChamadoEvento.query.filter(ChamadoEvento.chamado_id == ch_id,
                                      ChamadoEvento.tipo.in_(tipos)).count()


def _em_atendimento(app_module, cena, enc, gestora, tec, titulo):  # noqa: F811
    # Título diferente a cada rodada: o mesmo título em segundos é tratado
    # como o formulário enviado duas vezes (devolve o chamado anterior).
    _abrir(enc, cena, titulo=titulo)
    with app_module.app.app_context():
        ch_id = Chamado.query.order_by(Chamado.id.desc()).first().id
    _acao(gestora, ch_id, 'atribuir', responsavel_id=cena['tec'])
    _acao(tec, ch_id, 'iniciar')
    return ch_id


def test_duplo_clique_em_resolver_grava_um_resolvido(app_module, cena):  # noqa: F811
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    tec_a = _entrar(app_module, 'tec.ch@trino.com')
    tec_b = _entrar(app_module, 'tec.ch@trino.com')
    for i in range(RODADAS):
        ch_id = _em_atendimento(app_module, cena, enc, gestora, tec_a, f'Torneira {i}')
        respostas = _ao_mesmo_tempo(
            lambda: _acao(tec_a, ch_id, 'resolver', texto='Troquei o reparo'),
            lambda: _acao(tec_b, ch_id, 'resolver', texto='Troquei o reparo'))
        assert [r.status_code for r in respostas] == [302, 302]
        with app_module.app.app_context():
            assert _eventos(ch_id, 'resolvido') == 1
    with app_module.app.app_context():
        assert sum('resolvido' in t for t in _avisos(cena['enc'])) == RODADAS


def test_cancelar_e_resolver_ao_mesmo_tempo_so_um_vale(app_module, cena):  # noqa: F811
    """O "resolver" que leu o chamado antes do cancelamento não pode
    ressuscitá-lo; e o cancelamento não entra em chamado já resolvido."""
    from app import db
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    gestora_b = _entrar(app_module, 'gestora.ch@trino.com')
    tec = _entrar(app_module, 'tec.ch@trino.com')
    for i in range(RODADAS):
        ch_id = _em_atendimento(app_module, cena, enc, gestora, tec, f'Lâmpada {i}')
        _ao_mesmo_tempo(
            lambda: _acao(gestora_b, ch_id, 'cancelar', texto='Duplicado'),
            lambda: _acao(tec, ch_id, 'resolver', texto='Feito'))
        with app_module.app.app_context():
            ch = db.session.get(Chamado, ch_id)
            assert _eventos(ch_id, 'resolvido', 'cancelado') == 1
            assert (ch.status == 'cancelado') == (ch.cancelado_em is not None)


def test_comentario_enviado_duas_vezes_ao_mesmo_tempo_entra_uma_vez(app_module, cena):  # noqa: F811
    enc = _entrar(app_module, 'enc.ch@trino.com')
    a = _entrar(app_module, 'gestora.ch@trino.com')
    b = _entrar(app_module, 'gestora.ch@trino.com')
    for i in range(RODADAS):
        _abrir(enc, cena, titulo=f'Comentário {i}')
        with app_module.app.app_context():
            ch_id = Chamado.query.order_by(Chamado.id.desc()).first().id
        _ao_mesmo_tempo(lambda: _acao(a, ch_id, 'comentar', texto='Vou amanhã'),
                        lambda: _acao(b, ch_id, 'comentar', texto='Vou amanhã'))
        with app_module.app.app_context():
            assert _eventos(ch_id, 'comentario') == 1


def test_abrir_chamado_enviado_duas_vezes_ao_mesmo_tempo_abre_uma_os(app_module, cena):  # noqa: F811
    a = _entrar(app_module, 'enc.ch@trino.com')
    b = _entrar(app_module, 'enc.ch@trino.com')
    for i in range(RODADAS):
        titulo = f'Porta travada {i}'
        respostas = _ao_mesmo_tempo(lambda: _abrir(a, cena, titulo=titulo),
                                    lambda: _abrir(b, cena, titulo=titulo))
        assert respostas[0].headers['Location'] == respostas[1].headers['Location']
        with app_module.app.app_context():
            assert Chamado.query.filter_by(titulo=titulo).count() == 1


def test_dois_cliques_na_mesma_ocorrencia_abrem_uma_os(app_module, cena):  # noqa: F811
    from app import db
    from facilities.passagem.models import DiarioOcorrencia
    a = _entrar(app_module, 'gestora.ch@trino.com')
    b = _entrar(app_module, 'enc.ch@trino.com')
    for i in range(RODADAS):
        with app_module.app.app_context():
            o = DiarioOcorrencia(client_id=cena['c1'], tipo='Vazamento',
                                 descricao=f'Pia {i}', created_by=cena['enc'])
            db.session.add(o)
            db.session.commit()
            oid = o.id
        url = f'/passagem-de-turno/api/ocorrencias/{oid}/chamado'
        respostas = _ao_mesmo_tempo(lambda: a.post(url), lambda: b.post(url))
        assert sorted(r.status_code for r in respostas) == [200, 201], \
            [r.get_data(as_text=True) for r in respostas]
        assert respostas[0].get_json()['id'] == respostas[1].get_json()['id']
        with app_module.app.app_context():
            assert Chamado.query.filter_by(origem='ocorrencia', origem_id=oid).count() == 1
