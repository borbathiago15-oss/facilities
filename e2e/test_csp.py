"""Fase 9A — com a CSP ligada (script só dos arquivos do sistema), as telas
que tinham JavaScript embutido continuam funcionando, no celular e no PC.

A fixture ``_sem_violacao_de_csp`` do conftest reprova se o navegador
bloquear qualquer coisa.
"""
from conftest import abrir_contexto, entrar


def test_passagem_funciona_sem_script_embutido(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        r = pg.goto(servidor['base'] + '/passagem-de-turno/turno')
        assert "script-src 'self'" in r.headers['content-security-policy']
        pg.wait_for_load_state('networkidle')
        pg.get_by_role('button', name='Nova pendência').click()
        assert pg.locator('.pending-row').count() == 1
        pg.locator('.pending-row button[data-remover]').click()
        assert pg.locator('.pending-row').count() == 0
    finally:
        b.close()


def test_gestao_painel_e_configuracao(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.dismiss())
        entrar(pg, servidor['base'], 'admin@e2e.test')
        for url in ('/passagem-de-turno/', '/passagem-de-turno/relatorio-mensal',
                    '/chamados/', '/chamados/novo', '/painel', '/demandas/'):
            pg.goto(servidor['base'] + url)
            pg.wait_for_load_state('networkidle')
        pg.goto(servidor['base'] + '/passagem-de-turno/configuracao')
        pg.wait_for_load_state('networkidle')
        pg.locator('[data-acao="novoModelo"]').first.click()
        pg.get_by_role('button', name='Adicionar turno').click()
        assert pg.locator('#cfg-shifts .config-row').count() >= 1
        pg.goto(servidor['base'] + '/passagem-de-turno/')
        # O filtro fica recolhido; o que importa é o "change" chegar à ação.
        pg.evaluate("var s = document.getElementById('dopPeriodo'); s.value = 'custom';"
                    "s.dispatchEvent(new Event('change', {bubbles: true}))")
        assert pg.evaluate("!document.querySelector('.dop-custom').hidden")
    finally:
        b.close()
