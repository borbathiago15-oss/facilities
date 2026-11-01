"""GPS na leitura do QR (27/10/2026), num navegador de verdade (celular e PC).

A gestão, no local, toca em "Marcar a posição deste local"; depois o Tito
adianta a recepção a ~1,1 km dali: a limpeza é aceita e fica marcada "fora do
local" na tela da gestão. A posição é marcada nas telas antigas e nas novas
(React, Fase 3a: ``/novo/centros/<id>``); o dia e a execução também (Fase 3b:
``/novo/rotas/...``)."""
from conftest import PERFIS, abrir, abrir_contexto, entrar, tela_pronta
from servidor import QR_RECEPCAO

LOCAL = {'latitude': -12.977749, 'longitude': -38.501630, 'accuracy': 15}
LONGE = {'latitude': -12.987749, 'longitude': -38.501630, 'accuracy': 25}


def test_marca_a_posicao_e_leitura_longe_fica_fora_do_local(servidor, navegador, perfil, campo,
                                                            cadastros):
    base = servidor['base']
    cid = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 3'")[0][0]
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        ctx.grant_permissions(['camera', 'geolocation'])
        ctx.set_geolocation(LOCAL)
        gestor = ctx.new_page()
        entrar(gestor, base, 'admin@e2e.test')
        abrir(gestor, base + cadastros + f'/centros/{cid}', 'centro')
        gestor.get_by_role('button', name='Marcar a posição deste local').click()
        gestor.wait_for_selector('text=Posição de GL Armazém 3 marcada')
        assert servidor['sql']('SELECT latitude IS NOT NULL FROM clients WHERE id = ?', cid) == [(1,)]
        tecnico = b.new_context(**PERFIS[perfil])
        tecnico.grant_permissions(['camera', 'geolocation'])
        tecnico.set_geolocation(LONGE)
        pg = tecnico.new_page()
        entrar(pg, base, 'tito@e2e.test')
        abrir(pg, base + campo + '/turno?ponto=' + QR_RECEPCAO)
        pg.get_by_role('button', name='Adiantar esta área').click()
        pg.get_by_role('button', name='Pedido da gestão').click()
        pg.get_by_role('button', name='Feito: Balcão limpo?').click()
        pg.get_by_role('button', name='Pronto').click()
        pg.wait_for_selector('text=Pronto. Recepção feito às', timeout=15000)
        assert servidor['sql']('SELECT gps_situacao FROM execucoes') == [('fora',)]

        # O dia do local e a execução (Fase 3b: antiga e nova, com o mesmo
        # prefixo dos cadastros), e a correção de uma resposta.
        abrir(gestor, base + cadastros + f'/rotas/locais/{cid}/dia', 'rotas-dia')
        assert gestor.locator('text=Fora do local (1,1 km)').count() >= 1
        gestor.get_by_role('link', name='Tito Técnico').first.click()
        gestor.wait_for_selector('text=Localização na leitura do QR')
        tela_pronta(gestor, 'rotas-execucao')
        assert gestor.locator('strong.text-danger', has_text='Fora do local (1,1 km)').is_visible()
        gestor.locator('summary', has_text='Corrigir uma resposta').click()
        gestor.locator('details form input[name^="r_"]').first.fill('nao')
        gestor.fill('#cmotivo', 'Conferido no local')
        gestor.get_by_role('button', name='Registrar correção').click()
        gestor.wait_for_selector('text=Correção registrada. A resposta original continua na trilha.')
        assert servidor['sql']('SELECT motivo FROM execucao_correcoes') == [('Conferido no local',)]
    finally:
        b.close()
