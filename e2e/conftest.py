"""Testes de navegador (Playwright) do aplicativo de campo — perfis
``celular`` e ``pc``.

Rodam só onde há Playwright e Chromium (``pip install playwright`` e o
navegador; no ambiente do Claude Code, ``/opt/pw-browsers``). Sem isso, são
pulados — a suíte do CI (``pytest -q``) não depende deles.

    pytest -q e2e
"""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from servidor import QR_DO_TESTE, SENHA  # noqa: E402

PERFIS = {
    'celular': {'viewport': {'width': 390, 'height': 844}, 'is_mobile': True,
                'has_touch': True, 'device_scale_factor': 2},
    'pc': {'viewport': {'width': 1280, 'height': 900}},
}


def _chromium():
    for caminho in (os.environ.get('CHROMIUM'), '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
                    '/opt/pw-browsers/chromium'):
        if caminho and os.path.exists(caminho) and os.path.isfile(caminho):
            return caminho
    return None


def _porta_livre():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


@pytest.fixture()
def servidor():
    """Um servidor novo por teste: banco limpo e fila sem resto do anterior."""
    fd, banco = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    porta = _porta_livre()
    proc = subprocess.Popen([sys.executable, os.path.join(AQUI, 'servidor.py'), str(porta), banco],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{porta}'
    for _ in range(100):
        try:
            urllib.request.urlopen(base + '/healthz', timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail('o servidor de teste não subiu')

    def consultar(sql, *args):
        con = sqlite3.connect(banco)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    yield {'base': base, 'sql': consultar, 'qr': QR_DO_TESTE}
    proc.terminate()
    proc.wait(timeout=10)
    os.remove(banco)


@pytest.fixture(scope='session')
def navegador(tmp_path_factory):
    # Aqui, e não no topo do arquivo: sem Playwright (o CI), cada teste é
    # pulado — um skip no topo do conftest derrubaria a coleta inteira.
    pw = pytest.importorskip('playwright.sync_api')
    caminho = _chromium()
    if not caminho:
        pytest.skip('Chromium não encontrado')
    video = str(tmp_path_factory.mktemp('camera') / 'qr.y4m')
    with pw.sync_playwright() as p:
        yield p, caminho, video


@pytest.fixture(params=list(PERFIS))
def perfil(request):
    return request.param


def abrir_contexto(navegador, perfil, camera_com=None):
    """Um contexto (um "aparelho") no perfil pedido; ``camera_com`` = texto
    do QR que a câmera de mentira mostra."""
    p, caminho, video = navegador
    args = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']
    if camera_com:
        from camera import gerar_video_com_qr
        gerar_video_com_qr(camera_com, video)
        args.append(f'--use-file-for-fake-video-capture={video}')
    b = p.chromium.launch(executable_path=caminho, args=args)
    ctx = b.new_context(**PERFIS[perfil])
    ctx.grant_permissions(['camera'])
    # Fase 9A: script embutido bloqueado pela CSP aparece no console — e
    # reprova o teste (ver ``_sem_violacao_de_csp``).
    ctx.on('console', lambda m: VIOLACOES_CSP.append(m.text)
           if 'Content Security Policy' in m.text else None)
    return b, ctx


VIOLACOES_CSP = []


@pytest.fixture(autouse=True)
def _sem_violacao_de_csp():
    VIOLACOES_CSP.clear()
    yield
    assert not VIOLACOES_CSP, 'A CSP bloqueou algo na tela: ' + ' | '.join(VIOLACOES_CSP[:3])


def entrar(pagina, base, email):
    pagina.goto(base + '/login')
    pagina.fill('input[name=email]', email)
    pagina.fill('input[name=password]', SENHA)
    pagina.click('button[type=submit]')
    pagina.wait_for_load_state('networkidle')


def esperar(pagina, expressao, timeout=15000):
    """Espera ``expressao`` (JavaScript) ficar verdadeira.

    No lugar do ``wait_for_function`` do Playwright: ele compila o texto
    dentro da página, e a CSP (Fase 9A) bloqueia isso — com razão.
    ``evaluate`` vai pelo protocolo do navegador, fora da CSP.
    """
    import time
    fim = time.monotonic() + timeout / 1000
    while time.monotonic() < fim:
        if pagina.evaluate(expressao):
            return
        pagina.wait_for_timeout(150)
    raise AssertionError(f'Não aconteceu a tempo: {expressao}')
