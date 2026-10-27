"""Bloco do técnico, etapa 2 — as telas do aplicativo no CELULAR (decisões do
dono de 22/10/2026):

* chegada pelo QR da entrada → o turno do local → o ponto abre direto no
  checklist (antes → um check por item, foto no item que exige → depois →
  Pronto) → "Pronto. Copa feito às…" e a PRÓXIMA tarefa com "Ler o QR";
* QR comum antes da chegada: só "Confirme a chegada";
* "Não deu" com "Faltou material" → não conformidade + pedido de insumo;
* levou mais que o previsto: a tela do motivo do atraso, e o reenvio;
* a página pública do QR: "É aqui?" → itens do checklist → enviar.

Com ``E2E_CAPTURAS=<pasta>`` as telas principais viram PNG (para o dono ver).
"""
import os
from datetime import datetime, timedelta

from conftest import abrir_contexto, entrar
from servidor import QR_COPA, QR_ENTRADA

CAPTURAS = os.environ.get('E2E_CAPTURAS')


def _capturar(pg, nome):
    if CAPTURAS:
        os.makedirs(CAPTURAS, exist_ok=True)
        pg.screenshot(path=os.path.join(CAPTURAS, nome + '.png'), full_page=True)


def _foto(tmp_path, nome='foto.jpg'):
    from camera import _qr_em_imagem
    caminho = tmp_path / nome
    _qr_em_imagem(nome, 120).save(caminho, 'JPEG')
    return str(caminho)


def _abrir_ponto(pg, base, codigo):
    """Abre o ponto como o código digitado no leitor abre (a câmera de
    mentira só mostra um QR por navegador): sem o selo, com a hora do
    celular."""
    pg.goto(base + '/app/turno?ponto=' + codigo)
    pg.wait_for_timeout(300)


def _sem_rolagem_lateral(pg):
    assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']


def test_chegada_turno_checklist_e_proxima_tarefa(servidor, navegador, tmp_path):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, 'celular', camera_com=base + '/q/' + QR_ENTRADA)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'ana@e2e.test')
        # O início: um cartão por local — o Armazém 2 pede o QR da entrada.
        assert pg.locator('[data-local][data-situacao="sem_chegada"]', has_text='GL Armazém 2').is_visible()
        assert pg.locator('[data-local][data-situacao="sem_entrada"]', has_text='GL Armazém 1').is_visible()
        _capturar(pg, '01-inicio-locais')
        # QR comum antes da chegada: só "Confirme a chegada" e o botão.
        pg.goto(base + '/app/turno?ponto=' + QR_COPA)
        pg.wait_for_selector('text=Confirme a chegada')
        assert pg.get_by_role('link', name='Ler o QR').is_visible()
        assert pg.locator('#turno-ponto button').count() == 0
        _capturar(pg, '02-confirme-a-chegada')
        # A câmera lê o QR da entrada: chegada registrada e o turno do local.
        pg.goto(base + '/app/ler-qr')
        pg.wait_for_url('**/app/turno?local=*', timeout=20000)
        pg.wait_for_selector('text=Você chegou ao GL Armazém 2 às')
        assert pg.locator('.fc-roteiro-n').count() == 2
        assert pg.locator('.fc-proxima', has_text='Copa').count() == 1
        assert servidor['sql']('SELECT com_camera FROM chegadas') == [(1,)]
        _capturar(pg, '03-chegou-turno-do-local')
        # O ponto abre DIRETO no checklist: antes → checks → depois → Pronto.
        _abrir_ponto(pg, base, QR_COPA)
        assert pg.get_by_role('heading', name='Copa').is_visible()
        assert pg.locator('.fc-exec-sub').inner_text().endswith('Previsto: 1 min')
        assert pg.get_by_role('button', name='Fazer agora').count() == 0
        pronto = pg.get_by_role('button', name='Pronto')
        assert pronto.is_disabled()
        assert 'Faltam a foto do antes, 2 itens e a foto do depois' in pg.locator('.fc-faltam').inner_text()
        pg.set_input_files('[data-foto="antes"]', _foto(tmp_path, 'antes.jpg'))
        pg.get_by_role('button', name='Feito: Pia limpa?').click()
        assert pg.locator('.fc-item-feito', has_text='Pia limpa?').count() == 1
        # O "como fazer" fica atrás do (i).
        assert pg.locator('text=Esponja macia').is_visible() is False
        pg.get_by_role('button', name='Como fazer: Pia limpa?').click()
        assert pg.locator('text=Esponja macia e detergente neutro.').is_visible()
        # Item com foto exigida: o check só fica verde com a foto.
        pg.get_by_role('button', name='Feito: Lixo retirado?').click()
        assert pg.locator('.fc-item-feito', has_text='Lixo retirado?').count() == 0
        pg.set_input_files('[data-foto="item:lixo_retirado"]', _foto(tmp_path, 'lixo.jpg'))
        assert pg.locator('.fc-item-feito', has_text='Lixo retirado?').count() == 1
        assert 'Falta a foto do depois' in pg.locator('.fc-faltam').inner_text()
        _capturar(pg, '04-ponto-com-checks')
        pg.set_input_files('[data-foto="depois"]', _foto(tmp_path, 'depois.jpg'))
        assert pronto.is_enabled()
        pronto.click()
        pg.wait_for_selector('text=Pronto. Copa feito às', timeout=15000)
        # A próxima tarefa da rota, com "Ler o QR" — nunca a tela do mesmo ponto.
        assert pg.locator('.fc-proxima-tarefa', has_text='Refeitório').is_visible()
        assert pg.locator('.fc-proxima-tarefa').get_by_role('link', name='Ler o QR').is_visible()
        assert pg.locator('#turno-execucao').is_hidden()
        _capturar(pg, '06-pronto-proxima-tarefa')
        _sem_rolagem_lateral(pg)
        assert servidor['sql']('SELECT t.status, e.n_nao_conformes, e.motivo_atraso FROM execucoes e '
                               'JOIN tarefas_dia t ON t.id = e.tarefa_id') == \
            [('concluida_no_prazo', 0, None)]
        assert servidor['sql']('SELECT momento FROM execucao_fotos ORDER BY momento') == \
            [('antes',), ('depois',), ('item',)]
    finally:
        b.close()


def _chegar(pg, base):
    pg.goto(base + '/app/turno?ponto=' + QR_ENTRADA + '&lido=camera')
    pg.wait_for_selector('text=Você chegou ao GL Armazém 2 às', timeout=15000)


def test_nao_deu_com_faltou_material(servidor, navegador, tmp_path):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, 'celular')
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'ana@e2e.test')
        _chegar(pg, base)
        _abrir_ponto(pg, base, QR_COPA)
        pg.set_input_files('[data-foto="antes"]', _foto(tmp_path, 'antes.jpg'))
        pg.locator('.fc-item', has_text='Pia limpa?').get_by_role('button', name='Não deu').click()
        pg.get_by_role('button', name='Faltou material').click()
        pg.wait_for_selector('select option:has-text("Detergente neutro")', state='attached')
        _capturar(pg, '05-nao-deu-faltou-material')
        pg.select_option('.fc-folha select', label='Detergente neutro (L)')
        pg.get_by_role('button', name='Confirmar').click()
        item = pg.locator('.fc-item-naodeu', has_text='Pia limpa?')
        assert item.count() == 1 and 'Faltou material' in item.inner_text()
        assert 'Detergente neutro' in item.inner_text()
        _capturar(pg, '05b-item-nao-deu')
        pg.get_by_role('button', name='Feito: Lixo retirado?').click()
        pg.set_input_files('[data-foto="item:lixo_retirado"]', _foto(tmp_path, 'lixo.jpg'))
        pg.set_input_files('[data-foto="depois"]', _foto(tmp_path, 'depois.jpg'))
        pg.get_by_role('button', name='Pronto').click()
        pg.wait_for_selector('text=Pronto. Copa feito às', timeout=15000)
        assert pg.locator('text=1 item com problema: a gestão foi avisada e o material foi pedido').is_visible()
        assert servidor['sql']('SELECT item_codigo, resposta FROM nao_conformidades') == \
            [('pia_limpa', 'Não feito: faltou material')]
        assert servidor['sql']('SELECT m.nome, p.status FROM pedidos_insumo p '
                               'JOIN materiais m ON m.id = p.material_id') == \
            [('Detergente neutro', 'aberto')]
        assert servidor['sql']("SELECT COUNT(*) FROM chamados WHERE origem != 'preventiva'") == [(1,)]
    finally:
        b.close()


def test_atraso_pede_o_motivo_e_reenvia(servidor, navegador, tmp_path):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, 'celular')
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'ana@e2e.test')
        _chegar(pg, base)
        # O relógio do celular volta 25 min para a leitura do QR (sem câmera,
        # vale a hora do aparelho); antes do "Pronto" ele volta ao normal: a
        # limpeza "levou" 25 min contra 1 previsto (+10 de tolerância).
        pg.clock.install(time=datetime.now() - timedelta(minutes=25))
        _abrir_ponto(pg, base, QR_COPA)
        pg.set_input_files('[data-foto="antes"]', _foto(tmp_path, 'antes.jpg'))
        pg.get_by_role('button', name='Feito: Pia limpa?').click()
        pg.get_by_role('button', name='Feito: Lixo retirado?').click()
        pg.set_input_files('[data-foto="item:lixo_retirado"]', _foto(tmp_path, 'lixo.jpg'))
        pg.set_input_files('[data-foto="depois"]', _foto(tmp_path, 'depois.jpg'))
        pg.clock.set_system_time(datetime.now())
        pg.get_by_role('button', name='Pronto').click()
        pg.wait_for_selector('text=o previsto era 1.', timeout=15000)
        assert pg.get_by_role('heading', name='Esta limpeza levou 2').is_visible()
        assert pg.locator('text=O que aconteceu?').is_visible()
        assert pg.locator('.fc-motivo').count() == 6
        _capturar(pg, '07-atraso-motivo')
        pg.get_by_role('button', name='Outro', exact=True).click()
        pg.get_by_role('button', name='Confirmar').click()          # sem texto: não vai
        assert pg.locator('text=Escreva o que aconteceu.').is_visible()
        pg.get_by_label('O que aconteceu').fill('Pia entupida, tive que desentupir')
        pg.get_by_role('button', name='Confirmar').click()
        pg.wait_for_selector('text=Pronto. Copa feito às', timeout=15000)
        assert pg.locator('text=o motivo ficou registrado').is_visible()
        assert servidor['sql']('SELECT motivo_atraso, motivo_atraso_texto, sem_sinal FROM execucoes') == \
            [('outro', 'Pia entupida, tive que desentupir', 1)]
    finally:
        b.close()


def test_pagina_publica_e_aqui_itens_e_enviar(servidor, navegador):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, 'celular')
    try:
        pg = ctx.new_page()
        pg.goto(base + '/q/' + QR_COPA)
        assert pg.get_by_role('heading', name='Você está no Copa · GL Armazém 2. É aqui?').is_visible()
        assert pg.locator('[data-passo="problema"]').is_hidden()
        _capturar(pg, '08-publico-e-aqui')
        pg.get_by_role('button', name='Sim').click()
        assert pg.locator('[data-passo="lugar"]').is_hidden()
        # 27/10/2026: avisar um problema ou elogiar.
        assert pg.get_by_role('link', name='Fazer um elogio').is_visible()
        pg.get_by_role('button', name='Avisar um problema').click()
        # Sem marcar nada: não passa.
        pg.get_by_role('button', name='Continuar').click()
        assert pg.locator('[data-erro-problema]').is_visible()
        pg.locator('label.fc-qr-item', has_text='Lixeira cheia').click()
        pg.fill('#texto', 'Transbordando')
        _capturar(pg, '09-publico-itens')
        pg.get_by_role('button', name='Continuar').click()
        assert pg.locator('[data-passo="foto"]').is_visible()
        pg.get_by_role('button', name='Enviar').click()
        pg.wait_for_url('**/acompanhar/**')
        assert 'Recebemos o seu aviso' in pg.content() and 'Lixeira cheia' in pg.content()
        assert 'Itens do checklist' not in pg.content()
        _sem_rolagem_lateral(pg)
        _capturar(pg, '10-publico-obrigado')
        assert servidor['sql']('SELECT tipo, texto, itens_json, autor_id FROM ocorrencias_publicas') == \
            [('itens', 'Transbordando', '["lixo_retirado"]', None)]
    finally:
        b.close()


def test_ponto_sem_checklist_mantem_os_tipos(servidor, navegador):
    """Sem rota no ponto, a lista de tipos de antes continua (fallback)."""
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, 'celular')
    try:
        pg = ctx.new_page()
        pg.goto(base + '/q/' + QR_ENTRADA)              # a portaria não tem rota
        pg.get_by_role('button', name='Sim').click()
        pg.get_by_role('button', name='Avisar um problema').click()
        assert pg.locator('label.fc-opcao', has_text='Local sujo').is_visible()
        assert pg.locator('label.fc-opcao', has_text='Itens do checklist').count() == 0
    finally:
        b.close()
