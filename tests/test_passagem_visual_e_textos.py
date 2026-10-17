"""Passagem de Turno: o que a tela DIZ — nomes, caminhos, plurais e botões.

Nada aqui muda conta nenhuma. O que se prova é o que quem usa lê:

* O CAMINHO NO TOPO diz onde a pessoa está. Todas as telas da passagem (e a
  Torre) mostravam "Dashboard", o padrão do ``base.html`` — e no celular é a
  única palavra que sobra na barra.
* O NOME ANTIGO SAIU. "Diário Operacional" ainda aparecia no sobretítulo da
  Nova passagem, nas duas faixas do PDF e no nome do arquivo baixado (que
  ainda saía "CD-Eletro---PB", com hífens repetidos).
* O PDF É DO QUE ESTÁ NA TELA. Com uma área escolhida, "Baixar PDF" baixava
  o relatório do contrato inteiro.
* O BOTÃO SÓ APARECE PARA QUEM PODE USÁ-LO. O Visualizador lê a Passagem e
  abre Plano de Ação: via "Abrir PDCA" e "marcar resolvida", clicava e
  recebia 403.
* O SISTEMA SABE CONTAR. "1 turno(s) encerrado(s)", "0 dia(s)", "há 0h",
  "slas críticos": cada um, sozinho, é pequeno; juntos dizem ao leitor que
  ninguém revisou a tela.

O que é CSS/JS (menu do sino, cartões do relatório no celular, botão
"Remover", a fila sem internet) foi conferido renderizando as telas em
390×844; os testes de texto no fim deste arquivo só seguram as decisões que
uma edição distraída desfaria.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Cenário ──────────────────────────────────────────────────────────────

@pytest.fixture()
def contrato(app_module):
    """Um contrato com um modelo de uma rotina obrigatória e dois turnos."""
    from facilities.passagem.models import DiarioConfiguracao

    with app_module.app.app_context():
        cliente = app_module.Client.query.first()
        admin = app_module.User.query.filter_by(
            email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Expedição — passagem',
            turnos_json=json.dumps([{'nome': 'T1'}, {'nome': 'T2'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Conferência da doca',
                                         'codigo': 'doca',
                                         'obrigatorio': True}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'client_id': cliente.id, 'config_id': cfg.id,
                'user_id': admin.id, 'cliente': cliente.name}


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


@pytest.fixture()
def visualizador(app_module, contrato):
    """A diretoria: lê tudo, trabalha nas Ferramentas, não grava na Passagem."""
    with app_module.app.app_context():
        from app import Client, db
        u = app_module.User.query.filter_by(email='diretoria.vis@trino.com').first()
        if u is None:
            u = app_module.User(name='Diretoria Visualizadora',
                                email='diretoria.vis@trino.com')
            db.session.add(u)
        u.role = 'visualizador'
        u.is_active = True
        u.is_deleted = False
        u.must_change_password = False
        u.permissions_json = '[]'
        u.set_password('senha12345')
        db.session.flush()
        u.clients = [Client.query.get(contrato['client_id'])]
        db.session.commit()
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'diretoria.vis@trino.com',
                           'password': 'senha12345'})
    return c


def _turno(app_module, contrato, dia, nome='T1', cumpriu=True,
           status='encerrado'):
    from facilities.passagem.models import DiarioTurno
    t = DiarioTurno(
        client_id=contrato['client_id'], configuracao_id=contrato['config_id'],
        data_turno=dia, turno=nome, status=status,
        dados_json=json.dumps({'atividade:doca': {'concluido': cumpriu}}),
        created_by=contrato['user_id'],
        submitted_at=datetime.utcnow() if status == 'encerrado' else None)
    app_module.db.session.add(t)
    app_module.db.session.flush()
    return t


def _pendencia_da_gestao(app_module, contrato, titulo, criada_ha=timedelta(0),
                         prioridade='media', resolvida=False):
    """Pendência aberta pela gestão (sem turno de origem)."""
    from facilities.passagem.models import DiarioPendencia
    criada = datetime.utcnow() - criada_ha
    p = DiarioPendencia(
        client_id=contrato['client_id'], titulo=titulo, prioridade=prioridade,
        status='resolvida' if resolvida else 'aberta',
        created_by=contrato['user_id'], created_at=criada,
        resolved_at=datetime.utcnow() if resolvida else None,
        resolved_by=contrato['user_id'] if resolvida else None,
        resolucao='Trocada a mangueira.' if resolvida else None)
    app_module.db.session.add(p)
    app_module.db.session.flush()
    return p


def _passou_por(app_module, pendencia, turnos):
    """A trilha: a pendência atravessou estes turnos."""
    from facilities.passagem.models import DiarioPendenciaEvento
    for t in turnos:
        app_module.db.session.add(DiarioPendenciaEvento(
            pendencia_id=pendencia.id, turno_id=t.id, tipo='recebida',
            created_by=pendencia.created_by))
    app_module.db.session.flush()


def _codigo_js(nome):
    """O JS sem os comentários de linha — que citam de propósito o texto
    antigo para explicar por que ele saiu."""
    with open(os.path.join(RAIZ, 'facilities', 'static', 'js', nome), encoding='utf-8') as f:
        return '\n'.join(l for l in f.read().splitlines()
                         if not l.lstrip().startswith('//'))


def _ativo(html):
    """O texto do item ATIVO do caminho no topo."""
    m = re.search(r'<li class="breadcrumb-item active">(.*?)</li>', html, re.S)
    return ' '.join(m.group(1).split()) if m else None


# ── O caminho no topo ────────────────────────────────────────────────────

def test_o_painel_diz_passagem_de_turno_no_caminho(mestre, contrato):
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert _ativo(html) == 'Passagem de Turno'


def test_a_nova_passagem_diz_nova_passagem(mestre, contrato):
    html = mestre.get(f'/passagem-de-turno/turno?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert _ativo(html) == 'Nova passagem'
    # E o nível de cima volta para o painel do MESMO contrato.
    assert (f'href="/passagem-de-turno/?client_id={contrato["client_id"]}">'
            'Passagem de Turno</a>') in html


def test_a_passagem_aberta_diz_passagem_de_turno(app_module, mestre, contrato):
    with app_module.app.app_context():
        t = _turno(app_module, contrato, tempo.hoje())
        app_module.db.session.commit()
        tid = t.id
    html = mestre.get(f'/passagem-de-turno/turno/{tid}').get_data(as_text=True)
    assert _ativo(html) == 'Passagem de turno'


def test_o_relatorio_diz_relatorio_mensal(mestre, contrato):
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["client_id"]}').get_data(as_text=True)
    assert _ativo(html) == 'Relatório mensal'
    # O título da aba do navegador também larga o nome antigo.
    assert 'Mensal do Diário' not in html


def test_a_configuracao_diz_modelo_de_passagem(mestre, contrato):
    html = mestre.get('/passagem-de-turno/configuracao'
                      f'?client_id={contrato["client_id"]}').get_data(as_text=True)
    assert _ativo(html) == 'Modelo de passagem'


# ── O nome antigo ────────────────────────────────────────────────────────

def test_a_nova_passagem_nao_usa_mais_o_nome_antigo(mestre, contrato):
    html = mestre.get(f'/passagem-de-turno/turno?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert 'PASSAGEM DE TURNO</div>' in html
    assert 'DIÁRIO OPERACIONAL' not in html


@pytest.fixture()
def contrato_cd_eletro(app_module, contrato):
    """O contrato com o nome que produzia "CD-Eletro---PB" no arquivo.

    O cliente é do seed (sobrevive entre testes): o nome volta ao fim.
    """
    with app_module.app.app_context():
        c = app_module.Client.query.get(contrato['client_id'])
        antigo = c.name
        c.name = 'CD Eletro - PB'
        app_module.db.session.commit()
    yield contrato
    with app_module.app.app_context():
        c = app_module.Client.query.get(contrato['client_id'])
        c.name = antigo
        app_module.db.session.commit()


def test_o_pdf_baixa_com_o_nome_novo_e_sem_hifen_repetido(mestre, contrato_cd_eletro):
    r = mestre.get('/passagem-de-turno/relatorio-mensal'
                   f'?client_id={contrato_cd_eletro["client_id"]}'
                   '&mes=10&ano=2026&format=pdf')
    assert r.status_code == 200
    disp = r.headers.get('Content-Disposition', '')
    assert 'Passagem-de-Turno-CD-Eletro-PB-10-2026.pdf' in disp
    assert '--' not in disp and 'Diario' not in disp


def test_o_pdf_com_area_leva_a_area_no_nome(app_module, mestre, contrato_cd_eletro):
    from facilities.passagem.models import DiarioArea
    with app_module.app.app_context():
        a = DiarioArea(client_id=contrato_cd_eletro['client_id'],
                       nome='Doca 2 - Norte', ativo=True)
        app_module.db.session.add(a)
        app_module.db.session.commit()
        area_id = a.id
    r = mestre.get('/passagem-de-turno/relatorio-mensal'
                   f'?client_id={contrato_cd_eletro["client_id"]}'
                   f'&area_id={area_id}&mes=10&ano=2026&format=pdf')
    disp = r.headers.get('Content-Disposition', '')
    assert 'Passagem-de-Turno-CD-Eletro-PB-Doca-2-Norte-10-2026.pdf' in disp


def test_o_pdf_traz_passagem_de_turno_nas_faixas(app_module, mestre, contrato):
    from pypdf import PdfReader
    with app_module.app.app_context():
        _turno(app_module, contrato, tempo.hoje())
        app_module.db.session.commit()
    r = mestre.get('/passagem-de-turno/relatorio-mensal'
                   f'?client_id={contrato["client_id"]}&format=pdf')
    texto = '\n'.join((p.extract_text() or '')
                      for p in PdfReader(io.BytesIO(r.data)).pages)
    assert 'PASSAGEM DE TURNO' in texto
    # Capa e faixa do topo das páginas: as duas largaram o nome antigo.
    assert 'PASSAGEM DE TURNO · RELATÓRIO EXECUTIVO MENSAL' in texto
    assert 'OPERACIONAL' not in texto


# ── O PDF é do que está na tela ──────────────────────────────────────────

def _href_do_pdf(html):
    m = re.search(r'<a class="btn btn-primary"\s+href="([^"]+)">\s*'
                  r'<i class="bi bi-file-earmark-pdf"></i> Baixar PDF', html)
    assert m, 'botão Baixar PDF não encontrado'
    return m.group(1).replace('&amp;', '&')


def test_baixar_pdf_leva_a_area_escolhida(app_module, mestre, contrato):
    from facilities.passagem.models import DiarioArea
    with app_module.app.app_context():
        a = DiarioArea(client_id=contrato['client_id'], nome='Expedição',
                       ativo=True)
        app_module.db.session.add(a)
        app_module.db.session.commit()
        area_id = a.id
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["client_id"]}&area_id={area_id}'
                      ).get_data(as_text=True)
    href = _href_do_pdf(html)
    assert 'format=pdf' in href
    assert f'area_id={area_id}' in href


def test_baixar_pdf_sem_area_nao_inventa_area(app_module, mestre, contrato):
    from facilities.passagem.models import DiarioArea
    with app_module.app.app_context():
        app_module.db.session.add(DiarioArea(client_id=contrato['client_id'],
                                             nome='Expedição', ativo=True))
        app_module.db.session.commit()
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["client_id"]}').get_data(as_text=True)
    assert 'area_id' not in _href_do_pdf(html)


# ── O botão só aparece para quem pode usá-lo ─────────────────────────────

@pytest.fixture()
def painel_com_acao(app_module, contrato):
    """Uma ocorrência no período e uma pendência de prioridade alta."""
    from facilities.passagem.models import DiarioOcorrencia
    with app_module.app.app_context():
        t = _turno(app_module, contrato, tempo.hoje())
        app_module.db.session.add(DiarioOcorrencia(
            client_id=contrato['client_id'], turno_id=t.id, tipo='Avaria',
            descricao='Palete tombado na doca 3.', status='aberta',
            created_by=contrato['user_id']))
        p = _pendencia_da_gestao(app_module, contrato, 'Doca 3 interditada',
                                 prioridade='alta')
        app_module.db.session.commit()
        return {'pendencia_id': p.id}


def test_o_visualizador_nao_ve_abrir_pdca_nem_marcar_resolvida(
        visualizador, contrato, painel_com_acao):
    r = visualizador.get(f'/passagem-de-turno/?client_id={contrato["client_id"]}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # O painel abre e mostra o que há para ver...
    assert 'Palete tombado na doca 3.' in html
    assert 'Doca 3 interditada' in html
    # ...mas não oferece as duas ações que dariam 403 no clique.
    assert 'Abrir PDCA' not in html
    assert 'marcar resolvida' not in html


def test_e_o_403_que_o_botao_escondia_e_real(visualizador, painel_com_acao):
    """A razão de esconder: a rota recusa o Visualizador."""
    r = visualizador.post(
        f'/passagem-de-turno/api/pendencias/{painel_com_acao["pendencia_id"]}/resolver',
        json={'resolucao': 'Feito.'})
    assert r.status_code == 403


def test_o_master_continua_vendo_as_duas_acoes(mestre, contrato, painel_com_acao):
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert 'Abrir PDCA' in html
    assert 'marcar resolvida' in html


# ── O painel sabe contar ─────────────────────────────────────────────────

def test_raio_x_mostra_uma_casa_decimal(app_module, mestre, contrato):
    """18 de 19 é 94,7% — abaixo da meta. Arredondado, virava "95%"."""
    hoje = tempo.hoje()
    with app_module.app.app_context():
        for i in range(19):
            _turno(app_module, contrato, hoje - timedelta(days=i),
                   cumpriu=(i != 0))
        app_module.db.session.commit()
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["client_id"]}'
                      '&periodo=30d').get_data(as_text=True)
    celulas = re.findall(r'<div class="dop-rot-pct">\s*(.*?)\s*<', html, re.S)
    assert celulas == ['94,7%']


def test_pendencia_que_acabou_de_entrar_diz_agora(app_module, mestre, contrato):
    with app_module.app.app_context():
        _pendencia_da_gestao(app_module, contrato, 'Empilhadeira 4 parada',
                             prioridade='alta')
        app_module.db.session.commit()
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert 'há 0h' not in html
    assert re.search(r'<span class="dop-tag alerta">\s*agora</span>', html)


def test_o_painel_conta_no_singular_quando_e_um(app_module, mestre, contrato):
    from facilities.passagem.models import DiarioOcorrencia
    with app_module.app.app_context():
        t = _turno(app_module, contrato, tempo.hoje())
        app_module.db.session.add(DiarioOcorrencia(
            client_id=contrato['client_id'], turno_id=t.id, tipo='Avaria',
            descricao='Uma só.', status='aberta', created_by=contrato['user_id']))
        app_module.db.session.commit()
    html = ' '.join(mestre.get(
        f'/passagem-de-turno/?client_id={contrato["client_id"]}&periodo=hoje'
    ).get_data(as_text=True).split())
    assert '<strong>1</strong> turno encerrado no recorte' in html
    assert '1 ocorrência ÷ 1 turno' in html
    assert '1 de 1 atividade ·' in html
    assert '(s)' not in html.split('id="dopHero"')[1].split('Pareto')[0]


# ── O relatório sabe contar ──────────────────────────────────────────────

_PASSOU = re.compile(r'passou por (\d+) (turnos?)\b')
_PARADA = re.compile(r'data-rot="Parada">([^<]*)</td>')


def test_o_relatorio_escreve_os_plurais_por_extenso(app_module, mestre, contrato):
    hoje = tempo.hoje()
    with app_module.app.app_context():
        turnos = [_turno(app_module, contrato, hoje, nome)
                  for nome in ('T1', 'T2')]
        # Uma que atravessou dois turnos e uma que atravessou um só.
        velha = _pendencia_da_gestao(app_module, contrato, 'Rampa 2 quebrada',
                                     criada_ha=timedelta(days=5))
        _passou_por(app_module, velha, turnos)
        nova = _pendencia_da_gestao(app_module, contrato, 'Etiqueta faltando')
        _passou_por(app_module, nova, turnos[:1])
        app_module.db.session.commit()
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["client_id"]}').get_data(as_text=True)

    assert 'turno(s)' not in html and 'dia(s)' not in html
    passou = _PASSOU.findall(html)
    assert passou, 'nenhuma linha "passou por N turnos" no relatório'
    for n, palavra in passou:
        assert palavra == ('turno' if int(n) == 1 else 'turnos'), (n, palavra)

    paradas = [' '.join(p.split()) for p in _PARADA.findall(html)]
    assert len(paradas) == 2
    for p in paradas:
        m = re.fullmatch(r'há (\d+) (dias?)', p)
        assert p == 'hoje' or (m and m.group(2) == ('dia' if m.group(1) == '1'
                                                    else 'dias')), p
    # A aberta agora não é "0 dia(s)": é de hoje.
    assert 'hoje' in paradas
    assert any(p.startswith('há ') and p.endswith(' dias') for p in paradas)


def test_celulas_compostas_do_bloco_3_empilham_no_celular(app_module, mestre,
                                                          contrato):
    """Pendência e Turno têm vários filhos; no cartão do celular eles
    empilham (`cel-pilha`) em vez de virar colunas espremidas."""
    with app_module.app.app_context():
        _pendencia_da_gestao(app_module, contrato, 'Rampa 2 quebrada')
        app_module.db.session.commit()
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["client_id"]}').get_data(as_text=True)
    assert 'class="small cel-pilha" data-rot="Pendência"' in html
    assert 'class="small cel-pilha" data-rot="Turno"' in html
    css = open(os.path.join(RAIZ, 'facilities', 'static', 'css', 'app.css'),
               encoding='utf-8').read()
    assert '.tab-cartao td.cel-pilha { display: block; }' in css


# ── Configuração ─────────────────────────────────────────────────────────

def test_a_lista_de_modelos_escreve_os_plurais(mestre, contrato):
    html = ' '.join(mestre.get('/passagem-de-turno/configuracao'
                               f'?client_id={contrato["client_id"]}'
                               ).get_data(as_text=True).split())
    assert '1 pergunta · 2 turnos · 0 turnos lançados' in html
    assert 'data-usos="0"' in html
    assert '(s)' not in html.split('id="cfg-lista"')[1].split('</div> </div>')[0]


def test_o_aviso_de_uso_le_o_numero_do_atributo_e_nao_do_texto():
    """O JS pescava "N turno(s) lançado" do texto da linha com regex — o
    plural certo quebraria o aviso sem ninguém ver."""
    js = _codigo_js('diario_config.js')
    assert 'dataset.usos' in js
    assert r'turno\(s\) lançado' not in js
    assert 'modelo(s)' not in js
    assert "'<span class=\"ar-acoes\">'" in js


# ── Torre de Comando ─────────────────────────────────────────────────────


# ── Sino ─────────────────────────────────────────────────────────────────


# ── A nova passagem: nome de quem anota, contador e o "×" ────────────────

def test_a_passagem_entrega_o_nome_de_quem_anota(mestre, contrato):
    html = mestre.get(f'/passagem-de-turno/turno?client_id={contrato["client_id"]}'
                      ).get_data(as_text=True)
    assert re.search(r'id="diario-turno-app"[^>]*data-usuario="[^"]+"', html, re.S)


def test_o_js_da_passagem_mostra_nome_reconta_e_remove_sem_caixa_vermelha():
    js = _codigo_js('diario_operacional.js')
    # "— agora" ganhou o nome de quem anotou.
    assert 'raiz.dataset.usuario' in js
    # O cabeçalho "Pendências em aberto N" também é recontado.
    reconta = js[js.index('function recontarPendencias'):]
    reconta = reconta[:reconta.index('function resolverPendencia')]
    assert 'contadorDoCartao()' in reconta
    # O "×" virou o link "Remover" no celular, nas duas listas.
    assert js.count("botaoRemover('pending-row')") == 1
    assert js.count("botaoRemover('occurrence-row')") == 1
    assert '<span class="dt-remover-txt">Remover</span>' in js
    css = open(os.path.join(RAIZ, 'facilities', 'static', 'css', 'app.css'),
               encoding='utf-8').read()
    assert '.dt-linha-remover .dt-remover-txt { display: inline; }' in css


# ── Sem internet: o que a tela promete ───────────────────────────────────

def test_a_caixa_de_guardado_nao_promete_envio_com_a_tela_fechada():
    """Não há envio em segundo plano: o SW não tem 'sync', e a fila só roda
    com o sistema aberto. "Pode fechar a tela" era promessa falsa."""
    sw = open(os.path.join(RAIZ, 'facilities', 'static', 'pwa', 'sw.js'), encoding='utf-8').read()
    assert "'sync'" not in sw          # se um dia tiver, este texto pode mudar
    js = _codigo_js('diario_operacional.js')
    assert 'pode fechar a tela' not in js
    assert 'com o sistema aberto neste' in js
    # E a caixa vira "Enviado" quando a fila confirma.
    assert "addEventListener('trino-fila:enviado'" in js


def test_a_fila_separa_falta_de_rede_de_falta_de_sessao():
    """Sem sinal, o item dizia "Aguardando você entrar no sistema"."""
    js = _codigo_js('fila-offline.js')
    sessao = js[js.index('function sessao()'):]
    sessao = sessao[:sessao.index('function avisarEnviado')]
    # Falha de rede e resposta que não é o JSON do servidor → 'rede'.
    assert sessao.count("{situacao: 'rede'}") >= 3
    assert "{situacao: 'sessao'}" in sessao
    fila = js[js.index('function enviarPendentes'):]
    assert "quem.situacao === 'rede'" in fila
    assert "new CustomEvent('trino-fila:enviado'" in js
