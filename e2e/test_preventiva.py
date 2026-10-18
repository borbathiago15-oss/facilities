"""Fase 5 — o Caio faz a preventiva no aplicativo, no celular e no PC.

Lê o QR da porta → o cartão "Preventiva a fazer aqui" → "Fazer a preventiva"
→ responde → Confirmar → a ordem de serviço fica resolvida.
"""
from conftest import abrir_contexto, entrar


def test_caio_faz_a_preventiva_pelo_qr(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'caio@e2e.test')
        pg.goto(servidor['base'] + '/app/turno?ponto=' + servidor['qr'])
        pg.wait_for_selector('text=Preventiva a fazer aqui', timeout=15000)
        pg.get_by_role('button', name='Fazer a preventiva').click()
        pg.locator('label.fc-opcao', has_text='Sim').click()
        pg.get_by_role('button', name='Confirmar').click()
        pg.wait_for_selector('text=Preventiva feita', timeout=15000)
        assert servidor['sql']("SELECT status FROM chamados WHERE origem='preventiva'") == \
            [('resolvido',)]
        assert pg.locator('text=Preventiva a fazer aqui').count() == 0
        largura = pg.evaluate('document.documentElement.scrollWidth')
        assert largura <= pg.viewport_size['width']
    finally:
        b.close()
