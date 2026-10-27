"""Troca de área no aplicativo (27/10/2026), num navegador de verdade.

O Tito abre o turno do "GL Armazém 3":
* "Ir para outra área" pergunta o motivo e manda ler o QR;
* a recepção (da rota, daqui a duas horas) é ADIANTADA: o checklist abre com
  o motivo e a tarefa fica concluída;
* a sala de reunião (fora da rota hoje) abre o escopo da área como atividade
  fora da rota, com o motivo.
"""
from conftest import abrir_contexto, entrar
from servidor import QR_RECEPCAO, QR_SALA


def _feito_e_pronto(pg, item):
    pg.get_by_role('button', name='Feito: ' + item).click()
    pg.get_by_role('button', name='Pronto').click()


def test_ir_para_outra_area_adianta_a_da_rota(servidor, navegador, perfil):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'tito@e2e.test')
        pg.goto(base + '/app/turno?local=' + str(servidor['sql'](
            "SELECT id FROM clients WHERE name = 'GL Armazém 3'")[0][0]))
        pg.get_by_role('button', name='Ir para outra área').click()
        assert pg.get_by_role('dialog').is_visible()
        assert pg.locator('[data-motivo-troca]').count() == 4
        # "Pedido do cliente" e o leitor abre; a câmera de mentira não lê a
        # recepção, então o QR é aberto pelo endereço (como o código digitado).
        with pg.expect_navigation():
            pg.get_by_role('button', name='Pedido do cliente').click()
        assert '/app/ler-qr' in pg.url
        pg.goto(base + '/app/turno?ponto=' + QR_RECEPCAO)
        pg.wait_for_selector('.fc-exec-sub')
        assert 'adiantada: Pedido do cliente' in pg.locator('.fc-exec-sub').inner_text()
        _feito_e_pronto(pg, 'Balcão limpo?')
        pg.wait_for_selector('text=Pronto. Recepção feito às', timeout=15000)
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
        linhas = servidor['sql'](
            "SELECT t.status, e.motivo_troca FROM execucoes e JOIN tarefas_dia t "
            "ON t.id = e.tarefa_id JOIN pontos_inspecao p ON p.id = e.ponto_id "
            "WHERE p.codigo_qr = '%s'" % QR_RECEPCAO)
        assert ('concluida_no_prazo', 'pedido_cliente') in linhas
    finally:
        b.close()


def test_area_fora_da_rota_abre_o_escopo(servidor, navegador, perfil):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'tito@e2e.test')
        pg.goto(base + '/app/turno?ponto=' + QR_SALA)
        pg.wait_for_selector('text=Nenhuma tarefa de rota aqui hoje.')
        pg.get_by_role('button', name='Limpar esta área fora da rota').click()
        pg.get_by_role('button', name='Área mais suja, precisa adiantar').click()
        sub = pg.locator('.fc-exec-sub').inner_text()
        assert 'Limpeza da sala' in sub and 'fora da rota' in sub and 'Área mais suja' in sub
        _feito_e_pronto(pg, 'Mesa limpa?')
        pg.wait_for_selector('text=Pronto.', timeout=15000)
        linhas = servidor['sql'](
            "SELECT e.extra, e.motivo_troca FROM execucoes e JOIN pontos_inspecao p "
            "ON p.id = e.ponto_id WHERE p.codigo_qr = '%s'" % QR_SALA)
        assert (1, 'area_mais_suja') in linhas
    finally:
        b.close()
