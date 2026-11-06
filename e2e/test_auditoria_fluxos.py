"""Auditoria da Fase 2 (05/11/2026): o que o e2e ainda não cobria, com um
VIGIA em cada página — reprova em qualquer erro no console, erro de script,
resposta 5xx ou ``alert``/``confirm`` aberto por texto digitado.

* o chamado: anexar foto pelo botão "Anexar", reabrir ("Não ficou bom") e
  cancelar, nas telas antiga e nova (o ciclo abrir → atribuir → atender →
  resolver → confirmar já está em ``test_chamados_gestao.py``; a passagem
  completa, em ``test_passagem.py``);
* as telas de gestão (antigas e novas) abertas por administrador, gerente e
  supervisora;
* XSS: título, descrição e nome do local com ``<script>``, ``"><img onerror>``
  e ``');alert(1)//`` nas telas antiga e nova — nenhum vira código;
* responsividade em 375×812, 768×1024 e 1366×768: sem rolagem lateral e
  com os campos e botões dentro da tela, nas telas do campo e nas antigas que
  ficam (login, QR público).
"""
import os
import re
import sqlite3
import struct
import tempfile
import zlib

import pytest

from conftest import MANIFESTO, VIOLACOES_CSP, abrir_contexto, entrar

XSS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "');alert(1)//"]


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


class Vigia:
    """Junta o que deu errado em todas as páginas de um contexto."""

    # Ruído conhecido: a página pública do QR não declara ícone e o navegador
    # pede /favicon.ico (404) — achado de baixa no relatório da Fase 2.
    IGNORAR = ('favicon.ico',)

    def __init__(self, ctx):
        self.problemas = []
        ctx.on('page', self._ligar)
        for pg in ctx.pages:
            self._ligar(pg)

    def _ligar(self, pg):
        pg.on('console', lambda m: self._console(pg, m))
        pg.on('pageerror', lambda e: self.problemas.append(f'erro de script em {pg.url}: {e}'))
        pg.on('response', lambda r: self.problemas.append(f'{r.status} em {r.url}')
              if r.status >= 500 else None)
        pg.on('dialog', self._dialogo)

    def _console(self, pg, m):
        if 'Content Security Policy' in m.text:
            VIOLACOES_CSP.append(m.text)
        recurso = (m.location or {}).get('url', '')
        if m.type == 'error' and not any(x in m.text + recurso for x in self.IGNORAR):
            self.problemas.append(f'console em {pg.url}: {m.text[:200]} [{recurso}]')

    def _dialogo(self, d):
        self.problemas.append(f'diálogo "{d.type}" aberto: {d.message[:80]}')
        d.dismiss()

    def conferir(self):
        assert not self.problemas, ' | '.join(self.problemas[:6])


def _contexto(navegador, perfil, viewport=None):
    b, ctx = abrir_contexto(navegador, perfil)
    if viewport:
        ctx.close()
        p, caminho, _video = navegador
        ctx = b.new_context(viewport=viewport, is_mobile=viewport['width'] < 800,
                            has_touch=viewport['width'] < 800)
    return b, ctx, Vigia(ctx)


def _pronta(pg, nome):
    if '/novo/' in pg.url:
        pg.wait_for_selector(f'[data-tela-pronta="{nome}"]', state='attached')


def _enviar(pg, botao, recado, nome='chamado'):
    pg.get_by_role('button', name=botao).click()
    pg.wait_for_selector(f'.alert:has-text("{recado}")')
    _pronta(pg, nome)


def _abrir(pg, url, nome):
    resp = pg.goto(url)
    assert resp is not None and resp.ok, f'{url} → {resp.status if resp else "?"}'
    _pronta(pg, nome)
    pg.wait_for_load_state('networkidle')


def _csrf(pg, base):
    return pg.request.get(base + '/api/v1/eu').json()['csrf']


def _criar_chamado(pg, base, cid, titulo, descricao=''):
    r = pg.request.post(base + '/api/v1/chamados/', headers={'X-CSRFToken': _csrf(pg, base)},
                        data={'client_id': cid, 'titulo': titulo, 'descricao': descricao,
                              'prioridade': 'media', 'categoria': 'eletrica'})
    assert r.ok, r.text()
    return int(re.search(r'/chamados/(\d+)', r.json()['destino']).group(1))


def _local(servidor, nome='GL Armazém 1'):
    [(cid,)] = servidor['sql']('SELECT id FROM clients WHERE name = ?', nome)
    return cid


# ── 1. O chamado: anexar, reabrir e cancelar ──────────────────────────────

def test_chamado_anexar_reabrir_e_cancelar(servidor, navegador, perfil, chamados):
    base, foto = servidor['base'], _foto()
    b, ctx, vigia = _contexto(navegador, perfil)
    try:
        ana = ctx.new_page()
        entrar(ana, base, 'ana@e2e.test')
        cid = _criar_chamado(ana, base, _local(servidor), 'Porta emperrada')
        adm_ctx = b.new_context(**({'viewport': ana.viewport_size}))
        vigia_adm = Vigia(adm_ctx)
        adm = adm_ctx.new_page()
        entrar(adm, base, 'admin@e2e.test')
        _abrir(adm, base + chamados + f'/chamados/{cid}', 'chamado')
        adm.locator('select[name=responsavel_id]').select_option(
            label='Caio Técnico — Técnico de manutenção')
        _enviar(adm, 'Atribuir', 'Chamado atribuído a Caio Técnico')

        caio_ctx = b.new_context(viewport=ana.viewport_size)
        vigia_caio = Vigia(caio_ctx)
        caio = caio_ctx.new_page()
        entrar(caio, base, 'caio@e2e.test')
        _abrir(caio, base + chamados + f'/chamados/{cid}', 'chamado')
        _enviar(caio, 'Iniciar atendimento', 'Atendimento iniciado.')
        caio.fill('textarea[name=texto]', 'Ajustei a dobradiça')
        _enviar(caio, 'Marcar como resolvido', 'Chamado marcado como resolvido.')

        # A Ana anexa a foto pelo botão "Anexar" (não pela abertura) e reabre.
        _abrir(ana, base + chamados + f'/chamados/{cid}', 'chamado')
        ana.locator('input[name=arquivo]').last.set_input_files(foto)
        ana.get_by_role('button', name='Anexar').click()
        ana.locator('.ch-anexos img').first.wait_for(timeout=15000)
        assert servidor['sql']('SELECT COUNT(*) FROM chamado_anexos WHERE chamado_id = ?',
                               cid) == [(1,)]
        assert ana.locator('.ch-anexos img').count() == 1
        ana.locator('summary', has_text='Não ficou bom — reabrir').click()
        ana.locator('details', has=ana.locator('summary', has_text='Não ficou bom')) \
            .locator('[name=texto]').fill('Continua emperrando')
        _enviar(ana, 'Reabrir', 'Chamado reaberto.')
        [(status,)] = servidor['sql']('SELECT status FROM chamados WHERE id = ?', cid)
        assert status not in ('resolvido', 'fechado'), status
        assert ana.locator('text=Continua emperrando').count() >= 1

        # O administrador cancela.
        _abrir(adm, base + chamados + f'/chamados/{cid}', 'chamado')
        adm.locator('summary', has_text='Cancelar chamado').click()
        caixa = adm.locator('details', has=adm.locator('summary', has_text='Cancelar chamado'))
        caixa.locator('[name=texto]').fill('Aberto em duplicidade')
        caixa.get_by_role('button', name='Cancelar chamado').click()
        adm.wait_for_selector('.alert:has-text("Chamado cancelado.")')
        _pronta(adm, 'chamado')
        assert servidor['sql']('SELECT status FROM chamados WHERE id = ?', cid) == \
            [('cancelado',)]
        for v in (vigia, vigia_adm, vigia_caio):
            v.conferir()
    finally:
        b.close()


# ── 2. As telas de gestão, por perfil, sem erro ───────────────────────────

def _telas(cid):
    return ['/', '/painel', '/demandas/', '/chamados/', '/chamados/novo', '/rotas/',
            '/materiais/', '/materiais/pedidos', '/cadastros/', '/passagem-de-turno/',
            f'/passagem-de-turno/?client_id={cid}', f'/passagem-de-turno/turno?client_id={cid}',
            f'/passagem-de-turno/configuracao?client_id={cid}',
            f'/passagem-de-turno/relatorio-mensal?client_id={cid}', '/cobrancas/', '/avisos',
            '/relatorios/', f'/rotas/locais/{cid}', f'/equipes/locais/{cid}',
            f'/visitas/locais/{cid}', f'/materiais/locais/{cid}', f'/preventiva/locais/{cid}',
            f'/cadastros/locais/{cid}', '/conta/seguranca']


SO_ADMIN = ['/admin/usuarios', '/admin/contratos', '/admin/integracao/', '/clientes',
            '/novo-contrato', '/convites', '/rotas/biblioteca']


@pytest.mark.parametrize('email', ['admin@e2e.test', 'gerente@e2e.test', 'sueli@e2e.test'])
@pytest.mark.parametrize('prefixo', ['', '/novo'], ids=['tela-antiga', 'tela-nova'])
def test_telas_de_gestao_sem_erro(servidor, navegador, perfil, email, prefixo):
    if prefixo and not os.path.exists(MANIFESTO):
        pytest.skip('telas novas não compiladas')
    base, cid = servidor['base'], _local(servidor)
    telas = _telas(cid) + (SO_ADMIN if email.startswith('admin') else [])
    b, ctx, vigia = _contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, base, email)
        abertas = 0
        for t in telas:
            antes = len(vigia.problemas)
            resp = pg.goto(base + prefixo + t)
            if resp.status in (403, 404):
                # O perfil não abre (régua da Fase 1) ou a tela não migrou: o
                # "Failed to load resource: 403" do console é dessa recusa.
                del vigia.problemas[antes:]
                continue
            assert resp.ok, f'{prefixo}{t} → {resp.status}'
            pg.wait_for_load_state('networkidle')
            abertas += 1
        assert abertas >= 10
        vigia.conferir()
    finally:
        b.close()


# ── 3. XSS nas telas antiga e nova ────────────────────────────────────────

def test_texto_digitado_nunca_vira_codigo(servidor, navegador, perfil):
    base, cid = servidor['base'], _local(servidor)
    # O nome do local também (vem do cadastro, digitado pela gestão).
    con = sqlite3.connect(servidor['banco'])
    con.execute('UPDATE clients SET name = ? WHERE id = ?', ('GL ' + XSS[1] + XSS[2], cid))
    con.commit()
    con.close()
    b, ctx, vigia = _contexto(navegador, perfil)
    try:
        ana = ctx.new_page()
        entrar(ana, base, 'ana@e2e.test')
        chamado = _criar_chamado(ana, base, cid, 'Lâmpada ' + XSS[0] + XSS[2],
                                 ' | '.join(XSS))
        ana.request.post(base + f'/api/v1/chamados/{chamado}/acao',
                         headers={'X-CSRFToken': _csrf(ana, base)},
                         data={'acao': 'comentar', 'texto': ' | '.join(XSS)})
        telas = [f'/chamados/{chamado}', '/chamados/', '/', '/demandas/',
                 f'/novo/chamados/{chamado}', '/novo/chamados/', '/novo/', '/novo/demandas/',
                 '/app/', '/novo/app/', '/chamados/novo', '/novo/chamados/novo',
                 f'/passagem-de-turno/turno?client_id={cid}',
                 f'/novo/passagem-de-turno/turno?client_id={cid}']
        if not os.path.exists(MANIFESTO):
            telas = [t for t in telas if not t.startswith('/novo')]
        for t in telas:
            ana.goto(base + t)
            ana.wait_for_load_state('networkidle')
            # O texto aparece como texto (escapado), e nenhum <img> de fora.
            assert ana.locator('img[src="x"]').count() == 0, t
        adm = ctx.new_page()
        ctx.clear_cookies()
        entrar(adm, base, 'admin@e2e.test')
        for t in (f'/cadastros/locais/{cid}', '/admin/contratos', f'/rotas/locais/{cid}',
                  f'/novo/cadastros/locais/{cid}', '/novo/admin/contratos', '/painel',
                  '/novo/painel', f'/chamados/{chamado}'):
            if t.startswith('/novo') and not os.path.exists(MANIFESTO):
                continue
            adm.goto(base + t)
            adm.wait_for_load_state('networkidle')
            assert adm.locator('img[src="x"]').count() == 0, t
        pub = ctx.new_page()
        pub.goto(base + '/q/' + servidor['qr'])
        pub.wait_for_load_state('networkidle')
        vigia.conferir()
    finally:
        b.close()


# ── 4. Responsividade ─────────────────────────────────────────────────────

TAMANHOS = {'375x812': {'width': 375, 'height': 812}, '768x1024': {'width': 768, 'height': 1024},
            '1366x768': {'width': 1366, 'height': 768}}

FORA_DA_TELA = """(w) => [...document.querySelectorAll('input:not([type=hidden]), select, textarea, button, a.btn')]
  .filter(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                 return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'
                        && !e.closest('[hidden], .d-none, #fc-lateral, .offcanvas')
                        && (r.right > w + 1 || (r.left < -1 && r.right > 0)); })
  .slice(0, 5).map(e => e.tagName.toLowerCase() + '#' + (e.id || e.name || e.className) + ' ' +
                   Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right))"""


def _medir(pg, onde, w):
    pg.wait_for_load_state('networkidle')
    largura = pg.evaluate('document.documentElement.scrollWidth')
    assert largura <= w, f'{onde}: rola de lado ({largura}px em {w}px)'
    fora = pg.evaluate(FORA_DA_TELA, w)
    assert not fora, f'{onde}: controle fora da tela: {fora}'


@pytest.mark.parametrize('tamanho', list(TAMANHOS))
def test_telas_do_campo_e_publicas_cabem_na_tela(servidor, navegador, tamanho):
    base, cid, vp = servidor['base'], _local(servidor), TAMANHOS[tamanho]
    b, ctx, vigia = _contexto(navegador, 'celular', viewport=vp)
    try:
        pg = ctx.new_page()
        pg.goto(base + '/login')
        _medir(pg, 'login', vp['width'])
        for t in ('/q/' + servidor['qr'], '/q/' + servidor['qr'] + '/elogio'):
            pg.goto(base + t)
            _medir(pg, t, vp['width'])
        entrar(pg, base, 'ana@e2e.test')
        telas = ['/app/', '/app/turno', '/app/materiais', '/chamados/', '/chamados/novo',
                 f'/passagem-de-turno/turno?client_id={cid}', '/avisos']
        if os.path.exists(MANIFESTO):
            telas += ['/novo/app/', '/novo/app/turno', '/novo/app/materiais', '/novo/chamados/novo',
                      f'/novo/passagem-de-turno/turno?client_id={cid}']
        for t in telas:
            resp = pg.goto(base + t)
            assert resp.ok, f'{t} → {resp.status}'
            _medir(pg, t, vp['width'])
        # A supervisora: equipe e visitas no aplicativo.
        ctx.clear_cookies()
        entrar(pg, base, 'sueli@e2e.test')
        telas = ['/app/', '/app/equipe', '/app/visitas']
        if os.path.exists(MANIFESTO):
            telas += ['/novo/app/equipe', '/novo/app/visitas']
        for t in telas:
            resp = pg.goto(base + t)
            assert resp.ok, f'{t} → {resp.status}'
            _medir(pg, t, vp['width'])
        vigia.conferir()
    finally:
        b.close()
