"""Fase 6 — a Sueli (supervisora) no aplicativo, no celular e no PC.

* Equipe de hoje: marca a falta da Ana, registra que a Mariana cobriu por
  atestado — as tarefas da rota do posto deixam de ser da Ana;
* Visita de supervisão: abre a visita do dia, responde e registra.
"""
from conftest import abrir_contexto, entrar


def _sem_rolagem_lateral(pg):
    assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']


def test_sueli_lanca_a_falta_e_a_cobertura(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'sueli@e2e.test')
        pg.goto(servidor['base'] + '/app/')
        pg.get_by_role('link', name='Equipe de hoje').click()
        pg.wait_for_selector('text=Ana Souza')
        pg.get_by_role('button', name='Faltou').click()
        pg.wait_for_selector('text=Alguém cobriu esta falta?')
        pg.get_by_text('Alguém cobriu esta falta?').click()
        pg.get_by_label('Quem cobriu').select_option(label='Mariana Lima')
        pg.get_by_label('Motivo').fill('atestado médico')
        pg.get_by_role('button', name='Registrar cobertura').click()
        pg.wait_for_selector('text=Cobertura registrada: Mariana Lima')
        assert servidor['sql']("SELECT situacao FROM presencas") == [('faltou',)]
        assert servidor['sql']("SELECT motivo FROM coberturas") == [('atestado médico',)]
        # Mariana não usa o aplicativo: as tarefas da rota ficam sem escalado.
        assert servidor['sql']("SELECT count(*) FROM tarefas_dia t JOIN users u "
                               "ON u.id = t.user_id WHERE u.email='ana@e2e.test' "
                               "AND t.status='prevista'") == [(0,)]
        _sem_rolagem_lateral(pg)
    finally:
        b.close()


def test_sueli_faz_a_visita_de_supervisao(servidor, navegador, perfil):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'sueli@e2e.test')
        pg.goto(servidor['base'] + '/app/')
        pg.get_by_role('link', name='Visitas de supervisão').click()
        pg.get_by_role('link', name='Visita semanal').click()
        pg.locator('label.fc-opcao', has_text='Sim').click()
        pg.get_by_role('button', name='Registrar a visita').click()
        pg.wait_for_selector('text=Tudo conforme')
        assert servidor['sql']("SELECT status, n_nao_conformes FROM visitas") == [('feita', 0)]
        _sem_rolagem_lateral(pg)
    finally:
        b.close()
