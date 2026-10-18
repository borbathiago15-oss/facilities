"""Fase 9A — Content-Security-Policy sem 'unsafe-inline' para script.

* toda resposta leva a CSP;
* nenhuma tela tem <script> embutido nem atributo de evento (onclick=...);
* nenhum JavaScript do sistema monta HTML com atributo de evento.

Tela nova que volte a embutir script falha aqui, antes de chegar ao navegador.
"""
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), '..', 'facilities')
EVENTO = re.compile(r'\son[a-z]+\s*=\s*["\']', re.I)
SCRIPT_EMBUTIDO = re.compile(r'<script(?![^>]*\bsrc=)(?![^>]*type="application/json")[^>]*>',
                             re.I)


def _arquivos(pasta, ext):
    for raiz, _d, nomes in os.walk(os.path.join(RAIZ, pasta)):
        if 'vendor' in raiz:
            continue
        for n in nomes:
            if n.endswith(ext):
                yield os.path.join(raiz, n)


def test_csp_em_toda_resposta(client):
    for url in ('/login', '/q/inexistente', '/healthz'):
        csp = client.get(url).headers.get('Content-Security-Policy', '')
        assert "script-src 'self';" in csp, url
        assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
        assert "'unsafe-inline'" not in csp.split('script-src', 1)[1].split(';', 1)[0]


def test_nenhuma_tela_com_script_ou_evento_embutido():
    problemas = []
    for p in _arquivos('templates', '.html'):
        texto = open(p, encoding='utf-8').read()
        for padrao in (SCRIPT_EMBUTIDO, EVENTO):
            for m in padrao.finditer(texto):
                linha = texto.count('\n', 0, m.start()) + 1
                problemas.append(f'{os.path.relpath(p, RAIZ)}:{linha}: {m.group(0)}')
    assert not problemas, 'Script embutido (use static/js e data-acao):\n' + '\n'.join(problemas)


def test_javascript_nao_monta_html_com_evento():
    problemas = []
    for p in _arquivos('static/js', '.js'):
        for i, linha in enumerate(open(p, encoding='utf-8'), 1):
            if linha.lstrip().startswith(('/*', '*', '//')):
                continue
            if EVENTO.search(linha):
                problemas.append(f'{os.path.relpath(p, RAIZ)}:{i}: {linha.strip()}')
    assert not problemas, '\n'.join(problemas)
