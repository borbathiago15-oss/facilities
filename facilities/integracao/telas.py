"""Tela do administrador: as chaves da integração e o registro de acessos."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities.extensions import db
from facilities.core.acesso import admin_required
from facilities.core.models import Client
from facilities.integracao import servico
from facilities.integracao.models import IntegracaoAcesso, IntegracaoChave
from facilities.integracao.servico import RegraDaIntegracao

bp = Blueprint('integracao', __name__, url_prefix='/admin/integracao')


def _tela(nova_chave=None, nova=None):
    return render_template(
        'integracao/chaves.html', nova_chave=nova_chave, nova=nova,
        chaves=IntegracaoChave.query.order_by(IntegracaoChave.is_active.desc(),
                                              IntegracaoChave.criada_em.desc()).all(),
        acessos=IntegracaoAcesso.query.order_by(IntegracaoAcesso.em.desc()).limit(100).all(),
        locais=Client.query.filter(Client.is_deleted.is_(False)).order_by(Client.name).all())


@bp.get('/')
@login_required
@admin_required
def chaves():
    return _tela()


@bp.post('/')
@login_required
@admin_required
def criar():
    try:
        ch, texto = servico.criar_chave(request.form.get('nome'),
                                        request.form.getlist('client_id'),
                                        request.form.get('todos') == '1', current_user)
        db.session.commit()
    except RegraDaIntegracao as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('integracao.chaves'))
    # A chave aparece só nesta resposta (nada de flash: o flash vai no cookie).
    resp = _tela(nova_chave=texto, nova=ch)
    return resp, 200, {'Cache-Control': 'no-store'}


@bp.post('/<int:kid>/revogar')
@login_required
@admin_required
def revogar(kid):
    ch = db.get_or_404(IntegracaoChave, kid)
    servico.revogar(ch)
    db.session.commit()
    flash(f'Chave "{ch.nome}" revogada: deixa de funcionar agora.', 'success')
    return redirect(url_for('integracao.chaves'))
