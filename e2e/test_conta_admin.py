"""O Início, os avisos, a segurança da conta, a troca de senha e as pessoas e
os locais do administrador, num navegador de verdade (celular e PC), nas
telas antigas e nas novas (React, Fase 6a: os mesmos endereços abaixo de
``/novo``). Os recados são os mesmos nas duas, o segredo da segunda etapa e
a senha temporária não voltam depois de sair da tela, e nenhuma tela rola de
lado. O login continua no servidor nas duas."""
import re
import sqlite3
from datetime import datetime

from conftest import abrir, abrir_contexto, entrar, esperar, tela_pronta
from servidor import SENHA


def _sem_rolagem(pg, onde):
    # Mede só com a página inteira carregada: com a máquina ocupada, o CSS
    # ainda chegando deixa a tabela sem estilo, mais larga que a tela.
    pg.wait_for_load_state('load')
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{onde} rola de lado ({largura}px)'


def _recado(pg, texto, nome):
    pg.wait_for_selector(f'.alert:has-text("{texto}")')
    tela_pronta(pg, nome)


def _guardado(pg):
    """Tudo o que a tela deixou no aparelho e no histórico."""
    return pg.evaluate('JSON.stringify([history.state, Object.entries(localStorage),'
                       ' Object.entries(sessionStorage)])')


def _avisar(servidor, email, titulo, link):
    [(uid,)] = servidor['sql']('SELECT id FROM users WHERE email_index = ?',
                               servidor['indice'](email))
    con = sqlite3.connect(servidor['banco'])
    try:
        con.execute("INSERT INTO notifications (user_id, notification_type, title, message, link,"
                    " status, created_at) VALUES (?, 'geral', ?, 'Veja no sistema.', ?, 'unread', ?)",
                    (uid, titulo, link, datetime.utcnow().isoformat(sep=' ')))
        con.commit()
    finally:
        con.close()


def test_o_inicio_e_os_avisos(servidor, navegador, perfil, conta):
    base = servidor['base']
    _avisar(servidor, 'admin@e2e.test', 'Chamado novo no GL', '/chamados/')
    _avisar(servidor, 'admin@e2e.test', 'Pendência da noite', '/passagem-de-turno/')
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + conta + '/', 'inicio')
        assert pg.get_by_role('heading', name='Olá, Administrador').is_visible()
        assert pg.get_by_role('heading', name='O que espera você hoje').is_visible()
        assert pg.locator('text=Primeiros passos do administrador').is_visible()
        _sem_rolagem(pg, 'o início')
        pg.get_by_role('link', name='Ver a fila inteira').click()
        pg.wait_for_url(f'**{conta}/demandas/')

        abrir(pg, base + conta + '/avisos', 'avisos')
        assert pg.locator('.fc-aviso.nao-lido').count() == 2
        _sem_rolagem(pg, 'os avisos')
        pg.get_by_role('button', name='Marcar todos como lidos').click()
        esperar(pg, "document.querySelectorAll('.fc-aviso').length === 2 && "
                    "document.querySelectorAll('.fc-aviso.nao-lido').length === 0")
        tela_pronta(pg, 'avisos')
        assert pg.get_by_role('button', name='Marcar todos como lidos').count() == 0
        assert servidor['sql']("SELECT count(*) FROM notifications WHERE status = 'unread' "
                               "AND title IN ('Chamado novo no GL', 'Pendência da noite')") == [(0,)]
        # Abrir o aviso leva ao link dele (na tela nova, à tela nova).
        pg.locator('.fc-aviso', has_text='Chamado novo no GL').click()
        pg.wait_for_url(f'**{conta}/chamados/')
    finally:
        b.close()


def test_a_segunda_etapa_e_a_troca_de_senha(servidor, navegador, perfil, conta):
    from facilities.core import totp
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'sueli@e2e.test')
        abrir(pg, base + conta + '/conta/seguranca', 'seguranca')
        segredo = pg.locator('code.user-select-all').inner_text().strip()
        assert re.fullmatch(r'[A-Z2-7]{32}', segredo)
        assert pg.locator('.fc-qr-totp').bounding_box()['width'] > 100
        _sem_rolagem(pg, 'a segurança da conta')
        # Ativar pede a senha atual: com ela errada, nada muda.
        assert pg.get_by_label('Sua senha atual').get_attribute('type') == 'password'
        pg.fill('#codigo', totp.codigo(segredo))
        pg.fill('#senha', 'senha-errada')
        pg.get_by_role('button', name='Ativar a segunda etapa').click()
        _recado(pg, 'A senha atual não confere.', 'seguranca')
        pg.fill('#codigo', '000000')
        pg.fill('#senha', SENHA)
        pg.get_by_role('button', name='Ativar a segunda etapa').click()
        _recado(pg, 'O código não confere.', 'seguranca')
        # O mesmo segredo depois da recusa.
        assert pg.locator('code.user-select-all').inner_text().strip() == segredo
        pg.fill('#codigo', totp.codigo(segredo))
        pg.fill('#senha', SENHA)
        pg.get_by_role('button', name='Ativar a segunda etapa').click()
        _recado(pg, 'Segunda etapa ativada. A partir de agora', 'seguranca')
        assert pg.locator('text=Segunda etapa ativada.').first.is_visible()
        assert pg.locator('code.user-select-all').count() == 0
        assert segredo not in pg.content() and segredo not in _guardado(pg)
        assert servidor['sql']('SELECT totp_ativo FROM users WHERE email_index = ?',
                               servidor['indice']('sueli@e2e.test')) == [(1,)]
        pg.fill('#senha', 'senha-errada')
        pg.get_by_role('button', name='Desativar a segunda etapa').click()
        _recado(pg, 'A senha não confere.', 'seguranca')
        pg.fill('#senha', SENHA)
        pg.get_by_role('button', name='Desativar a segunda etapa').click()
        _recado(pg, 'Segunda etapa desativada.', 'seguranca')

        abrir(pg, base + conta + '/trocar-senha', 'trocar-senha')
        _sem_rolagem(pg, 'a troca de senha')
        pg.fill('#atual', 'senha-errada')
        pg.fill('#nova', 'Nova-senha-do-e2e-7')
        pg.fill('#confirma', 'Nova-senha-do-e2e-7')
        pg.get_by_role('button', name='Salvar senha').click()
        _recado(pg, 'A senha atual não confere.', 'trocar-senha')
        pg.fill('#atual', SENHA)
        pg.fill('#nova', 'Nova-senha-do-e2e-7')
        pg.fill('#confirma', 'Nova-senha-do-e2e-7')
        pg.get_by_role('button', name='Salvar senha').click()
        # (O roteador das telas novas escreve o Início como /novo, sem a barra.)
        pg.wait_for_url(re.compile(re.escape(base + conta) + '/?$'))
        _recado(pg, 'Senha trocada.', 'inicio')
        # A senha nova abre o sistema noutro aparelho.
        outra = ctx.browser.new_context().new_page()
        outra.goto(base + '/login')
        outra.fill('input[name=email]', 'sueli@e2e.test')
        outra.fill('input[name=password]', 'Nova-senha-do-e2e-7')
        outra.click('button[type=submit]')
        outra.wait_for_load_state('networkidle')
        assert '/login' not in outra.url
    finally:
        b.close()


def _senha_do_recado(pg):
    texto = pg.locator('.alert-success', has_text='Senha temporária').first.inner_text()
    return re.search(r'Senha temporária(?: de [^:]+)?: (\S+)', texto).group(1)


def test_as_pessoas_e_os_locais(servidor, navegador, perfil, conta):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + conta + '/admin/usuarios', 'pessoas')
        assert pg.get_by_role('heading', name='Pessoas').is_visible()
        _sem_rolagem(pg, 'as pessoas')
        pg.locator('summary', has_text='Cadastrar pessoa').click()
        novo = pg.locator('details', has=pg.locator('summary', has_text='Cadastrar pessoa'))
        novo.locator('input[name=name]').fill('Paula do E2E')
        novo.locator('input[name=email]').fill('paula@e2e.test')
        novo.locator('select[name=role]').select_option('supervisor')
        novo.locator('label', has_text='GL Armazém 1').locator('input').check()
        novo.get_by_role('button', name='Cadastrar').click()
        _recado(pg, 'Cadastro de Paula do E2E criado. Senha temporária:', 'pessoas')
        senha = _senha_do_recado(pg)
        assert re.fullmatch(r'[a-km-zA-HJ-NP-Z2-9]{12}', senha)
        if conta:
            assert senha not in _guardado(pg)
        # A senha temporária abre o sistema e pede a troca.
        outra = ctx.browser.new_context().new_page()
        outra.goto(base + '/login')
        outra.fill('input[name=email]', 'paula@e2e.test')
        outra.fill('input[name=password]', senha)
        outra.click('button[type=submit]')
        outra.wait_for_url('**/trocar-senha')
        # Saiu da tela e voltou: a senha não aparece de novo.
        abrir(pg, base + conta + '/admin/contratos', 'locais')
        abrir(pg, base + conta + '/admin/usuarios', 'pessoas')
        assert pg.locator('.alert', has_text='Senha temporária').count() == 0
        assert senha not in pg.content()

        paula = pg.locator('details', has=pg.locator('summary', has_text='Paula do E2E'))
        paula.locator('summary').click()
        paula.locator('input[name=name]').fill('Paula Editada')
        paula.get_by_role('button', name='Salvar').click()
        _recado(pg, 'Cadastro de Paula Editada atualizado.', 'pessoas')
        paula = pg.locator('details', has=pg.locator('summary', has_text='Paula Editada'))
        paula.locator('summary').click()
        # Gerar a senha pede a senha do próprio administrador: errada, nada muda.
        gerar = paula.locator('form', has=pg.get_by_role('button', name='Gerar senha temporária'))
        gerar.get_by_label('Sua senha atual').fill('senha-errada')
        pg.once('dialog', lambda d: d.accept())
        paula.get_by_role('button', name='Gerar senha temporária').click()
        _recado(pg, 'A sua senha não confere. Nada foi alterado.', 'pessoas')
        paula = pg.locator('details', has=pg.locator('summary', has_text='Paula Editada'))
        if paula.get_attribute('open') is None:
            paula.locator('summary').click()
        gerar = paula.locator('form', has=pg.get_by_role('button', name='Gerar senha temporária'))
        gerar.get_by_label('Sua senha atual').fill(SENHA)
        pg.once('dialog', lambda d: d.accept())
        paula.get_by_role('button', name='Gerar senha temporária').click()
        _recado(pg, 'Senha temporária de Paula Editada:', 'pessoas')
        assert _senha_do_recado(pg) != senha

        abrir(pg, base + conta + '/admin/contratos', 'locais')
        assert pg.get_by_role('heading', name='Locais').is_visible()
        _sem_rolagem(pg, 'os locais')
        pg.locator('summary', has_text='Cadastrar local').click()
        cad = pg.locator('details', has=pg.locator('summary', has_text='Cadastrar local'))
        cad.locator('input[name=name]').fill('CD do E2E')
        cad.locator('input[name=cost_center]').fill('E2E-01')
        cad.get_by_role('button', name='Cadastrar').click()
        _recado(pg, 'Local CD do E2E cadastrado.', 'locais')
        local = pg.locator('details', has=pg.locator('summary', has_text='CD do E2E'))
        local.locator('summary').click()
        assert local.locator('text=CC E2E-01').count() == 1
        _sem_rolagem(pg, 'os locais abertos')
        local.get_by_role('link', name='Estrutura (setores, ambientes, QR)').click()
        pg.wait_for_url(f'**{conta}/cadastros/locais/*')
    finally:
        b.close()
