"""Telas das visitas: a gestão programa no site; o supervisor faz a visita no
aplicativo (``/app/visitas``)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import clientes_visiveis, require_client
from facilities.core.models import Client
from facilities.visitas import servico
from facilities.visitas.models import PREVISTA, Visita, VisitaProgramada
from facilities.visitas.servico import RegraDaVisita

bp = Blueprint('visitas', __name__)


def _local(cid, montar=False):
    pode = current_user.e_gestao() if montar else (
        current_user.e_gestao() or current_user._effective_role() in ('supervisor',
                                                                        'visualizador'))
    if not pode:
        raise Forbidden('As visitas de supervisão são programadas pela gestão.')
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _gravar(funcao, *args, destino, sucesso):
    try:
        funcao(*args)
        db.session.commit()
    except RegraDaVisita as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(destino)
    flash(sucesso, 'success')
    return redirect(destino)


@bp.get('/visitas/locais/<int:cid>')
@login_required
def local(cid):
    from facilities.rotas.models import ChecklistModelo
    loc = _local(cid)
    modelos = [m for m in ChecklistModelo.query.filter_by(client_id=loc.id, is_active=True)
               .order_by(ChecklistModelo.nome)
               if m.versao_atual and not servico.pede_foto(m.versao_atual)]
    return render_template(
        'visitas/local.html', local=loc, modelos=modelos,
        programadas=VisitaProgramada.query.filter_by(client_id=loc.id)
        .order_by(VisitaProgramada.is_active.desc(), VisitaProgramada.proxima_em).all(),
        recentes=Visita.query.filter_by(client_id=loc.id)
        .order_by(Visita.vencimento.desc()).limit(30).all(),
        supervisores=servico.supervisores_do_local(loc.id), hoje=tempo.hoje().isoformat(),
        pode_montar=current_user.e_gestao())


@bp.post('/visitas/locais/<int:cid>')
@login_required
def criar(cid):
    loc = _local(cid, montar=True)
    return _gravar(servico.salvar_programada, loc, None, request.form, current_user,
                   destino=url_for('visitas.local', cid=loc.id),
                   sucesso='Visita programada. Ela abre sozinha na data e avisa quem faz.')


@bp.post('/visitas/programadas/<int:pid>')
@login_required
def editar(pid):
    prog = db.get_or_404(VisitaProgramada, pid)
    loc = _local(prog.client_id, montar=True)
    destino = url_for('visitas.local', cid=loc.id)
    if request.form.get('ativo') in ('0', '1'):
        prog.is_active = request.form.get('ativo') == '1'
        db.session.commit()
        flash('Programação reativada.' if prog.is_active else
              'Programação desativada: não abre mais visitas (o histórico fica).', 'success')
        return redirect(destino)
    return _gravar(servico.salvar_programada, loc, prog, request.form, current_user,
                   destino=destino, sucesso='Programação atualizada.')


# ── Aplicativo ────────────────────────────────────────────────────────────

@bp.get('/app/visitas')
@login_required
def app_lista():
    if current_user._effective_role() not in servico.PERFIS_QUE_VISITAM:
        raise Forbidden('As visitas de supervisão são feitas pelo supervisor ou pela gestão.')
    locais = clientes_visiveis()
    return render_template('visitas/app_lista.html',
                           visitas=servico.abertas([c.id for c in locais], current_user),
                           hoje=tempo.hoje())


def _visita(vid):
    v = db.get_or_404(Visita, vid)
    require_client(v.client_id)
    if not (current_user._effective_role() in servico.PERFIS_QUE_VISITAM
            or current_user._effective_role() == 'visualizador'):
        raise Forbidden('Sem acesso às visitas de supervisão.')
    return v


@bp.get('/app/visitas/<int:vid>')
@login_required
def ver(vid):
    from facilities.rotas.servico import itens_da_versao
    v = _visita(vid)
    versao = v.versao if v.status != PREVISTA else v.programada.modelo.versao_atual
    itens = itens_da_versao(versao) if versao else []
    return render_template('visitas/app_visita.html', v=v, itens=itens,
                           textos={i['codigo']: i['texto'] for i in itens},
                           respostas=servico.respostas_de(v),
                           pode_fazer=v.status == PREVISTA and servico.pode_fazer(current_user, v),
                           hoje=tempo.hoje())


@bp.post('/app/visitas/<int:vid>')
@login_required
def fazer(vid):
    v = _visita(vid)
    respostas = {k[2:]: val for k, val in request.form.items() if k.startswith('r_')}
    try:
        servico.registrar(current_user, v, respostas, request.form.get('observacao'))
        db.session.commit()
    except RegraDaVisita as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('visitas.ver', vid=v.id))
    if v.chamado_id:
        flash(f'Visita registrada. {v.n_nao_conformes} item(ns) não conforme(s): o chamado '
              f'{v.chamado.numero} foi aberto e a gestão avisada.', 'warning')
    else:
        flash('Visita registrada. Tudo conforme.', 'success')
    return redirect(url_for('visitas.ver', vid=v.id))
