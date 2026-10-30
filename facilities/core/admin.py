"""Cadastros do administrador: pessoas e locais (os antigos "contratos").

Nada se apaga: pessoa e contrato são DESATIVADOS. O histórico de passagens,
pendências e chamados aponta para eles, e apagar deixaria o histórico sem
dono ("quem encerrou esta passagem?").
"""
import json
import secrets

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities.extensions import db
from facilities.core.acesso import admin_required
from facilities.core.models import PERFIS, PERFIS_DE_GESTAO, Client, User

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _senha_temporaria():
    # 12 caracteres sem ambiguidade visual (sem 0/O, 1/l/I).
    alfabeto = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alfabeto) for _ in range(12))


# ── Pessoas ──────────────────────────────────────────────────────────────

@bp.get('/usuarios')
@login_required
@admin_required
def usuarios():
    from facilities.cadastros.models import Contratante
    from facilities.core.hierarquia import cadeia_acima, superiores_possiveis
    from sqlalchemy.orm import selectinload
    pessoas = (User.query.filter(User.is_deleted.is_(False))
               .options(selectinload(User.clients))
               .order_by(User.is_active.desc(), User.name).all())
    contratos = Client.query.filter(Client.is_deleted.is_(False)).order_by(Client.name).all()
    return render_template('core/usuarios.html', pessoas=pessoas, contratos=contratos,
                           perfis=PERFIS, permissoes=User.PERMISSOES_FINAS,
                           superiores=superiores_possiveis(), cadeia_acima=cadeia_acima,
                           clientes=Contratante.query.order_by(Contratante.nome).all())


def _aplicar_formulario(u, form):
    u.name = (form.get('name') or '').strip()[:100]
    u.email = (form.get('email') or '').strip().lower()[:150]
    role = form.get('role') or 'encarregado'
    u.role = role if role in PERFIS else 'encarregado'
    u.all_clients = bool(form.get('all_clients'))
    ids = [int(x) for x in form.getlist('clients') if str(x).isdigit()]
    u.clients = Client.query.filter(Client.id.in_(ids or [-1])).all()
    finas = [p for p in form.getlist('permissoes') if p in User.PERMISSOES_FINAS]
    u.permissions_json = json.dumps(finas)


def _aplicar_cadeia(u, form, role_antes=None):
    """Superior e cliente: devolve a mensagem de erro, ou None."""
    from facilities.cadastros.models import Contratante
    from facilities.core.hierarquia import (CadeiaInvalida, problema_ao_mudar_perfil,
                                            validar_superior)
    if u.id is not None and role_antes is not None and role_antes != u.role:
        erro = problema_ao_mudar_perfil(u, u.role)
        if erro:
            return erro
    sid = form.get('superior_id')
    try:
        u.superior_id = validar_superior(u, int(sid) if str(sid or '').isdigit() else None)
    except CadeiaInvalida as erro:
        return str(erro)
    if u.role == 'cliente':
        cid = form.get('cliente_id')
        cli = db.session.get(Contratante, int(cid)) if str(cid or '').isdigit() else None
        if cli is None:
            return 'Escolha de qual cliente é esta pessoa.'
        u.cliente_id = cli.id
        u.all_clients = False
    else:
        u.cliente_id = None
    return None


def _validar(u, original_id=None):
    if not u.name:
        return 'Informe o nome.'
    if '@' not in (u.email or ''):
        return 'Informe um e-mail válido.'
    outro = User.por_email(u.email)
    if outro is not None and outro.id != original_id:
        return 'Já existe uma pessoa com este e-mail.'
    return None


@bp.post('/usuarios')
@login_required
@admin_required
def criar_usuario():
    u = User()
    _aplicar_formulario(u, request.form)
    erro = _validar(u) or _aplicar_cadeia(u, request.form)
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return redirect(url_for('admin.usuarios'))
    senha = _senha_temporaria()
    u.set_password(senha)
    u.must_change_password = True
    db.session.add(u)
    db.session.commit()
    flash(f'Cadastro de {u.name} criado. Senha temporária: {senha} — entregue '
          f'pessoalmente; no primeiro acesso o sistema pede uma senha nova.', 'success')
    return redirect(url_for('admin.usuarios'))


@bp.post('/usuarios/<int:uid>')
@login_required
@admin_required
def editar_usuario(uid):
    u = db.get_or_404(User, uid)
    era_ativo = u.is_active
    role_antes = u.role
    _aplicar_formulario(u, request.form)
    u.is_active = bool(request.form.get('is_active'))
    if u.id == current_user.id and (not u.is_active or u.role != 'master'):
        db.session.rollback()
        flash('Você não pode tirar o seu próprio acesso de administrador.', 'danger')
        return redirect(url_for('admin.usuarios'))
    erro = _validar(u, original_id=u.id) or _aplicar_cadeia(u, request.form, role_antes)
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return redirect(url_for('admin.usuarios'))
    if era_ativo and not u.is_active:
        u.session_epoch = (u.session_epoch or 0) + 1   # derruba as sessões abertas
    db.session.commit()
    flash(f'Cadastro de {u.name} atualizado.', 'success')
    return redirect(url_for('admin.usuarios'))


@bp.post('/usuarios/<int:uid>/nova-senha')
@login_required
@admin_required
def nova_senha(uid):
    u = db.get_or_404(User, uid)
    senha = _senha_temporaria()
    u.set_password(senha)
    u.must_change_password = True
    u.failed_login_count = 0
    u.lockout_until = None
    u.session_epoch = (u.session_epoch or 0) + 1
    db.session.commit()
    flash(f'Senha temporária de {u.name}: {senha}', 'success')
    return redirect(url_for('admin.usuarios'))


@bp.post('/usuarios/<int:uid>/desligar-codigo')
@login_required
@admin_required
def desligar_codigo(uid):
    """A pessoa perdeu o celular: o administrador desliga a segunda etapa.
    As sessões abertas caem (quem achou o celular não continua dentro)."""
    u = db.get_or_404(User, uid)
    u.totp_ativo = False
    u.totp_segredo = None
    u.totp_ultimo_passo = None
    u.session_epoch = (u.session_epoch or 0) + 1
    db.session.commit()
    flash(f'Segunda etapa de {u.name} desligada. No próximo login ela entra só com a '
          f'senha e pode ativar de novo em "Segurança da conta".', 'success')
    return redirect(url_for('admin.usuarios'))


# ── Locais (a tabela ``clients``; o endereço /admin/contratos é o de sempre) ─

@bp.get('/contratos')
@login_required
@admin_required
def contratos():
    from facilities.cadastros.models import Contratante, Estado
    lista = Client.query.filter(Client.is_deleted.is_(False)).order_by(
        Client.is_active.desc(), Client.name).all()
    gestores = (User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                                  User.role.in_(PERFIS_DE_GESTAO))
                .order_by(User.name).all())
    return render_template('core/contratos.html', contratos=lista, gestores=gestores,
                           clientes=Contratante.query.order_by(Contratante.nome).all(),
                           estados=Estado.query.order_by(Estado.nome).all())


def _aplicar_contrato(c, form):
    c.name = (form.get('name') or '').strip()[:120]
    c.cost_center = (form.get('cost_center') or '').strip()[:50] or None
    c.endereco = (form.get('endereco') or '').strip()[:255] or None
    rid = form.get('responsible_user_id')
    c.responsible_user_id = int(rid) if str(rid or '').isdigit() else None


def _responsavel_invalido(c):
    """O responsável tem de ser gestor ou administrador ATIVO — a lista da
    tela já é só essa, mas um POST montado à mão aceitava qualquer id (e o
    encarregado escolhido passava a receber os avisos de gestor)."""
    if c.responsible_user_id is None:
        return None
    u = db.session.get(User, c.responsible_user_id)
    if (u is None or u.is_deleted or not u.is_active
            or u.role not in PERFIS_DE_GESTAO):
        return 'O responsável precisa ser um gestor ou administrador ativo.'
    return None


def _vincular(c):
    """Cliente e estado do local; o erro volta como mensagem para a tela."""
    from facilities.cadastros.servico import CadastroInvalido, vincular_local
    try:
        vincular_local(c, request.form, current_user)
    except CadastroInvalido as erro:
        return str(erro)
    return None


@bp.post('/contratos')
@login_required
@admin_required
def criar_contrato():
    from facilities.cadastros.servico import registrar_local
    c = Client(is_active=True)
    _aplicar_contrato(c, request.form)
    erro = ('Informe o nome do local.' if not c.name
            else _responsavel_invalido(c) or _vincular(c))
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return redirect(url_for('admin.contratos'))
    db.session.add(c)
    registrar_local(c, None, current_user, nova=True)
    db.session.commit()
    flash(f'Local {c.name} cadastrado. Agora cadastre a estrutura dele (setores, '
          f'ambientes e pontos) e configure a passagem de turno.', 'success')
    return redirect(url_for('admin.contratos'))


@bp.post('/contratos/<int:cid>')
@login_required
@admin_required
def editar_contrato(cid):
    from facilities.cadastros.servico import foto, registrar_local
    c = db.get_or_404(Client, cid)
    antes = foto(c)
    _aplicar_contrato(c, request.form)
    c.is_active = bool(request.form.get('is_active'))
    erro = ('Informe o nome do local.' if not c.name
            else _responsavel_invalido(c) or _vincular(c))
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return redirect(url_for('admin.contratos'))
    registrar_local(c, antes, current_user)
    db.session.commit()
    flash(f'Local {c.name} atualizado.', 'success')
    return redirect(url_for('admin.contratos'))
