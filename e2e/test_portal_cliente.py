"""Fase 9B — o cliente ativa a segunda etapa, vê o local, cobra e encerra;
a coordenação responde. Nos dois formatos, sem rolagem lateral."""
import re
from datetime import timedelta

from conftest import abrir_contexto, entrar


def _sem_rolagem_lateral(pg):
    assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']


def test_cliente_cobra_e_a_coordenacao_responde(servidor, navegador, perfil):
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
        assert cli.get_by_role('heading', name='Seus locais').is_visible()
        assert cli.locator('text=GL Armazém 1').count() >= 1
        _sem_rolagem_lateral(cli)
        cli.click('text=GL Armazém 1')
        assert cli.get_by_role('heading', name='Indicadores').is_visible()
        _sem_rolagem_lateral(cli)

        cli.goto(base + '/cliente/cobrancas')
        prazo = (tempo.hoje() + timedelta(days=3)).isoformat()
        cli.fill('#cprazo', prazo)
        cli.fill('#ctit', 'Vidros da recepção')
        cli.fill('#ctex', 'Os vidros estão manchados desde segunda.')
        cli.click('button:has-text("Enviar à coordenação")')
        assert cli.locator('text=Aguardando a coordenação').count() >= 1
        numero = int(re.search(r'/cliente/cobrancas/(\d+)', cli.url).group(1))
        _sem_rolagem_lateral(cli)

        adm = ctx2.new_page()
        entrar(adm, base, 'admin@e2e.test')
        adm.goto(base + '/demandas/?tipo=cobranca')
        assert adm.locator('text=Vidros da recepção').count() == 1
        adm.goto(base + f'/cobrancas/{numero}')
        adm.fill('#rtex', 'Vidros limpos hoje às 15h.')
        adm.click('button:has-text("Responder")')
        assert adm.locator('text=Esperando o cliente confirmar').count() == 1

        cli.reload()
        assert cli.locator('text=Vidros limpos hoje às 15h.').count() == 1
        assert cli.locator('text=Administrador').count() == 0
        cli.click('button:has-text("Confirmar e encerrar")')
        assert cli.locator('text=Cobrança encerrada').count() == 1
        assert servidor['sql']('SELECT status FROM cobrancas WHERE id = ?', numero) == \
            [('fechada',)]
        # A equipe abre o site; o cliente não.
        cli.goto(base + '/chamados/')
        assert cli.locator('text=Esta parte do sistema é da equipe da Trino').count() == 1
    finally:
        b.close()
        b2.close()
