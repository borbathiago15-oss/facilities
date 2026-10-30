"""Login próprio: entrar, sair e trocar a senha.

* Cinco tentativas erradas seguidas bloqueiam a conta por 15 minutos — e o
  limite do Flask-Limiter (por IP + e-mail) segura a enxurrada de tentativas.
* A resposta é a MESMA — mensagem, status e tempo — para e-mail inexistente,
  senha errada e conta bloqueada: não diz a quem tenta quais e-mails existem.
* Trocar a senha (ou o administrador desativar a pessoa) sobe a "época" da
  sessão, e o cookie antigo deixa de valer em todo aparelho. SAIR também
  (Fase 2): antes o "Sair" só apagava o cookie deste navegador, e uma cópia
  dele (ou o "Manter conectado" de 14 dias) continuava abrindo o sistema.
* Segunda etapa (Fase 2): quem ativou o código do aplicativo autenticador
  passa pela senha E pelo código. Entre as duas etapas a pessoa NÃO está
  logada — só o id fica guardado na sessão, por 5 minutos e 5 tentativas.
* O perfil cliente ainda não entra (liberação na Fase 9).
* Auditoria de segurança (19/10/2026): o erro de senha é contado com UPDATE
  atômico (rajadas em paralelo não escapam do bloqueio); os erros de código
  ficam no servidor, não no cookie; a gestão é obrigada a usar a segunda
  etapa (``exige_segunda_etapa``); e trocar a senha ou desligar o código
  também contam os erros da senha atual.
"""
import functools
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_limiter.util import get_remote_address
from flask import current_app
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, update
from werkzeug.security import check_password_hash, generate_password_hash

from facilities.extensions import db, limiter
from facilities.core import senhas, totp
from facilities.core.models import PERFIS_COM_SEGUNDA_ETAPA, PERFIS_SEM_LOGIN, User

bp = Blueprint('auth', __name__)

TENTATIVAS_ANTES_DO_BLOQUEIO = 5
MINUTOS_DE_BLOQUEIO = 15
SENHA_MINIMA = 8

# Uma mensagem só para e-mail inexistente, senha errada e conta bloqueada. Ela
# já conta do bloqueio a quem errou de verdade — sem dizer se o e-mail existe.
MSG_CLIENTE_SEM_ACESSO = ('O acesso de clientes ao Trino Facilities ainda não foi '
                          'liberado. Fale com o seu gerente na Trino.')
MINUTOS_PARA_O_CODIGO = 5
TENTATIVAS_DO_CODIGO = 5
MINUTOS_DE_BLOQUEIO_DO_CODIGO = 15

MSG_CODIGO_TRAVADO = (f'Código errado {TENTATIVAS_DO_CODIGO} vezes. Por segurança, a entrada '
                      f'por código fica travada por {MINUTOS_DE_BLOQUEIO_DO_CODIGO} minutos.')

MSG_LOGIN_RECUSADO = (f'E-mail ou senha incorretos. Depois de {TENTATIVAS_ANTES_DO_BLOQUEIO} '
                      f'tentativas erradas, o acesso fica bloqueado por '
                      f'{MINUTOS_DE_BLOQUEIO} minutos.')


def exige_segunda_etapa(u):
    """A pessoa é obrigada a usar o código do aplicativo? O cliente sempre
    (Fase 9B); a gestão e a diretoria, salvo ``MFA_OBRIGATORIO_GESTAO=0``
    (só os testes desligam)."""
    papel = u._effective_role()
    if papel == 'cliente':
        return True
    return (papel in PERFIS_COM_SEGUNDA_ETAPA
            and current_app.config.get('MFA_OBRIGATORIO_GESTAO', True))


def _contar_erro_de_senha(u, agora):
    """Soma um erro de senha NO BANCO (UPDATE atômico) e bloqueia ao chegar
    no limite. Antes era ler-somar-gravar em Python: 12 tentativas em
    paralelo terminavam contando 1 (auditoria SEC-002). Devolve True quando
    esta tentativa bloqueou a conta."""
    n = db.session.execute(
        update(User).where(User.id == u.id)
        .values(failed_login_count=User.failed_login_count + 1)
        .returning(User.failed_login_count)).scalar()
    bloqueou = (n or 0) >= TENTATIVAS_ANTES_DO_BLOQUEIO
    if bloqueou:
        db.session.execute(
            update(User).where(User.id == u.id)
            .values(lockout_until=agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO),
                    failed_login_count=0))
    db.session.commit()
    db.session.expire(u)
    return bloqueou


def _contar_erro_de_codigo(u, agora):
    """Soma um erro de código no servidor e trava a segunda etapa ao chegar
    no limite. Devolve True quando travou."""
    n = db.session.execute(
        update(User).where(User.id == u.id)
        .values(totp_falhas=User.totp_falhas + 1)
        .returning(User.totp_falhas)).scalar()
    travou = (n or 0) >= TENTATIVAS_DO_CODIGO
    if travou:
        db.session.execute(
            update(User).where(User.id == u.id)
            .values(totp_bloqueio_ate=agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO_DO_CODIGO),
                    totp_falhas=0))
    db.session.commit()
    db.session.expire(u)
    return travou


def _marcar_codigo_usado(u, passo):
    """Grava o passo aceito SÓ se ninguém gravou este passo antes (dois
    envios simultâneos do mesmo código: um só entra — auditoria SEC-018)."""
    r = db.session.execute(
        update(User).where(User.id == u.id,
                           or_(User.totp_ultimo_passo.is_(None),
                               User.totp_ultimo_passo < passo))
        .values(totp_ultimo_passo=passo, totp_falhas=0, totp_bloqueio_ate=None))
    db.session.commit()
    db.session.expire(u)
    return r.rowcount == 1


def _senha_atual_errada(u):
    """A senha atual errou numa tela de quem já está logado (trocar a senha,
    desligar o código): conta como erro de login. No limite, a conta bloqueia
    e a sessão cai — quem roubou a sessão não descobre a senha por tentativa
    (auditoria SEC-011). Devolve a resposta quando derrubou a sessão."""
    if not _contar_erro_de_senha(u, datetime.utcnow()):
        return None
    u.session_epoch = (u.session_epoch or 0) + 1
    db.session.commit()
    logout_user()
    session.clear()
    flash(MSG_LOGIN_RECUSADO, 'danger')
    return redirect(url_for('auth.login'))


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
        u = User.por_email(email)
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
                if _contar_erro_de_senha(u, agora):
                    _avisar_bloqueio(u)
            flash(MSG_LOGIN_RECUSADO, 'danger')
            return render_template('core/login.html', email=email), 401
        # Fase 9B: o cliente só entra com o portal liberado (padrão: não) e
        # com o cadastro apontando para um cliente.
        # A resposta é a mesma de senha errada: dizer "o portal ainda não foi
        # liberado" só depois da senha certa confirmaria o par e-mail/senha
        # a quem está tentando (auditoria N-17).
        if u.role in PERFIS_SEM_LOGIN and not (_portal_liberado() and _cliente_ativo(u)):
            flash(MSG_LOGIN_RECUSADO, 'danger')
            return render_template('core/login.html', email=email), 401
        u.failed_login_count = 0
        u.lockout_until = None
        if senhas.precisa_refazer(u.password_hash):
            u.set_password(senha)   # o hash sobe para o padrão atual
        db.session.commit()
        if u.totp_ativo and u.totp_segredo:
            session.pop('_2fa', None)
            session['_2fa'] = {'uid': u.id, 'epoca': u.session_epoch or 0,
                               'lembrar': bool(request.form.get('lembrar')),
                               'next': _destino_seguro(request.args.get('next')),
                               'ate': (agora + timedelta(minutes=MINUTOS_PARA_O_CODIGO)).isoformat()}
            return redirect(url_for('auth.codigo'))
        return _concluir_login(u, bool(request.form.get('lembrar')),
                               _destino_seguro(request.args.get('next')))
    # O convite aceito volta para cá com o e-mail já preenchido.
    return render_template('core/login.html', email=(request.args.get('email') or '')[:150])


def _avisar_bloqueio(u):
    """Conta bloqueada por senha errada: o administrador fica sabendo (no
    sino e no celular). Quem trava a conta de propósito não passa
    despercebido (auditoria SEC-007)."""
    try:
        from facilities.core import push
        from facilities.core.rotas import avisar
        admins = [a.id for a in User.query.filter_by(role='master', is_active=True,
                                                      is_deleted=False)]
        titulo = f'Conta bloqueada por senha errada: {u.email}'
        texto = (f'{TENTATIVAS_ANTES_DO_BLOQUEIO} tentativas erradas seguidas. O acesso volta '
                 f'sozinho em {MINUTOS_DE_BLOQUEIO} minutos. Se não foi a própria pessoa, '
                 'alguém está tentando entrar nesta conta.')
        link = url_for('admin.usuarios')
        avisados = avisar(admins, titulo, texto, link)
        db.session.commit()
        # No celular o aviso aparece na tela bloqueada: vai sem o e-mail da
        # pessoa. O detalhe fica no sino, atrás do login (auditoria N-08).
        push.avisar(list(avisados), 'Uma conta foi bloqueada por senha errada',
                    'Veja qual em Pessoas e acessos.', link=link, marca=f'bloqueio-{u.id}')
        db.session.commit()
    except Exception:
        # O aviso nunca impede a resposta do login.
        db.session.rollback()
        current_app.logger.exception('Falha ao avisar o bloqueio de conta.')


def _portal_liberado():
    from facilities.portal.servico import liberado
    return liberado()


def _cliente_ativo(u):
    from facilities.portal.servico import cliente_ativo
    return cliente_ativo(u)


def _concluir_login(u, lembrar, destino):
    """Entra. Sem destino pedido, cada perfil cai na sua porta: o pessoal do
    posto no aplicativo de campo, a gestão no site (Fase 3), o cliente no
    portal (Fase 9B) — e o cliente só aceita destino dentro do portal."""
    from facilities.campo.rotas import destino_depois_do_login
    if u.role == 'cliente' and not (destino or '').startswith('/cliente'):
        destino = None
    u.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(u, remember=lembrar)
    if u.must_change_password:
        return redirect(url_for('auth.trocar_senha'))
    return redirect(destino or destino_depois_do_login(u))


def _pendente():
    """O login que passou pela senha e espera o código (ou None)."""
    p = session.get('_2fa')
    if not isinstance(p, dict):
        return None, None
    try:
        vencido = datetime.fromisoformat(p['ate']) < datetime.utcnow()
    except (KeyError, TypeError, ValueError):
        vencido = True
    u = db.session.get(User, p.get('uid') or 0)
    if (vencido or u is None or not u.is_active or u.is_deleted or not u.totp_ativo
            or (u.session_epoch or 0) != p.get('epoca')):
        session.pop('_2fa', None)
        return None, None
    return p, u


@bp.route('/login/codigo', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def codigo():
    if current_user.is_authenticated:
        return redirect(url_for('core.inicio'))
    p, u = _pendente()
    if u is None:
        flash('Entre de novo com o e-mail e a senha.', 'warning')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        agora = datetime.utcnow()
        if u.totp_bloqueio_ate and u.totp_bloqueio_ate > agora:
            session.pop('_2fa', None)
            flash(MSG_CODIGO_TRAVADO, 'danger')
            return redirect(url_for('auth.login'))
        aceito = totp.verificar(u.totp_segredo, request.form.get('codigo'),
                                ultimo_passo=u.totp_ultimo_passo)
        if aceito is None or not _marcar_codigo_usado(u, aceito):
            if _contar_erro_de_codigo(u, agora):
                session.pop('_2fa', None)
                flash(MSG_CODIGO_TRAVADO, 'danger')
                return redirect(url_for('auth.login'))
            flash('Código incorreto ou já usado. Confira o aplicativo e digite o código '
                  'que aparece agora.', 'danger')
            return render_template('core/login_codigo.html'), 401
        session.pop('_2fa', None)
        return _concluir_login(u, p.get('lembrar'), p.get('next'))
    return render_template('core/login_codigo.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    # A época sobe: o cookie desta sessão (e qualquer cópia dele, e o
    # "Manter conectado") deixa de valer. Vale em todos os aparelhos.
    u = current_user._get_current_object()
    u.session_epoch = (u.session_epoch or 0) + 1
    # Os avisos no celular param junto com a sessão: num aparelho
    # compartilhado, quem sai não continua recebendo chamado e cobrança na
    # tela bloqueada (auditoria N-04). Quem entrar de novo liga outra vez.
    from facilities.core.models import PushInscricao
    PushInscricao.query.filter_by(user_id=u.id).delete()
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))


# ── Segunda etapa: ativar e desativar (pela própria pessoa) ──────────────

@bp.route('/conta/seguranca', methods=['GET'])
@login_required
def seguranca():
    novo = None
    if not current_user.totp_ativo:
        segredo = session.get('_totp_novo') or totp.novo_segredo()
        session['_totp_novo'] = segredo
        endereco = totp.uri(segredo, current_user.email)
        novo = {'segredo': segredo, 'qr': totp.qr_svg(endereco)}
    return render_template('core/seguranca.html', novo=novo)


@bp.route('/conta/seguranca/ativar', methods=['POST'])
@login_required
def ativar_codigo():
    segredo = session.get('_totp_novo')
    if not segredo or current_user.totp_ativo:
        return redirect(url_for('auth.seguranca'))
    aceito = totp.verificar(segredo, request.form.get('codigo'))
    if aceito is None:
        flash('O código não confere. Confira se o aplicativo leu o QR desta tela e digite '
              'o código que aparece agora.', 'danger')
        return redirect(url_for('auth.seguranca'))
    u = current_user._get_current_object()
    u.totp_segredo = segredo
    u.totp_ativo = True
    u.totp_ultimo_passo = aceito
    u.totp_falhas = 0
    u.totp_bloqueio_ate = None
    # As outras sessões (abertas só com a senha) caem; este aparelho segue.
    u.session_epoch = (u.session_epoch or 0) + 1
    session.pop('_totp_novo', None)
    db.session.commit()
    login_user(u)
    flash('Segunda etapa ativada. A partir de agora, o login pede a senha e o código do '
          'aplicativo.', 'success')
    return redirect(url_for('auth.seguranca'))


@bp.route('/conta/seguranca/desativar', methods=['POST'])
@login_required
def desativar_codigo():
    u = current_user._get_current_object()
    if exige_segunda_etapa(u):
        # Fase 9B (cliente) e auditoria SEC-001 (gestão): obrigatória.
        flash('No seu perfil a segunda etapa é obrigatória e não pode ser desligada. '
              'Trocou de celular? Peça ao administrador para zerar o código e cadastre '
              'de novo.', 'warning')
        return redirect(url_for('auth.seguranca'))
    if not u.check_password(request.form.get('senha') or ''):
        derrubou = _senha_atual_errada(u)
        if derrubou:
            return derrubou
        flash('A senha não confere.', 'danger')
        return redirect(url_for('auth.seguranca'))
    u.totp_ativo = False
    u.totp_segredo = None
    u.totp_ultimo_passo = None
    db.session.commit()
    flash('Segunda etapa desativada.', 'success')
    return redirect(url_for('auth.seguranca'))


@bp.route('/trocar-senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if request.method == 'POST':
        atual = request.form.get('atual') or ''
        nova = request.form.get('nova') or ''
        confirma = request.form.get('confirma') or ''
        erro = None
        if not current_user.check_password(atual):
            derrubou = _senha_atual_errada(current_user._get_current_object())
            if derrubou:
                return derrubou
            erro = 'A senha atual não confere.'
        elif len(nova) < SENHA_MINIMA:
            erro = f'A senha nova precisa ter pelo menos {SENHA_MINIMA} caracteres.'
        elif nova != confirma:
            erro = 'A confirmação não é igual à senha nova.'
        elif nova == atual:
            erro = 'A senha nova precisa ser diferente da atual.'
        elif senhas.problema(nova, current_user.email):
            erro = senhas.problema(nova, current_user.email)
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
