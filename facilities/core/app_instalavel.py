"""O sistema como app instalável (PWA) — no celular do posto.

* ``/sw.js`` mora na RAIZ: o service worker só controla as páginas no mesmo
  caminho dele ou abaixo. Servido de ``/static/pwa/sw.js`` não controlaria
  tela nenhuma.
* ``/manifest.webmanifest`` daqui garante o tipo certo também no Flask local.
* ``/app/sessao`` diz quem está logado neste aparelho e entrega um CSRF novo:
  a fila sem internet só reenvia em nome de quem escreveu, e com token válido.
* ``/app/versao`` é a impressão digital do que está no ar — a tela aberta
  descobre que saiu versão nova e oferece "Atualizar".

Os quatro são públicos (o navegador os busca antes do login) e não expõem
dado de ninguém.
"""
import functools
import hashlib
import os

from flask import Blueprint, current_app, jsonify, send_from_directory
from flask_login import current_user

bp = Blueprint('app_instalavel', __name__)

ENDPOINTS = frozenset({'app_instalavel.service_worker', 'app_instalavel.manifesto',
                       'app_instalavel.versao', 'app_instalavel.sessao'})
EXTENSOES_DA_VERSAO = ('.py', '.html', '.js', '.css', '.webmanifest')


@functools.lru_cache(maxsize=4)
def versao_do_sistema(raiz):
    """Os 12 primeiros caracteres do SHA-256 do que foi publicado em ``raiz``."""
    fixa = os.environ.get('FACILITIES_VERSAO', '').strip()
    if fixa:
        return fixa[:40]
    h = hashlib.sha256()
    arquivos = [os.path.join(pasta, nome) for pasta, _sub, nomes in os.walk(raiz)
                for nome in nomes]
    for arq in sorted(arquivos):
        if not arq.endswith(EXTENSOES_DA_VERSAO) or '__pycache__' in arq:
            continue
        h.update(os.path.relpath(arq, raiz).encode('utf-8'))
        with open(arq, 'rb') as f:
            h.update(f.read())
    return h.hexdigest()[:12]


def _versao():
    return versao_do_sistema(current_app.root_path)


@bp.app_context_processor
def _no_template():
    return {'versao_do_app': _versao}


def _pasta():
    return os.path.join(current_app.static_folder, 'pwa')


@bp.get('/sw.js')
def service_worker():
    resp = send_from_directory(_pasta(), 'sw.js', mimetype='application/javascript',
                               max_age=0)
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@bp.get('/manifest.webmanifest')
def manifesto():
    resp = send_from_directory(_pasta(), 'manifest.webmanifest',
                               mimetype='application/manifest+json', max_age=0)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.get('/app/versao')
def versao():
    resp = jsonify({'versao': _versao()})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.get('/app/sessao')
def sessao():
    """Quem está logado neste aparelho, e um token CSRF novo (401 sem sessão)."""
    if not current_user.is_authenticated:
        return jsonify({'autenticado': False}), 401
    from flask_wtf.csrf import generate_csrf
    resp = jsonify({'autenticado': True, 'user_id': current_user.id,
                    'csrf': generate_csrf()})
    resp.headers['Cache-Control'] = 'no-store'
    return resp
