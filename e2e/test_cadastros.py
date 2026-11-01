"""Os cadastros num navegador de verdade (celular e PC), nas telas antigas e
nas novas (React, Fase 3a: os mesmos endereços abaixo de ``/novo``):

* o administrador cadastra a empresa e o cliente, ativa um estado, monta a
  estrutura do local (setor, ambiente, ponto), desativa e vê o histórico;
* o gerente gera um link novo para um convite e cancela outro;
* nenhuma tela dos cadastros rola de lado.
"""
from conftest import abrir, abrir_contexto, entrar, tela_pronta


def _sem_rolagem_lateral(pg, onde):
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{onde} rola de lado ({largura}px)'


def _abrir_resumo(pg, texto):
    """Abre o ``<details>`` (o formulário recolhido) com este resumo."""
    resumo = pg.locator('summary', has_text=texto).first
    if resumo.evaluate('s => !s.parentElement.open'):
        resumo.click()


def test_administrador_cadastra_e_monta_a_estrutura(servidor, navegador, perfil, cadastros):
    base = servidor['base']
    [(cid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + cadastros + '/cadastros/', 'cadastros')
        _sem_rolagem_lateral(pg, 'início dos cadastros')

        # A empresa: da lista do início, sem sair da tela (nova ou antiga).
        pg.locator('.fc-conteudo .fc-modulo', has_text='Empresas do grupo').click()
        tela_pronta(pg, 'empresas')
        _abrir_resumo(pg, 'Cadastrar empresa')
        pg.fill('#enome', 'Trino Limpeza ' + perfil)
        pg.get_by_role('button', name='Cadastrar', exact=True).click()
        pg.wait_for_selector(f'text=Empresa Trino Limpeza {perfil} cadastrada.')
        assert ('/novo/' in pg.url) == bool(cadastros)
        # O mesmo nome de novo: a recusa, com a frase da regra.
        _abrir_resumo(pg, 'Cadastrar empresa')
        pg.fill('#enome', 'trino limpeza ' + perfil)
        pg.get_by_role('button', name='Cadastrar', exact=True).click()
        pg.wait_for_selector('text=Já existe uma empresa com este nome.')
        _sem_rolagem_lateral(pg, 'empresas')

        # O cliente, atendido pela empresa nova.
        abrir(pg, base + cadastros + '/cadastros/clientes', 'clientes')
        _abrir_resumo(pg, 'Cadastrar cliente')
        pg.fill('#cnomenovo', 'Cliente E2E ' + perfil)
        pg.select_option('#cempnovo', label='Trino Limpeza ' + perfil)
        pg.locator('form', has=pg.locator('#cnomenovo')).get_by_role('button', name='Cadastrar').click()
        pg.wait_for_selector(f'text=Cliente Cliente E2E {perfil} cadastrado.')
        _sem_rolagem_lateral(pg, 'clientes')

        # Um estado em uso a mais.
        abrir(pg, base + cadastros + '/cadastros/estados', 'estados')
        pg.locator('form', has_text='Sergipe').get_by_role('button', name='Ativar').click()
        pg.wait_for_selector('text=Sergipe ativado.')
        assert servidor['sql']("SELECT is_active FROM estados WHERE sigla = 'SE'") == [(1,)]
        _sem_rolagem_lateral(pg, 'estados')

        # A estrutura do local: setor, ambiente e ponto; depois desativar.
        abrir(pg, base + cadastros + '/cadastros/', 'cadastros')
        pg.locator('.fc-conteudo').get_by_role('link', name='GL Armazém 1').first.click()
        tela_pronta(pg, 'local')
        _abrir_resumo(pg, 'Cadastrar setor')
        pg.fill('#snovo', 'Armazém ' + perfil)
        pg.locator('form', has=pg.locator('#snovo')).get_by_role('button', name='Cadastrar').click()
        pg.wait_for_selector(f'text=Setor "Armazém {perfil}" cadastrado.')
        secao = pg.locator('section', has=pg.get_by_role('heading', name='Armazém ' + perfil))
        secao.locator('summary', has_text='+ Cadastrar ambiente neste setor').click()
        secao.get_by_label('Nome do ambiente').fill('Doca 1')
        secao.get_by_role('button', name='Cadastrar ambiente').click()
        pg.wait_for_selector('text=Ambiente "Doca 1" cadastrado.')
        secao = pg.locator('section', has=pg.get_by_role('heading', name='Armazém ' + perfil))
        secao.locator('summary', has_text='+ Cadastrar ponto').click()
        secao.get_by_label('Ponto', exact=True).fill('Portão da doca')
        secao.get_by_role('button', name='Cadastrar ponto').click()
        pg.wait_for_selector('text=Ponto "Portão da doca" cadastrado.')
        _sem_rolagem_lateral(pg, 'estrutura do local')
        secao = pg.locator('section', has=pg.get_by_role('heading', name='Armazém ' + perfil))
        secao.get_by_role('button', name='Desativar').first.click()
        pg.wait_for_selector('text=Setor desativado (com o que estava dentro dele).')
        assert not pg.get_by_role('heading', name='Armazém ' + perfil).count()
        pg.locator('.fc-conteudo').get_by_role('link', name='Mostrar os desativados').click()
        pg.get_by_role('heading', name='Armazém ' + perfil).wait_for()
        assert pg.locator('section', has=pg.get_by_role('heading', name='Armazém ' + perfil)) \
            .get_by_text('desativado').first.is_visible()
        assert servidor['sql']("SELECT is_active FROM pontos_inspecao WHERE nome = 'Portão da doca'") == [(0,)]

        # O histórico do local: quem desativou, com o antes e o depois.
        pg.locator('.fc-conteudo').get_by_role('link', name='Histórico').click()
        tela_pronta(pg, 'trilha')
        pg.get_by_role('heading', name='Histórico de alterações — GL Armazém 1').wait_for()
        assert pg.get_by_text('Desativado').first.is_visible()
        assert pg.locator('code', has_text='is_active').first.is_visible()
        _sem_rolagem_lateral(pg, 'histórico do local')
        # O do grupo, com o filtro por tipo.
        abrir(pg, base + cadastros + '/cadastros/trilha', 'trilha')
        pg.select_option('#fent', label='Empresa')
        pg.get_by_role('button', name='Filtrar').click()
        pg.wait_for_url('**entidade=empresa')
        tela_pronta(pg, 'trilha')
        pg.locator('li', has_text=f'Trino Limpeza {perfil}').first.wait_for()
        assert pg.locator('.badge', has_text='Empresa').count() >= 1
        assert pg.locator('.badge', has_text='Cliente').count() == 0
        assert cid
    finally:
        b.close()


def test_gerente_gera_link_novo_e_cancela_convite(servidor, navegador, perfil, cadastros):
    base = servidor['base']
    [(cid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'gerente@e2e.test')
        for nome in ('Paulo Porteiro', 'Rita Recepção'):
            abrir(pg, base + cadastros + f'/novo-contrato/{cid}/equipe', 'equipe')
            pg.fill('#nome', nome)
            pg.fill('#email', nome.split()[0].lower() + f'.{perfil}@e2e.test')
            pg.click('button:has-text("Criar convite")')
            pg.wait_for_load_state('networkidle')
            tela_pronta(pg, 'convite-criado')
            pg.get_by_role('heading', name='Convite pronto').wait_for()
        primeiro = pg.input_value('#link')
        pg.get_by_role('link', name='Meus convites').click()
        tela_pronta(pg, 'convites')
        _sem_rolagem_lateral(pg, 'convites')
        assert pg.locator('.badge', has_text='aguardando').count() == 2
        # Link novo: a mesma página "Convite pronto", com outro link.
        pg.locator('div.border-top', has_text='Rita Recepção').get_by_role('button', name='Gerar link novo').click()
        pg.wait_for_load_state('networkidle')
        tela_pronta(pg, 'convite-criado')
        pg.get_by_role('heading', name='Convite pronto').wait_for()
        assert pg.input_value('#link') != primeiro and '/convite/' in pg.input_value('#link')
        assert not pg.get_by_role('link', name='Convidar outra pessoa').count()
        # Cancelar o outro.
        pg.get_by_role('link', name='Meus convites').click()
        tela_pronta(pg, 'convites')
        pg.locator('div.border-top', has_text='Paulo Porteiro').get_by_role('button', name='Cancelar convite').click()
        pg.wait_for_selector('text=Convite de Paulo Porteiro cancelado: o link não abre mais.')
        assert pg.locator('div.border-top', has_text='Paulo Porteiro').locator('.badge').inner_text() == 'cancelado'
        _sem_rolagem_lateral(pg, 'convites')
    finally:
        b.close()


def test_telas_do_cadastro_simplificado_sem_rolagem_lateral(servidor, navegador, perfil, cadastros):
    """O início, a estrutura, as áreas, as rotas e os passos do novo contrato:
    nenhuma rola de lado, e no máximo um item do menu fica marcado."""
    base = servidor['base']
    [(cid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    [(ctid,)] = servidor['sql']("SELECT id FROM contratantes WHERE nome = 'Grupo GL'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        for caminho, nome in (('/cadastros/', 'cadastros'), (f'/cadastros/locais/{cid}', 'local'),
                              ('/clientes', 'centros-clientes'), (f'/clientes/{ctid}', 'centros-cliente'),
                              (f'/centros/{cid}', 'centro'), (f'/centros/{cid}?aba=rotas', 'centro'),
                              ('/novo-contrato', 'novo-contrato'),
                              (f'/novo-contrato/cliente/{ctid}/local', 'novo-local'),
                              (f'/novo-contrato/{cid}/estrutura', 'estrutura'),
                              (f'/novo-contrato/{cid}/equipe', 'equipe'), ('/convites', 'convites')):
            abrir(pg, base + cadastros + caminho, nome)
            pg.wait_for_load_state('networkidle')
            _sem_rolagem_lateral(pg, caminho)
            assert pg.locator('.fc-lat-item.ativo').count() <= 1
    finally:
        b.close()
