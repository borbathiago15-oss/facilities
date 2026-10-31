"""As telas novas (React): a casca abre no celular e no PC, com o mesmo menu
do site, a gaveta do celular e sem rolagem lateral; os módulos ainda não
migrados abrem na tela de sempre. Sem violação de CSP (conftest).

Precisa das telas compiladas (``npm run build`` em frontend/).
"""
import os
import time

import pytest

from conftest import abrir_contexto, entrar

MANIFESTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'facilities', 'static', 'app', '.vite', 'manifest.json')


@pytest.fixture(autouse=True)
def _compilado():
    if not os.path.exists(MANIFESTO):
        pytest.skip('telas novas não compiladas: rode "npm run build" em frontend/')


def _esperar(pg, expressao, sim=True):
    # ``wait_for_function`` usa eval, que a CSP do sistema (com razão) barra.
    for _ in range(50):
        if bool(pg.evaluate(expressao)) == sim:
            return
        time.sleep(0.1)
    raise AssertionError(f'{expressao} não ficou {sim}')


def test_casca_react_no_celular_e_no_pc(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'admin@e2e.test')
        pg.goto(servidor['base'] + '/novo/')
        pg.get_by_role('heading', name='Olá, Administrador').wait_for()
        dentro = "document.getElementById('fc-lateral').getBoundingClientRect().right > 0"
        assert pg.locator('.fc-lat-item', has_text='Pessoas e acessos').count() == 1
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
        if perfil == 'celular':
            # A gaveta fica fora da tela até o botão "Menu"; o Esc fecha.
            assert not pg.evaluate(dentro)
            pg.get_by_role('button', name='Menu').click()
            _esperar(pg, dentro)
            pg.keyboard.press('Escape')
            _esperar(pg, dentro, sim=False)
        else:
            assert pg.evaluate(dentro)
        # Módulo ainda não migrado: abre a tela de sempre.
        pg.locator('.card', has_text='Chamados').click()
        pg.wait_for_url('**/chamados/')
        # Endereço que não existe nas telas novas: aviso, com caminho de volta.
        pg.goto(servidor['base'] + '/novo/nao-existe')
        pg.get_by_role('heading', name='Página não encontrada').wait_for()
        assert pg.get_by_role('link', name='Voltar ao início').is_visible()
    finally:
        b.close()


def test_inicio_do_campo_em_react(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/novo/app')
        pg.get_by_role('heading', name='Olá, Ana').wait_for()
        # A moldura do aplicativo: navegação embaixo, sem o menu lateral do site.
        nav = pg.get_by_role('navigation', name='Aplicativo de campo')
        assert nav.is_visible() and pg.locator('#fc-lateral').count() == 0
        assert pg.evaluate("document.body.classList.contains('fc-app')")
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
        # O mesmo cartão do turno da tela antiga, para o mesmo endereço.
        pg.goto(servidor['base'] + '/app/')
        antigo = pg.locator('.fc-local-turno').first
        nome, destino = antigo.locator('.fc-local-turno-nome').inner_text(), antigo.get_attribute('href')
        pg.goto(servidor['base'] + '/novo/app')
        novo = pg.locator('.fc-local-turno').first
        novo.wait_for()
        assert novo.locator('.fc-local-turno-nome').inner_text() == nome
        assert novo.get_attribute('href') == destino
        novo.click()
        pg.wait_for_url('**' + destino.split('?')[0] + '*')
    finally:
        b.close()
