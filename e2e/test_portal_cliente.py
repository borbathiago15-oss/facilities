"""Fase 9B — o cliente ativa a segunda etapa, vê o local, cobra e encerra;
a coordenação responde. Nos dois formatos, sem rolagem lateral, nas telas
antigas e nas novas (React, Fase 5: os mesmos endereços abaixo de
``/novo``): o portal do cliente e a cobrança vista pela equipe."""
import re
from datetime import timedelta

from conftest import abrir, abrir_contexto, entrar, tela_pronta


def _sem_rolagem_lateral(pg):
    # Mede só com a página inteira carregada: com a máquina ocupada, o CSS
    # ainda chegando deixa a tabela sem estilo, mais larga que a tela.
    pg.wait_for_load_state('load')
    assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']


def test_cliente_cobra_e_a_coordenacao_responde(servidor, navegador, perfil, portal):
    from facilities import tempo
    from facilities.core import totp
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    b2, ctx2 = abrir_contexto(navegador, perfil)
    try:
        cli = ctx.new_page()
        entrar(cli, base, 'cliente@e2e.test')
        # Sem a segunda etapa, o portal manda para a tela de segurança.
        assert '/conta/seguranca' in cli.url
        segredo = cli.locator('code.user-select-all').inner_text().strip()
        cli.fill('#codigo', totp.codigo(segredo))
        cli.click('button:has-text("Ativar a segunda etapa")')
        cli.goto(base + '/')
        assert cli.url.endswith('/cliente/')
        abrir(cli, base + portal + '/cliente/', 'portal-inicio')
        assert cli.get_by_role('heading', name='Seus locais').is_visible()
        assert cli.locator('text=GL Armazém 1').count() >= 1
        _sem_rolagem_lateral(cli)
        cli.click('text=GL Armazém 1')
        cli.wait_for_url(f'**{portal}/cliente/locais/*')
        tela_pronta(cli, 'portal-local')
        assert cli.get_by_role('heading', name='Indicadores').is_visible()
        _sem_rolagem_lateral(cli)

        # A aba dos avisos pelo QR e a volta às cobranças.
        abrir(cli, base + portal + '/cliente/cobrancas', 'portal-cobrancas')
        cli.locator('.nav-tabs').get_by_role('link', name='Avisos pelo QR').click()
        cli.wait_for_url('**/cliente/cobrancas?aba=qr')
        tela_pronta(cli, 'portal-avisos-qr')
        assert cli.get_by_role('link', name='Todos').is_visible()
        _sem_rolagem_lateral(cli)
        cli.locator('.nav-tabs').get_by_role('link', name='Cobranças').click()
        cli.wait_for_url(f'**{portal}/cliente/cobrancas')
        tela_pronta(cli, 'portal-cobrancas')

        prazo = (tempo.hoje() + timedelta(days=3)).isoformat()
        cli.fill('#cprazo', prazo)
        cli.fill('#ctit', 'Vidros da recepção')
        cli.fill('#ctex', 'Os vidros estão manchados desde segunda.')
        cli.click('button:has-text("Enviar à coordenação")')
        cli.wait_for_selector('.alert:has-text("enviada à coordenação do contrato")')
        cli.wait_for_url(f'**{portal}/cliente/cobrancas/*')
        tela_pronta(cli, 'portal-cobranca')
        assert cli.locator('text=Aguardando a coordenação').count() >= 1
        numero = int(re.search(r'/cliente/cobrancas/(\d+)', cli.url).group(1))
        _sem_rolagem_lateral(cli)

        adm = ctx2.new_page()
        entrar(adm, base, 'admin@e2e.test')
        adm.goto(base + '/demandas/?tipo=cobranca')
        assert adm.locator('text=Vidros da recepção').count() == 1
        abrir(adm, base + portal + '/cobrancas/', 'cobrancas')
        adm.locator('a', has_text='Vidros da recepção').click()
        adm.wait_for_url(f'**{portal}/cobrancas/{numero}')
        tela_pronta(adm, 'cobranca')
        _sem_rolagem_lateral(adm)
        adm.fill('#rtex', 'Vidros limpos hoje às 15h.')
        adm.click('button:has-text("Responder")')
        adm.wait_for_selector('.alert:has-text("Resposta enviada")')
        tela_pronta(adm, 'cobranca')
        assert adm.locator('text=Esperando o cliente confirmar').count() == 1

        cli.reload()
        tela_pronta(cli, 'portal-cobranca')
        assert cli.locator('text=Vidros limpos hoje às 15h.').count() == 1
        assert cli.locator('text=Administrador').count() == 0
        cli.click('button:has-text("Confirmar e encerrar")')
        cli.wait_for_selector('.alert:has-text("Cobrança encerrada")')
        assert cli.locator('text=Cobrança encerrada').count() == 1
        assert servidor['sql']('SELECT status FROM cobrancas WHERE id = ?', numero) == \
            [('fechada',)]
        # A equipe abre o site; o cliente não (nem nas telas novas).
        cli.goto(base + portal + '/chamados/')
        assert cli.locator('text=Esta parte do sistema é da equipe da Trino').count() == 1
    finally:
        b.close()
        b2.close()
