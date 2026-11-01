"""Fase 2b — as telas da gestão da passagem nas duas telas (antiga e nova,
em React), no celular e no PC.

* o painel: o recorte do filtro (turno, período personalizado), a
  ocorrência, a pendência crítica baixada pelo painel e a passagem aberta
  pela lista dos últimos turnos;
* a "Tarefa para um turno" e a "Deixar pendência" da gestão;
* a configuração: uma pergunta e um tipo de ocorrência novos, salvos, com o
  recado; a área nova;
* o relatório mensal com os dados do mês, o PDF do servidor e a troca de mês.
"""
import json

from conftest import abrir, abrir_contexto, entrar, tela_pronta

from facilities import tempo


def _cliente(servidor):
    [(cid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    return cid


def _abrir_filtro(pg):
    """O filtro fica recolhido (e volta recolhido a cada recorte)."""
    tela_pronta(pg, 'painel')
    if not pg.locator('#dopTurno').is_visible():
        pg.locator('.pg-filtros summary').click()
    pg.locator('#dopTurno').wait_for()


def _ate(servidor, sql, esperado, timeout=15):
    import time
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if servidor['sql'](sql) == esperado:
            return
        time.sleep(0.15)
    assert servidor['sql'](sql) == esperado


def _encerrar_turno(pg, servidor, cid):
    """Uma passagem encerrada do 1º Turno, pela API de sempre (com uma
    ocorrência de atenção, uma pendência alta e um fato no diário de bordo)."""
    csrf = pg.request.get(servidor['base'] + '/api/v1/eu').json()['csrf']
    [(cfg,)] = servidor['sql']("SELECT id FROM diario_operacional_configuracoes WHERE nome = 'Limpeza — rotina'")
    r = pg.request.post(servidor['base'] + '/passagem-de-turno/api/turnos', headers={
        'X-CSRFToken': csrf, 'Content-Type': 'application/json'}, data=json.dumps({
            'client_id': cid, 'configuracao_id': cfg, 'data_turno': tempo.hoje().isoformat(),
            'turno': '1º Turno', 'dados': {'atividade:banheiros': {'concluido': True, 'observacao': ''}},
            'observacao': 'Vazamento na copa contido com balde',
            'ocorrencias': [{'tipo': 'Vazamento', 'referencia': 'Copa', 'descricao': 'Cano da pia rompido',
                             'gravidade': 'critica'}],
            'pendencias': [{'titulo': 'Chamar o encanador', 'prioridade': 'alta'}],
            'finalizar': True}))
    assert r.status == 201, r.text()
    return r.json()['id']


def test_painel_filtra_baixa_pendencia_e_abre_o_turno(servidor, navegador, perfil, passagem):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept('Encanador veio e trocou o cano') if d.type == 'prompt' else d.accept())
        entrar(pg, servidor['base'], 'admin@e2e.test')
        cid = _cliente(servidor)
        turno_id = _encerrar_turno(pg, servidor, cid)
        abrir(pg, servidor['base'] + passagem + f'/?client_id={cid}', 'painel')
        assert '1 turno encerrado no recorte' in pg.locator('.dop-gov').inner_text()
        assert pg.get_by_text('Cano da pia rompido').is_visible()
        assert pg.locator('.dop-crit', has_text='Chamar o encanador').is_visible()
        assert pg.get_by_role('button', name='Abrir chamado').count() == 1

        # O filtro: o turno escolhido recorta a tela inteira.
        _abrir_filtro(pg)
        pg.select_option('#dopTurno', '2º Turno')
        pg.wait_for_url('**turno=2*')
        pg.locator('td.dop-vazio', has_text='Nenhuma ocorrência no período.').wait_for()
        assert '2º Turno' in pg.locator('.pg-recorte').inner_text()
        _abrir_filtro(pg)
        assert pg.input_value('#dopTurno') == '2º Turno'
        pg.select_option('#dopTurno', 'todos')
        pg.wait_for_url('**turno=todos*')
        pg.get_by_text('Cano da pia rompido').wait_for()
        # O período personalizado só se aplica com o "Aplicar".
        _abrir_filtro(pg)
        pg.select_option('#dopPeriodo', 'custom')
        assert pg.locator('#dopDe').is_visible()
        assert 'periodo=custom' not in pg.url
        pg.fill('#dopDe', '2000-01-01')
        pg.fill('#dopAte', '2000-01-31')
        pg.get_by_role('button', name='Aplicar').click()
        pg.wait_for_url('**periodo=custom*')
        pg.locator('td.dop-vazio', has_text='Nenhuma ocorrência no período.').wait_for()
        assert '01/01/2000 a 31/01/2000' in pg.locator('.dop-gov').inner_text()

        # Marcar resolvida pelo painel (com a nota): a fila fica limpa.
        abrir(pg, servidor['base'] + passagem + f'/?client_id={cid}', 'painel')
        pg.get_by_role('button', name='marcar resolvida').click()
        pg.get_by_text('Nenhuma pendência crítica ou vencida. Fila limpa.').wait_for(timeout=15000)
        assert servidor['sql']("SELECT status, resolucao FROM diario_operacional_pendencias") == [
            ('resolvida', 'Encanador veio e trocou o cano')]

        # A passagem aberta pela lista dos últimos turnos: a leitura dela.
        tela_pronta(pg, 'painel')
        pg.get_by_role('link', name='abrir').click()
        pg.wait_for_url(f'**/turno/{turno_id}')
        tela_pronta(pg, 'ver-turno')
        assert pg.locator('.vt-obs', has_text='Vazamento na copa contido com balde').is_visible()
        assert ('/novo/' in pg.url) == ('/novo/' in passagem)
    finally:
        b.close()


def test_painel_tarefa_para_um_turno_e_pendencia_da_gestao(servidor, navegador, perfil, passagem):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept())
        entrar(pg, servidor['base'], 'admin@e2e.test')
        cid = _cliente(servidor)
        abrir(pg, servidor['base'] + passagem + f'/?client_id={cid}', 'painel')
        pg.get_by_role('button', name='Tarefa para um turno').click()
        pg.locator('#tt-titulo').wait_for()
        assert pg.input_value('#tt-turno') == '1º Turno'
        pg.select_option('#tt-turno', '2º Turno')
        pg.fill('#tt-titulo', 'Conferir a bomba da caixa d’água')
        pg.select_option('#tt-forma', 'numero')
        pg.get_by_role('button', name='Atribuir ao turno').click()
        _ate(servidor, 'SELECT turno, titulo, forma_resposta FROM diario_operacional_tarefas_turno',
             [('2º Turno', 'Conferir a bomba da caixa d’água', 'numero')])
        # A tela recarrega (o modal fecha) e segue pronta para a próxima.
        pg.locator('#tt-titulo').wait_for(state='hidden', timeout=15000)
        pg.wait_for_load_state('networkidle')
        tela_pronta(pg, 'painel')

        pg.get_by_role('button', name='Deixar pendência').click()
        pg.fill('#gestor-p-title', 'Trocar a lâmpada da doca')
        pg.select_option('#gestor-p-priority', 'alta')
        pg.get_by_role('button', name='Salvar').click()
        pg.locator('.dop-crit', has_text='Trocar a lâmpada da doca').wait_for(timeout=15000)
        assert servidor['sql']('SELECT titulo, prioridade FROM diario_operacional_pendencias') == [
            ('Trocar a lâmpada da doca', 'alta')]
    finally:
        b.close()


def test_configuracao_edita_e_salva_o_modelo(servidor, navegador, perfil, passagem):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        pg.on('dialog', lambda d: d.accept('Portaria') if d.type == 'prompt' else d.accept())
        entrar(pg, servidor['base'], 'admin@e2e.test')
        cid = _cliente(servidor)
        abrir(pg, servidor['base'] + passagem + f'/configuracao?client_id={cid}', 'configuracao')
        assert pg.input_value('#cfg-name') == 'Limpeza — rotina'
        assert pg.input_value('#cfg-area') != ''
        assert pg.locator('.cfg-p-nome').count() == 1
        assert pg.input_value('.cfg-p-nome') == 'Banheiros limpos'
        assert pg.locator('#cfg-shifts .config-row').count() == 3
        # Uma pergunta nova (de escolha, com opções), um tipo de ocorrência e
        # um turno a menos.
        pg.get_by_role('button', name='Adicionar pergunta').click()
        nova = pg.locator('#cfg-perguntas .config-row').last
        nova.locator('.cfg-p-nome').fill('Situação geral')
        nova.locator('.cfg-p-tipo').select_option('escolha')
        nova.locator('.cfg-p-opcoes').fill('Normal\nCrítico')
        pg.get_by_role('button', name='Adicionar tipo').click()
        pg.locator('.cfg-occ').last.fill('Vazamento')
        pg.locator('#cfg-shifts .config-row').last.locator('button[data-remover]').click()
        pg.get_by_role('button', name='Salvar modelo').click()
        pg.wait_for_url('**editar=*', timeout=20000)
        tela_pronta(pg, 'configuracao')
        aviso = pg.locator('#fc-aviso-js .alert')
        assert 'Modelo "Limpeza — rotina" salvo.' in aviso.inner_text()
        [(ativ, campos, turnos, tipos)] = servidor['sql'](
            "SELECT atividades_json, campos_json, turnos_json, tipos_ocorrencia_json "
            "FROM diario_operacional_configuracoes WHERE nome = 'Limpeza — rotina'")
        assert [a['codigo'] for a in json.loads(ativ)] == ['banheiros']
        [escolha] = json.loads(campos)
        assert escolha['nome'] == 'Situação geral' and escolha['opcoes'] == ['Normal', 'Crítico']
        assert [t['nome'] for t in json.loads(turnos)] == ['1º Turno', '2º Turno']
        assert [t['nome'] for t in json.loads(tipos)] == ['Vazamento']
        # Reaberta, a tela mostra o que foi salvo.
        assert pg.locator('.cfg-p-nome').count() == 2
        assert pg.locator('#cfg-shifts .config-row').count() == 2
        assert '0 turnos lançados' in pg.locator('.cf-item').inner_text()

        # A área nova entra na lista (e no seletor do modelo).
        pg.get_by_role('button', name='Nova área').click()
        pg.locator('.ar-item', has_text='Portaria').wait_for(timeout=15000)
        tela_pronta(pg, 'configuracao')
        assert pg.locator('#cfg-area option', has_text='Portaria').count() == 1
    finally:
        b.close()


def test_relatorio_mensal_mostra_o_mes(servidor, navegador, perfil, passagem):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'admin@e2e.test')
        cid = _cliente(servidor)
        _encerrar_turno(pg, servidor, cid)
        abrir(pg, servidor['base'] + passagem + f'/?client_id={cid}', 'painel')
        pg.get_by_role('link', name='Relatório mensal').click()
        pg.wait_for_url('**/relatorio-mensal?client_id=*')
        tela_pronta(pg, 'relatorio')
        hoje = tempo.hoje()
        assert pg.get_by_role('heading', name='Passagem de Turno — Relatório Executivo Mensal').is_visible()
        assert pg.locator('.rm-big-value').first.inner_text() == '1'
        assert pg.get_by_text('1º Turno: 1').is_visible()
        assert pg.get_by_text('Pontos de atenção da competência (1)').is_visible()
        assert pg.locator('.rm-bloco', has_text='4. Matriz').get_by_text('Cano da pia rompido').count() == 2
        assert pg.locator('.rm-item-texto', has_text='Vazamento na copa contido com balde').is_visible()
        assert pg.locator('.cel-pilha', has_text='Chamar o encanador').is_visible()
        # O PDF continua no servidor, com o mês da tela.
        pdf = pg.get_by_role('link', name='Baixar PDF')
        assert f'mes={hoje.month}' in pdf.get_attribute('href') and 'format=pdf' in pdf.get_attribute('href')
        with pg.expect_download() as baixado:
            pdf.click()
        assert baixado.value.suggested_filename.startswith('Passagem-de-Turno-GL-Armaz')
        # Outro mês: sem nada.
        outro = 1 if hoje.month != 1 else 2
        pg.select_option('select[name="mes"]', str(outro))
        pg.wait_for_url(f'**mes={outro}*')
        pg.get_by_text('Nenhuma ocorrência registrada na competência.').wait_for()
        assert pg.locator('.rm-big-value').first.inner_text() == '0'
        # Voltar: ao painel da mesma tela.
        pg.get_by_role('link', name='Voltar').click()
        pg.wait_for_url('**/passagem-de-turno/?client_id=*')
        tela_pronta(pg, 'painel')
        assert ('/novo/' in pg.url) == ('/novo/' in passagem)
    finally:
        b.close()
