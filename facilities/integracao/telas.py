"""Tela do administrador: as chaves da integração e o registro de acessos."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import admin_required
from facilities.core.models import Client
from facilities.integracao import servico
from facilities.integracao.models import IntegracaoAcesso, IntegracaoChave
from facilities.integracao.servico import RegraDaIntegracao

bp = Blueprint('integracao', __name__, url_prefix='/admin/integracao')


# As telas antiga e nova (React, Fase 4c: ``/novo/admin/integracao/`` e
# ``/api/v1/admin/integracao/...``) saem das MESMAS funções: ``contexto_chaves``
# monta a lista (nunca o texto nem o hash de chave nenhuma); ``acao_*`` faz o
# envio (a regra, o commit e o recado). Só o administrador (``admin_required``
# nas rotas das duas telas).

def contexto_chaves():
    return dict(
        chaves=IntegracaoChave.query.order_by(IntegracaoChave.is_active.desc(),
                                              IntegracaoChave.criada_em.desc()).all(),
        acessos=IntegracaoAcesso.query.order_by(IntegracaoAcesso.em.desc()).limit(100).all(),
        locais=Client.query.filter(Client.is_deleted.is_(False)).order_by(Client.name).all())


def _tela(nova_chave=None, nova=None):
    return render_template('integracao/chaves.html', nova_chave=nova_chave, nova=nova,
                           **contexto_chaves())


@bp.get('/')
@login_required
@admin_required
def chaves():
    return _tela()


@bp.post('/')
@login_required
@admin_required
def criar():
    feito = acao_criar(request.form)
    if feito is None:
        return redirect(url_for('integracao.chaves'))
    ch, texto = feito
    # A chave aparece só nesta resposta (nada de flash: o flash vai no cookie).
    resp = _tela(nova_chave=texto, nova=ch)
    return resp, 200, {'Cache-Control': 'no-store'}


def acao_criar(dados):
    """Cria a chave: ``(registro, texto)`` — o texto só existe nesta resposta;
    na recusa, o recado e ``None``."""
    try:
        ch, texto = servico.criar_chave(dados.get('nome'), dados.getlist('client_id'),
                                        dados.get('todos') == '1', current_user)
        db.session.commit()
    except RegraDaIntegracao as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return None
    return ch, texto


@bp.post('/<int:kid>/revogar')
@login_required
@admin_required
def revogar(kid):
    return redirect(acao_revogar(kid))


def acao_revogar(kid):
    ch = db.get_or_404(IntegracaoChave, kid)
    if not servico.revogar(ch):
        flash(f'A chave "{ch.nome}" já estava revogada desde '
              f'{tempo.fmt(ch.revogada_em)}. Nada mudou.', 'info')
        return url_for('integracao.chaves')
    db.session.commit()
    flash(f'Chave "{ch.nome}" revogada: deixa de funcionar agora.', 'success')
    return url_for('integracao.chaves')
