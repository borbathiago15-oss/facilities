"""Os relatórios do cliente, o painel e as chaves da integração na gestão,
num navegador de verdade (celular e PC), nas telas antigas e nas novas
(React, Fase 4c: os mesmos endereços abaixo de ``/novo``): o administrador
abre o mês passado, deixa um recado, libera e recolhe o relatório; filtra o
painel por período; cria uma chave da integração (que aparece uma vez só e
não volta depois de sair da tela) e a revoga. Os recados são os mesmos nas
duas, e nenhuma tela rola de lado."""
from datetime import date, timedelta

from conftest import abrir, abrir_contexto, entrar


def _sem_rolagem(pg, onde):
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{onde} rola de lado ({largura}px)'


def _pronta(pg, nome):
    if '/novo/' in pg.url:
        pg.wait_for_selector(f'[data-tela-pronta="{nome}"]', state='attached')


def _enviar(pg, botao, recado, nome):
    # (sem ``exact``: o ícone do Bootstrap entra no nome do botão)
    pg.get_by_role('button', name=botao).click()
    pg.wait_for_selector(f'.alert:has-text("{recado}")')
    _pronta(pg, nome)


def test_o_relatorio_do_cliente(servidor, navegador, perfil, relatorios):
    base = servidor['base']
    [(lid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    passado = (date.today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + relatorios + '/relatorios/', 'relatorios')
        _sem_rolagem(pg, 'os relatórios')
        assert pg.get_by_role('heading', name='Relatório do cliente').is_visible()
        pg.locator('.fc-fila-item', has_text='GL Armazém 1').click()
        pg.wait_for_url(f'**{relatorios}/relatorios/cliente/{lid}/{passado}')
        _pronta(pg, 'relatorio-cliente')
        assert pg.get_by_role('heading', name='GL Armazém 1').is_visible()
        assert pg.locator('text=ainda não liberado ao cliente').count() == 1
        # O PDF continua no servidor (o mesmo endereço nas duas telas).
        assert pg.get_by_role('link', name='PDF').get_attribute('href') == \
            f'/relatorios/cliente/{lid}/{passado}/arquivo.pdf'
        _sem_rolagem(pg, 'o relatório')
        pg.fill('#recado', 'Reforçamos a limpeza do 2º andar.')
        _enviar(pg, 'Salvar recado', 'Recado salvo.', 'relatorio-cliente')
        assert pg.locator('.fc-rel-recado', has_text='Reforçamos a limpeza do 2º andar.').count() == 1
        _enviar(pg, 'Liberar para o cliente', 'Relatório liberado', 'relatorio-cliente')
        assert pg.locator('text=liberado ao cliente em').count() == 1
        assert servidor['sql']('SELECT liberado_em IS NOT NULL FROM relatorios_cliente '
                               'WHERE client_id = ?', lid) == [(1,)]
        _enviar(pg, 'Recolher do portal', 'Relatório recolhido', 'relatorio-cliente')
        assert servidor['sql']('SELECT liberado_em IS NULL FROM relatorios_cliente '
                               'WHERE client_id = ?', lid) == [(1,)]
        pg.locator('.breadcrumb').get_by_role('link', name='Relatórios').click()
        pg.wait_for_url(f'**{relatorios}/relatorios/?mes={passado}')
        _pronta(pg, 'relatorios')
    finally:
        b.close()


def test_o_painel_por_periodo(servidor, navegador, perfil, relatorios):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + relatorios + '/painel', 'painel')
        _sem_rolagem(pg, 'o painel')
        pg.fill('#pde', '2026-01-01')
        pg.fill('#pate', '2026-01-31')
        pg.get_by_role('button', name='Ver').click()
        pg.wait_for_url('**/painel?de=2026-01-01&ate=2026-01-31')
        _pronta(pg, 'painel')
        assert pg.locator('text=O período vai de 01/01/2026 a 31/01/2026.').count() == 1
        assert pg.locator('text=GL Armazém 1').count() >= 1
    finally:
        b.close()


def test_a_chave_da_integracao(servidor, navegador, perfil, relatorios):
    base = servidor['base']
    nome = f'Intelligence {perfil} {relatorios or "antiga"}'
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + relatorios + '/admin/integracao/', 'integracao')
        _sem_rolagem(pg, 'a integração')
        pg.locator('summary', has_text='Criar chave').click()
        pg.fill('#kn', nome)
        pg.check('input[name=todos]')
        pg.get_by_role('button', name='Criar chave').click()
        pg.wait_for_selector('.alert:has-text("Copie agora")')
        texto = pg.locator('.alert code').inner_text().strip()
        assert texto.startswith('fac_')
        # Nada da chave no endereço, no histórico nem no aparelho.
        assert texto not in pg.url
        guardado = pg.evaluate('JSON.stringify([history.state, Object.entries(localStorage), '
                               'Object.entries(sessionStorage)])')
        assert texto not in guardado
        _pronta(pg, 'integracao')
        assert pg.locator('.border-top', has_text=nome).count() == 1
        # Saiu e voltou: a chave não aparece de novo.
        abrir(pg, base + relatorios + '/painel', 'painel')
        abrir(pg, base + relatorios + '/admin/integracao/', 'integracao')
        assert pg.locator('text=Copie agora').count() == 0
        assert texto not in pg.content()
        linha = pg.locator('.border-top', has_text=nome)
        linha.get_by_role('button', name='Revogar').click()
        pg.wait_for_selector(f'.alert:has-text("Chave \\"{nome}\\" revogada")')
        _pronta(pg, 'integracao')
        assert pg.locator('.border-top', has_text=nome).locator('text=revogada').count() == 1
        assert servidor['sql']('SELECT is_active FROM integracao_chaves WHERE nome = ?', nome) == [(0,)]
        _sem_rolagem(pg, 'a integração depois dos envios')
    finally:
        b.close()
