"""Chamados / ordens de serviço: a lista, abrir, o detalhe e as ações.

Formulários comuns (POST + redirect): funcionam no celular do posto sem
depender de JavaScript, e o botão "voltar" não reenvia nada.
"""
import io
import uuid
from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from facilities.extensions import db
from facilities.core.acesso import allowed_client_ids_or_none, clientes_visiveis, module_required
from facilities.core.anexos import ANEXO_ASSINATURA, ANEXO_MAX, ANEXO_TIPOS, storage
from facilities.chamados import servico
from facilities.chamados.models import (
    CATEGORIAS, ORDEM_DA_PRIORIDADE, PRIORIDADES, RESOLVIDO, STATUS, STATUS_CONTA_PRAZO,
    STATUS_EM_ABERTO,
    STATUS_ENCERRADOS, Chamado, ChamadoAnexo)

bp = Blueprint('chamados', __name__, url_prefix='/chamados')
MODULO = 'chamados'

VISOES = {
    'abertos': 'Em aberto',
    'atrasados': 'Atrasados',
    'meus': 'Comigo',
    'confirmar': 'Aguardando confirmação',
    'todos': 'Todos',
}
# Só a aba "Todos" é cortada (os mais recentes primeiro). As abas de
# trabalho — em aberto, atrasados, comigo, aguardando confirmação — mostram
# TUDO o que pede ação: cortar antes de ordenar sumia justamente com o
# atrasado antigo, que o cartão do topo continuava contando.
POR_PAGINA = 100
ANEXOS_POR_ENVIO = 6


def _chamado_autorizado(chamado_id, travar=False):
    """O chamado, se esta pessoa pode vê-lo (404/403 senão).

    ``travar``: para ALTERAR — carrega com a trava de linha
    (``servico.chamado_para_alterar``), e o pedido concorrente espera este
    gravar antes de ler o estado.
    """
    if travar:
        ch = servico.chamado_para_alterar(chamado_id)
        if ch is None:
            abort(404)
    else:
        ch = db.get_or_404(Chamado, chamado_id)
    if not servico.pode_ver(current_user, ch):
        abort(403)
    return ch


def _ordem_de_urgencia(agora):
    """O que pede ação primeiro: atrasado, depois a prioridade, depois o
    prazo mais próximo — calculado NO BANCO, para valer sobre a lista inteira
    e não sobre um pedaço já cortado."""
    atrasado = db.case((db.and_(Chamado.status.in_(STATUS_CONTA_PRAZO),
                                Chamado.prazo.isnot(None), Chamado.prazo < agora), 0),
                       else_=1)
    prioridade = db.case(ORDEM_DA_PRIORIDADE, value=Chamado.prioridade, else_=9)
    return (atrasado, prioridade, Chamado.prazo.is_(None), Chamado.prazo, Chamado.id)


@bp.get('/')
@login_required
@module_required(MODULO)
def index():
    contratos = clientes_visiveis()
    cid = request.args.get('client_id', type=int)
    if cid and cid not in {c.id for c in contratos}:
        abort(403)
    visao = request.args.get('visao') or 'abertos'
    if visao not in VISOES:
        visao = 'abertos'
    prioridade = request.args.get('prioridade') or ''
    categoria = request.args.get('categoria') or ''

    ids = [cid] if cid else allowed_client_ids_or_none()
    agora = datetime.utcnow()
    # A linha da lista mostra contrato, área e responsável: carregados de uma
    # vez, e não um SELECT por chamado.
    q = Chamado.query.options(db.selectinload(Chamado.contrato),
                              db.selectinload(Chamado.area),
                              db.selectinload(Chamado.responsavel))
    if ids is not None:
        q = q.filter(Chamado.client_id.in_(ids or [-1]))
    if visao in ('abertos', 'atrasados'):
        q = q.filter(Chamado.status.in_(STATUS_EM_ABERTO))
        if visao == 'atrasados':
            # O mesmo critério de ``Chamado.atrasado`` (e do cartão do topo),
            # no SQL: "Aguardando" tem o relógio parado (D8).
            q = q.filter(Chamado.status.in_(STATUS_CONTA_PRAZO),
                         Chamado.prazo.isnot(None), Chamado.prazo < agora)
    elif visao == 'meus':
        q = q.filter(Chamado.status.notin_(('fechado', 'cancelado')),
                     db.or_(Chamado.responsavel_id == current_user.id,
                            Chamado.solicitante_id == current_user.id))
    elif visao == 'confirmar':
        q = q.filter(Chamado.status == RESOLVIDO)
    if prioridade in PRIORIDADES:
        q = q.filter(Chamado.prioridade == prioridade)
    if categoria in CATEGORIAS:
        q = q.filter(Chamado.categoria == categoria)
    cortada = False
    if visao == 'todos':
        chamados = (q.order_by(Chamado.aberto_em.desc(), Chamado.id.desc())
                    .limit(POR_PAGINA + 1).all())
        cortada = len(chamados) > POR_PAGINA
        chamados = chamados[:POR_PAGINA]
    elif visao == 'confirmar':
        chamados = q.order_by(Chamado.aberto_em.desc(), Chamado.id.desc()).all()
    else:
        chamados = q.order_by(*_ordem_de_urgencia(agora)).all()
    return render_template('chamados/index.html', chamados=chamados, cortada=cortada,
                           por_pagina=POR_PAGINA,
                           contratos=contratos, client_id=cid, visao=visao, visoes=VISOES,
                           prioridade=prioridade, categoria=categoria,
                           prioridades=PRIORIDADES, categorias=CATEGORIAS,
                           numeros=servico.indicadores(ids), agora=agora,
                           pode_abrir=current_user.can_access(MODULO))


def _areas_por_contrato(contratos):
    from facilities.passagem.models import DiarioArea
    ids = [c.id for c in contratos]
    saida = {}
    for a in (DiarioArea.query.filter(DiarioArea.client_id.in_(ids or [-1]),
                                      DiarioArea.ativo.is_(True))
              .order_by(DiarioArea.nome).all()):
        saida.setdefault(a.client_id, []).append({'id': a.id, 'nome': a.nome})
    return saida


@bp.get('/novo')
@login_required
@module_required(MODULO)
def novo():
    if not current_user.can_access(MODULO):
        abort(403)
    contratos = clientes_visiveis()
    return render_template('chamados/novo.html', contratos=contratos,
                           areas=_areas_por_contrato(contratos),
                           client_id=request.args.get('client_id', type=int),
                           prioridades=PRIORIDADES, categorias=CATEGORIAS)


@bp.post('/')
@login_required
@module_required(MODULO)
def criar():
    f = request.form
    try:
        ch, criado = servico.abrir_sem_duplicar(
            current_user, f.get('client_id'), f.get('titulo'),
            descricao=f.get('descricao'), local=f.get('local'),
            categoria=f.get('categoria') or 'outro',
            prioridade=f.get('prioridade') or 'media',
            area_id=f.get('area_id') or None)
    except servico.RecusaChamado as ex:
        db.session.rollback()
        flash(ex.mensagem, 'danger')
        return redirect(url_for('chamados.novo', client_id=f.get('client_id') or None))
    # Formulário enviado duas vezes: as fotos já vieram com o primeiro envio.
    erro = _guardar_anexos(ch, request.files.getlist('arquivo'), 'antes') if criado else None
    db.session.commit()
    if erro:
        flash(f'Chamado {ch.numero} aberto, mas {erro}', 'warning')
    else:
        flash(f'Chamado {ch.numero} aberto. Os gestores do contrato foram avisados.', 'success')
    return redirect(url_for('chamados.ver', chamado_id=ch.id))


@bp.get('/<int:chamado_id>')
@login_required
@module_required(MODULO)
def ver(chamado_id):
    ch = _chamado_autorizado(chamado_id)
    acoes = servico.acoes_disponiveis(current_user, ch)
    tecnicos = servico.tecnicos_do_contrato(ch.client_id) if 'atribuir' in acoes else []
    from facilities.materiais import servico as materiais
    from facilities.materiais.models import Material
    pode_consumir = (servico.pode_agir(current_user, ch) and ch.status not in ('fechado', 'cancelado')
                     and current_user._effective_role() in materiais.PERFIS_QUE_CONSOMEM)
    return render_template('chamados/ver.html', ch=ch, acoes=acoes, tecnicos=tecnicos,
                           consumos=materiais.consumos_do_chamado(ch.id),
                           ve_custo=materiais.ve_custo(current_user),
                           materiais=Material.query.filter_by(is_active=True)
                           .order_by(Material.nome).all() if pode_consumir else [],
                           prioridades=PRIORIDADES, status=STATUS, agora=datetime.utcnow(),
                           pode_anexar=servico.pode_agir(current_user, ch)
                           and ch.status not in ('fechado', 'cancelado'))


@bp.post('/<int:chamado_id>/acao')
@login_required
@module_required(MODULO)
def acao(chamado_id):
    ch = _chamado_autorizado(chamado_id, travar=True)
    nome = request.form.get('acao') or ''
    try:
        feito = servico.executar(current_user, ch, nome, request.form)
    except servico.RecusaChamado as ex:
        db.session.rollback()
        if request.is_json:
            return jsonify({'error': ex.mensagem}), ex.status
        flash(ex.mensagem, 'danger')
        return redirect(url_for('chamados.ver', chamado_id=ch.id))
    erro = None
    arquivos = [a for a in request.files.getlist('arquivo') if a and a.filename]
    # Anexo só entra em chamado que continua vivo depois da ação (o
    # "resolver" leva a foto do serviço feito). Fechado ou cancelado não
    # recebe arquivo — a mesma regra da rota /anexos, que um POST montado
    # com acao=cancelar contornava. Pedido repetido não grava a foto de novo.
    if arquivos and feito.gravou:
        if ch.status in STATUS_ENCERRADOS:
            erro = 'os arquivos não foram guardados: o chamado está encerrado.'
        else:
            momento = 'depois' if nome == 'resolver' else 'antes'
            erro = _guardar_anexos(ch, arquivos, momento)
    db.session.commit()
    flash(feito.mensagem, feito.categoria)
    if erro:
        flash(erro[:1].upper() + erro[1:], 'warning')
    return redirect(url_for('chamados.ver', chamado_id=ch.id))


# ── Anexos ───────────────────────────────────────────────────────────────

def _guardar_anexos(ch, arquivos, momento):
    """Guarda as fotos/PDFs enviados; devolve uma mensagem se algum foi recusado.

    Extensão E assinatura conferidas (``facilities.core.anexos``). O que passa
    é gravado; o que não passa vira aviso — o chamado não deixa de existir
    porque uma foto veio num formato estranho.
    """
    arquivos = [a for a in (arquivos or []) if a and a.filename]
    if not arquivos:
        return None
    aviso = None
    if len(arquivos) > ANEXOS_POR_ENVIO:
        aviso = f'só os {ANEXOS_POR_ENVIO} primeiros arquivos foram considerados.'
    recusados = []
    for arq in arquivos[:ANEXOS_POR_ENVIO]:
        nome = secure_filename(arq.filename) or 'arquivo'
        ext = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
        dados = arq.read(ANEXO_MAX + 1)
        assinaturas = ANEXO_ASSINATURA.get(ext)
        if (ext not in ANEXO_TIPOS or len(dados) > ANEXO_MAX or not dados
                or (assinaturas and not any(dados.startswith(a) for a in assinaturas))):
            recusados.append(arq.filename)
            continue
        chave = f'chamados/{ch.id}/{uuid.uuid4().hex}.{ext}'
        storage().save(chave, dados, ANEXO_TIPOS[ext])
        db.session.add(ChamadoAnexo(chamado=ch, nome=nome[:200], mime=ANEXO_TIPOS[ext],
                                    tamanho=len(dados), storage_key=chave, momento=momento,
                                    uploaded_by=current_user.id))
    if recusados:
        return ('arquivo recusado (formato, tamanho ou conteúdo não confere): '
                + ', '.join(recusados[:3]) + '.')
    return aviso


@bp.post('/<int:chamado_id>/anexos')
@login_required
@module_required(MODULO)
def anexar(chamado_id):
    # Travado como as ações: a foto que chega junto com um cancelamento só
    # confere o status depois que o cancelamento gravou.
    ch = _chamado_autorizado(chamado_id, travar=True)
    if not servico.pode_agir(current_user, ch) or ch.status in STATUS_ENCERRADOS:
        abort(403)
    momento = 'depois' if request.form.get('momento') == 'depois' else 'antes'
    arquivos = [a for a in request.files.getlist('arquivo') if a and a.filename]
    if not arquivos:
        flash('Escolha ao menos um arquivo.', 'warning')
        return redirect(url_for('chamados.ver', chamado_id=ch.id))
    erro = _guardar_anexos(ch, arquivos, momento)
    db.session.commit()
    flash(erro or 'Arquivo anexado.', 'warning' if erro else 'success')
    return redirect(url_for('chamados.ver', chamado_id=ch.id))


@bp.get('/anexos/<int:anexo_id>')
@login_required
@module_required(MODULO)
def baixar_anexo(anexo_id):
    a = db.get_or_404(ChamadoAnexo, anexo_id)
    _chamado_autorizado(a.chamado_id)
    try:
        dados = storage().load(a.storage_key)
    except Exception:
        abort(404)
    # Só imagem abre na própria página (é a miniatura do chamado). PDF vai
    # como download, como na Passagem: aberto inline, ele roda na mesma origem
    # do sistema, e o arquivo veio de qualquer pessoa que abre chamado.
    inline = (a.mime or '').startswith('image/')
    return send_file(io.BytesIO(dados), mimetype=a.mime or 'application/octet-stream',
                     as_attachment=not inline, download_name=a.nome)
