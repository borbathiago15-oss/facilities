"""Fase 8 — o painel abre no celular e no PC, sem rolagem lateral da página.
Na tela antiga e na nova (React, Fase 4c: ``/novo/painel``)."""
from conftest import abrir, abrir_contexto, entrar


def test_painel_abre_nos_dois_formatos(servidor, navegador, perfil, relatorios):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'sueli@e2e.test')
        abrir(pg, servidor['base'] + relatorios + '/painel', 'painel')
        assert pg.get_by_role('heading', name='Painel').is_visible()
        assert pg.locator('text=GL Armazém 1').count() >= 1
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
    finally:
        b.close()
