"""Fase 3 — o aplicativo de campo num navegador de verdade, no celular e no PC.

* o encarregado entra e cai na tela do posto; o administrador cai no site;
* a câmera lê o QR da etiqueta e abre o ponto certo;
* sem sinal, a passagem encerrada fica no aparelho e sobe UMA vez quando o
  sinal volta;
* celular compartilhado: o que a Ana guardou sem sinal não sobe com a
  Mariana logada — sobe quando a Ana entra de novo, em nome dela.
"""
import re

from conftest import abrir_contexto, entrar, esperar


def test_cada_um_cai_na_sua_porta(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        assert pg.url.endswith('/app/')
        assert pg.get_by_text('Ler o QR do local').is_visible()
        assert pg.locator('.fc-app-nav').is_visible()
        largura = pg.evaluate('document.documentElement.scrollWidth')
        assert largura <= pg.viewport_size['width'], 'a tela do posto rola de lado'
        outro = ctx.browser.new_context()
        pg2 = outro.new_page()
        entrar(pg2, servidor['base'], 'admin@e2e.test')
        assert re.search(r'/$', pg2.url) and '/app/' not in pg2.url
        outro.close()
    finally:
        b.close()


def test_a_camera_le_o_qr_e_abre_o_ponto(servidor, navegador, perfil):
    url_do_qr = servidor['base'] + '/q/' + servidor['qr']
    b, ctx = abrir_contexto(navegador, perfil, camera_com=url_do_qr)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/app/ler-qr')
        pg.wait_for_url('**/app/turno?ponto=' + servidor['qr'], timeout=20000)
        assert pg.get_by_role('heading', name='Porta do banheiro').is_visible()
    finally:
        b.close()


def test_qr_de_fora_nao_tira_o_celular_do_sistema(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil, camera_com='https://golpe.example/q/abcdefgh1234')
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/app/ler-qr')
        esperar(pg, "document.getElementById('fc-leitor-msg').textContent"
                             ".includes('não é do Trino Facilities')", timeout=20000)
        assert pg.url.endswith('/app/ler-qr')
    finally:
        b.close()


def _turnos(servidor, email):
    return servidor['sql'](
        'SELECT t.turno FROM diario_operacional_turnos t JOIN users u ON u.id = t.created_by '
        'WHERE u.email = ? AND t.status = ?', email, 'encerrado')


def test_sem_sinal_guarda_e_sobe_uma_vez(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept())
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/passagem-de-turno/turno')
        pg.wait_for_load_state('networkidle')
        ctx.set_offline(True)
        _encerrar_passagem_sem_navegar(pg, '1º Turno')
        pg.wait_for_selector('.fila-selo:not([hidden])', timeout=10000)
        assert _turnos(servidor, 'ana@e2e.test') == []
        ctx.set_offline(False)
        pg.evaluate('window.TrinoFila.enviarAgora()')
        esperar(pg, "!document.querySelector('.fila-selo') || "
                             "document.querySelector('.fila-selo').hidden", timeout=15000)
        # Mais uma rodada da fila não duplica.
        pg.evaluate('window.TrinoFila.enviarAgora()')
        pg.wait_for_timeout(1500)
        assert _turnos(servidor, 'ana@e2e.test') == [('1º Turno',)]
    finally:
        b.close()


def _encerrar_passagem_sem_navegar(pg, turno):
    pg.select_option('#diario-shift', turno)
    pg.get_by_role('button', name='Encerrar turno').click()


def test_celular_compartilhado_nao_mistura_os_envios(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept())
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/passagem-de-turno/turno')
        pg.wait_for_load_state('networkidle')
        # A Ana encerra sem sinal; o sinal volta mas o envio da passagem não
        # passa (bloqueado aqui), e ela entrega o celular para a Mariana.
        ctx.set_offline(True)
        _encerrar_passagem_sem_navegar(pg, '1º Turno')
        pg.wait_for_selector('.fila-selo:not([hidden])', timeout=10000)
        ctx.route('**/passagem-de-turno/api/turnos', lambda rota: rota.abort())
        ctx.set_offline(False)
        pg.goto(servidor['base'] + '/app/')
        pg.locator('.fc-app-pessoa').click()
        pg.get_by_role('button', name='Sair / trocar de pessoa').click()
        pg.wait_for_url('**/login**')
        ctx.unroute('**/passagem-de-turno/api/turnos')
        entrar(pg, servidor['base'], 'mariana@e2e.test')
        pg.evaluate('window.TrinoFila && window.TrinoFila.enviarAgora()')
        pg.wait_for_timeout(2500)
        assert _turnos(servidor, 'mariana@e2e.test') == []
        assert _turnos(servidor, 'ana@e2e.test') == []
        # A Ana volta: o envio dela sobe, em nome dela, uma vez.
        pg.locator('.fc-app-pessoa').click()
        pg.get_by_role('button', name='Sair / trocar de pessoa').click()
        pg.wait_for_url('**/login**')
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.evaluate('window.TrinoFila.enviarAgora()')
        esperar(pg, "!document.querySelector('.fila-selo') || "
                             "document.querySelector('.fila-selo').hidden", timeout=15000)
        assert _turnos(servidor, 'ana@e2e.test') == [('1º Turno',)]
        assert _turnos(servidor, 'mariana@e2e.test') == []
    finally:
        b.close()
