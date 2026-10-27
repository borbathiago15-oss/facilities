"""Cadastro simplificado (27/10/2026), num navegador de verdade (celular e PC):
o gerente abre o cliente, cria o centro de custo, escreve as áreas e digita a
rota em linhas — "06:00 · Banheiro 01"."""
from conftest import abrir_contexto, entrar


def test_cliente_centro_areas_e_rota(servidor, navegador, perfil):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'gerente@e2e.test')
        pg.goto(base + '/clientes')
        pg.get_by_role('link', name='Abrir o cliente').first.click()
        pg.wait_for_selector('text=Novo centro de custo')
        if not pg.locator('#name').is_visible():
            pg.locator('summary', has_text='Novo centro de custo').click()
        pg.fill('#name', 'CD Centros ' + perfil)
        pg.select_option('#estado_id', label='Bahia')
        pg.get_by_role('button', name='Criar e cadastrar as áreas').click()
        pg.wait_for_selector('text=Nenhuma área ainda')
        pg.fill('#areas', 'Banheiro 01\nBanheiro 02\nRecepção')
        pg.get_by_role('button', name='Cadastrar as áreas').click()
        pg.wait_for_selector('text=3 área(s) cadastrada(s)')
        assert pg.locator('text=QR 003').is_visible()
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
        pg.get_by_role('link', name='Seguir para as rotas').click()
        pg.fill('#rnome', 'Banheiros — manhã')
        pg.get_by_role('button', name='Criar e digitar os horários').click()
        pg.wait_for_selector('text=Nenhum horário ainda')
        pg.fill('#h0', '06:00')
        pg.select_option('#a0', label='Banheiro 01')
        pg.fill('#h1', '06:30')
        pg.select_option('#a1', label='Banheiro 02')
        pg.get_by_role('button', name='Incluir na rota').click()
        pg.wait_for_selector('text=Horários incluídos na rota.')
        linhas = pg.locator('[data-linha]')
        assert linhas.count() == 2
        assert 'Banheiro 01' in linhas.nth(0).inner_text() and '06:00' in linhas.nth(0).inner_text()
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
    finally:
        b.close()
