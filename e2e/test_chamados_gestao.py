"""Os chamados, o painel de demandas e a preventiva num navegador de verdade
(celular e PC), nas telas antigas e nas novas (React, Fase 4a: os mesmos
endereços abaixo de ``/novo``): a Ana abre o chamado com foto, o
administrador atribui ao Caio e muda a prioridade, o Caio atende, espera a
peça e resolve com a foto do serviço, a Ana confirma; o administrador acha a
preventiva no painel de demandas e cuida dos planos do local. Os recados são
os mesmos nas duas, e nenhuma tela rola de lado."""
import os
import re
import struct
import tempfile
import zlib

from conftest import PERFIS, VIOLACOES_CSP, abrir, abrir_contexto, entrar


def _png():
    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00\x10\x20\x30')) + bloco(b'IEND', b''))


def _foto():
    fd, caminho = tempfile.mkstemp(suffix='.png')
    with os.fdopen(fd, 'wb') as f:
        f.write(_png())
    return caminho


def _outra_pessoa(b, perfil):
    """Outro "aparelho" no mesmo navegador (cada pessoa com a sua sessão)."""
    ctx = b.new_context(**PERFIS[perfil])
    ctx.on('console', lambda m: VIOLACOES_CSP.append(m.text)
           if 'Content Security Policy' in m.text else None)
    return ctx.new_page()


def _sem_rolagem(pg, onde):
    largura = pg.evaluate('document.documentElement.scrollWidth')
    if largura > pg.viewport_size['width']:
        # Diz QUEM passa da tela (a falha foi intermitente: o culpado depende
        # do conteúdo do momento, e sem o nome não há como achar a causa).
        culpados = pg.evaluate("""(w) => [...document.querySelectorAll('body *')]
            .filter(e => e.getBoundingClientRect().right > w)
            .slice(-5).map(e => e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).trim().replace(/ +/g, '.') : '')
                + ' «' + (e.textContent || '').trim().slice(0, 60) + '» ' + Math.round(e.getBoundingClientRect().right) + 'px')""",
            pg.viewport_size['width'])
        raise AssertionError(f'{onde} rola de lado ({largura}px): ' + ' | '.join(culpados))


def _pronta(pg, nome):
    """Depois de um envio: a tela nova desenha de novo (espera ela); a antiga
    já chegou carregada."""
    if '/novo/' in pg.url:
        pg.wait_for_selector(f'[data-tela-pronta="{nome}"]', state='attached')


def _enviar(pg, botao, recado, nome='chamado'):
    # (sem ``exact``: o ícone do Bootstrap entra no nome do botão)
    pg.get_by_role('button', name=botao).click()
    pg.wait_for_selector(f'.alert:has-text("{recado}")')
    _pronta(pg, nome)


def test_o_ciclo_do_chamado(servidor, navegador, perfil, chamados):
    base = servidor['base']
    foto = _foto()
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        # A Ana abre o chamado, com a área e a foto do problema.
        ana = ctx.new_page()
        entrar(ana, base, 'ana@e2e.test')
        abrir(ana, base + chamados + '/chamados/', 'chamados')
        _sem_rolagem(ana, 'a lista')
        ana.get_by_role('link', name='Abrir chamado').click()
        ana.wait_for_selector('text=Diga o que está errado e onde.')
        _pronta(ana, 'chamados-novo')
        assert ana.url.startswith(base + chamados + '/chamados/novo')
        # Dois contratos: escolhe o contrato, e as áreas dele aparecem.
        assert ana.locator('#area_id').is_disabled()
        ana.select_option('#client_id', label='GL Armazém 1')
        ana.select_option('#area_id', label='Limpeza')
        ana.fill('#titulo', 'Torneira do banheiro vazando')
        ana.fill('#local', 'Banheiro masculino')
        ana.select_option('#categoria', label='Hidráulica')
        ana.set_input_files('#arquivo', foto)
        _sem_rolagem(ana, 'abrir')
        ana.get_by_role('button', name='Abrir chamado').click()
        ana.wait_for_selector('text=Os gestores do contrato foram avisados.')
        _pronta(ana, 'chamado')
        cid = int(re.search(r'/chamados/(\d+)', ana.url).group(1))
        assert ana.url == base + chamados + f'/chamados/{cid}'
        assert ana.locator('.ch-dados', has_text='GL Armazém 1 · Limpeza').count() == 1
        assert ana.locator('.ch-anexos img').count() == 1
        _sem_rolagem(ana, 'o chamado')

        # O administrador atribui ao Caio e sobe a prioridade.
        adm = _outra_pessoa(b, perfil)
        entrar(adm, base, 'admin@e2e.test')
        abrir(adm, base + chamados + f'/chamados/{cid}', 'chamado')
        adm.locator('select[name=responsavel_id]').select_option(label='Caio Técnico — Técnico de manutenção')
        _enviar(adm, 'Atribuir', 'Chamado atribuído a Caio Técnico')
        assert adm.locator('.ch-dados', has_text='Caio Técnico').count() == 1
        adm.locator('summary', has_text='Mudar prioridade').click()
        adm.locator('select[name=prioridade]').select_option(label='Urgente')
        _enviar(adm, 'Salvar', 'Prioridade alterada para urgente')
        assert adm.locator('.ch-cab .ch-pri-urgente').count() == 1
        # A lista do administrador: a aba "Todos" e o filtro de prioridade.
        abrir(adm, base + chamados + '/chamados/', 'chamados')
        adm.get_by_role('link', name='Todos', exact=True).click()
        adm.wait_for_url('**visao=todos**')
        _pronta(adm, 'chamados')
        adm.locator('select[name=prioridade]').select_option('urgente')
        adm.wait_for_url('**prioridade=urgente**')
        _pronta(adm, 'chamados')
        assert adm.locator('.ch-item', has_text='Torneira do banheiro vazando').count() == 1
        assert adm.locator('.ch-item', has_text='Filtro do secador').count() == 0

        # O Caio atende, espera a peça, retoma e resolve com a foto.
        caio = _outra_pessoa(b, perfil)
        entrar(caio, base, 'caio@e2e.test')
        abrir(caio, base + chamados + f'/chamados/{cid}', 'chamado')
        _enviar(caio, 'Iniciar atendimento', 'Atendimento iniciado.')
        caio.locator('summary', has_text='Pôr em espera').click()
        caio.fill('input[name=texto]', 'Reparo encomendado')
        _enviar(caio, 'Aguardar', 'Chamado posto em espera.')
        assert caio.locator('text=Reparo encomendado').count() >= 1
        _enviar(caio, 'Retomar atendimento', 'Atendimento retomado.')
        caio.fill('textarea[name=texto]', 'Troquei o reparo da torneira')
        caio.locator('details.ch-acao[open] input[type=file]').set_input_files(foto)
        _enviar(caio, 'Marcar como resolvido', 'Chamado marcado como resolvido.')
        assert caio.locator('text=O que foi feito:').count() == 1
        assert caio.locator('.ch-anexos img').count() == 2
        _sem_rolagem(caio, 'o chamado do técnico')

        # A Ana confirma.
        abrir(ana, base + chamados + f'/chamados/{cid}', 'chamado')
        _enviar(ana, 'Ficou bom — fechar', 'Chamado fechado. Obrigado por confirmar.')
        assert ana.locator('.ch-st-fechado').count() == 1
        assert servidor['sql']('SELECT status, prioridade FROM chamados WHERE id = ?', cid) == \
            [('fechado', 'urgente')]
        assert servidor['sql']('SELECT momento FROM chamado_anexos WHERE chamado_id = ? ORDER BY id', cid) == \
            [('antes',), ('depois',)]
    finally:
        b.close()
        os.remove(foto)


def test_demandas_e_preventiva(servidor, navegador, perfil, chamados):
    base = servidor['base']
    [(lid,)] = servidor['sql']("SELECT id FROM clients WHERE name = 'GL Armazém 1'")
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, 'admin@e2e.test')
        # O painel de demandas: o filtro e a preventiva de hoje.
        abrir(pg, base + chamados + '/demandas/', 'demandas')
        _sem_rolagem(pg, 'as demandas')
        pg.select_option('#ftipo', 'preventiva')
        pg.get_by_role('button', name='Filtrar').click()
        pg.wait_for_url('**tipo=preventiva**')
        _pronta(pg, 'demandas')
        assert pg.locator('.fc-cartao.p-0 a').count() == 1
        pg.locator('.fc-cartao.p-0 a', has_text='Filtro do secador').click()
        pg.wait_for_selector('text=Manutenção preventiva programada')
        _pronta(pg, 'chamado')
        assert pg.url.startswith(base + chamados + '/chamados/')
        assert pg.locator('text=Para fazer esta preventiva').count() == 1
        # Os planos do local: cadastrar, editar e desativar.
        abrir(pg, base + chamados + f'/preventiva/locais/{lid}', 'preventiva')
        _sem_rolagem(pg, 'a preventiva')
        assert pg.locator('text=Filtro do secador').count() >= 1
        pg.fill('#nomenovo', 'Revisão do ar-condicionado')
        pg.select_option('#modelonovo', label='Limpeza do filtro')
        pg.fill('#intnovo', '90')
        pg.select_option('#respnovo', label='Caio Técnico')
        pg.get_by_role('button', name='Cadastrar plano').click()
        pg.wait_for_selector('text=Plano preventivo cadastrado.')
        _pronta(pg, 'preventiva')
        [(pid,)] = servidor['sql']("SELECT id FROM planos_preventivos WHERE nome = 'Revisão do ar-condicionado'")
        linha = pg.locator('.border-top', has_text='Revisão do ar-condicionado')
        assert linha.locator('text=a cada 90 dia(s)').count() == 1
        linha.locator('summary', has_text='Editar').click()
        pg.fill(f'#int{pid}', '60')
        linha.get_by_role('button', name='Salvar').click()
        pg.wait_for_selector('text=Plano atualizado. Vale para os próximos ciclos.')
        _pronta(pg, 'preventiva')
        linha = pg.locator('.border-top', has_text='Revisão do ar-condicionado')
        assert linha.locator('text=a cada 60 dia(s)').count() == 1
        linha.locator('summary', has_text='Editar').click()
        linha.get_by_role('button', name='Desativar plano').click()
        pg.wait_for_selector('text=Plano desativado')
        _pronta(pg, 'preventiva')
        assert pg.locator('.border-top', has_text='Revisão do ar-condicionado').locator('text=desativado').count() == 1
        assert servidor['sql']('SELECT intervalo_dias, is_active FROM planos_preventivos WHERE id = ?', pid) == [(60, 0)]
        # O caminho de migalhas leva à rotina do local.
        pg.locator('.breadcrumb').get_by_role('link', name='GL Armazém 1').click()
        pg.wait_for_selector('text=Checklists deste local')
        assert pg.url.startswith(base + chamados + f'/rotas/locais/{lid}')
    finally:
        b.close()
