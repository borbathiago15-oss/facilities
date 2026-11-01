"""Fase 2a — a passagem de turno nas duas telas (antiga e nova, em React),
no celular e no PC.

* a Ana responde a pergunta, prende a foto, deixa uma pendência e encerra:
  a passagem entra, o painel mostra o recado e a leitura mostra tudo — com a
  foto; ela corrige a passagem e a correção aparece;
* o turno seguinte abre nas pendências, no turno ainda em aberto, com o que
  o anterior deixou; "Resolver" baixa a pendência e leva à aba da passagem;
* nenhuma das duas telas rola de lado.
"""
import re

from conftest import abrir, abrir_contexto, entrar, esperar

PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8cf'
    'c0f0030005fe02fea7d6a4a60000000049454e44ae426082')


def _sem_rolagem_lateral(pg, tela):
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= pg.viewport_size['width'], f'{tela} rola de lado ({largura}px)'


def test_encerrar_ler_corrigir_e_receber(servidor, navegador, perfil, passagem):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        respostas = {'prompt': 'Liguei para o CD e resolvi'}
        pg.on('dialog', lambda d: d.accept(respostas['prompt']) if d.type == 'prompt' else d.accept())
        entrar(pg, servidor['base'], 'ana@e2e.test')
        abrir(pg, servidor['base'] + passagem + '/turno', 'passagem')
        # Sem pendência recebida, abre direto na passagem.
        assert pg.locator('.dt-aba[data-painel="passagem"]').get_attribute('class').endswith('ativa')
        assert pg.input_value('#diario-shift') == '1º Turno'
        assert pg.get_by_text('Banheiros limpos').is_visible()
        _sem_rolagem_lateral(pg, 'a nova passagem')
        pg.get_by_label('Concluído').check()
        pg.fill('#diario-observacao', 'Faltou papel no 2º andar')
        pg.locator('.dt-atividade .diario-activity-file').first.set_input_files(
            {'name': 'banheiro.png', 'mimeType': 'image/png', 'buffer': PNG})
        esperar(pg, "document.querySelector('.dt-atividade .dt-escolhidos').textContent.includes('foto')")
        pg.get_by_role('button', name='Nova pendência').click()
        pg.fill('.pending-row .p-title', 'Repor papel toalha')
        pg.get_by_role('button', name='Encerrar turno').click()
        # O painel (tela de sempre) com o recado de que entrou.
        pg.wait_for_url('**/passagem-de-turno/?client_id=*', timeout=20000)
        aviso = pg.locator('#fc-aviso-js .alert')
        assert re.search(r'Passagem do 1º Turno de \d\d/\d\d encerrada\. 1 pendência ficou para o próximo turno\.',
                         aviso.inner_text())
        [(turno_id, status)] = servidor['sql']('SELECT id, status FROM diario_operacional_turnos')
        assert status == 'encerrado'
        assert servidor['sql']('SELECT COUNT(*) FROM diario_operacional_anexos WHERE turno_id = ?',
                               turno_id) == [(1,)]

        # A leitura: o checklist, a foto e a pendência deixada.
        abrir(pg, servidor['base'] + passagem + f'/turno/{turno_id}', 'ver-turno')
        assert pg.locator('.vt-lin.sim', has_text='Banheiros limpos').is_visible()
        assert pg.locator('.vt-prova img').count() == 1
        assert pg.get_by_text('Repor papel toalha').is_visible()
        assert pg.locator('.vt-obs', has_text='Faltou papel no 2º andar').is_visible()
        _sem_rolagem_lateral(pg, 'a leitura da passagem')
        # A autora corrige: com o motivo, a correção fica à vista.
        pg.get_by_role('button', name='Corrigir').click()
        pg.fill('#vt-c-obs', 'Faltou papel no 2º e no 3º andar')
        pg.fill('#vt-c-motivo', 'Esqueci o 3º andar')
        pg.get_by_role('button', name='Registrar a correção').click()
        pg.get_by_text('Esta passagem foi corrigida 1×').wait_for(timeout=15000)
        assert pg.get_by_text('Esqueci o 3º andar').is_visible()
        assert pg.locator('.vt-obs', has_text='Faltou papel no 2º e no 3º andar').is_visible()

        # O turno seguinte: abre nas pendências, no 2º Turno (o 1º fechou).
        abrir(pg, servidor['base'] + passagem + '/turno', 'passagem')
        assert pg.locator('.dt-aba[data-painel="pendencias"]').get_attribute('class').endswith('ativa')
        assert pg.locator('.dt-aba[data-painel="pendencias"] .dt-aba-n').inner_text() == '1'
        assert pg.input_value('#diario-shift') == '2º Turno'
        assert pg.locator('#diario-shift option', has_text='1º Turno — já encerrado').count() == 1
        anterior = pg.locator('.dt-anterior:not([hidden])')
        assert 'Faltou papel no 2º e no 3º andar' in anterior.inner_text()
        assert pg.locator('.diario-pending', has_text='Repor papel toalha').is_visible()
        _sem_rolagem_lateral(pg, 'a nova passagem com pendência')
        # "Continua": o que se tentou aparece na hora, com o nome.
        respostas['prompt'] = 'Liguei para o almoxarifado'
        pg.get_by_role('button', name='Continua').click()
        pg.locator('.dt-pend-tent', has_text='Liguei para o almoxarifado').wait_for()
        assert 'Ana Souza, agora' in pg.locator('.dt-pend-tent').inner_text()
        # "Resolver" a última: a pendência sai e a tela vai para a passagem.
        respostas['prompt'] = 'Repus o papel'
        pg.get_by_role('button', name='Resolver').click()
        esperar(pg, "document.querySelector('.dt-aba[data-painel=\"passagem\"]').classList.contains('ativa')")
        assert pg.locator('.diario-pending').count() == 0
        assert servidor['sql']("SELECT status FROM diario_operacional_pendencias") == [('resolvida',)]
    finally:
        b.close()
