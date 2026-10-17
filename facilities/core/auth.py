"""Login próprio: entrar, sair e trocar a senha.

* Cinco tentativas erradas seguidas bloqueiam a conta por 15 minutos — e o
  limite do Flask-Limiter (por IP + e-mail) segura a enxurrada de tentativas.
* A resposta é a MESMA — mensagem, status e tempo — para e-mail inexistente,
  senha errada e conta bloqueada: não diz a quem tenta quais e-mails existem.
* Trocar a senha (ou o administrador desativar a pessoa) sobe a "época" da
  sessão, e o cookie antigo deixa de valer em todo aparelho.
"""
import functools
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from facilities.extensions import db, limiter
from facilities.core.models import User

bp = Blueprint('auth', __name__)

TENTATIVAS_ANTES_DO_BLOQUEIO = 5
MINUTOS_DE_BLOQUEIO = 15
SENHA_MINIMA = 8

# Uma mensagem só para e-mail inexistente, senha errada e conta bloqueada. Ela
# já conta do bloqueio a quem errou de verdade — sem dizer se o e-mail existe.
MSG_LOGIN_RECUSADO = (f'E-mail ou senha incorretos. Depois de {TENTATIVAS_ANTES_DO_BLOQUEIO} '
                      f'tentativas erradas, o acesso fica bloqueado por '
                      f'{MINUTOS_DE_BLOQUEIO} minutos.')


@functools.lru_cache(maxsize=1)
def _hash_de_mentira():
    """Hash de uma senha de ninguém, no MESMO algoritmo das senhas reais.

    Para e-mail inexistente a conferência roda contra ele (e recusa de
    qualquer jeito, porque não há usuário): sem isso a
    resposta saía ~50 vezes mais rápida (nenhum hash calculado) e o tempo
    entregava quais e-mails existem.
    """
    return generate_password_hash('nenhuma-senha-abre-este-hash')


def _destino_seguro(alvo):
    """Só volta para caminho interno — nunca para outro site.

    Recusa ``//host`` e ``/\\host`` (o navegador lê os dois como "outro
    site") e qualquer caractere de controle, que o navegador descarta e
    pode transformar ``/<TAB>/host`` em ``//host``.
    """
    if not alvo:
        return None
    if '\\' in alvo or any(ord(c) < 32 or ord(c) == 127 for c in alvo):
        return None
    p = urlparse(alvo)
    if p.scheme or p.netloc or not alvo.startswith('/') or alvo.startswith('//'):
        return None
    return alvo


def _chave_do_login():
    """Chave do limite de login: IP + e-mail digitado.

    Só pelo IP, atrás de proxy (ou da operadora, no 4G, ou do Wi-Fi do
    posto), todo mundo cai no MESMO balde: na troca de turno, o 21º
    encarregado do minuto levava 429 com a senha certa — e qualquer um
    derrubava o login de todos mandando 20 tentativas. Com o e-mail na chave,
    quem insiste trava só aquele par; contra adivinhar a senha de uma conta,
    vale o bloqueio da conta (5 erros).
    """
    email = (request.form.get('email') or '').strip().lower()[:254]
    return f'{get_remote_address()}|{email}'


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('20 per minute', methods=['POST'], key_func=_chave_do_login)
# Teto por IP, folgado para a troca de turno de um posto inteiro no mesmo
# Wi-Fi, mas que segura quem varre muitos e-mails de um lugar só.
@limiter.limit('60 per minute', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.inicio'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        senha = request.form.get('password') or ''
        u = User.query.filter(db.func.lower(User.email) == email).first()
        agora = datetime.utcnow()
        # O hash é conferido SEMPRE — e-mail inexistente e conta bloqueada
        # inclusive —, para o tempo de resposta não separar os casos.
        senha_confere = check_password_hash(
            (u.password_hash if u is not None and u.password_hash else None)
            or _hash_de_mentira(), senha)
        bloqueada = bool(u is not None and u.lockout_until and u.lockout_until > agora)
        if (u is None or not u.is_active or u.is_deleted or bloqueada
                or not senha_confere):
            # Durante o bloqueio não se conta erro: o prazo não se estende
            # sozinho enquanto alguém insiste.
            if u is not None and not bloqueada:
                u.failed_login_count = (u.failed_login_count or 0) + 1
                if u.failed_login_count >= TENTATIVAS_ANTES_DO_BLOQUEIO:
                    u.lockout_until = agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO)
                    u.failed_login_count = 0
                db.session.commit()
            flash(MSG_LOGIN_RECUSADO, 'danger')
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
