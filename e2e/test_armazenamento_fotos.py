"""A tela "Armazenamento de fotos" (React, só do administrador) no celular e
no PC: abre pelo menu "Administração do sistema", mostra o destino (uma pasta
no mesmo disco: avisa que não libera espaço), salva o prazo e não rola para
o lado. Quem não é administrador recebe 403. Sem violação de CSP (conftest).
"""
import os

import pytest

from conftest import MANIFESTO, abrir, abrir_contexto, entrar


@pytest.fixture(autouse=True)
def _compilado():
    if not os.path.exists(MANIFESTO):
        pytest.skip('telas novas não compiladas: rode "npm run build" em frontend/')


def test_armazenamento_no_celular_e_no_pc(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'admin@e2e.test')
        pg.goto(servidor['base'] + '/novo/')
        if perfil == 'celular':
            pg.get_by_role('button', name='Menu').click()
        item = pg.locator('.fc-lat-item', has_text='Armazenamento de fotos')
        item.click()
        pg.wait_for_selector('[data-tela-pronta="armazenamento"]', state='attached')
        assert pg.url.endswith('/novo/admin/armazenamento')
        assert 'ativo' in item.get_attribute('class')
        pg.get_by_role('heading', name='Armazenamento de fotos').wait_for()
        assert pg.get_by_text('não libera espaço nenhum').is_visible()
        assert pg.get_by_role('button', name='Arquivar 0 fotos').is_disabled()
        campo = pg.get_by_label('Arquivar fotos com mais de')
        campo.fill('90')
        pg.get_by_role('button', name='Salvar prazo').click()
        pg.get_by_text('Prazo salvo.').wait_for()
        assert pg.get_by_role('heading', name='Arquivar as fotos antigas').is_visible()
        assert servidor['sql']('SELECT dias FROM arquivo_fotos_ajustes') == [(90,)]
        assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']
        # Recarregar mantém o prazo (vem do banco).
        abrir(pg, servidor['base'] + '/novo/admin/armazenamento', nome='armazenamento')
        assert pg.get_by_label('Arquivar fotos com mais de').input_value() == '90'
    finally:
        b.close()


def test_so_o_administrador_abre(servidor, navegador):
    b, ctx = abrir_contexto(navegador, 'pc')
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'sueli@e2e.test')
        r = pg.goto(servidor['base'] + '/novo/admin/armazenamento')
        assert r.status == 403
        pg.goto(servidor['base'] + '/novo/')
        pg.get_by_role('heading', name='Olá, Sueli').wait_for()
        assert pg.locator('.fc-lat-item', has_text='Armazenamento de fotos').count() == 0
    finally:
        b.close()
