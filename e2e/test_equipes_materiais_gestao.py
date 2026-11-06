"""A equipe, as visitas e os materiais do local na gestão, num navegador de
verdade (celular e PC), nas telas antigas e nas novas (React, Fase 4b: os
mesmos endereços abaixo de ``/novo``): o administrador cadastra uma
funcionária e um posto, lança e encerra a escala, confere o mês e programa
uma visita de supervisão; no estoque, cadastra um material, lança entrada,
saída recusada e consumo, confere o mês e o custo e marca como visto o pedido
que a Ana fez pelo aplicativo. Os recados são os mesmos nas duas, e nenhuma
tela rola de lado."""
from conftest import abrir, abrir_contexto, contar_quando, entrar


def _sem_rolagem(pg, onde):
    # Mede só com a página inteira carregada: com a máquina ocupada, o CSS
    # ainda chegando deixa a tabela sem estilo, mais larga que a tela.
    pg.wait_for_load_state('load')
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{onde} rola de lado ({largura}px)'


def _pronta(pg, nome):
    """Depois de um envio: a tela nova desenha de novo (espera ela); a antiga
    já chegou carregada."""
    if '/novo/' in pg.url:
        pg.wait_for_selector(f'[data-tela-pronta="{nome}"]', state='attached')


def _enviar(pg, botao, recado, nome, onde=None):
    # (sem ``exact``: o ícone do Bootstrap entra no nome do botão)
    (onde or pg).get_by_role('button', name=botao).click()
    pg.wait_for_selector(f'.alert:has-text("{recado}")')
    _pronta(pg, nome)


def test_a_equipe_e_as_visitas_do_local(servidor, navegador, perfil, equipes):
    base = servidor['base']
    [(lid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + equipes + f'/equipes/locais/{lid}', 'equipe-local')
        _sem_rolagem(pg, 'a equipe')
        assert pg.locator('text=Ana Souza').count() >= 1
        # A funcionária nova e o posto novo.
        pg.locator('summary', has_text='Cadastrar funcionário').click()
        pg.fill('#nfn', 'Carla Dias')
        pg.fill('#nff', 'Recepcionista')
        pg.locator('#nfn').locator('xpath=ancestor::form').get_by_role('button', name='Cadastrar').click()
        pg.wait_for_selector('.alert:has-text("Funcionário cadastrado.")')
        _pronta(pg, 'equipe-local')
        pg.locator('summary', has_text='Cadastrar posto').click()
        pg.fill('#npn', 'Recepção — tarde')
        pg.fill('#npi', '13:00')
        pg.fill('#npf', '19:00')
        pg.locator('#npn').locator('xpath=ancestor::form').get_by_role('button', name='Cadastrar').click()
        pg.wait_for_selector('.alert:has-text("Posto cadastrado.")')
        _pronta(pg, 'equipe-local')
        [(fid,)] = servidor['sql']("SELECT id FROM funcionarios WHERE nome = 'Carla Dias'")
        [(pid,)] = servidor['sql']("SELECT id FROM postos WHERE nome = 'Recepção — tarde'")
        # A escala: a Carla na recepção, de segunda a sexta (o padrão) e no sábado.
        pg.locator('summary', has_text='Lançar escala').click()
        pg.select_option('#esf', label='Carla Dias')
        pg.select_option('#esp', label='Recepção — tarde (13:00–19:00)')
        pg.check('input[name=dia_6]')
        _enviar(pg, 'Lançar escala', 'Escala lançada.', 'equipe-local',
                onde=pg.locator('#esf').locator('xpath=ancestor::form'))
        assert servidor['sql']('SELECT dias_semana, data_fim FROM escalas WHERE funcionario_id = ?', fid) == \
            [('123456', None)]
        linha = pg.locator('.border-top', has_text='Carla Dias').filter(has_text='desde')
        assert linha.locator('text=Seg Ter Qua Qui Sex Sáb').count() == 1
        # Mudar o horário do posto e encerrar a escala.
        posto = pg.locator('.border-top', has_text='Recepção — tarde').filter(has=pg.locator(f'#pn{pid}'))
        posto.locator('summary', has_text='Editar').click()
        pg.fill(f'#pf{pid}', '20:00')
        _enviar(pg, 'Salvar', 'Posto atualizado.', 'equipe-local', onde=posto)
        assert pg.locator('text=13:00 às 20:00').count() == 1
        [(eid,)] = servidor['sql']('SELECT id FROM escalas WHERE funcionario_id = ?', fid)
        pg.locator(f'#ef{eid}').locator('xpath=ancestor::form').get_by_role('button', name='Encerrar').click()
        pg.wait_for_selector('.alert:has-text("Escala de Carla Dias encerrada em")')
        _pronta(pg, 'equipe-local')
        assert servidor['sql']('SELECT data_fim IS NOT NULL FROM escalas WHERE id = ?', eid) == [(1,)]
        _sem_rolagem(pg, 'a equipe depois dos envios')
        # O mês: a grade da Ana e o mês anterior.
        pg.get_by_role('link', name='Conferir o mês').click()
        pg.wait_for_selector('text=Escala e presença ·')
        _pronta(pg, 'equipe-mes')
        assert pg.url.startswith(base + equipes + f'/equipes/locais/{lid}/mes')
        assert pg.locator('table.fc-mes tbody th', has_text='Ana Souza').count() == 1
        pg.get_by_role('link', name='Mês anterior').click()
        pg.wait_for_url('**m=**')
        _pronta(pg, 'equipe-mes')
        _sem_rolagem(pg, 'o mês')
        pg.locator('.breadcrumb').get_by_role('link', name='Equipe · GL Armazém 1').click()
        pg.wait_for_selector('text=Quem trabalha aqui')
        _pronta(pg, 'equipe-local')
        # As visitas de supervisão do local: programar e desativar.
        pg.get_by_role('link', name='Visitas de supervisão').click()
        pg.wait_for_selector('text=Na data, a visita abre sozinha')
        _pronta(pg, 'visitas-local')
        assert pg.url.startswith(base + equipes + f'/visitas/locais/{lid}')
        assert pg.locator('text=Visita semanal').count() >= 1
        pg.locator('summary', has_text='Programar visita').click()
        pg.fill('#vnnova', 'Visita mensal da diretoria')
        pg.select_option('#vmnova', label='Visita de qualidade')
        pg.fill('#vinova', '30')
        pg.select_option('#vsnova', label='Sueli Supervisora (Supervisor)')
        _enviar(pg, 'Programar', 'Visita programada.', 'visitas-local')
        [(vid,)] = servidor['sql']("SELECT id FROM visitas_programadas WHERE nome = 'Visita mensal da diretoria'")
        linha = pg.locator('.border-top', has_text='Visita mensal da diretoria')
        assert linha.locator('text=a cada 30 dia(s)').count() == 1
        linha.locator('summary', has_text='Editar').click()
        _enviar(pg, 'Desativar', 'Programação desativada', 'visitas-local', onde=linha)
        assert servidor['sql']('SELECT intervalo_dias, is_active FROM visitas_programadas WHERE id = ?', vid) == [(30, 0)]
        assert pg.locator('.border-top', has_text='Visita mensal da diretoria').locator('text=desativada').count() == 1
        _sem_rolagem(pg, 'as visitas')
        # A visita em si: o aplicativo de campo (o novo, nas telas novas; Fase 1d).
        assert pg.locator(f'a[href^="{equipes}/app/visitas/"]').count() >= 1
        # O caminho de migalhas leva à rotina do local.
        pg.locator('.breadcrumb').get_by_role('link', name='GL Armazém 1').click()
        pg.wait_for_selector('text=Checklists deste local')
        assert pg.url.startswith(base + equipes + f'/rotas/locais/{lid}')
    finally:
        b.close()


def test_os_materiais_do_local(servidor, navegador, perfil, equipes):
    base = servidor['base']
    [(lid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        # A Ana avisa, pelo aplicativo (o de sempre), que falta saco de lixo.
        ana = ctx.new_page()
        entrar(ana, base, 'ana@e2e.test')
        ana.goto(base + '/app/materiais')
        ana.select_option('#pl', label='GL Armazém 1')
        ana.get_by_label('O que precisa').fill('saco de lixo 100 L')
        ana.get_by_role('button', name='Avisar o gestor').click()
        ana.wait_for_selector('text=Pedido enviado ao gestor do contrato')
        ana.context.clear_cookies()

        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        abrir(pg, base + equipes + '/materiais/', 'materiais')
        _sem_rolagem(pg, 'o catálogo')
        assert pg.locator('text=R$ 12,90 / L').count() == 1
        # O material novo, e o preço que muda.
        pg.locator('summary', has_text='Cadastrar material').click()
        pg.fill('#nmn', 'Saco de lixo 100 L')
        pg.fill('#nmu', 'un')
        pg.fill('#nmp', '0,85')
        _enviar(pg, 'Cadastrar', 'cadastrado.', 'materiais')
        [(mid,)] = servidor['sql']("SELECT id FROM materiais WHERE nome = 'Saco de lixo 100 L'")
        linha = pg.locator('.border-top').filter(has=pg.locator(f'#mn{mid}'))
        linha.locator('summary', has_text='Editar').click()
        assert pg.input_value(f'#mp{mid}') == '0,85'
        pg.fill(f'#mp{mid}', '0,90')
        _enviar(pg, 'Salvar', 'Material atualizado.', 'materiais', onde=linha)
        assert pg.locator('text=R$ 0,90 / un').count() == 1
        # O estoque do local: entrada, a saída sem motivo (recusada) e o consumo.
        pg.locator('a', has_text='GL Armazém 1').click()
        pg.wait_for_selector('text=O saldo é a soma de tudo que entrou e saiu.')
        _pronta(pg, 'materiais-local')
        assert pg.url == base + equipes + f'/materiais/locais/{lid}'
        pg.select_option('#mvt', 'entrada')
        pg.select_option('#mvm', label='Saco de lixo 100 L (un)')
        pg.fill('#mvq', '20')
        _enviar(pg, 'Lançar', 'Entrada: 20 un de Saco de lixo 100 L. Saldo agora: 20.', 'materiais-local',
                onde=pg.locator('#mvt').locator('xpath=ancestor::form'))
        pg.select_option('#mvt', 'saida')
        pg.select_option('#mvm', label='Saco de lixo 100 L (un)')
        pg.fill('#mvq', '2')
        pg.get_by_role('button', name='Lançar', exact=True).click()
        pg.wait_for_selector('.alert-danger')
        _pronta(pg, 'materiais-local')
        pg.select_option('#csm', label='Detergente neutro (L)')
        pg.fill('#csq', '1,5')
        pg.fill('#csmo', 'Limpeza da copa')
        _enviar(pg, 'Lançar consumo', 'Consumo registrado: 1,5 L de Detergente neutro.', 'materiais-local')
        assert servidor['sql']("SELECT tipo, quantidade FROM movimentos_estoque WHERE material_id = ? ORDER BY id", mid) == \
            [('entrada', 20)]
        assert pg.locator('.fc-cartao', has_text='Saldo').locator('text=8,5 L').count() == 1
        assert pg.locator('tbody tr', has_text='Limpeza da copa').count() == 1
        _sem_rolagem(pg, 'o estoque')
        # O consumo do mês e o custo.
        pg.get_by_role('link', name='Consumo do mês').click()
        pg.wait_for_selector('text=Custo do mês')
        _pronta(pg, 'materiais-mes')
        assert pg.locator('tbody tr', has_text='Detergente neutro').locator('text=R$ 19,35').count() == 1
        _sem_rolagem(pg, 'o consumo do mês')
        abrir(pg, base + equipes + '/materiais/custo', 'materiais-custo')
        assert pg.locator('.fs-4', has_text='R$ 19,35').count() == 1
        pg.fill('#cde', '2020-01-01')
        pg.fill('#cate', '2020-01-31')
        pg.get_by_role('button', name='Ver').click()
        pg.wait_for_url('**de=2020-01-01**')
        _pronta(pg, 'materiais-custo')
        assert contar_quando(pg.locator('.fs-4', has_text='R$ 0,00'), 1) == 1
        assert pg.locator('text=Nada no período.').count() == 3
        _sem_rolagem(pg, 'o custo')
        # Os pedidos de insumo: o da Ana, marcado como visto.
        pg.locator('.breadcrumb').get_by_role('link', name='Materiais').click()
        pg.wait_for_selector('text=O catálogo do grupo.')
        _pronta(pg, 'materiais')
        pg.get_by_role('link', name='Pedidos de insumo').click()
        pg.wait_for_selector('text=saco de lixo 100 L')
        _pronta(pg, 'materiais-pedidos')
        assert pg.url == base + equipes + '/materiais/pedidos'
        _enviar(pg, 'Marcar como visto', 'Pedido marcado como visto.', 'materiais-pedidos')
        assert pg.locator('text=visto por Administrador').count() == 1
        assert servidor['sql']("SELECT status FROM pedidos_insumo") == [('visto',)]
        _sem_rolagem(pg, 'os pedidos')
    finally:
        b.close()
