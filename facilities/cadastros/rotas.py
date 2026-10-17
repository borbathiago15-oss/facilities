"""Telas dos cadastros.

Quem faz o quê:

* Empresas, clientes e estados: só o administrador.
* Estrutura do local (setor, ambiente, equipamento, ponto): o administrador
  e o gestor, nos locais da carteira dele. A diretoria consulta.
* ``/q/<código>``: o endereço que vai no QR. Nesta fase exige login e mostra
  o ponto a quem tem o local na carteira; na Fase 4 abre o checklist.
"""
from flask import (Blueprint, abort, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities.extensions import db
from facilities.core.acesso import admin_required, clientes_visiveis, require_client
from facilities.core.models import PERFIS_DE_GESTAO, Client
from facilities.cadastros import servico
from facilities.cadastros.models import (ACOES, ENTIDADES, Contratante, Empresa, Estado)
from facilities.cadastros.servico import CadastroInvalido

bp = Blueprint('cadastros', __name__)

PERFIS_QUE_ESTRUTURAM = PERFIS_DE_GESTAO
PERFIS_QUE_CONSULTAM = PERFIS_DE_GESTAO + ('visualizador',)


def _perfil():
    return current_user._effective_role()


def _local_para_ler(cid):
    if _perfil() not in PERFIS_QUE_CONSULTAM:
        raise Forbidden('A estrutura dos locais é cadastrada pela gestão.')
    local = db.get_or_404(Client, cid)
    if local.is_deleted:
        abort(404)
    require_client(local.id)
    return local


def _local_para_alterar(cid):
    local = _local_para_ler(cid)
    if _perfil() not in PERFIS_QUE_ESTRUTURAM:
        raise Forbidden('Seu perfil pode consultar, mas não alterar a estrutura.')
    return local


def _gravar(funcao, *args, sucesso=None, destino):
    """Roda a regra; erro de cadastro volta à tela com a mensagem."""
    try:
        obj = funcao(*args)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return redirect(destino)
    if sucesso:
        flash(sucesso(obj) if callable(sucesso) else sucesso, 'success')
    return redirect(destino)


# ── Início dos cadastros ──────────────────────────────────────────────────

@bp.get('/cadastros/')
@login_required
def inicio():
    if _perfil() not in PERFIS_QUE_CONSULTAM:
        raise Forbidden('Os cadastros são feitos pela gestão.')
    locais = clientes_visiveis()
    return render_template('cadastros/inicio.html', locais=locais,
                           e_admin=_perfil() == 'master',
                           n_empresas=Empresa.query.count(),
                           n_clientes=Contratante.query.count(),
                           n_estados=Estado.query.filter_by(is_active=True).count())


# ── Empresas ──────────────────────────────────────────────────────────────

@bp.get('/cadastros/empresas')
@login_required
@admin_required
def empresas():
    lista = Empresa.query.order_by(Empresa.is_active.desc(), Empresa.nome).all()
    return render_template('cadastros/empresas.html', empresas=lista)


@bp.post('/cadastros/empresas')
@login_required
@admin_required
def criar_empresa():
    return _gravar(servico.salvar_empresa, None, request.form, current_user,
                   sucesso=lambda e: f'Empresa {e.nome} cadastrada.',
                   destino=url_for('cadastros.empresas'))


@bp.post('/cadastros/empresas/<int:eid>')
@login_required
@admin_required
def editar_empresa(eid):
    e = db.get_or_404(Empresa, eid)
    return _gravar(servico.salvar_empresa, e, request.form, current_user,
                   sucesso='Empresa atualizada.', destino=url_for('cadastros.empresas'))


@bp.post('/cadastros/empresas/<int:eid>/ativo')
@login_required
@admin_required
def ativo_empresa(eid):
    e = db.get_or_404(Empresa, eid)
    ativo = request.form.get('ativo') == '1'
    return _gravar(servico.definir_ativo_simples, 'empresa', e, ativo, current_user,
                   sucesso='Empresa reativada.' if ativo else 'Empresa desativada.',
                   destino=url_for('cadastros.empresas'))


# ── Clientes (contratantes) ───────────────────────────────────────────────

@bp.get('/cadastros/clientes')
@login_required
@admin_required
def clientes():
    lista = (Contratante.query.order_by(Contratante.is_active.desc(), Contratante.nome).all())
    return render_template('cadastros/clientes.html', clientes=lista,
                           empresas=Empresa.query.order_by(Empresa.nome).all(),
                           gerentes=servico.gerentes_possiveis())


@bp.post('/cadastros/clientes')
@login_required
@admin_required
def criar_cliente():
    return _gravar(servico.salvar_contratante, None, request.form, current_user,
                   sucesso=lambda c: (f'Cliente {c.nome} cadastrado. Agora ligue os locais '
                                      'dele em Locais.'),
                   destino=url_for('cadastros.clientes'))


@bp.post('/cadastros/clientes/<int:cid>')
@login_required
@admin_required
def editar_cliente(cid):
    c = db.get_or_404(Contratante, cid)
    return _gravar(servico.salvar_contratante, c, request.form, current_user,
                   sucesso='Cliente atualizado.', destino=url_for('cadastros.clientes'))


@bp.post('/cadastros/clientes/<int:cid>/ativo')
@login_required
@admin_required
def ativo_cliente(cid):
    c = db.get_or_404(Contratante, cid)
    ativo = request.form.get('ativo') == '1'
    return _gravar(servico.definir_ativo_simples, 'contratante', c, ativo, current_user,
                   sucesso='Cliente reativado.' if ativo else 'Cliente desativado.',
                   destino=url_for('cadastros.clientes'))


# ── Estados ───────────────────────────────────────────────────────────────

@bp.get('/cadastros/estados')
@login_required
@admin_required
def estados():
    lista = Estado.query.order_by(Estado.is_active.desc(), Estado.nome).all()
    return render_template('cadastros/estados.html', estados=lista)


@bp.post('/cadastros/estados/<int:eid>/ativo')
@login_required
@admin_required
def ativo_estado(eid):
    e = db.get_or_404(Estado, eid)
    ativo = request.form.get('ativo') == '1'
    return _gravar(servico.definir_estado_ativo, e, ativo, current_user,
                   sucesso=lambda x: f'{x.nome} {"ativado" if ativo else "desativado"}.',
                   destino=url_for('cadastros.estados'))


# ── Estrutura do local ────────────────────────────────────────────────────

@bp.get('/cadastros/locais/<int:cid>')
@login_required
def local(cid):
    loc = _local_para_ler(cid)
    com_inativos = request.args.get('inativos') == '1'
    return render_template('cadastros/local.html', local=loc,
                           setores=servico.arvore(loc, com_inativos=com_inativos),
                           todos_setores=servico.arvore(loc, com_inativos=False),
                           com_inativos=com_inativos,
                           pode_alterar=_perfil() in PERFIS_QUE_ESTRUTURAM)


_SALVAR = {
    'setor': servico.salvar_setor,
    'ambiente': servico.salvar_ambiente,
    'equipamento': servico.salvar_equipamento,
    'ponto': servico.salvar_ponto,
}


def _destino_local(loc):
    sufixo = '?inativos=1' if request.form.get('inativos') == '1' else ''
    return url_for('cadastros.local', cid=loc.id) + sufixo


@bp.post('/cadastros/locais/<int:cid>/<entidade>')
@login_required
def criar_item(cid, entidade):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    return _gravar(_SALVAR[entidade], loc, None, request.form, current_user,
                   sucesso=lambda o: f'{ENTIDADES[entidade]} "{o.nome}" cadastrado.',
                   destino=_destino_local(loc))


@bp.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>')
@login_required
def editar_item(cid, entidade, oid):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    try:
        obj = servico.item_do_local(entidade, oid, loc)
    except CadastroInvalido:
        abort(404)
    return _gravar(_SALVAR[entidade], loc, obj, request.form, current_user,
                   sucesso=f'{ENTIDADES[entidade]} atualizado.', destino=_destino_local(loc))


@bp.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>/ativo')
@login_required
def ativo_item(cid, entidade, oid):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    try:
        obj = servico.item_do_local(entidade, oid, loc)
    except CadastroInvalido:
        abort(404)
    ativo = request.form.get('ativo') == '1'
    msg = (f'{ENTIDADES[entidade]} reativado.' if ativo else
           f'{ENTIDADES[entidade]} desativado (com o que estava dentro dele).')
    return _gravar(servico.definir_ativo, entidade, obj, ativo, current_user,
                   sucesso=msg, destino=_destino_local(loc))


@bp.get('/cadastros/locais/<int:cid>/etiquetas.pdf')
@login_required
def etiquetas(cid):
    from facilities.cadastros.etiquetas import gerar
    loc = _local_para_ler(cid)
    ids = {int(x) for x in request.args.getlist('ponto') if x.isdigit()}
    pontos = [p for s in servico.arvore(loc) for a in s.ambientes if a.is_active
              for p in a.pontos if p.is_active and (not ids or p.id in ids)]
    if not pontos:
        flash('Não há ponto ativo para imprimir. Cadastre os pontos nos ambientes.', 'warning')
        return redirect(url_for('cadastros.local', cid=loc.id))
    itens = [{'nome': p.nome, 'ambiente': p.ambiente.nome, 'setor': p.ambiente.setor.nome,
              'codigo': p.codigo_qr,
              'url': url_for('cadastros.qr', codigo=p.codigo_qr, _external=True)}
             for p in pontos]
    pdf = gerar(loc.name, itens)
    return send_file(pdf, mimetype='application/pdf', as_attachment=False,
                     download_name=f'etiquetas-qr-local-{loc.id}.pdf')


# ── Trilha ────────────────────────────────────────────────────────────────

@bp.get('/cadastros/trilha')
@login_required
@admin_required
def trilha():
    entidade = request.args.get('entidade') or None
    if entidade not in ENTIDADES:
        entidade = None
    lista = servico.eventos(entidade=entidade)
    return render_template('cadastros/trilha.html', eventos=lista, local=None,
                           entidade=entidade, entidades=ENTIDADES, acoes=ACOES,
                           diferencas=servico.diferencas)


@bp.get('/cadastros/locais/<int:cid>/trilha')
@login_required
def trilha_local(cid):
    loc = _local_para_ler(cid)
    lista = servico.eventos(client_id=loc.id)
    return render_template('cadastros/trilha.html', eventos=lista, local=loc, entidade=None,
                           entidades=ENTIDADES, acoes=ACOES, diferencas=servico.diferencas)


# ── O endereço do QR ──────────────────────────────────────────────────────

@bp.get('/q/<codigo>')
@login_required
def qr(codigo):
    """O endereço do QR. Quem executa (posto e supervisor) vai direto ao
    turno, já no ponto; a gestão vê o ponto e o que foi feito ali hoje (D57)."""
    from facilities.campo.rotas import PERFIS_DO_CAMPO
    ponto = servico.ponto_pelo_codigo(codigo)
    if ponto is None:
        abort(404)
    require_client(ponto.client_id)
    if _perfil() in PERFIS_DO_CAMPO and ponto.is_active:
        return redirect(url_for('rotas.turno', ponto=ponto.codigo_qr))
    from facilities import tempo
    from facilities.rotas.models import Execucao, TarefaDia
    hoje = tempo.hoje()
    tarefas = (TarefaDia.query.filter_by(ponto_id=ponto.id, data=hoje)
               .order_by(TarefaDia.previsto_para).all())
    feitas = (Execucao.query.filter(Execucao.ponto_id == ponto.id)
              .order_by(Execucao.concluida_em.desc()).limit(20).all())
    feitas = [e for e in feitas if tempo.local(e.concluida_em).date() == hoje]
    return render_template('cadastros/ponto.html', ponto=ponto, tarefas=tarefas, feitas=feitas)
