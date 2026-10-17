"""Login próprio: entrar, sair e trocar a senha.

* Cinco tentativas erradas seguidas bloqueiam a conta por 15 minutos — e o
  limite por IP (Flask-Limiter) segura quem tenta muitas contas.
* A mensagem de erro é a mesma para e-mail inexistente e senha errada: não
  diz a quem tenta quais e-mails existem.
* Trocar a senha (ou o administrador desativar a pessoa) sobe a "época" da
  sessão, e o cookie antigo deixa de valer em todo aparelho.
"""
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from facilities.extensions import db, limiter
from facilities.core.models import User

bp = Blueprint('auth', __name__)

TENTATIVAS_ANTES_DO_BLOQUEIO = 5
MINUTOS_DE_BLOQUEIO = 15
SENHA_MINIMA = 8


def _destino_seguro(alvo):
    """Só volta para caminho interno — nunca para outro site."""
    if not alvo:
        return None
    p = urlparse(alvo)
    if p.scheme or p.netloc or not alvo.startswith('/') or alvo.startswith('//'):
        return None
    return alvo


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('20 per minute', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.inicio'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        senha = request.form.get('password') or ''
        u = User.query.filter(db.func.lower(User.email) == email).first()
        agora = datetime.utcnow()
        if u is not None and u.lockout_until and u.lockout_until > agora:
            flash('Conta bloqueada por excesso de tentativas. Tente de novo em '
                  'alguns minutos.', 'danger')
            return render_template('core/login.html', email=email), 429
        if (u is None or not u.is_active or u.is_deleted
                or not u.check_password(senha)):
            if u is not None:
                u.failed_login_count = (u.failed_login_count or 0) + 1
                if u.failed_login_count >= TENTATIVAS_ANTES_DO_BLOQUEIO:
                    u.lockout_until = agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO)
                    u.failed_login_count = 0
                db.session.commit()
            flash('E-mail ou senha incorretos.', 'danger')
            return render_template('core/login.html', email=email), 401
        u.failed_login_count = 0
        u.lockout_until = None
        u.last_login_at = agora
        db.session.commit()
        login_user(u, remember=bool(request.form.get('lembrar')))
        if u.must_change_password:
            return redirect(url_for('auth.trocar_senha'))
        return redirect(_destino_seguro(request.args.get('next')) or url_for('core.inicio'))
    return render_template('core/login.html', email='')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/trocar-senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if request.method == 'POST':
        atual = request.form.get('atual') or ''
        nova = request.form.get('nova') or ''
        confirma = request.form.get('confirma') or ''
        erro = None
        if not current_user.check_password(atual):
            erro = 'A senha atual não confere.'
        elif len(nova) < SENHA_MINIMA:
            erro = f'A senha nova precisa ter pelo menos {SENHA_MINIMA} caracteres.'
        elif nova != confirma:
            erro = 'A confirmação não é igual à senha nova.'
        elif nova == atual:
            erro = 'A senha nova precisa ser diferente da atual.'
        if erro:
            flash(erro, 'danger')
            return render_template('core/trocar_senha.html'), 400
        current_user.set_password(nova)
        current_user.must_change_password = False
        current_user.session_epoch = (current_user.session_epoch or 0) + 1
        db.session.commit()
        # A época mudou: renova a sessão DESTE aparelho com o id novo.
        login_user(current_user._get_current_object())
        flash('Senha trocada.', 'success')
        return redirect(url_for('core.inicio'))
    return render_template('core/trocar_senha.html')
