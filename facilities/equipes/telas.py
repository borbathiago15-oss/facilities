"""Telas da equipe: a gestão cadastra funcionários, postos e escala no site;
o supervisor lança a presença e a cobertura no aplicativo (``/app/equipe``)."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import clientes_visiveis, require_client
from facilities.core.models import Client
from facilities.equipes import servico
from facilities.equipes.models import (SITUACOES_PRESENCA, EscalaTrabalho, Funcionario, Posto,
                                       Presenca)
from facilities.equipes.servico import RegraDaEquipe

bp = Blueprint('equipes', __name__)

DIAS = (('1', 'Seg'), ('2', 'Ter'), ('3', 'Qua'), ('4', 'Qui'), ('5', 'Sex'), ('6', 'Sáb'),
        ('7', 'Dom'))


def _quem_ve():
    return current_user.e_gestao() or current_user._effective_role() in ('supervisor',
                                                                          'visualizador')


def _local(cid, montar=False):
    if not (current_user.e_gestao() if montar else _quem_ve()):
        raise Forbidden('Funcionários, postos e escala são cadastrados pela gestão.')
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _gravar(funcao, *args, destino, sucesso):
    try:
        funcao(*args)
        db.session.commit()
    except RegraDaEquipe as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(destino)
    flash(sucesso, 'success')
    return redirect(destino)


# ── Site: cadastro ────────────────────────────────────────────────────────

@bp.get('/equipes/locais/<int:cid>')
@login_required
def local(cid):
    from facilities.rotas.models import Rota
    loc = _local(cid)
    escalas = (EscalaTrabalho.query.filter_by(client_id=loc.id, is_active=True)
               .order_by(EscalaTrabalho.data_inicio).all())
    hoje = tempo.hoje()
    return render_template(
        'equipes/local.html', local=loc, hoje=hoje.isoformat(), dias=DIAS,
        funcionarios=Funcionario.query.filter_by(client_id=loc.id)
        .order_by(Funcionario.is_active.desc(), Funcionario.nome).all(),
        postos=Posto.query.filter_by(client_id=loc.id)
        .order_by(Posto.is_active.desc(), Posto.hora_inicio, Posto.nome).all(),
        escalas=[e for e in escalas if e.data_fim is None or e.data_fim >= hoje],
        rotas=Rota.query.filter_by(client_id=loc.id, is_active=True).order_by(Rota.nome).all(),
        logins=servico.logins_possiveis(loc.id), pode_montar=current_user.e_gestao())


@bp.post('/equipes/locais/<int:cid>/funcionarios')
@login_required
def criar_funcionario(cid):
    loc = _local(cid, montar=True)
    return _gravar(servico.salvar_funcionario, loc, None, request.form, current_user,
                   destino=url_for('equipes.local', cid=loc.id),
                   sucesso='Funcionário cadastrado.')


@bp.post('/equipes/funcionarios/<int:fid>')
@login_required
def editar_funcionario(fid):
    func = db.get_or_404(Funcionario, fid)
    loc = _local(func.client_id, montar=True)
    destino = url_for('equipes.local', cid=loc.id)
    if request.form.get('ativo') in ('0', '1'):
        func.is_active = request.form.get('ativo') == '1'
        db.session.commit()
        flash('Funcionário reativado.' if func.is_active else
              'Funcionário desligado: sai da escala (o histórico fica).', 'success')
        return redirect(destino)
    return _gravar(servico.salvar_funcionario, loc, func, request.form, current_user,
                   destino=destino, sucesso='Funcionário atualizado.')


@bp.post('/equipes/locais/<int:cid>/postos')
@login_required
def criar_posto(cid):
    loc = _local(cid, montar=True)
    return _gravar(servico.salvar_posto, loc, None, request.form,
                   destino=url_for('equipes.local', cid=loc.id), sucesso='Posto cadastrado.')


@bp.post('/equipes/postos/<int:pid>')
@login_required
def editar_posto(pid):
    posto = db.get_or_404(Posto, pid)
    loc = _local(posto.client_id, montar=True)
    destino = url_for('equipes.local', cid=loc.id)
    if request.form.get('ativo') in ('0', '1'):
        posto.is_active = request.form.get('ativo') == '1'
        db.session.commit()
        flash('Posto reativado.' if posto.is_active else 'Posto desativado.', 'success')
        return redirect(destino)
    return _gravar(servico.salvar_posto, loc, posto, request.form, destino=destino,
                   sucesso='Posto atualizado.')


@bp.post('/equipes/locais/<int:cid>/escalas')
@login_required
def criar_escala(cid):
    loc = _local(cid, montar=True)
    return _gravar(servico.salvar_escala, loc, request.form, current_user,
                   destino=url_for('equipes.local', cid=loc.id),
                   sucesso='Escala lançada.')


@bp.post('/equipes/escalas/<int:eid>/encerrar')
@login_required
def encerrar_escala(eid):
    e = db.get_or_404(EscalaTrabalho, eid)
    loc = _local(e.client_id, montar=True)
    try:
        fim = servico._data(request.form.get('data_fim'), 'o último dia da escala')
    except RegraDaEquipe as erro:
        flash(erro.mensagem, 'danger')
        return redirect(url_for('equipes.local', cid=loc.id))
    servico.encerrar_escala(e, fim)
    db.session.commit()
    flash(f'Escala de {e.funcionario.nome} encerrada em {fim.strftime("%d/%m/%Y")}.', 'success')
    return redirect(url_for('equipes.local', cid=loc.id))


@bp.get('/equipes/locais/<int:cid>/mes')
@login_required
def mes(cid):
    loc = _local(cid)
    hoje = tempo.hoje()
    try:
        ano, m = (int(x) for x in (request.args.get('m') or hoje.strftime('%Y-%m')).split('-'))
        primeiro = date(ano, m, 1)
    except ValueError:
        primeiro = hoje.replace(day=1)
    anterior = (primeiro - timedelta(days=1)).replace(day=1)
    seguinte = (primeiro + timedelta(days=32)).replace(day=1)
    return render_template('equipes/mes.html', local=loc, primeiro=primeiro,
                           anterior=anterior.strftime('%Y-%m'),
                           seguinte=seguinte.strftime('%Y-%m'),
                           grade=servico.mes(loc.id, primeiro.year, primeiro.month))


# ── Aplicativo: presença e cobertura ──────────────────────────────────────

def _pode_lancar():
    if current_user._effective_role() not in servico.PERFIS_QUE_LANCAM:
        raise Forbidden('A presença é lançada pelo supervisor ou pela gestão.')


def _dia_pedido():
    hoje = tempo.hoje()
    try:
        dia = datetime.strptime(request.values.get('data') or '', '%Y-%m-%d').date()
    except ValueError:
        return hoje
    return dia if hoje - timedelta(days=servico.DIAS_PARA_TRAS) <= dia <= hoje else hoje


@bp.get('/app/equipe')
@login_required
def app_equipe():
    _pode_lancar()
    dia = _dia_pedido()
    locais = clientes_visiveis()
    linhas = servico.escalados_do_dia([c.id for c in locais], dia)
    por_local = {}
    for linha in linhas:
        por_local.setdefault(linha['escala'].client_id, []).append(linha)
    cobridores = {c.id: servico.funcionarios_ativos(c.id) for c in locais if c.id in por_local}
    hoje = tempo.hoje()
    return render_template('equipes/app_equipe.html', dia=dia, hoje=hoje,
                           ontem=(dia - timedelta(days=1)).isoformat(),
                           amanha=(dia + timedelta(days=1)).isoformat() if dia < hoje else None,
                           locais=[c for c in locais if c.id in por_local],
                           por_local=por_local, cobridores=cobridores,
                           situacoes=SITUACOES_PRESENCA)


@bp.post('/app/equipe/presenca')
@login_required
def app_presenca():
    _pode_lancar()
    e = db.session.get(EscalaTrabalho, servico._id(request.form, 'escala_id'))
    if e is None:
        abort(404)
    require_client(e.client_id)
    dia = _dia_pedido()
    try:
        p = servico.registrar_presenca(current_user, e, dia, request.form.get('situacao'),
                                       request.form.get('observacao'))
        db.session.commit()
    except RegraDaEquipe as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
    else:
        flash(f'{e.funcionario.nome}: {p.situacao_rotulo.lower()}.'
              + (' Registre quem cobriu, se alguém cobriu.' if p.situacao == 'faltou' else ''),
              'success')
    return redirect(url_for('equipes.app_equipe', data=dia.isoformat()) + f'#escala-{e.id}')


@bp.post('/app/equipe/presencas/<int:prid>/cobertura')
@login_required
def app_cobertura(prid):
    _pode_lancar()
    p = db.get_or_404(Presenca, prid)
    require_client(p.client_id)
    try:
        c, passadas = servico.registrar_cobertura(current_user, p, request.form)
        db.session.commit()
    except RegraDaEquipe as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
    else:
        extra = ''
        if passadas:
            extra = (f' {passadas} tarefa(s) da rota passaram para {c.funcionario.nome}.'
                     if c.funcionario.user_id else
                     f' {passadas} tarefa(s) da rota ficaram sem escalado: '
                     f'{c.funcionario.nome} não usa o aplicativo.')
        flash(f'Cobertura registrada: {c.funcionario.nome}.{extra}', 'success')
    return redirect(url_for('equipes.app_equipe', data=p.data.isoformat()))
