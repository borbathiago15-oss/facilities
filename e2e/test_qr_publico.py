"""Fase 4B — o QR público num navegador de verdade (celular e PC).

Um visitante, sem login, lê o QR do banheiro, confirma "É aqui?" e marca o
item do checklist ("Problema: Papel higiênico reposto?"); a página de
acompanhamento mostra "Recebida". A Ana abre o aplicativo, vê o aviso no
ponto e marca "Resolvido"; o visitante vê "Resolvida".
"""
from conftest import abrir_contexto, entrar


def test_visitante_avisa_e_a_ana_resolve(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        visitante = ctx.new_page()
        visitante.goto(servidor['base'] + '/q/' + servidor['qr'])
        assert visitante.get_by_role('heading', name='É aqui?').is_visible()
        visitante.get_by_role('button', name='Sim').click()
        visitante.locator('label.fc-qr-item', has_text='Papel higiênico reposto?').click()
        visitante.fill('#texto', 'Piso molhado perto da pia')
        visitante.get_by_role('button', name='Continuar').click()
        visitante.get_by_role('button', name='Enviar').click()
        visitante.wait_for_url('**/acompanhar/**')
        assert 'Recebida' in visitante.content()
        largura = visitante.evaluate('document.documentElement.scrollWidth')
        assert largura <= visitante.viewport_size['width']
        link = visitante.url

        equipe = ctx.browser.new_context()
        ana = equipe.new_page()
        entrar(ana, servidor['base'], 'ana@e2e.test')
        assert 'Itens do checklist' in ana.content()            # início do app
        ana.goto(servidor['base'] + '/app/turno?ponto=' + servidor['qr'])
        # O ponto abre no checklist da hora; o aviso fica em "Outras coisas".
        ana.get_by_role('button', name='Outras coisas neste ponto').click()
        ana.get_by_role('button', name='Resolvido').click()
        ana.wait_for_selector('text=Aviso resolvido')
        equipe.close()

        visitante.goto(link)
        assert 'Resolvida' in visitante.content()
    finally:
        b.close()
