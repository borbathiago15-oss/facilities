"""A rotina dos locais pela gestão, num navegador de verdade (celular e PC),
nas telas antigas e nas novas (React, Fase 3b: os mesmos endereços abaixo de
``/novo``): o checklist, a rota com atividades e escala, a biblioteca com a
rota pronta aplicada, a planilha do cliente e os feriados. Os recados são os
mesmos nas duas, e nenhuma tela rola de lado."""
from conftest import abrir, abrir_contexto, entrar


def _id(servidor, nome):
    return servidor['sql']('SELECT id FROM clients WHERE name = ?', nome)[0][0]


def _sem_rolagem(pg, onde):
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{onde} rola de lado ({largura}px)'


def _pronta(pg, nome):
    """Depois de um envio: a tela nova desenha de novo (espera ela); a antiga
    já chegou carregada."""
    if '/novo/' in pg.url:
        pg.wait_for_selector(f'[data-tela-pronta="{nome}"]', state='attached')


def test_checklist_rota_atividade_e_escala(servidor, navegador, perfil, rotas):
    base = servidor['base']
    cid = _id(servidor, 'GL Armazém 1')
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + rotas + '/rotas/', 'rotas-inicio')
        _sem_rolagem(pg, 'o início')
        pg.locator('.fc-local', has_text='GL Armazém 1').get_by_role('link', name='Rotas e checklists').click()
        pg.wait_for_selector('text=Checklists deste local')
        _pronta(pg, 'rotas-local')
        assert pg.url.startswith(base + rotas + f'/rotas/locais/{cid}')
        # O checklist novo: cria, escreve a pergunta e publica.
        pg.fill('#novock', 'Checklist do e2e')
        pg.get_by_role('button', name='Criar', exact=True).click()
        pg.wait_for_selector('text=Ainda não publicado.')
        _pronta(pg, 'rotas-modelo')
        pg.fill('#t0', 'Pia limpa?')
        pg.fill('#cf0', 'Esfregue a cuba')
        pg.get_by_role('button', name='Publicar a primeira versão').click()
        pg.wait_for_selector('text=Versão 1 publicada')
        _pronta(pg, 'rotas-modelo')
        assert pg.locator('text=Código:').count() == 1
        _sem_rolagem(pg, 'o checklist')
        # A rota do zero, pelo caminho de migalhas até o local.
        pg.locator('.breadcrumb').get_by_role('link', name='GL Armazém 1').click()
        pg.wait_for_selector('text=Criar rota do zero')
        _pronta(pg, 'rotas-local')
        pg.locator('summary', has_text='Criar rota do zero').click()
        pg.fill('#rnome', 'Rota do e2e')
        pg.fill('#rturno', 'Manhã')
        pg.get_by_role('button', name='Criar rota').click()
        pg.wait_for_selector('text=Rota criada. Agora inclua as atividades')
        _pronta(pg, 'rotas-rota')
        _sem_rolagem(pg, 'a rota')
        # As atividades (o formulário já vem aberto na rota sem atividade).
        pg.locator('.fc-ponto-opcao', has_text='Porta do banheiro').locator('input').check()
        pg.select_option('#imnovo', label='Checklist do e2e')
        pg.fill('#ihnovo', '08:00, 10:00')
        pg.get_by_role('button', name='Incluir', exact=True).click()
        pg.wait_for_selector('text=Atividade incluída na rota.')
        _pronta(pg, 'rotas-rota')
        assert pg.locator('text=Horários: 08:00, 10:00').count() == 1
        # A escala.
        pg.locator('summary', has_text='+ Escalar pessoa').click()
        pg.select_option('#epes', label='Ana Souza — Encarregado / ASG')
        pg.get_by_role('button', name='Escalar', exact=True).click()
        pg.wait_for_selector('text=Ana Souza escalado(a) nesta rota.')
        _pronta(pg, 'rotas-rota')
        assert servidor['sql']("SELECT COUNT(*) FROM rota_escalas e JOIN rotas r ON r.id = e.rota_id "
                               "WHERE r.nome = 'Rota do e2e' AND e.is_active") == [(1,)]
        # O dia do local.
        pg.locator('.breadcrumb').get_by_role('link', name='GL Armazém 1').click()
        _pronta(pg, 'rotas-local')
        pg.get_by_role('link', name='Acompanhar hoje').click()
        pg.wait_for_selector('text=Aderência à rota')
        _pronta(pg, 'rotas-dia')
        _sem_rolagem(pg, 'o dia')
    finally:
        b.close()


def test_biblioteca_rota_pronta_e_planilha(servidor, navegador, perfil, rotas):
    from facilities.rotas.plano_limpeza import caminho_da_planilha_trino_frio
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + rotas + '/rotas/biblioteca', 'rotas-biblioteca')
        pg.get_by_role('button', name='Instalar na biblioteca').click()
        pg.wait_for_selector('text=modelo(s) instalado(s)')
        _pronta(pg, 'rotas-biblioteca')
        _sem_rolagem(pg, 'a biblioteca')
        # Aplicar uma rota pronta no local 2: escolhe, vê a prévia, cria.
        cid = _id(servidor, 'GL Armazém 2')
        abrir(pg, base + rotas + f'/rotas/locais/{cid}/rota-pronta', 'rotas-aplicar')
        pg.select_option('#escolha', index=1)
        pg.get_by_role('button', name='Ver a prévia').click()
        pg.wait_for_selector('text=A rota que será criada')
        _pronta(pg, 'rotas-aplicar')
        _sem_rolagem(pg, 'aplicar a rota pronta')
        pg.get_by_role('button', name='Criar a rota neste local').click()
        pg.wait_for_selector('text=Falta a escala: quem faz esta rota.')
        _pronta(pg, 'rotas-rota')
        assert '/rotas/' in pg.url and pg.url.startswith(base + rotas + '/rotas/')
        # A planilha do cliente no local 3: a prévia e o "Criar".
        cid = _id(servidor, 'GL Armazém 3')
        abrir(pg, base + rotas + f'/rotas/locais/{cid}/importar-plano', 'rotas-importar-plano')
        pg.set_input_files('#arquivo', caminho_da_planilha_trino_frio())
        pg.get_by_role('button', name='Ver a prévia').click()
        pg.wait_for_selector('text=Responsável: ROSA')
        _sem_rolagem(pg, 'a prévia da planilha')
        pg.get_by_role('button', name='Criar blocos, checklists e rotas neste local').click()
        pg.wait_for_selector('text=Plano importado: 8 rota(s)')
        _pronta(pg, 'rotas-local')
        assert servidor['sql']('SELECT COUNT(*) FROM rotas WHERE client_id = ?', cid)[0][0] >= 8
    finally:
        b.close()


def test_feriados_do_local(servidor, navegador, perfil, rotas):
    base = servidor['base']
    cid = _id(servidor, 'GL Armazém 1')
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + rotas + f'/rotas/locais/{cid}/feriados?ano=2030', 'rotas-feriados')
        pg.get_by_role('heading', name='Feriados de 2030').wait_for()
        pg.fill('#fdata', '2030-07-02')
        pg.fill('#fnome', 'Independência da Bahia')
        pg.get_by_role('button', name='Cadastrar').click()
        pg.wait_for_selector('text=Independência da Bahia (02/07/2030) cadastrado.')
        _pronta(pg, 'rotas-feriados')
        linha = pg.locator('.fc-cartao.p-0 > div', has_text='Independência da Bahia')
        assert 'deste local' in linha.inner_text()
        _sem_rolagem(pg, 'os feriados')
        linha.get_by_role('button', name='Remover').click()
        pg.wait_for_selector('text=Feriado removido.')
        _pronta(pg, 'rotas-feriados')
        assert servidor['sql']("SELECT COUNT(*) FROM feriados WHERE nome = 'Independência da Bahia'") == [(0,)]
        # O ano seguinte, pelo botão.
        pg.get_by_role('link', name='2031').click()
        pg.get_by_role('heading', name='Feriados de 2031').wait_for()
    finally:
        b.close()
