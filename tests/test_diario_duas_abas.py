"""A tela do encarregado dividida em duas: Pendências e Passagem de turno.

Era uma página só empilhando DOIS trabalhos diferentes:

* resolver o que o turno passado deixou — que se faz ao CHEGAR, e ao longo
  do dia, conforme as coisas se resolvem;
* preencher a passagem — que se faz ao SAIR.

Com sete pendências abertas, responder uma pergunta do checklist custava
rolar a lista inteira. No celular a página passava de 4.000px.

A divisão segue o que o encarregado de fato faz: RECEBI de um lado,
ENTREGO do outro.

O que se prova aqui:

* as duas abas existem e cada bloco está do lado certo;
* a aba de pendências abre primeiro quando há alguma, e a da passagem
  quando não há — o encarregado chega para saber o que recebeu;
* o contador da aba conta o que existe, e marca em vermelho quando há
  vencida: é o número que ele olha enquanto preenche do outro lado;
* o seletor de contrato/área continua ÚNICO — dividir a tela não pode
  custar escolher o contrato duas vezes.
"""
import json

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo
from facilities.passagem.models import DiarioConfiguracao, DiarioPendencia, DiarioTurno


@pytest.fixture()
def operacao(app_module):
    with app_module.app.app_context():
        from app import db
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Passagem CD',
            turnos_json=json.dumps([{'nome': '1º Turno'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Rua organizada',
                                         'codigo': 'rua'}]),
            tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id)
        db.session.add(cfg)
        db.session.commit()
        return {'cid': cliente.id, 'cfg': cfg.id, 'admin': admin.id}


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


def _pendencia(app_module, operacao, titulo='Devolução 445.221', dias=0):
    from datetime import datetime, timedelta
    from app import db
    p = DiarioPendencia(client_id=operacao['cid'], titulo=titulo,
                        status='aberta', prioridade='media',
                        created_by=operacao['admin'],
                        created_at=datetime.utcnow() - timedelta(days=dias))
    db.session.add(p)
    db.session.commit()
    return p


def _abrir(mestre, operacao):
    r = mestre.get(f"/passagem-de-turno/turno?client_id={operacao['cid']}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ── As duas abas existem, e cada coisa está do seu lado ──────────────────

def test_as_duas_abas_aparecem(app_module, mestre, operacao):
    with app_module.app.app_context():
        _pendencia(app_module, operacao)
    corpo = _abrir(mestre, operacao)
    assert 'data-painel="pendencias"' in corpo
    assert 'data-painel="passagem"' in corpo
    assert 'Passagem de turno' in corpo


def test_com_pendencia_abre_em_pendencias(app_module, mestre, operacao):
    """Ele chega ao turno para saber o que recebeu."""
    with app_module.app.app_context():
        _pendencia(app_module, operacao)
    corpo = _abrir(mestre, operacao)
    # O painel de pendências visível; o da passagem, escondido.
    assert '<div class="dt-painel" data-painel="pendencias" >' in corpo \
        or '<div class="dt-painel" data-painel="pendencias">' in corpo
    assert 'data-painel="passagem" hidden' in corpo


def test_sem_pendencia_abre_na_passagem(app_module, mestre, operacao):
    """Não recebeu nada: a primeira coisa a fazer é preencher."""
    corpo = _abrir(mestre, operacao)
    assert 'data-painel="pendencias" hidden' in corpo
    assert 'Nenhuma pendência aberta neste contrato' in corpo


def test_o_contador_da_aba_conta_o_que_existe(app_module, mestre, operacao):
    with app_module.app.app_context():
        for i in range(3):
            _pendencia(app_module, operacao, titulo=f'Pendência {i}')
    corpo = _abrir(mestre, operacao)
    assert '<span class="dt-aba-n ">3</span>' in corpo \
        or '<span class="dt-aba-n">3</span>' in corpo


def test_pendencia_vencida_pinta_o_contador(app_module, mestre, operacao):
    """A aba precisa gritar mesmo com o encarregado do outro lado."""
    with app_module.app.app_context():
        _pendencia(app_module, operacao, dias=5)
    corpo = _abrir(mestre, operacao)
    assert 'dt-aba-n ruim' in corpo


def test_o_formulario_fica_na_aba_da_passagem(app_module, mestre, operacao):
    """O que se ENTREGA: perguntas, observação, ocorrência, pendência nova."""
    corpo = _abrir(mestre, operacao)
    pos_aba = corpo.index('data-painel="passagem"')
    for marca in ('Perguntas deste contrato', 'Observações do turno',
                  'Ocorrências', 'Pendências para o próximo turno',
                  'Encerrar turno'):
        assert corpo.index(marca) > pos_aba, f'{marca} caiu na aba errada'


def test_o_que_recebi_fica_na_aba_das_pendencias(app_module, mestre, operacao):
    """O turno anterior e as pendências são a mesma coisa: o que chegou."""
    with app_module.app.app_context():
        from app import db
        _pendencia(app_module, operacao)
        t = DiarioTurno(client_id=operacao['cid'],
                        configuracao_id=operacao['cfg'],
                        data_turno=tempo.hoje(), turno='1º Turno',
                        status='encerrado', dados_json='{}',
                        observacao='Rua 3 ficou bagunçada.',
                        created_by=operacao['admin'])
        db.session.add(t)
        db.session.commit()
    corpo = _abrir(mestre, operacao)
    # A fatia sai do PAINEL, não do botão da aba — os dois carregam o mesmo
    # `data-painel`, e recortar pelo botão pegava só o cabeçalho.
    ini = corpo.index('<div class="dt-painel" data-painel="pendencias"')
    fim = corpo.index('<div class="dt-painel" data-painel="passagem"', ini)
    trecho = corpo[ini:fim]
    assert 'O turno anterior deixou' in trecho
    assert 'Pendências em aberto' in trecho


def test_o_seletor_de_contrato_continua_unico(app_module, mestre, operacao):
    """Dividir a tela não pode custar escolher o contrato duas vezes."""
    with app_module.app.app_context():
        _pendencia(app_module, operacao)
    corpo = _abrir(mestre, operacao)
    # (a área só é renderizada em contrato que tem áreas — este não tem)
    assert corpo.count('id="diario-client"') == 1
    assert corpo.count('id="diario-shift"') == 1
    assert corpo.count('id="diario-config"') == 1
    # E o cabeçalho fica FORA das duas abas: ele vale para as duas.
    assert corpo.index('id="diario-client"') < corpo.index('class="dt-abas"')
