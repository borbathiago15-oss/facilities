"""Cadastros do administrador: pessoas e contratos.

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
from facilities.core.models import PERFIS, Client, User

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
    pessoas = (User.query.filter(User.is_deleted.is_(False))
               .order_by(User.is_active.desc(), User.name).all())
    contratos = Client.query.filter(Client.is_deleted.is_(False)).order_by(Client.name).all()
    return render_template('core/usuarios.html', pessoas=pessoas, contratos=contratos,
                           perfis=PERFIS, permissoes=User.PERMISSOES_FINAS)


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


def _validar(u, original_id=None):
    if not u.name:
        return 'Informe o nome.'
    if '@' not in (u.email or ''):
        return 'Informe um e-mail válido.'
    outro = User.query.filter(db.func.lower(User.email) == u.email).first()
    if outro is not None and outro.id != original_id:
        return 'Já existe uma pessoa com este e-mail.'
    return None


@bp.post('/usuarios')
@login_required
@admin_required
def criar_usuario():
    u = User()
    _aplicar_formulario(u, request.form)
    erro = _validar(u)
    if erro:
        flash(erro, 'danger')
        return redirect(url_for('admin.usuarios'))
    senha = _senha_temporaria()
    u.set_password(senha)
    u.must_change_password = True
    db.session.add(u)
    db.session.commit()
    flash(f'{u.name} cadastrado. Senha temporária: {senha} — passe a ele; '
          f'no primeiro acesso o sistema pede uma senha nova.', 'success')
    return redirect(url_for('admin.usuarios'))


@bp.post('/usuarios/<int:uid>')
@login_required
@admin_required
def editar_usuario(uid):
    u = db.get_or_404(User, uid)
    era_ativo = u.is_active
    _aplicar_formulario(u, request.form)
    u.is_active = bool(request.form.get('is_active'))
    if u.id == current_user.id and (not u.is_active or u.role != 'master'):
        db.session.rollback()
        flash('Você não pode tirar o seu próprio acesso de administrador.', 'danger')
        return redirect(url_for('admin.usuarios'))
    erro = _validar(u, original_id=u.id)
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return redirect(url_for('admin.usuarios'))
    if era_ativo and not u.is_active:
        u.session_epoch = (u.session_epoch or 0) + 1   # derruba as sessões abertas
    db.session.commit()
    flash(f'{u.name} atualizado.', 'success')
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


# ── Contratos ────────────────────────────────────────────────────────────

@bp.get('/contratos')
@login_required
@admin_required
def contratos():
    lista = Client.query.filter(Client.is_deleted.is_(False)).order_by(
        Client.is_active.desc(), Client.name).all()
    gestores = (User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                                  User.role.in_(('master', 'pleno')))
                .order_by(User.name).all())
    return render_template('core/contratos.html', contratos=lista, gestores=gestores)


def _aplicar_contrato(c, form):
    c.name = (form.get('name') or '').strip()[:120]
    c.cost_center = (form.get('cost_center') or '').strip()[:50] or None
    c.endereco = (form.get('endereco') or '').strip()[:255] or None
    rid = form.get('responsible_user_id')
    c.responsible_user_id = int(rid) if str(rid or '').isdigit() else None


@bp.post('/contratos')
@login_required
@admin_required
def criar_contrato():
    c = Client(is_active=True)
    _aplicar_contrato(c, request.form)
    if not c.name:
        flash('Informe o nome do contrato.', 'danger')
        return redirect(url_for('admin.contratos'))
    db.session.add(c)
    db.session.commit()
    flash(f'Contrato {c.name} cadastrado. Agora configure a passagem de turno '
          f'dele (áreas, turnos e perguntas).', 'success')
    return redirect(url_for('admin.contratos'))


@bp.post('/contratos/<int:cid>')
@login_required
@admin_required
def editar_contrato(cid):
    c = db.get_or_404(Client, cid)
    _aplicar_contrato(c, request.form)
    c.is_active = bool(request.form.get('is_active'))
    if not c.name:
        db.session.rollback()
        flash('Informe o nome do contrato.', 'danger')
        return redirect(url_for('admin.contratos'))
    db.session.commit()
    flash(f'Contrato {c.name} atualizado.', 'success')
    return redirect(url_for('admin.contratos'))
