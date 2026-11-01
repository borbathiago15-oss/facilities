"""Fase 1c — as telas do campo abrem SEM sinal, da cópia do aparelho.

* o turno aberto com sinal reabre sem sinal (tela antiga e nova); a nova
  avisa que é a cópia das HH:MM;
* celular compartilhado: depois de sair e entrar outra pessoa, nada da
  primeira aparece sem sinal;
* tela da gestão nunca abre da cópia.
"""
import re

from conftest import abrir, abrir_contexto, entrar, esperar, tela_pronta

COPIAS = ("caches.open('trino-telas').then((c) => c.keys())"
          ".then((k) => k.map((r) => new URL(r.url).pathname))")


def _sem_sinal(ctx, servidor):
    """A página fica sem rede (o selo) e o servidor sai do ar (o service
    worker, que o ``set_offline`` não alcança)."""
    ctx.set_offline(True)
    servidor['desligar']()


def _com_sinal(ctx, servidor):
    servidor['religar']()
    ctx.set_offline(False)


def _com_service_worker(pg):
    esperar(pg, '!!(navigator.serviceWorker && navigator.serviceWorker.controller)')


def test_o_turno_abre_da_copia_sem_sinal(servidor, navegador, perfil, campo):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        _com_service_worker(pg)
        # Com sinal, as três telas abrem uma vez (é aí que a cópia é guardada).
        pg.goto(servidor['base'] + campo + '/')
        pg.wait_for_load_state('networkidle')
        abrir(pg, servidor['base'] + campo + '/ler-qr', 'ler-qr')
        abrir(pg, servidor['base'] + campo + '/turno')
        pg.wait_for_load_state('networkidle')
        assert pg.locator('.fc-local-turno').count() == 2
        _sem_sinal(ctx, servidor)
        pg.reload()
        tela_pronta(pg)
        assert pg.locator('.fc-local-turno').count() == 2
        assert pg.get_by_text('GL Armazém 2').first.is_visible()
        assert pg.locator('.fc-app-rede', has_text='Sem sinal').is_visible()
        if '/novo/' in campo:
            aviso = pg.get_by_test_id('aviso-de-copia')
            assert re.search(r'cópia guardada neste aparelho às \d\d:\d\d', aviso.inner_text())
        # O início e o leitor também abrem.
        abrir(pg, servidor['base'] + campo + '/ler-qr', 'ler-qr')
        assert pg.locator('.fc-app-nav').is_visible()
        pg.goto(servidor['base'] + campo + '/')
        pg.get_by_text('Ler o QR do local').first.wait_for()
        _com_sinal(ctx, servidor)
        # Com sinal de novo, a tela vem da rede e o aviso some.
        abrir(pg, servidor['base'] + campo + '/turno')
        assert pg.get_by_test_id('aviso-de-copia').count() == 0
    finally:
        b.close()


def test_celular_compartilhado_nao_mostra_a_copia_de_quem_saiu(servidor, navegador, perfil, campo):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        _com_service_worker(pg)
        abrir(pg, servidor['base'] + campo + '/turno')
        pg.wait_for_load_state('networkidle')
        assert pg.evaluate(COPIAS), 'a cópia do turno da Ana não foi guardada'
        pg.locator('.fc-app-pessoa').click()
        pg.get_by_role('button', name='Sair / trocar de pessoa').click()
        pg.wait_for_url('**/login**')
        entrar(pg, servidor['base'], 'mariana@e2e.test')
        # A tela de login apagou as cópias da Ana (a de agora é da Mariana).
        assert not [c for c in pg.evaluate(COPIAS) if 'turno' in c or c.startswith('/api/')]
        # Sem sinal, antes de a Mariana abrir o turno: nada da Ana.
        _sem_sinal(ctx, servidor)
        pg.goto(servidor['base'] + campo + '/turno')
        pg.wait_for_timeout(1500)
        assert 'Ana Souza' not in pg.content() and 'GL Armazém 2' not in pg.content()
        # A Mariana abre o turno com sinal; sem sinal, vê o dela, não o da Ana.
        _com_sinal(ctx, servidor)
        abrir(pg, servidor['base'] + campo + '/turno')
        pg.wait_for_load_state('networkidle')
        _sem_sinal(ctx, servidor)
        pg.reload()
        tela_pronta(pg)
        assert pg.get_by_text('GL Armazém 1').first.is_visible()
        # (O nome da Ana pode aparecer como escalada de uma tarefa do local que
        # as duas dividem — isso é da Mariana ver. O segundo local, só da Ana, não.)
        assert 'Mariana' in pg.locator('.fc-app-pessoa').inner_text()
        assert 'GL Armazém 2' not in pg.content()
    finally:
        b.close()


def test_tela_da_gestao_nunca_abre_da_copia(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'admin@e2e.test')
        _com_service_worker(pg)
        for tela in ('/novo/', '/novo/admin/armazenamento'):
            pg.goto(servidor['base'] + tela)
            pg.wait_for_load_state('networkidle')
        # Nem a tela, nem os dados que ela buscou (/api/v1/eu, /api/v1/admin…).
        assert pg.evaluate(COPIAS) == []
        _sem_sinal(ctx, servidor)
        pg.reload()
        assert pg.get_by_role('heading', name='Sem conexão').is_visible()
        assert 'Armazenamento' not in pg.content()
    finally:
        b.close()


def test_a_nova_passagem_abre_da_copia_sem_sinal(servidor, navegador, perfil, passagem):
    """A nova passagem de turno abre sem sinal nas duas telas (a antiga já
    abria: sw.js, Fase 3); a nova diz que é a cópia das HH:MM. Encerrar sem
    sinal guarda na fila do aparelho. Quem sai do sistema leva a cópia junto."""
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept())
        entrar(pg, servidor['base'], 'ana@e2e.test')
        _com_service_worker(pg)
        abrir(pg, servidor['base'] + passagem + '/turno', 'passagem')
        pg.wait_for_load_state('networkidle')
        copias = pg.evaluate(COPIAS)
        assert passagem + '/turno' in copias
        if '/novo/' in passagem:
            assert '/api/v1/passagem/turno' in copias and '/api/v1/eu' in copias
        _sem_sinal(ctx, servidor)
        pg.reload()
        tela_pronta(pg, 'passagem')
        assert pg.get_by_text('Banheiros limpos').is_visible()
        assert pg.input_value('#diario-shift') == '1º Turno'
        if '/novo/' in passagem:
            aviso = pg.get_by_test_id('aviso-de-copia')
            assert re.search(r'cópia guardada neste aparelho às \d\d:\d\d', aviso.inner_text())
        pg.get_by_role('button', name='Encerrar turno').click()
        pg.locator('.dt-guardado', has_text='Guardado neste aparelho.').wait_for(timeout=10000)
        assert pg.locator('.fila-selo:not([hidden])').count() == 1
        _com_sinal(ctx, servidor)
        pg.evaluate('window.TrinoFila.enviarAgora()')
        pg.locator('.dt-guardado.dt-enviado', has_text='Enviado.').wait_for(timeout=15000)
        assert servidor['sql']("SELECT turno, status FROM diario_operacional_turnos") == [
            ('1º Turno', 'encerrado')]
        # Sair apaga as cópias: a Mariana, no mesmo aparelho, não abre a da Ana.
        pg.goto(servidor['base'] + '/app/')
        pg.locator('.fc-app-pessoa').click()
        pg.get_by_role('button', name='Sair / trocar de pessoa').click()
        pg.wait_for_url('**/login**')
        entrar(pg, servidor['base'], 'mariana@e2e.test')
        assert not [c for c in pg.evaluate(COPIAS) if 'passagem' in c or c.startswith('/api/')]
    finally:
        b.close()
