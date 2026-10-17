"""Início, avisos e saúde do serviço."""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities.extensions import db
from facilities.core.models import MODULO_CHAMADOS, MODULO_PASSAGEM, Notification

bp = Blueprint('core', __name__)

AVISOS_POR_PAGINA = 50


def avisar(user_ids, titulo, mensagem='', link=None, tipo='geral'):
    """Grava um aviso para cada pessoa (o commit é de quem chama)."""
    for uid in {u for u in (user_ids or []) if u}:
        db.session.add(Notification(user_id=uid, notification_type=tipo,
                                    title=(titulo or '')[:150], message=mensagem,
                                    link=link, status='unread'))


@bp.app_context_processor
def _avisos_no_topo():
    """O número do sino vai para toda tela."""
    if not current_user.is_authenticated:
        return {}
    n = Notification.query.filter_by(user_id=current_user.id, status='unread').count()
    return {'avisos_nao_lidos': n}


@bp.get('/healthz')
def healthz():
    """Liveness: público, sem banco, sempre 200 com o processo de pé."""
    return jsonify({'status': 'ok'}), 200


@bp.get('/')
@login_required
def inicio():
    modulos = []
    if current_user.can_view(MODULO_PASSAGEM):
        modulos.append({'nome': 'Passagem de Turno', 'icone': 'bi-journal-text',
                        'url': url_for('diario_operacional.index'),
                        'texto': 'O que o turno fez, o que ficou pendente e o que aconteceu.'})
    if current_user.can_view(MODULO_CHAMADOS):
        modulos.append({'nome': 'Chamados', 'icone': 'bi-tools',
                        'url': url_for('chamados.index'),
                        'texto': 'Ordens de serviço: abrir, atribuir, acompanhar o prazo e fechar.'})
    return render_template('core/inicio.html', modulos=modulos)


@bp.get('/avisos')
@login_required
def avisos():
    lista = (Notification.query.filter_by(user_id=current_user.id)
             .order_by(Notification.created_at.desc()).limit(AVISOS_POR_PAGINA).all())
    return render_template('core/avisos.html', avisos=lista)


@bp.post('/avisos/<int:aviso_id>/abrir')
@login_required
def abrir_aviso(aviso_id):
    """Marca como lido e leva ao link do aviso."""
    a = Notification.query.filter_by(id=aviso_id, user_id=current_user.id).first_or_404()
    a.status = 'read'
    db.session.commit()
    return redirect(a.link if (a.link or '').startswith('/') else url_for('core.avisos'))


@bp.post('/avisos/ler-todos')
@login_required
def ler_todos():
    (Notification.query.filter_by(user_id=current_user.id, status='unread')
     .update({'status': 'read'}))
    db.session.commit()
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('core.avisos'))
