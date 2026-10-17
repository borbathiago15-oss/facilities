"""Passagem de Turno com a cara e a língua do Facilities.

A Passagem veio do Trino Intelligence, e vieram junto restos que o piso lê:

* a MARCA antiga — o sobretítulo do painel, o rodapé do relatório mensal e
  o logo da capa do PDF (o arquivo de logo da casa traz o nome do outro
  sistema por extenso);
* o "Master", perfil que no Facilities se chama administrador — e a tela
  mandava o encarregado pedir a ele, sem dizer que o gestor do contrato
  também configura;
* "carteira", palavra de quem já conhece o sistema;
* o cabeçalho da nova passagem que dizia "Encarregado" para qualquer um.

E duas coisas que a pessoa no posto precisa ver:

* a confirmação depois de encerrar (o painel é longo no celular, e nada
  dizia que o encerramento tinha entrado);
* o aviso dos envios guardados ao tocar em "Sair" — que no Facilities é um
  formulário POST, e não o link GET do Trino que a fila conhecia.
"""
import ast
import io
import json
import os
import re
import uuid

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD
from facilities import tempo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALAVRAS_PROIBIDAS = ('Master', 'Trino Intelligence', 'Torre de Comando', 'PDCA',
                      'carteira')


def _js(nome):
    """O JS sem as linhas de comentário — que citam o texto antigo de propósito."""
    with open(os.path.join(RAIZ, 'facilities', 'static', 'js', nome), encoding='utf-8') as f:
        return '\n'.join(l for l in f.read().splitlines()
                         if not l.lstrip().startswith('//'))


@pytest.fixture()
def contrato(app_module):
    from facilities.passagem.models import DiarioConfiguracao
    with app_module.app.app_context():
        cliente = app_module.Client.query.order_by(app_module.Client.id).first()
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').first()
        cfg = DiarioConfiguracao(
            client_id=cliente.id, nome='Limpeza — rotina do turno',
            turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Sanitários abastecidos',
                                         'codigo': 'sanitarios', 'obrigatorio': True}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Vazamento'}]),
            ativo=True, created_by=admin.id)
        app_module.db.session.add(cfg)
        app_module.db.session.commit()
        return {'cid': cliente.id, 'cfg': cfg.id, 'admin': admin.id}


@pytest.fixture()
def mestre(app_module):
    c = app_module.app.test_client()
    c.post('/login', data={'email': 'admin@grupotrino.com.br',
                           'password': TEST_ADMIN_PASSWORD})
    return c


@pytest.fixture()
def pessoas(app_module):
    """Cria gente sob medida; ao fim, desativa (não apaga: turnos e avisos
    lançados por ela ainda apontam para o cadastro até a limpeza do teste)."""
    criadas = []

    def criar(nome, role, client_ids=()):
        with app_module.app.app_context():
            from app import Client, db
            u = app_module.User(name=nome, email=f'{uuid.uuid4().hex[:10]}@marca.test',
                                role=role, must_change_password=False)
            u.set_password('senha12345')
            u.clients = [db.session.get(Client, cid) for cid in client_ids]
            db.session.add(u)
            db.session.commit()
            criadas.append(u.id)
            c = app_module.app.test_client()
            c.post('/login', data={'email': u.email, 'password': 'senha12345'})
            return u.id, c

    yield criar
    with app_module.app.app_context():
        from app import db
        for uid in criadas:
            u = db.session.get(app_module.User, uid)
            u.is_active, u.is_deleted, u.clients = False, True, []
        db.session.commit()


# ── A marca ──────────────────────────────────────────────────────────────

def test_o_painel_nao_tem_mais_a_marca_antiga(mestre, contrato):
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["cid"]}').get_data(as_text=True)
    assert 'intelligence' not in html.lower()
    olho = re.search(r'<div class="pg-olho">([^<]+)</div>', html).group(1)
    assert 'FACILITIES' in olho


def test_o_relatorio_mensal_nao_tem_mais_a_marca_antiga(mestre, contrato):
    html = mestre.get('/passagem-de-turno/relatorio-mensal'
                      f'?client_id={contrato["cid"]}').get_data(as_text=True)
    assert 'intelligence' not in html.lower()
    cabeca = re.search(r'<div class="rm-cabeca">(.*?)<div class="rm-sub text-end">',
                       html, re.S).group(1)
    # A marca é texto — o arquivo de logo traz o nome do outro sistema.
    assert '<img' not in cabeca
    assert 'Grupo Trino · Facilities' in cabeca
    assert 'Grupo Trino · Trino Facilities — documento confidencial' in html


def test_o_pdf_tem_a_marca_em_texto_e_nenhuma_imagem(app_module, mestre, contrato):
    from pypdf import PdfReader
    r = mestre.get('/passagem-de-turno/relatorio-mensal'
                   f'?client_id={contrato["cid"]}&format=pdf')
    assert r.status_code == 200
    leitor = PdfReader(io.BytesIO(r.data))
    texto = '\n'.join((p.extract_text() or '') for p in leitor.pages)
    assert 'GRUPO TRINO · FACILITIES' in texto
    assert 'intelligence' not in texto.lower()
    # O logo da casa é o do outro sistema: o PDF não embute imagem nenhuma.
    assert all(len(p.images) == 0 for p in leitor.pages)


# ── "Master", "carteira" e as outras palavras de dentro ──────────────────

def test_os_textos_da_passagem_nao_falam_master():
    for nome in ('diario_operacional.js', 'diario_config.js', 'fila-offline.js'):
        js = _js(nome)
        for palavra in PALAVRAS_PROIBIDAS:
            assert palavra not in js, (nome, palavra)
    js = _js('diario_operacional.js')
    assert js.count('Peça ao gestor do contrato ou ao administrador') == 2


def test_as_mensagens_de_erro_da_passagem_nao_falam_master():
    """Toda frase que a API devolve com ``jsonify`` — é o que o alerta mostra."""
    caminho = os.path.join(RAIZ, 'facilities', 'passagem', 'rotas.py')
    arvore = ast.parse(open(caminho, encoding='utf-8').read())
    frases = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and getattr(no.func, 'id', '') == 'jsonify':
            for sub in ast.walk(no):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    frases.append(sub.value)
    assert frases
    for frase in frases:
        for palavra in PALAVRAS_PROIBIDAS:
            assert palavra not in frase, frase


def test_quem_nao_tem_contrato_le_uma_frase_sem_carteira(pessoas):
    _uid, gestor = pessoas('Gestora Sem Contrato', 'pleno')
    html = gestor.get('/passagem-de-turno/').get_data(as_text=True)
    assert 'carteira' not in html
    assert 'Peça ao administrador para' in html


# ── O cabeçalho diz o perfil de quem lança ───────────────────────────────

def _rotulo_de(html, nome):
    m = re.search(r'<div class="dt-cab-rot">([^<]*)</div>\s*'
                  r'<div class="dt-cab-val">' + re.escape(nome) + '</div>', html)
    assert m, f'cabeçalho com o nome {nome!r} não encontrado'
    return m.group(1).strip()


def test_o_cabecalho_da_nova_passagem_diz_o_perfil(app_module, mestre, contrato, pessoas):
    html = mestre.get(f'/passagem-de-turno/turno?client_id={contrato["cid"]}').get_data(as_text=True)
    assert _rotulo_de(html, 'Administrador') == 'Administrador'
    for nome, role, rotulo in [('Ana Encarregada', 'encarregado', 'Encarregado'),
                               ('Téo Técnico', 'tecnico', 'Técnico de manutenção'),
                               ('Gil Gestor', 'pleno', 'Gestor')]:
        _uid, c = pessoas(nome, role, [contrato['cid']])
        html = c.get(f'/passagem-de-turno/turno?client_id={contrato["cid"]}').get_data(as_text=True)
        assert _rotulo_de(html, nome) == rotulo


# ── A confirmação depois de encerrar ─────────────────────────────────────

def test_o_encerramento_diz_quantas_pendencias_ficaram(mestre, contrato):
    r = mestre.post('/passagem-de-turno/api/turnos', json={
        'client_id': contrato['cid'], 'configuracao_id': contrato['cfg'],
        'data_turno': tempo.hoje().isoformat(), 'turno': '1º Turno',
        'dados': {'atividade:sanitarios': {'concluido': True}},
        'pendencias': [{'titulo': 'Repor papel do 2º andar', 'prioridade': 'media'},
                       {'titulo': 'Torneira pingando no térreo', 'prioridade': 'baixa'}],
        'finalizar': True})
    assert r.status_code == 201
    assert r.get_json()['pendencias_deixadas'] == 2


def test_a_tela_deixa_o_recado_antes_de_voltar_ao_painel():
    js = _js('diario_operacional.js')
    salvar = js[js.index('function continuarSalvar'):]
    salvar = salvar[:salvar.index('function resolverPendencia')] \
        if 'function resolverPendencia' in salvar else salvar
    recado = salvar.index('avisarNaProximaTela(finalizar, corpo, res.x)')
    assert recado < salvar.index("window.location = '/passagem-de-turno/?client_id='")
    funcao = js[js.index('function avisarNaProximaTela'):js.index('function continuarSalvar')]
    assert "sessionStorage.setItem('fc-aviso'" in funcao
    assert "tipo: 'success'" in funcao
    assert 'encerrada.' in funcao and 'pendencias_deixadas' in funcao


# ── "Sair" com envio guardado ────────────────────────────────────────────

def test_a_fila_avisa_tambem_no_sair_por_formulario():
    js = _js('fila-offline.js')
    assert "document.addEventListener('submit'" in js
    envio = js[js.index("document.addEventListener('submit'"):]
    envio = envio[:envio.index('}, true);')]
    assert 'ehLogout(form.getAttribute(' in envio
    assert 'ev.preventDefault()' in envio
    assert 'conferirSaida()' in envio
    assert 'HTMLFormElement.prototype.submit.call(form)' in envio
    # A conferência é UMA, para o link e para o formulário: avisa dos envios
    # guardados e apaga as telas guardadas.
    conferir = js[js.index('function conferirSaida'):js.index('function ehLogout')]
    assert 'meus(itens).length' in conferir
    assert 'apagarTelasGuardadas()' in conferir
    assert r"/\/logout$/" in js


def test_o_sair_da_tela_e_o_formulario_que_a_fila_reconhece(mestre, contrato):
    """O contrato entre o menu (base.html) e a fila: POST para .../logout."""
    html = mestre.get(f'/passagem-de-turno/?client_id={contrato["cid"]}').get_data(as_text=True)
    forms = re.findall(r'<form[^>]*method="post"[^>]*action="([^"]+)"', html)
    assert any(acao.endswith('/logout') for acao in forms), forms
    assert 'js/fila-offline.js' in html
