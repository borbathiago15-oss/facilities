"""Trino Facilities — fábrica do app.

    flask --app facilities run          # desenvolvimento (SQLite em instance/)
    flask --app facilities criar-admin  # o primeiro administrador

Produção (Postgres): o schema vem SÓ das migrações (``flask db upgrade``); o
boot não faz DDL. ``create_all`` roda apenas em SQLite — desenvolvimento e
testes —, a mesma regra do Trino Intelligence.
"""
import logging
import os
import secrets
from datetime import timedelta

import click
from flask import Flask, jsonify, redirect, request, url_for
from flask_login import current_user

from facilities import tempo
from facilities.extensions import csrf, db, limiter, login_manager, migrate
from facilities.object_storage import get_storage

log = logging.getLogger(__name__)

# Endpoints que quem precisa trocar a senha ainda pode abrir.
_LIVRES_NA_TROCA = {'auth.trocar_senha', 'auth.logout', 'static', 'core.healthz',
                    'app_instalavel.service_worker', 'app_instalavel.manifesto',
                    'app_instalavel.versao', 'app_instalavel.sessao'}


def _url_do_banco(app):
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        os.makedirs(app.instance_path, exist_ok=True)
        return 'sqlite:///' + os.path.join(app.instance_path, 'facilities.db')
    # Heroku/Supabase às vezes entregam o esquema antigo.
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    segredo = os.environ.get('SECRET_KEY')
    if not segredo:
        segredo = secrets.token_hex(32)
        log.warning('SECRET_KEY não definida: usando uma aleatória (as sessões '
                    'caem a cada reinício). Defina SECRET_KEY em produção.')
    app.config.update(
        SECRET_KEY=segredo,
        SQLALCHEMY_DATABASE_URI=_url_do_banco(app),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        UPLOAD_FOLDER=os.environ.get('UPLOAD_FOLDER')
        or os.path.join(app.instance_path, 'uploads'),
        MAX_CONTENT_LENGTH=30 * 1024 * 1024,
        WTF_CSRF_TIME_LIMIT=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '1') == '1',
        REMEMBER_COOKIE_DURATION=timedelta(days=14),
        REMEMBER_COOKIE_HTTPONLY=True,
        RATELIMIT_ENABLED=os.environ.get('RATELIMIT_ENABLED', '1') == '1',
        RATELIMIT_STORAGE_URI=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Entre para continuar.'
    login_manager.login_message_category = 'warning'

    app.extensions['facilities_storage'] = get_storage(app.config['UPLOAD_FOLDER'])

    _modelos(app)
    _rotas(app)
    _sessao(app)
    _jinja(app)
    _comandos(app)

    with app.app_context():
        if db.engine.url.get_backend_name() == 'sqlite':
            db.create_all()
    return app


def _modelos(app):
    # Importar registra as tabelas na metadata única.
    from facilities.core import models  # noqa: F401
    from facilities.passagem import models as _p  # noqa: F401
    from facilities.chamados import models as _c  # noqa: F401


def _rotas(app):
    from facilities.core.admin import bp as admin_bp
    from facilities.core.app_instalavel import bp as app_bp
    from facilities.core.auth import bp as auth_bp
    from facilities.core.rotas import bp as core_bp
    from facilities.passagem.rotas import bp as passagem_bp
    from facilities.chamados.rotas import bp as chamados_bp
    for bp in (core_bp, auth_bp, admin_bp, app_bp, passagem_bp, chamados_bp):
        app.register_blueprint(bp)


def _sessao(app):
    from facilities.core.models import User

    @login_manager.user_loader
    def _carregar(ident):
        try:
            uid, _, epoca = str(ident).partition(':')
            u = db.session.get(User, int(uid))
        except (TypeError, ValueError):
            return None
        if u is None or not u.is_active or u.is_deleted:
            return None
        if str(u.session_epoch or 0) != (epoca or '0'):
            return None
        return u

    @login_manager.unauthorized_handler
    def _sem_login():
        if request.is_json or '/api/' in request.path or request.method != 'GET':
            return jsonify({'error': 'Sessão expirada. Entre de novo.'}), 401
        return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))

    @app.before_request
    def _troca_obrigatoria():
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint not in _LIVRES_NA_TROCA):
            if request.is_json or request.method != 'GET':
                return jsonify({'error': 'Troque a sua senha antes de continuar.'}), 403
            return redirect(url_for('auth.trocar_senha'))

    @app.after_request
    def _cabecalhos(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp


def _hora_local(dt, fmt='%d/%m/%Y %H:%M'):
    """Datetime gravado em UTC → horário de Brasília, formatado."""
    try:
        return tempo.fmt(dt, fmt)
    except Exception:
        try:
            return dt.strftime(fmt)
        except Exception:
            return str(dt)


def _jinja(app):
    app.jinja_env.filters['hora_local'] = _hora_local
    app.jinja_env.filters['fmt'] = tempo.fmt
    app.jinja_env.filters['local'] = tempo.local
    app.jinja_env.globals['tempo'] = tempo
    app.jinja_env.globals['NOME_DO_SISTEMA'] = 'Trino Facilities'


def _comandos(app):
    @app.cli.command('criar-admin')
    @click.option('--email', prompt='E-mail do administrador')
    @click.option('--nome', prompt='Nome')
    def criar_admin(email, nome):
        """Cria (ou reativa) um administrador e mostra uma senha temporária."""
        from facilities.core.admin import _senha_temporaria
        from facilities.core.models import User
        email = email.strip().lower()
        u = User.query.filter(db.func.lower(User.email) == email).first()
        if u is None:
            u = User(email=email, name=nome.strip() or email)
            db.session.add(u)
        u.role = 'master'
        u.is_active = True
        u.is_deleted = False
        senha = _senha_temporaria()
        u.set_password(senha)
        u.must_change_password = True
        db.session.commit()
        click.echo(f'Administrador {u.email} pronto. Senha temporária: {senha}')

    @app.cli.command('semear-modelos')
    @click.option('--contrato', 'contrato_id', type=int, required=True,
                  help='Id do contrato que recebe os modelos prontos.')
    @click.option('--servico', type=click.Choice(['limpeza', 'portaria', 'manutencao']),
                  multiple=True, help='Quais serviços (padrão: os três).')
    def semear_modelos(contrato_id, servico):
        """Cria as áreas e os modelos prontos de passagem de um contrato."""
        from facilities.passagem.modelos_prontos import semear
        criados = semear(contrato_id, servico or None)
        db.session.commit()
        click.echo(f'{len(criados)} modelo(s) criado(s): ' + ', '.join(criados))
