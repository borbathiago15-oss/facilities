"""Telas do cadastro simplificado: Cliente › Centro de custo › Áreas › Rotas
(decisões do dono, 27/10/2026). As regras ficam em ``cadastros/centros.py``.

Quem usa: administrador, gerente e coordenador (``montagem.pode_montar``),
dentro da carteira. Por baixo são os mesmos locais, pontos e rotas da tela
completa: o que se faz aqui aparece lá, e vice-versa.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import require_client
from facilities.core.models import Client
from facilities.cadastros import centros, montagem
from facilities.cadastros.models import Contratante, PontoInspecao
from facilities.cadastros.servico import CadastroInvalido

bp = Blueprint('centros', __name__)


def _exigir():
    if not montagem.pode_montar(current_user):
        raise Forbidden('O cadastro de clientes, áreas e rotas é da gestão (administrador, '
                        'gerente e coordenador).')


def _cliente(ctid):
    _exigir()
    c = db.get_or_404(Contratante, ctid)
    if c.id not in {x.id for x in montagem.clientes_da_montagem(current_user)}:
        raise Forbidden('Este cliente não é seu.')
    return c


def _centro(cid):
    _exigir()
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _rota(loc, rid):
    from facilities.rotas.models import Rota
    r = db.get_or_404(Rota, rid)
    if r.client_id != loc.id:
        abort(404)
    return r


def _erro(erro, destino):
    db.session.rollback()
    flash(getattr(erro, 'mensagem', None) or str(erro), 'danger')
    return redirect(destino)


def _regras():
    from facilities.rotas.servico import RegraDaRota
    return (CadastroInvalido, RegraDaRota)


# ── Clientes e centros de custo ───────────────────────────────────────────

@bp.get('/clientes')
@login_required
def clientes():
    _exigir()
    lista = montagem.clientes_da_montagem(current_user)
    return render_template('cadastros/centros/clientes.html', clientes=lista,
                           centros={c.id: centros.centros_do_cliente(c) for c in lista},
                           pode_criar=montagem.pode_criar_cliente(current_user))


@bp.get('/clientes/<int:ctid>')
@login_required
def cliente(ctid):
    c = _cliente(ctid)
    lista = centros.centros_do_cliente(c)
    return render_template('cadastros/centros/cliente.html', cliente=c, centros=lista,
                           resumo={x.id: centros.resumo_do_centro(x) for x in lista},
                           estados=montagem.estados_ativos())


@bp.post('/clientes/<int:ctid>/centros')
@login_required
def criar_centro(ctid):
    c = _cliente(ctid)
    try:
        loc = montagem.criar_local(c, request.form, current_user)
        db.session.commit()
    except CadastroInvalido as erro:
        return _erro(erro, url_for('centros.cliente', ctid=c.id))
    flash(f'Centro de custo "{loc.name}" criado. Agora cadastre as áreas.', 'success')
    return redirect(url_for('centros.centro', cid=loc.id))


# ── O centro de custo: áreas e rotas ──────────────────────────────────────

@bp.get('/centros/<int:cid>')
@login_required
def centro(cid):
    from facilities.rotas.models import Rota
    loc = _centro(cid)
    aba = request.args.get('aba') or 'areas'
    return render_template('cadastros/centros/centro.html', local=loc, aba=aba,
                           areas=centros.areas(loc),
                           numeros=montagem.numeros_dos_pontos(loc.id),
                           checklists=centros.checklists_do_centro(loc),
                           rotas=Rota.query.filter_by(client_id=loc.id)
                           .order_by(Rota.is_active.desc(), Rota.hora_inicio, Rota.nome).all())


@bp.post('/centros/<int:cid>/areas')
@login_required
def criar_areas(cid):
    loc = _centro(cid)
    try:
        novas = centros.criar_areas(loc, request.form.get('areas'), current_user)
        db.session.commit()
    except _regras() as erro:
        return _erro(erro, url_for('centros.centro', cid=loc.id))
    flash(f'{len(novas)} área(s) cadastrada(s), cada uma com o seu QR e o seu checklist.',
          'success')
    return redirect(url_for('centros.centro', cid=loc.id))


@bp.post('/centros/<int:cid>/areas/<int:pid>/checklist')
@login_required
def trocar_checklist(cid, pid):
    loc = _centro(cid)
    ponto = db.get_or_404(PontoInspecao, pid)
    try:
        m = centros.trocar_checklist(loc, ponto, request.form.get('checklist_id'))
        db.session.commit()
    except CadastroInvalido as erro:
        return _erro(erro, url_for('centros.centro', cid=loc.id))
    flash(f'{ponto.nome}: checklist "{m.nome}". Vale para as linhas de rota que você incluir '
          'daqui em diante.', 'success')
    return redirect(url_for('centros.centro', cid=loc.id))


@bp.post('/centros/<int:cid>/rotas')
@login_required
def criar_rota(cid):
    from facilities.rotas import servico as rotas
    loc = _centro(cid)
    dados = request.form.to_dict()
    dados['dias_semana'] = ''.join(request.form.getlist('dias_semana'))
    try:
        r = rotas.salvar_rota(loc, None, dados)
        db.session.commit()
    except _regras() as erro:
        return _erro(erro, url_for('centros.centro', cid=loc.id, aba='rotas'))
    flash(f'Rota "{r.nome}" criada. Agora digite os horários e as áreas.', 'success')
    return redirect(url_for('centros.rota', cid=loc.id, rid=r.id))


@bp.get('/centros/<int:cid>/rotas/<int:rid>')
@login_required
def rota(cid, rid):
    from facilities.rotas import servico as rotas
    loc = _centro(cid)
    r = _rota(loc, rid)
    return render_template('cadastros/centros/rota.html', local=loc, rota=r,
                           linhas=centros.linhas_da_rota(r), areas=centros.areas(loc),
                           pessoas=rotas.pessoas_escalaveis(loc.id),
                           dias=rotas.DIAS_DA_SEMANA, hoje=tempo.hoje().isoformat(),
                           vazias=range(8))


def _replanejar(r):
    from facilities.rotas.telas import _replanejar as refazer
    refazer(r)


@bp.post('/centros/<int:cid>/rotas/<int:rid>/linhas')
@login_required
def adicionar_linhas(cid, rid):
    loc = _centro(cid)
    r = _rota(loc, rid)
    linhas = list(zip(request.form.getlist('hora'), request.form.getlist('area')))
    try:
        centros.adicionar_linhas(r, linhas, current_user)
        db.session.commit()
    except _regras() as erro:
        return _erro(erro, url_for('centros.rota', cid=loc.id, rid=r.id))
    flash('Horários incluídos na rota.', 'success')
    _replanejar(r)
    return redirect(url_for('centros.rota', cid=loc.id, rid=r.id))


@bp.post('/centros/<int:cid>/rotas/<int:rid>/linhas/<int:iid>/remover')
@login_required
def remover_linha(cid, rid, iid):
    from facilities.rotas.models import RotaItem
    loc = _centro(cid)
    r = _rota(loc, rid)
    item = db.get_or_404(RotaItem, iid)
    try:
        centros.remover_horario(r, item, (request.form.get('hora') or '').strip())
        db.session.commit()
    except CadastroInvalido as erro:
        return _erro(erro, url_for('centros.rota', cid=loc.id, rid=r.id))
    flash('Horário tirado da rota (o que já foi feito continua no histórico).', 'success')
    _replanejar(r)
    return redirect(url_for('centros.rota', cid=loc.id, rid=r.id))


@bp.post('/centros/<int:cid>/rotas/<int:rid>/escala')
@login_required
def escalar(cid, rid):
    from facilities.rotas import servico as rotas
    loc = _centro(cid)
    r = _rota(loc, rid)
    dados = request.form.to_dict()
    dados['dias_semana'] = ''.join(request.form.getlist('dias_semana')) or r.dias_semana
    try:
        e = rotas.salvar_escala(r, dados)
        db.session.commit()
    except _regras() as erro:
        return _erro(erro, url_for('centros.rota', cid=loc.id, rid=r.id))
    flash(f'{e.pessoa.name} faz esta rota.', 'success')
    _replanejar(r)
    return redirect(url_for('centros.rota', cid=loc.id, rid=r.id))
