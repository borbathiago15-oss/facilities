"""Visual (padrão do Trino Intelligence): o login com o painel da marca, o
menu lateral no PC e a gaveta no celular, e nenhuma tela principal com
rolagem lateral — nos dois formatos."""
from conftest import abrir_contexto, entrar

TELAS = ['/', '/painel', '/demandas/', '/chamados/', '/rotas/', '/materiais/', '/cadastros/',
         '/passagem-de-turno/', '/cobrancas/', '/avisos']


def test_login_menu_e_telas_sem_rolagem_lateral(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.goto(servidor['base'] + '/login')
        assert pg.get_by_role('heading', name='Entrar').is_visible()
        marca = pg.locator('.fc-porta-marca')
        assert marca.is_visible() == (perfil == 'pc')     # no celular, só o formulário
        pg.fill('#password', 'abc')
        pg.click('[data-ver-senha]')
        assert pg.get_attribute('#password', 'type') == 'text'
        entrar(pg, servidor['base'], 'admin@e2e.test')
        menu = pg.locator('#fc-lateral')
        if perfil == 'pc':
            assert menu.is_visible() and not pg.locator('[data-menu-abrir]').is_visible()
        else:
            caixa = menu.bounding_box()
            assert caixa['x'] + caixa['width'] <= 0       # fora da tela
            pg.click('[data-menu-abrir]')
            pg.wait_for_timeout(350)
            assert menu.bounding_box()['x'] >= 0
            assert pg.get_attribute('[data-menu-abrir]', 'aria-expanded') == 'true'
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(350)
            assert menu.bounding_box()['x'] < 0
        for t in TELAS:
            pg.goto(servidor['base'] + t)
            largura = pg.evaluate('document.documentElement.scrollWidth')
            assert largura <= pg.viewport_size['width'], f'{t} rola de lado ({largura}px)'
            assert pg.locator('.fc-lat-item.ativo').count() <= 1
    finally:
        b.close()
