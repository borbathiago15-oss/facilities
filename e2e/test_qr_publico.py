"""Fase 4B — o QR público num navegador de verdade (celular e PC).

Um visitante, sem login, lê o QR do banheiro e avisa "Local sujo"; a
página de acompanhamento mostra "Recebida". A Ana abre o aplicativo, vê o
aviso no ponto e marca "Resolvido"; o visitante vê "Resolvida".
"""
from conftest import abrir_contexto, entrar


def test_visitante_avisa_e_a_ana_resolve(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        visitante = ctx.new_page()
        visitante.goto(servidor['base'] + '/q/' + servidor['qr'])
        assert visitante.get_by_role('heading', name='Viu algum problema aqui?').is_visible()
        visitante.locator('label.fc-opcao', has_text='Local sujo').click()
        visitante.fill('#texto', 'Piso molhado perto da pia')
        visitante.get_by_role('button', name='Enviar').click()
        visitante.wait_for_url('**/acompanhar/**')
        assert 'Recebida' in visitante.content()
        largura = visitante.evaluate('document.documentElement.scrollWidth')
        assert largura <= visitante.viewport_size['width']
        link = visitante.url

        equipe = ctx.browser.new_context()
        ana = equipe.new_page()
        entrar(ana, servidor['base'], 'ana@e2e.test')
        assert 'Local sujo' in ana.content()                    # início do app
        ana.goto(servidor['base'] + '/app/turno?ponto=' + servidor['qr'])
        ana.get_by_role('button', name='Resolvido').click()
        ana.wait_for_selector('text=Aviso resolvido')
        equipe.close()

        visitante.goto(link)
        assert 'Resolvida' in visitante.content()
    finally:
        b.close()
