"""Telas de materiais: catálogo, estoque, custo e pedidos no site; consumo e
pedido de insumo no aplicativo (``/app/materiais``)."""
import io
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import allowed_client_ids_or_none, clientes_visiveis, require_client
from facilities.core.models import Client
from facilities.materiais import servico
from facilities.materiais.models import (CONSUMO, TIPOS_MOVIMENTO, Material, MovimentoEstoque,
                                         PedidoInsumo, fmt_qtd)
from facilities.materiais.servico import RegraDoMaterial

bp = Blueprint('materiais', __name__)


@bp.app_template_filter('qtd')
def _filtro_qtd(q):
    return fmt_qtd(q)


@bp.app_template_filter('reais')
def _filtro_reais(v):
    return servico.reais(v)


def _so_quem_ve_custo():
    if not servico.ve_custo(current_user):
        raise Forbidden('Estoque e custo ficam com a supervisão, a gestão e a diretoria.')


def _so_gestao():
    if not current_user.e_gestao():
        raise Forbidden('O catálogo e o estoque são cuidados pela gestão.')


def _local(cid):
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _erro(erro, destino):
    db.session.rollback()
    flash(erro.mensagem, 'danger')
    return redirect(destino)


def _periodo():
    hoje = tempo.hoje()
    try:
        de = datetime.strptime(request.args.get('de') or '', '%Y-%m-%d').date()
    except ValueError:
        de = hoje.replace(day=1)
    try:
        ate = datetime.strptime(request.args.get('ate') or '', '%Y-%m-%d').date()
    except ValueError:
        ate = hoje
    return (de, ate) if de <= ate else (ate, de)


# ── Catálogo ──────────────────────────────────────────────────────────────

@bp.get('/materiais/')
@login_required
def catalogo():
    _so_quem_ve_custo()
    return render_template('materiais/catalogo.html',
                           materiais=Material.query.order_by(Material.is_active.desc(),
                                                             Material.nome).all(),
                           locais=clientes_visiveis(), pode_montar=current_user.e_gestao())


@bp.post('/materiais/')
@login_required
def criar_material():
    _so_gestao()
    try:
        m = servico.salvar_material(None, request.form)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, url_for('materiais.catalogo'))
    flash(f'Material "{m.nome}" cadastrado.', 'success')
    return redirect(url_for('materiais.catalogo'))


@bp.post('/materiais/<int:mid>')
@login_required
def editar_material(mid):
    _so_gestao()
    m = db.get_or_404(Material, mid)
    if request.form.get('ativo') in ('0', '1'):
        m.is_active = request.form.get('ativo') == '1'
        db.session.commit()
        flash('Material reativado.' if m.is_active else
              'Material desativado: some das listas (o histórico fica).', 'success')
        return redirect(url_for('materiais.catalogo'))
    try:
        servico.salvar_material(m, request.form)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, url_for('materiais.catalogo'))
    flash('Material atualizado. O preço novo vale para os próximos lançamentos.', 'success')
    return redirect(url_for('materiais.catalogo'))


# ── Estoque do local ──────────────────────────────────────────────────────

@bp.get('/materiais/locais/<int:cid>')
@login_required
def local(cid):
    from facilities.rotas.models import Rota
    _so_quem_ve_custo()
    loc = _local(cid)
    saldos = servico.saldos(loc.id)
    materiais = Material.query.filter_by(is_active=True).order_by(Material.nome).all()
    return render_template(
        'materiais/local.html', local=loc, materiais=materiais, saldos=saldos,
        com_saldo=[m for m in Material.query.order_by(Material.nome) if m.id in saldos],
        movimentos=MovimentoEstoque.query.filter_by(client_id=loc.id)
        .order_by(MovimentoEstoque.criado_em.desc()).limit(50).all(),
        rotas=Rota.query.filter_by(client_id=loc.id, is_active=True).order_by(Rota.nome).all(),
        tipos=TIPOS_MOVIMENTO, pode_montar=current_user.e_gestao(),
        gestor_do_contrato=servico.e_gestor_do_contrato(current_user, loc.id))


@bp.post('/materiais/locais/<int:cid>/movimento')
@login_required
def movimento(cid):
    loc = _local(cid)
    destino = url_for('materiais.local', cid=loc.id)
    tipo = request.form.get('tipo')
    if tipo not in TIPOS_MOVIMENTO or tipo == CONSUMO:
        flash('Escolha entrada, saída ou ajuste.', 'danger')
        return redirect(destino)
    try:
        mov = servico.movimentar(current_user, loc, request.form, tipo)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, destino)
    flash(f'{mov.tipo_rotulo}: {fmt_qtd(abs(mov.quantidade))} {mov.material.unidade} de '
          f'{mov.material.nome}. Saldo agora: '
          f'{fmt_qtd(servico.saldo(loc.id, mov.material_id))}.', 'success')
    return redirect(destino)


@bp.post('/materiais/locais/<int:cid>/consumo')
@login_required
def consumo(cid):
    loc = _local(cid)
    ch_id = servico._id(request.form, 'chamado_id')
    destino = (url_for('chamados.ver', chamado_id=ch_id) if request.form.get('voltar') == 'chamado'
               and ch_id else url_for('materiais.local', cid=loc.id)
               if servico.ve_custo(current_user) else url_for('materiais.app'))
    try:
        mov = servico.consumir(current_user, loc, request.form)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, destino)
    flash(f'Consumo registrado: {fmt_qtd(abs(mov.quantidade))} {mov.material.unidade} de '
          f'{mov.material.nome}.', 'success')
    return redirect(destino)


@bp.get('/materiais/locais/<int:cid>/mes')
@login_required
def mes(cid):
    _so_quem_ve_custo()
    loc = _local(cid)
    hoje = tempo.hoje()
    try:
        ano, m = (int(x) for x in (request.args.get('m') or hoje.strftime('%Y-%m')).split('-'))
        primeiro = date(ano, m, 1)
    except ValueError:
        primeiro = hoje.replace(day=1)
    ultimo = (primeiro + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    linhas = servico.consumo_do_mes(loc.id, primeiro, ultimo)
    return render_template('materiais/mes.html', local=loc, primeiro=primeiro, linhas=linhas,
                           total=sum((x['valor'] for x in linhas if x['valor'] is not None),
                                     servico.Decimal('0.00')),
                           sem_preco=[x for x in linhas if x['valor'] is None],
                           anterior=(primeiro - timedelta(days=1)).strftime('%Y-%m'),
                           seguinte=(ultimo + timedelta(days=1)).strftime('%Y-%m'))


@bp.get('/materiais/custo')
@login_required
def custo():
    _so_quem_ve_custo()
    de, ate = _periodo()
    return render_template('materiais/custo.html', de=de, ate=ate,
                           r=servico.custo(allowed_client_ids_or_none(), de, ate))


# ── Pedidos de insumo ─────────────────────────────────────────────────────

@bp.get('/materiais/pedidos')
@login_required
def pedidos():
    _so_quem_ve_custo()
    ids = allowed_client_ids_or_none()
    q = PedidoInsumo.query
    if ids is not None:
        q = q.filter(PedidoInsumo.client_id.in_(ids or [-1]))
    lista = q.order_by(PedidoInsumo.status, PedidoInsumo.criado_em.desc()).limit(200).all()
    return render_template('materiais/pedidos.html', pedidos=lista, agora=datetime.utcnow(),
                           gestor_de={p.client_id: servico.e_gestor_do_contrato(current_user,
                                                                                p.client_id)
                                      for p in lista})


@bp.post('/materiais/pedidos/<int:pid>/visto')
@login_required
def visto(pid):
    p = db.get_or_404(PedidoInsumo, pid)
    require_client(p.client_id)
    try:
        servico.marcar_visto(current_user, p)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, url_for('materiais.pedidos'))
    flash('Pedido marcado como visto. A compra segue no sistema de compras.', 'success')
    return redirect(url_for('materiais.pedidos'))


@bp.get('/materiais/pedidos/<int:pid>/foto')
@login_required
def foto(pid):
    from facilities.core.anexos import storage
    p = db.get_or_404(PedidoInsumo, pid)
    require_client(p.client_id)
    if not (servico.ve_custo(current_user) or p.user_id == current_user.id) or not p.foto_key:
        abort(404)
    try:
        dados = storage().load(p.foto_key)
    except Exception:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype=p.foto_mime or 'image/jpeg')


# ── Aplicativo ────────────────────────────────────────────────────────────

def _pode_usar_app():
    if current_user._effective_role() not in servico.PERFIS_QUE_CONSOMEM:
        raise Forbidden('Seu perfil não lança material.')


@bp.get('/app/materiais')
@login_required
def app():
    from facilities.chamados.models import STATUS_EM_ABERTO, Chamado
    from facilities.rotas.models import Rota
    _pode_usar_app()
    locais = clientes_visiveis()
    ids = [c.id for c in locais] or [-1]
    return render_template(
        'materiais/app.html', locais=locais,
        materiais=Material.query.filter_by(is_active=True).order_by(Material.nome).all(),
        chamados=Chamado.query.filter(Chamado.client_id.in_(ids),
                                      Chamado.status.in_(STATUS_EM_ABERTO))
        .order_by(Chamado.aberto_em.desc()).limit(100).all(),
        rotas=Rota.query.filter(Rota.client_id.in_(ids), Rota.is_active.is_(True))
        .order_by(Rota.nome).all(),
        meus=PedidoInsumo.query.filter_by(user_id=current_user.id)
        .order_by(PedidoInsumo.criado_em.desc()).limit(10).all())


@bp.post('/app/materiais/consumo')
@login_required
def app_consumo():
    _pode_usar_app()
    loc = _local(servico._id(request.form, 'client_id') or -1)
    try:
        mov = servico.consumir(current_user, loc, request.form)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, url_for('materiais.app'))
    flash(f'Consumo registrado: {fmt_qtd(abs(mov.quantidade))} {mov.material.unidade} de '
          f'{mov.material.nome} ({loc.name}).', 'success')
    return redirect(url_for('materiais.app'))


@bp.post('/app/materiais/pedido')
@login_required
def app_pedido():
    _pode_usar_app()
    loc = _local(servico._id(request.form, 'client_id') or -1)
    arq = request.files.get('foto')
    try:
        servico.pedir(current_user, loc, request.form, arq if arq and arq.filename else None)
        db.session.commit()
    except RegraDoMaterial as erro:
        return _erro(erro, url_for('materiais.app'))
    flash('Pedido enviado ao gestor do contrato.', 'success')
    return redirect(url_for('materiais.app'))
