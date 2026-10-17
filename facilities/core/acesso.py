"""Quem pode o quê: carteira de contratos e decoradores de rota.

As regras são as do Trino, de onde a Passagem de Turno veio:

* O administrador (``master``) e quem tem ``all_clients`` veem todos os
  contratos; qualquer outro perfil, só os vinculados — carteira vazia não vê
  NADA (o padrão antigo "sem vínculo vê tudo" vazava a carteira alheia).
* Ler e alterar são perguntas diferentes: ``GET`` consulta ``can_view``, o
  resto consulta ``can_access``. O bloqueio fica na ROTA, não só no botão —
  esconder o botão não impede um POST montado à mão.
"""
from functools import wraps

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user
from werkzeug.exceptions import Forbidden

from facilities.core.models import Client


def allowed_client_ids_or_none(user=None):
    """``None`` = sem restrição; senão a lista de contratos permitidos."""
    u = user or current_user
    if u._effective_role() == 'master' or getattr(u, 'all_clients', False):
        return None
    return u.client_ids


FORA_DOS_CONTRATOS = ('Este contrato não está entre os seus contratos. Se precisa '
                      'dele, peça ao administrador.')


def require_client(client_id):
    """Garante que o usuário pode agir sobre o contrato (``Forbidden`` se não).

    O ``Forbidden`` leva a mensagem em português; o tratador de erros
    (``core.erros``) a entrega em JSON a quem chamou por JavaScript — a fila
    sem internet marca o envio como recusado e segue — e numa página com o
    menu a quem navegou.
    """
    permitidos = allowed_client_ids_or_none()
    if permitidos is None:
        return
    try:
        cid = int(client_id) if client_id is not None else None
    except (TypeError, ValueError):
        cid = None
    if cid and cid in permitidos:
        return
    raise Forbidden(FORA_DOS_CONTRATOS)


def clientes_visiveis(extra_id=None):
    """Contratos ATIVOS que este usuário pode escolher — a carteira dele.

    ``extra_id`` mantém no seletor o contrato já vinculado ao registro
    aberto, mesmo fora da carteira: sem ele, abrir e salvar apagaria o
    vínculo em silêncio.
    """
    q = Client.query.filter(Client.is_active.is_(True), Client.is_deleted.is_(False))
    permitidos = allowed_client_ids_or_none()
    if permitidos is not None:
        ids = set(permitidos or [])
        if extra_id:
            ids.add(int(extra_id))
        q = q.filter(Client.id.in_(ids or [-1]))
    return q.order_by(Client.name).all()


def restringir_carteira(q, coluna):
    """Aplica a carteira do usuário a uma consulta."""
    permitidos = allowed_client_ids_or_none()
    if permitidos is not None:
        q = q.filter(coluna.in_(permitidos or [-1]))
    return q


def leitura_apenas():
    """True para quem só consulta — a diretoria."""
    return current_user._effective_role() == 'visualizador'


def _pede_json():
    return request.method != 'GET' or request.is_json or request.path.startswith('/api/') \
        or '/api/' in request.path


def admin_required(f):
    """Só o administrador. A tela volta ao início com um aviso."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user._effective_role() != 'master':
            if _pede_json():
                return jsonify({'error': 'Acesso restrito ao administrador.'}), 403
            flash('Acesso restrito ao administrador.', 'danger')
            return redirect(url_for('core.inicio'))
        return f(*args, **kwargs)
    return decorated


def permissao_requerida(permissao):
    """Exige uma permissão FINA (``User.PERMISSOES_FINAS``)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.pode(permissao):
                if _pede_json():
                    return jsonify({'error': 'Você não tem permissão para '
                                             'esta configuração.'}), 403
                flash('Esta configuração precisa de permissão do '
                      'administrador. Peça a ele para liberar no seu '
                      'cadastro de usuário.', 'warning')
                return redirect(url_for('core.inicio'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def module_required(module):
    """Exige acesso ao módulo — 403 em JSON caso contrário.

    ``GET``/``HEAD`` → ``can_view`` (abrir e consultar); qualquer outro
    método → ``can_access`` (criar, editar, excluir).
    """
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            somente_leitura = request.method in ('GET', 'HEAD')
            permitido = (current_user.can_view(module) if somente_leitura
                         else current_user.can_access(module))
            if not permitido:
                msg = ('Seu perfil pode consultar, mas não alterar este módulo.'
                       if not somente_leitura and current_user.can_view(module)
                       else 'Sem acesso a este módulo.')
                return jsonify({'error': msg}), 403
            return f(*args, **kwargs)
        return wrapper
    return deco
