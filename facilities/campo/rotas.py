"""O aplicativo de campo (Fase 3): o celular de quem está no posto.

Duas portas, um sistema: o aplicativo em ``/app/`` (instalado no celular,
abre direto na tela do posto) e o site de gestão em ``/``. Mesmo login,
mesmo banco, mesma carteira. Encarregado, ASG, técnico e supervisor caem
aqui depois do login; a gestão cai no site — e cada um pode abrir o outro
lado (o site tem o link "Aplicativo de campo"; o aplicativo, o "Site").

O aplicativo LANÇA; consultar, cadastrar e tirar relatório é no site.
"""
from datetime import timedelta

from flask import Blueprint, render_template, send_from_directory, current_app, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from facilities import tempo
from facilities.core.acesso import clientes_visiveis

bp = Blueprint('campo', __name__, url_prefix='/app')

# Quem cai no aplicativo depois do login.
PERFIS_DO_CAMPO = ('encarregado', 'tecnico', 'supervisor')


def destino_depois_do_login(user):
    if user._effective_role() in PERFIS_DO_CAMPO:
        return url_for('campo.inicio')
    return url_for('core.inicio')


def _hoje_do_posto(locais):
    """O que há para fazer hoje e o que ficou pendente, nos locais da pessoa."""
    from facilities.passagem.models import (TAREFA_TURNO_PENDENTE, DiarioPendencia,
                                            DiarioTarefaTurno)
    from facilities.chamados.models import STATUS_EM_ABERTO, Chamado
    ids = [c.id for c in locais] or [-1]
    hoje = tempo.hoje()
    tarefas = (DiarioTarefaTurno.query
               .filter(DiarioTarefaTurno.client_id.in_(ids),
                       DiarioTarefaTurno.status == TAREFA_TURNO_PENDENTE,
                       DiarioTarefaTurno.data_turno >= hoje - timedelta(days=1),
                       DiarioTarefaTurno.data_turno <= hoje)
               .order_by(DiarioTarefaTurno.data_turno, DiarioTarefaTurno.turno).limit(50).all())
    pendencias = (DiarioPendencia.query
                  .filter(DiarioPendencia.client_id.in_(ids), DiarioPendencia.status == 'aberta')
                  .order_by(DiarioPendencia.created_at).limit(50).all())
    chamados_q = Chamado.query.filter(Chamado.client_id.in_(ids),
                                      Chamado.status.in_(STATUS_EM_ABERTO))
    if current_user.e_tecnico():
        chamados_q = chamados_q.filter(or_(Chamado.responsavel_id == current_user.id,
                                           Chamado.responsavel_id.is_(None)))
    chamados = chamados_q.order_by(Chamado.prazo.is_(None), Chamado.prazo).limit(50).all()
    return {'tarefas': tarefas, 'pendencias': pendencias, 'chamados': chamados}


@bp.get('/')
@login_required
def inicio():
    locais = clientes_visiveis()
    return render_template('campo/inicio.html', locais=locais, **_hoje_do_posto(locais))


@bp.get('/ler-qr')
@login_required
def ler_qr():
    return render_template('campo/ler_qr.html')


@bp.get('/instalar')
def instalar():
    return render_template('campo/instalar.html')


@bp.get('/manifest.webmanifest')
def manifesto():
    import os
    resp = send_from_directory(os.path.join(current_app.static_folder, 'pwa'),
                               'manifest-campo.webmanifest',
                               mimetype='application/manifest+json', max_age=0)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp
