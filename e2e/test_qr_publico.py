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
        visitante.get_by_role('button', name='Avisar um problema').click()
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
        assert 'Checar aviso' in ana.content()                  # início do app
        # No turno do local, o aviso é uma tarefa "Checar aviso" (27/10/2026).
        [(local_id,)] = servidor['sql'](
            "SELECT client_id FROM pontos_inspecao WHERE codigo_qr = '%s'" % servidor['qr'])
        ana.goto(servidor['base'] + '/app/turno?local=%d' % local_id)
        ana.wait_for_selector('#turno-avisos')
        assert 'Papel higiênico reposto?' in ana.inner_text('#turno-avisos')
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


def test_visitante_elogia_com_estrelas(servidor, navegador, perfil):
    """27/10/2026: o QR também recebe elogio — 1 a 5 estrelas e comentário."""
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.goto(servidor['base'] + '/q/' + servidor['qr'])
        pg.get_by_role('button', name='Sim').click()
        pg.get_by_role('link', name='Fazer um elogio').click()
        pg.wait_for_url('**/elogio')
        pg.locator('label[for="nota4"]').click()
        assert pg.locator('#nota4').is_checked()
        pg.fill('#texto', 'Banheiro muito limpo')
        largura = pg.evaluate('document.documentElement.scrollWidth')
        assert largura <= pg.viewport_size['width']
        pg.get_by_role('button', name='Enviar elogio').click()
        pg.wait_for_selector('text=Obrigado!')
        assert servidor['sql']('SELECT nota, texto FROM elogios_publicos') == \
            [(4, 'Banheiro muito limpo')]
    finally:
        b.close()


def test_foto_grande_da_camera_e_reduzida_no_celular(servidor, navegador, tmp_path):
    """27/10/2026: a foto da câmera (vários MB) era recusada. A página reduz
    no próprio celular antes de subir."""
    import os
    from PIL import Image
    caminho = tmp_path / 'IMG_camera.jpg'
    Image.frombytes('RGB', (4000, 3000), os.urandom(4000 * 3000 * 3)).save(
        caminho, 'JPEG', quality=92)
    assert os.path.getsize(caminho) > 3 * 1024 * 1024
    b, ctx = abrir_contexto(navegador, 'celular')
    try:
        pg = ctx.new_page()
        pg.goto(servidor['base'] + '/q/' + servidor['qr'])
        pg.get_by_role('button', name='Sim').click()
        pg.get_by_role('button', name='Avisar um problema').click()
        pg.locator('label.fc-qr-item').first.click()
        pg.get_by_role('button', name='Continuar').click()
        pg.set_input_files('#foto', str(caminho))
        # O arquivo que vai subir vira a versão leve no próprio celular.
        pg.wait_for_function(
            "() => { var f = document.getElementById('foto').files[0];"
            " return f && f.size < 1024 * 1024 && f.type === 'image/jpeg'; }")
        pg.get_by_role('button', name='Enviar').click()
        pg.wait_for_url('**/acompanhar/**')
        assert 'Recebida' in pg.content()
        [(chave,)] = servidor['sql']('SELECT foto_key FROM ocorrencias_publicas')
        assert chave
    finally:
        b.close()
