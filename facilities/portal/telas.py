"""Telas da Fase 9B: o portal do cliente (``/cliente``) e a cobrança vista
pela equipe (``/cobrancas``).

O portal só abre para a conta de cliente (a porta em ``facilities/__init__``
segura o cliente aqui dentro e barra o resto). Cada rota confere o local
contra os locais do cliente: id de outro cliente dá 404, sem dizer se existe.
"""
import io
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities.extensions import db, limiter
from facilities.core.acesso import allowed_client_ids_or_none, require_client
from facilities.portal import servico
from facilities.portal.models import ABERTA, FECHADA, RESPONDIDA, STATUS, Cobranca
from facilities.portal.servico import RegraDaCobranca

bp = Blueprint('portal', __name__, url_prefix='/cliente')
bp_interno = Blueprint('cobrancas', __name__, url_prefix='/cobrancas')


def _so_cliente():
    if not servico.e_cliente(current_user) or not servico.liberado():
        raise Forbidden('O portal é do cliente.')


def _local(cid):
    loc = servico.local_do_cliente(current_user, cid)
    if loc is None:
        abort(404)
    return loc


def _erro(erro, destino):
    db.session.rollback()
    flash(erro.mensagem, 'danger')
    return redirect(destino)


def _periodo():
    from facilities.paineis.servico import ler_periodo
    return ler_periodo(request.args, maximo_dias=366)


# ── Portal do cliente ─────────────────────────────────────────────────────

@bp.get('/')
@login_required
def inicio():
    from facilities.chamados.models import STATUS_EM_ABERTO, Chamado
    from facilities.paineis.servico import FAIXAS, notas
    _so_cliente()
    locais = servico.locais_do_cliente(current_user)
    de, ate = _periodo()
    ids = [c.id for c in locais] or [-1]
    abertos = dict(db.session.query(Chamado.client_id, db.func.count(Chamado.id))
                   .filter(Chamado.client_id.in_(ids), Chamado.status.in_(STATUS_EM_ABERTO))
                   .group_by(Chamado.client_id).all())
    cobrancas = [c for c in servico.cobrancas_do_cliente(current_user) if c.status != FECHADA]
    return render_template('portal/inicio.html', linhas=notas(locais, de, ate), de=de, ate=ate,
                           faixas=FAIXAS, abertos=abertos, cobrancas=cobrancas,
                           agora=datetime.utcnow())


@bp.get('/locais/<int:cid>')
@login_required
def local(cid):
    from facilities.paineis.servico import FAIXAS, INDICADORES, nota_do_local
    _so_cliente()
    loc = _local(cid)
    de, ate = _periodo()
    chamados = servico.chamados_do_local(loc.id)
    return render_template('portal/local.html', local=loc, de=de, ate=ate,
                           nota=nota_do_local(loc, de, ate), faixas=FAIXAS,
                           indicadores=INDICADORES, chamados=chamados,
                           fotos={ch.id: servico.fotos_do_chamado(ch) for ch in chamados},
                           execucoes=servico.execucoes_do_local(loc.id),
                           quem_fez=servico.quem_fez, agora=datetime.utcnow())


@bp.get('/chamados/<int:chamado_id>')
@login_required
def chamado(chamado_id):
    from facilities.chamados.models import Chamado
    _so_cliente()
    ch = db.session.get(Chamado, chamado_id)
    if ch is None:
        abort(404)
    loc = _local(ch.client_id)
    return render_template('portal/chamado.html', ch=ch, local=loc,
                           fotos=servico.fotos_do_chamado(ch), agora=datetime.utcnow())


def _imagem(storage_key, mime):
    from facilities.core.anexos import storage
    if not (mime or '').startswith('image/'):
        abort(404)
    try:
        dados = storage().load(storage_key)
    except Exception:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype=mime)


@bp.get('/fotos/chamado/<int:anexo_id>')
@login_required
def foto_chamado(anexo_id):
    from facilities.chamados.models import ChamadoAnexo
    _so_cliente()
    a = db.session.get(ChamadoAnexo, anexo_id)
    if a is None:
        abort(404)
    _local(a.chamado.client_id)
    return _imagem(a.storage_key, a.mime)


@bp.get('/fotos/checklist/<int:fid>')
@login_required
def foto_checklist(fid):
    from facilities.rotas.models import ExecucaoFoto
    _so_cliente()
    f = db.session.get(ExecucaoFoto, fid)
    if f is None:
        abort(404)
    _local(f.execucao.client_id)
    return _imagem(f.storage_key, f.mime or 'image/jpeg')


@bp.get('/cobrancas')
@login_required
def cobrancas():
    _so_cliente()
    return render_template('portal/cobrancas.html',
                           cobrancas=servico.cobrancas_do_cliente(current_user),
                           locais=servico.locais_do_cliente(current_user),
                           minimo=servico.prazo_minimo(), status=STATUS,
                           local_escolhido=request.args.get('local', type=int),
                           agora=datetime.utcnow())


@bp.post('/cobrancas')
@login_required
@limiter.limit('30 per hour')
def abrir_cobranca():
    _so_cliente()
    try:
        cob = servico.abrir(current_user, request.form)
        db.session.commit()
    except RegraDaCobranca as erro:
        return _erro(erro, url_for('portal.cobrancas'))
    flash(f'Cobrança {cob.numero} enviada à coordenação do contrato.', 'success')
    return redirect(url_for('portal.cobranca', cobid=cob.id))


def _cobranca_do_cliente(cobid):
    cob = db.session.get(Cobranca, cobid)
    if cob is None:
        abort(404)
    _local(cob.client_id)
    return cob


@bp.get('/cobrancas/<int:cobid>')
@login_required
def cobranca(cobid):
    _so_cliente()
    cob = _cobranca_do_cliente(cobid)
    return render_template('portal/cobranca.html', cob=cob, autor=servico.autor_para_o_cliente,
                           minimo=servico.prazo_minimo(), respondida=cob.status == RESPONDIDA,
                           agora=datetime.utcnow())


@bp.post('/cobrancas/<int:cobid>/<acao>')
@login_required
def acao_cobranca(cobid, acao):
    _so_cliente()
    cob = _cobranca_do_cliente(cobid)
    destino = url_for('portal.cobranca', cobid=cob.id)
    passos = {'confirmar': (servico.confirmar, 'Obrigado! Cobrança encerrada.'),
              'reabrir': (servico.reabrir, 'Cobrança reaberta. A coordenação foi avisada.')}
    if acao not in passos:
        abort(404)
    fazer, ok = passos[acao]
    try:
        fazer(current_user, cob, request.form)
        db.session.commit()
    except RegraDaCobranca as erro:
        return _erro(erro, destino)
    flash(ok, 'success')
    return redirect(destino)


# ── A cobrança vista pela equipe ──────────────────────────────────────────

def _ve_cobrancas():
    if not current_user.can_view('chamados'):
        raise Forbidden('Sem acesso às cobranças.')


@bp_interno.get('/')
@login_required
def lista():
    _ve_cobrancas()
    ids = allowed_client_ids_or_none()
    q = Cobranca.query
    if ids is not None:
        q = q.filter(Cobranca.client_id.in_(ids or [-1]))
    status = request.args.get('status') or ''
    if status in STATUS:
        q = q.filter(Cobranca.status == status)
    itens = q.order_by(Cobranca.status != ABERTA, Cobranca.prazo).limit(300).all()
    return render_template('portal/interno_lista.html', itens=itens, status=status,
                           rotulos=STATUS, agora=datetime.utcnow())


def _cobranca_interna(cobid):
    cob = db.get_or_404(Cobranca, cobid)
    require_client(cob.client_id)
    return cob


@bp_interno.get('/<int:cobid>')
@login_required
def ver(cobid):
    _ve_cobrancas()
    cob = _cobranca_interna(cobid)
    return render_template('portal/interno_ver.html', cob=cob,
                           pode_responder=servico.pode_responder(current_user, cob)
                           and cob.status == ABERTA, agora=datetime.utcnow())


@bp_interno.post('/<int:cobid>/responder')
@login_required
def responder(cobid):
    _ve_cobrancas()
    cob = _cobranca_interna(cobid)
    destino = url_for('cobrancas.ver', cobid=cob.id)
    try:
        servico.responder(current_user, cob, request.form)
        db.session.commit()
    except RegraDaCobranca as erro:
        return _erro(erro, destino)
    flash('Resposta enviada. O cliente confirma ou reabre pelo portal.', 'success')
    return redirect(destino)
