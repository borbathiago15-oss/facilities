"""Fase 7 — a Ana lança o consumo e avisa que falta material, no celular e no PC.

Roda na tela antiga (``/app``) e na nova, em React (``/novo/app``, Fase 1d):
a fixture ``campo``."""
from conftest import abrir_contexto, entrar, tela_pronta


def test_ana_usa_material_e_avisa_o_que_falta(servidor, navegador, perfil, campo):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + campo + '/')
        pg.get_by_role('link', name='Material: usei / está faltando').click()
        pg.wait_for_url(f'**{campo}/materiais')
        tela_pronta(pg, 'campo-materiais')
        assert pg.locator('text=12,90').count() == 0          # a Ana não vê preço
        pg.get_by_label('Quantidade', exact=True).fill('1,5')
        pg.get_by_role('button', name='Registrar consumo').click()
        pg.wait_for_selector('text=Consumo registrado: 1,5 L de Detergente neutro')
        tela_pronta(pg, 'campo-materiais')
        pg.get_by_label('O que precisa').fill('saco de lixo 100 L')
        pg.get_by_role('button', name='Avisar o gestor').click()
        pg.wait_for_selector('text=Pedido enviado ao gestor do contrato')
        assert servidor['sql']("SELECT quantidade FROM movimentos_estoque "
                               "WHERE tipo='consumo'") == [(-1.5,)]
        assert servidor['sql']("SELECT texto, status FROM pedidos_insumo") == \
            [('saco de lixo 100 L', 'aberto')]
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
    finally:
        b.close()
