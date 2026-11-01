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
    """Roda a regra e deixa o recado (``flash``); erro de cadastro vira o
    recado em vermelho. Devolve o endereço de volta: a tela antiga redireciona
    para ele; a API das telas novas (``telas/cadastros.py``) devolve o recado
    e o endereço em JSON."""
    try:
        obj = funcao(*args)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return destino
    if sucesso:
        flash(sucesso(obj) if callable(sucesso) else sucesso, 'success')
    return destino


# ── Início dos cadastros ──────────────────────────────────────────────────

def exigir_consulta():
    if _perfil() not in PERFIS_QUE_CONSULTAM:
        raise Forbidden('Os cadastros são feitos pela gestão.')


def contexto_inicio():
    """O que a tela "Cadastros" mostra: a antiga (``inicio.html``) e a nova
    (React, ``/api/v1/cadastros/inicio``) saem daqui."""
    exigir_consulta()
    return dict(locais=clientes_visiveis(), e_admin=_perfil() == 'master',
                n_empresas=Empresa.query.count(), n_clientes=Contratante.query.count(),
                n_estados=Estado.query.filter_by(is_active=True).count())


@bp.get('/cadastros/')
@login_required
def inicio():
    return render_template('cadastros/inicio.html', **contexto_inicio())


# ── Empresas ──────────────────────────────────────────────────────────────

@bp.get('/cadastros/empresas')
@login_required
@admin_required
def empresas():
    return render_template('cadastros/empresas.html', **contexto_empresas())


def contexto_empresas():
    return dict(empresas=Empresa.query.order_by(Empresa.is_active.desc(), Empresa.nome).all())


@bp.post('/cadastros/empresas')
@login_required
@admin_required
def criar_empresa():
    return redirect(acao_criar_empresa(request.form))


def acao_criar_empresa(dados):
    return _gravar(servico.salvar_empresa, None, dados, current_user,
                   sucesso=lambda e: f'Empresa {e.nome} cadastrada.',
                   destino=url_for('cadastros.empresas'))


@bp.post('/cadastros/empresas/<int:eid>')
@login_required
@admin_required
def editar_empresa(eid):
    return redirect(acao_editar_empresa(eid, request.form))


def acao_editar_empresa(eid, dados):
    e = db.get_or_404(Empresa, eid)
    return _gravar(servico.salvar_empresa, e, dados, current_user,
                   sucesso='Empresa atualizada.', destino=url_for('cadastros.empresas'))


@bp.post('/cadastros/empresas/<int:eid>/ativo')
@login_required
@admin_required
def ativo_empresa(eid):
    return redirect(acao_ativo_empresa(eid, request.form))


def acao_ativo_empresa(eid, dados):
    e = db.get_or_404(Empresa, eid)
    ativo = dados.get('ativo') == '1'
    return _gravar(servico.definir_ativo_simples, 'empresa', e, ativo, current_user,
                   sucesso='Empresa reativada.' if ativo else 'Empresa desativada.',
                   destino=url_for('cadastros.empresas'))


# ── Clientes (contratantes) ───────────────────────────────────────────────

@bp.get('/cadastros/clientes')
@login_required
@admin_required
def clientes():
    return render_template('cadastros/clientes.html', **contexto_clientes())


def contexto_clientes():
    lista = (Contratante.query.order_by(Contratante.is_active.desc(), Contratante.nome).all())
    from facilities.rotas.models import TIPOS_OCORRENCIA_PUBLICA
    from facilities.chamados.models import PRAZO_POR_PRIORIDADE, PRIORIDADES
    return dict(clientes=lista,
                empresas=Empresa.query.order_by(Empresa.nome).all(),
                gerentes=servico.gerentes_possiveis(),
                tipos_ocorrencia=TIPOS_OCORRENCIA_PUBLICA, prazos_de=servico.prazos_de,
                regua_de=servico.regua_de, prioridades=PRIORIDADES,
                regua_padrao={k: int(v.total_seconds() // 3600)
                              for k, v in PRAZO_POR_PRIORIDADE.items()})


@bp.post('/cadastros/clientes')
@login_required
@admin_required
def criar_cliente():
    return redirect(acao_criar_cliente(request.form))


def acao_criar_cliente(dados):
    return _gravar(servico.salvar_contratante, None, dados, current_user,
                   sucesso=lambda c: (f'Cliente {c.nome} cadastrado. Agora ligue os locais '
                                      'dele em Locais.'),
                   destino=url_for('cadastros.clientes'))


@bp.post('/cadastros/clientes/<int:cid>')
@login_required
@admin_required
def editar_cliente(cid):
    return redirect(acao_editar_cliente(cid, request.form))


def acao_editar_cliente(cid, dados):
    c = db.get_or_404(Contratante, cid)
    return _gravar(servico.salvar_contratante, c, dados, current_user,
                   sucesso='Cliente atualizado.', destino=url_for('cadastros.clientes'))


@bp.post('/cadastros/clientes/<int:cid>/ativo')
@login_required
@admin_required
def ativo_cliente(cid):
    return redirect(acao_ativo_cliente(cid, request.form))


def acao_ativo_cliente(cid, dados):
    c = db.get_or_404(Contratante, cid)
    ativo = dados.get('ativo') == '1'
    return _gravar(servico.definir_ativo_simples, 'contratante', c, ativo, current_user,
                   sucesso='Cliente reativado.' if ativo else 'Cliente desativado.',
                   destino=url_for('cadastros.clientes'))


# ── Estados ───────────────────────────────────────────────────────────────

@bp.get('/cadastros/estados')
@login_required
@admin_required
def estados():
    return render_template('cadastros/estados.html', **contexto_estados())


def contexto_estados():
    return dict(estados=Estado.query.order_by(Estado.is_active.desc(), Estado.nome).all())


@bp.post('/cadastros/estados/<int:eid>/ativo')
@login_required
@admin_required
def ativo_estado(eid):
    return redirect(acao_ativo_estado(eid, request.form))


def acao_ativo_estado(eid, dados):
    e = db.get_or_404(Estado, eid)
    ativo = dados.get('ativo') == '1'
    return _gravar(servico.definir_estado_ativo, e, ativo, current_user,
                   sucesso=lambda x: f'{x.nome} {"ativado" if ativo else "desativado"}.',
                   destino=url_for('cadastros.estados'))


# ── Estrutura do local ────────────────────────────────────────────────────

@bp.get('/cadastros/locais/<int:cid>')
@login_required
def local(cid):
    return render_template('cadastros/local.html',
                           **contexto_local(cid, request.args.get('inativos') == '1'))


def contexto_local(cid, com_inativos):
    loc = _local_para_ler(cid)
    return dict(local=loc,
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


def _destino_local(loc, dados):
    sufixo = '?inativos=1' if dados.get('inativos') == '1' else ''
    return url_for('cadastros.local', cid=loc.id) + sufixo


@bp.post('/cadastros/locais/<int:cid>/<entidade>')
@login_required
def criar_item(cid, entidade):
    return redirect(acao_criar_item(cid, entidade, request.form))


def acao_criar_item(cid, entidade, dados):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    return _gravar(_SALVAR[entidade], loc, None, dados, current_user,
                   sucesso=lambda o: f'{ENTIDADES[entidade]} "{o.nome}" cadastrado.',
                   destino=_destino_local(loc, dados))


@bp.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>')
@login_required
def editar_item(cid, entidade, oid):
    return redirect(acao_editar_item(cid, entidade, oid, request.form))


def acao_editar_item(cid, entidade, oid, dados):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    try:
        obj = servico.item_do_local(entidade, oid, loc)
    except CadastroInvalido:
        abort(404)
    return _gravar(_SALVAR[entidade], loc, obj, dados, current_user,
                   sucesso=f'{ENTIDADES[entidade]} atualizado.',
                   destino=_destino_local(loc, dados))


@bp.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>/ativo')
@login_required
def ativo_item(cid, entidade, oid):
    return redirect(acao_ativo_item(cid, entidade, oid, request.form))


def acao_ativo_item(cid, entidade, oid, dados):
    loc = _local_para_alterar(cid)
    if entidade not in _SALVAR:
        abort(404)
    try:
        obj = servico.item_do_local(entidade, oid, loc)
    except CadastroInvalido:
        abort(404)
    ativo = dados.get('ativo') == '1'
    msg = (f'{ENTIDADES[entidade]} reativado.' if ativo else
           f'{ENTIDADES[entidade]} desativado (com o que estava dentro dele).')
    return _gravar(servico.definir_ativo, entidade, obj, ativo, current_user,
                   sucesso=msg, destino=_destino_local(loc, dados))


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
    from facilities.cadastros.montagem import logo_de, numeros_dos_pontos
    numeros = numeros_dos_pontos(loc.id)
    # A entrada primeiro (é a primeira etiqueta a colar); depois, pelo número.
    pontos.sort(key=lambda p: (not p.entrada_do_local, numeros.get(p.id, 0)))
    itens = [{'nome': p.nome, 'ambiente': p.ambiente.nome, 'setor': p.ambiente.setor.nome,
              'codigo': p.codigo_qr, 'numero': numeros.get(p.id),
              'entrada': bool(p.entrada_do_local),
              'url': url_for('cadastros.qr', codigo=p.codigo_qr, _external=True)}
             for p in pontos]
    cliente = loc.contratante
    pdf = gerar(loc.name, itens, cliente=cliente.nome if cliente else None,
                logo_cliente=logo_de(cliente))
    return send_file(pdf, mimetype='application/pdf', as_attachment=False,
                     download_name=f'etiquetas-qr-local-{loc.id}.pdf')


# ── Trilha ────────────────────────────────────────────────────────────────

@bp.get('/cadastros/trilha')
@login_required
@admin_required
def trilha():
    return render_template('cadastros/trilha.html',
                           **contexto_trilha(request.args.get('entidade') or None))


def contexto_trilha(entidade=None, cid=None):
    """O histórico do grupo (só o administrador, com o filtro por tipo) ou o
    de um local (``cid``: quem lê o local)."""
    loc = _local_para_ler(cid) if cid is not None else None
    if entidade not in ENTIDADES or loc is not None:
        entidade = None
    lista = servico.eventos(client_id=loc.id) if loc else servico.eventos(entidade=entidade)
    return dict(eventos=lista, local=loc, entidade=entidade, entidades=ENTIDADES, acoes=ACOES,
                diferencas=servico.diferencas)


@bp.get('/cadastros/locais/<int:cid>/trilha')
@login_required
def trilha_local(cid):
    return render_template('cadastros/trilha.html', **contexto_trilha(cid=cid))


# ── O endereço do QR ──────────────────────────────────────────────────────

@bp.get('/q/<codigo>')
def qr(codigo):
    """O endereço do QR.

    * Sem login (o público, Fase 4B): o formulário de ocorrência.
    * Quem executa (posto e supervisor): direto ao turno, já no ponto.
    * A gestão: o ponto e o que foi feito ali hoje (D57).
    """
    from flask_login import current_user as atual
    from facilities.campo.rotas import PERFIS_DO_CAMPO
    ponto = servico.ponto_pelo_codigo(codigo)
    if ponto is None:
        abort(404)
    if not atual.is_authenticated or _perfil() == 'cliente':
        # Sem login, e o cliente do portal também: o formulário público (o
        # cliente logado fica registrado como autor da ocorrência).
        from facilities.rotas.publico import pagina_publica
        return pagina_publica(ponto)
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
