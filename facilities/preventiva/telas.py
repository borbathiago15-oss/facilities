"""Telas da preventiva: a gestão cadastra os planos no site; o técnico faz o
checklist no aplicativo (``/app/turno``, pelo QR do ponto)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import require_client
from facilities.core.models import Client
from facilities.preventiva import servico
from facilities.preventiva.models import PlanoPreventivo
from facilities.preventiva.servico import RegraDaPreventiva

bp = Blueprint('preventiva', __name__, url_prefix='/preventiva')


def _local(cid, montar=False):
    pode = current_user.e_gestao() if montar else (
        current_user.e_gestao() or current_user._effective_role() in ('supervisor',
                                                                        'visualizador'))
    if not pode:
        raise Forbidden('Os planos preventivos são cadastrados pela gestão.')
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


# As telas antiga e nova (React, Fase 4a: ``/novo/preventiva/locais/<id>``
# e ``/api/v1/preventiva/...``) saem das MESMAS funções: ``contexto_local``
# monta os dados; ``acao_*`` faz o envio (a regra, o commit e o recado) e
# devolve o endereço de volta.

@bp.get('/locais/<int:cid>')
@login_required
def local(cid):
    return render_template('preventiva/local.html', **contexto_local(cid))


def contexto_local(cid):
    from facilities.cadastros.models import Equipamento, PontoInspecao
    from facilities.chamados.models import PRIORIDADES
    from facilities.chamados.servico import tecnicos_do_contrato
    from facilities.rotas.models import ChecklistModelo
    loc = _local(cid)
    planos = (PlanoPreventivo.query.filter_by(client_id=loc.id)
              .order_by(PlanoPreventivo.is_active.desc(), PlanoPreventivo.proxima_em).all())

    def com_os_dos_planos(modelo, campo, ativos):
        """Os ativos do local e, para o "Editar" de cada plano, o item atual
        dele que foi desativado: sem ele, o seletor caía na primeira opção e
        o "Salvar" mudava o plano de ponto (ou de checklist, ou de
        equipamento). O desativado só aparece no plano que já o usa."""
        usados = {getattr(p, campo) for p in planos} - {None} - {x.id for x in ativos}
        extra = (modelo.query.filter(modelo.client_id == loc.id, modelo.id.in_(usados),
                                     modelo.is_active.isnot(True)).all() if usados else [])
        return sorted(ativos + extra, key=lambda x: x.nome) if extra else ativos

    modelos = [m for m in ChecklistModelo.query.filter_by(client_id=loc.id, is_active=True)
               .order_by(ChecklistModelo.nome) if m.versao_atual]
    return dict(
        local=loc, planos=planos,
        modelos=com_os_dos_planos(ChecklistModelo, 'modelo_id', modelos),
        pontos=com_os_dos_planos(PontoInspecao, 'ponto_id', PontoInspecao.query.filter_by(
            client_id=loc.id, is_active=True).order_by(PontoInspecao.nome).all()),
        equipamentos=com_os_dos_planos(Equipamento, 'equipamento_id', Equipamento.query.filter_by(
            client_id=loc.id, is_active=True).order_by(Equipamento.nome).all()),
        tecnicos=tecnicos_do_contrato(loc.id), prioridades=PRIORIDADES,
        hoje=tempo.hoje().isoformat(), pode_montar=current_user.e_gestao())


def _gravar(funcao, *args, destino, sucesso):
    try:
        funcao(*args)
        db.session.commit()
    except RegraDaPreventiva as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return destino
    flash(sucesso, 'success')
    return destino


@bp.post('/locais/<int:cid>')
@login_required
def criar(cid):
    return redirect(acao_criar(cid, request.form))


def acao_criar(cid, dados):
    loc = _local(cid, montar=True)
    return _gravar(servico.salvar_plano, loc, None, dados, current_user,
                   destino=url_for('preventiva.local', cid=loc.id),
                   sucesso='Plano preventivo cadastrado. A ordem de serviço abre sozinha '
                           'na data.')


@bp.post('/<int:pid>')
@login_required
def editar(pid):
    return redirect(acao_editar(pid, request.form))


def acao_editar(pid, dados):
    plano = db.get_or_404(PlanoPreventivo, pid)
    loc = _local(plano.client_id, montar=True)
    if dados.get('ativo') in ('0', '1'):
        plano.is_active = dados.get('ativo') == '1'
        db.session.commit()
        flash('Plano reativado.' if plano.is_active else
              'Plano desativado: não abre mais ordens (o histórico fica).', 'success')
        return url_for('preventiva.local', cid=loc.id)
    return _gravar(servico.salvar_plano, loc, plano, dados, current_user,
                   destino=url_for('preventiva.local', cid=loc.id),
                   sucesso='Plano atualizado. Vale para os próximos ciclos.')
