"""As telas novas, em React (``frontend/``), servidas pelo próprio Flask.

Migração decidida pelo dono (31/10/2026): o servidor (regras, banco, testes)
continua em Python; só as telas mudam, módulo por módulo, com o sistema
sempre no ar. Ver ``docs/REACT.md``.

* ``/novo/`` (e tudo abaixo) entrega a casca React. O login, a segunda etapa
  e a troca de senha continuam valendo antes, pelas mesmas travas do site.
* ``/api/v1/...`` é a API das telas novas: JSON sempre, mesma sessão e o
  mesmo CSRF (cabeçalho ``X-CSRFToken``) — nenhum token novo, nenhuma porta
  nova de entrada.
"""
import json
import os

from flask import Blueprint, abort, current_app, jsonify, render_template, url_for
from flask_login import current_user, login_required

bp = Blueprint('telas', __name__)
api = Blueprint('api_v1', __name__, url_prefix='/api/v1')

PASTA_BUILD = os.path.join('static', 'app')    # saída do ``npm run build``
ENTRADA = 'src/main.tsx'


def _manifesto():
    """O manifesto do Vite: qual arquivo (com hash) é a entrada de hoje."""
    caminho = os.path.join(current_app.root_path, PASTA_BUILD, '.vite', 'manifest.json')
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


@bp.get('/novo/', defaults={'caminho': ''})
@bp.get('/novo/<path:caminho>')
@login_required
def casca(caminho):
    manifesto = _manifesto()
    if manifesto is None or ENTRADA not in manifesto:
        # O servidor sem as telas compiladas: em desenvolvimento, rodar
        # ``npm run build`` em frontend/ (ou ``npm run dev``).
        abort(503, description='As telas novas ainda não foram compiladas neste servidor.')
    entrada = manifesto[ENTRADA]
    return render_template('telas/casca.html',
                           js=url_for('static', filename=f'app/{entrada["file"]}'),
                           css=[url_for('static', filename=f'app/{c}')
                                for c in entrada.get('css', [])])


@api.get('/eu')
@login_required
def eu():
    """Quem está logado, o menu dela e um CSRF novo: o que a casca precisa."""
    from flask_wtf.csrf import generate_csrf
    from facilities.core.app_instalavel import versao_do_sistema
    from facilities.core.menu import montar
    from facilities.core.models import Notification
    u = current_user
    papel = u._effective_role()
    nome = (u.name or '').strip()
    resp = jsonify({
        'id': u.id,
        'nome': nome,
        'primeiro_nome': nome.split(' ')[0] if nome else '',
        'perfil': u.perfil_rotulo,
        'papel': papel,
        'cliente': papel == 'cliente',
        'avisos_nao_lidos': Notification.query.filter_by(user_id=u.id,
                                                         status='unread').count(),
        'menu': montar(u),
        'csrf': generate_csrf(),
        'versao': versao_do_sistema(current_app.root_path),
        'links': {
            'inicio': url_for('portal.inicio' if papel == 'cliente' else 'core.inicio'),
            'avisos': url_for('core.avisos'),
            'trocar_senha': url_for('auth.trocar_senha'),
            'seguranca': url_for('auth.seguranca'),
            'sair': url_for('auth.logout'),
        },
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.route('/<path:_resto>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@login_required
def nao_existe(_resto):
    abort(404)
