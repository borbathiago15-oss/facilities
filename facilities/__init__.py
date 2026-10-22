"""Trino Facilities — fábrica do app.

    flask --app facilities db upgrade   # o schema (SQLite em instance/, no dev)
    flask --app facilities criar-admin  # o primeiro administrador
    flask --app facilities run          # desenvolvimento

O schema vem SÓ das migrações (``flask db upgrade``), também no SQLite de
desenvolvimento: o boot não faz DDL em banco nenhum. (Antes o boot rodava
``create_all`` no SQLite; o ``flask db upgrade`` seguinte morria com "table
users already exists" e o autogenerate deixava de enxergar coluna nova — o
dev ficava sem migração. Os testes criam o schema por conta própria, em
``tests/conftest.py``.)

Fora do SQLite de desenvolvimento a fábrica RECUSA subir com configuração
que perde dado ou derruba sessão em silêncio: sem ``SECRET_KEY``, ou com os
anexos caindo no disco do contêiner sem ninguém ter pedido isso.
"""
import logging
import os
import secrets
from datetime import timedelta

import click
from flask import Flask, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user
from werkzeug.exceptions import Forbidden
from sqlalchemy.engine import make_url
from werkzeug.middleware.proxy_fix import ProxyFix

from facilities import tempo
from facilities.extensions import csrf, db, limiter, login_manager, migrate
from facilities.object_storage import get_storage

log = logging.getLogger(__name__)

# Endpoints que quem precisa trocar a senha ainda pode abrir.
_LIVRES_NA_TROCA = {'auth.trocar_senha', 'auth.logout', 'static', 'core.healthz',
                    'app_instalavel.service_worker', 'app_instalavel.manifesto',
                    'app_instalavel.versao', 'app_instalavel.sessao',
                    'campo.manifesto', 'campo.instalar'}


# Fase 9B: o que a conta de cliente abre fora do portal (``portal.*``) — e,
# antes de ativar a segunda etapa, só isto mais a tela de segurança.
_LIVRES_SEM_SEGUNDA_ETAPA = {'auth.logout', 'auth.trocar_senha', 'auth.seguranca',
                             'auth.ativar_codigo', 'static', 'core.healthz',
                             'app_instalavel.service_worker', 'app_instalavel.manifesto',
                             'app_instalavel.versao', 'app_instalavel.sessao'}
_LIVRES_DO_CLIENTE = _LIVRES_SEM_SEGUNDA_ETAPA | {'core.avisos', 'core.abrir_aviso',
                                                 'core.ler_todos',
                                                 # O QR público (D47) é de qualquer pessoa no
                                                 # local; o cliente logado abre e fica como autor.
                                                 'cadastros.qr', 'publico.abrir_ocorrencia',
                                                 'publico.acompanhar'}
MSG_SO_DA_EQUIPE = 'Esta parte do sistema é da equipe da Trino. Use o portal do cliente.'


CSP = ("default-src 'self'; script-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
       "frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'self'")

_SIM = frozenset({'1', 'true', 'yes', 'on', 'sim'})
_NAO = frozenset({'0', 'false', 'no', 'off', 'nao', 'não'})


def _flag(nome, padrao):
    """Liga/desliga lido do ambiente — e valor que não se entende PARA o boot.

    A leitura antiga (``== '1'``) falhava ABERTA: ``SESSION_COOKIE_SECURE=true``
    virava False e o cookie de sessão saía sem Secure, o contrário do que a
    pessoa quis. Agora 1/true/yes/on liga, 0/false/no/off desliga, vazio fica
    no padrão, e qualquer outra coisa é erro de configuração, dito no boot.
    """
    bruto = os.environ.get(nome)
    if bruto is None or not bruto.strip():
        return padrao
    valor = bruto.strip().lower()
    if valor in _SIM:
        return True
    if valor in _NAO:
        return False
    raise RuntimeError(f'{nome}={bruto!r} não é um valor reconhecido. '
                       'Use 1 (ligado) ou 0 (desligado).')


def _saltos_de_proxy():
    """Quantos proxies de confiança há na frente do app (``PROXY_HOPS``).

    Atrás de proxy (Cloudflare, balanceador do PaaS) o ``remote_addr`` é o IP
    do PROXY: o limite de login por IP vira um balde só para todo mundo.
    Com ``PROXY_HOPS=N`` o ProxyFix confia nos N últimos saltos de
    X-Forwarded-For/-Proto. Padrão 0: sem proxy declarado, ninguém forja o
    próprio IP mandando o cabeçalho.
    """
    bruto = (os.environ.get('PROXY_HOPS') or '').strip()
    if not bruto:
        return 0
    try:
        saltos = int(bruto)
    except ValueError:
        saltos = -1
    if saltos < 0:
        raise RuntimeError(f'PROXY_HOPS={bruto!r} inválido: use o número de proxies '
                           'de confiança na frente do app (0 = nenhum).')
    return saltos


def _conferir_limites_compartilhados(app):
    """memory:// conta por processo: com N workers cada limite (login,
    código, QR público, API) vale N vezes e zera a cada deploy (auditoria
    SEC-004 / N-02). Na imagem de produção isso vira aviso no log — e recusa
    de subir quando RATELIMIT_EXIGIR_COMPARTILHADO=1, depois de o Redis
    existir no ambiente."""
    uri = (app.config.get('RATELIMIT_STORAGE_URI') or 'memory://').strip()
    if not uri.startswith('memory') or not app.config.get('RATELIMIT_ENABLED', True):
        return
    if not _flag('EXIGIR_DATABASE_URL', False):
        return
    try:
        workers = int(os.environ.get('WEB_CONCURRENCY', '2') or 2)
    except ValueError:
        workers = 2
    if workers <= 1:
        return
    aviso = (f'RATELIMIT_STORAGE_URI=memory:// com {workers} workers: cada limite de acesso '
             f'vale {workers} vezes e zera a cada deploy. Aponte para um Redis '
             '(RATELIMIT_STORAGE_URI=redis://...).')
    if _flag('RATELIMIT_EXIGIR_COMPARTILHADO', False):
        raise RuntimeError(aviso)
    app.logger.warning(aviso)


def _atras_de_proxy(app, saltos):
    if saltos:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos)


def _url_do_banco(app):
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        if _flag('EXIGIR_DATABASE_URL', False):
            # A imagem de produção liga isto (Dockerfile): sem DATABASE_URL o
            # app subiria num SQLite dentro do contêiner, que some a cada
            # reinício — com todos os dados lançados.
            raise RuntimeError('DATABASE_URL não definida. Nesta imagem ela é '
                               'obrigatória: aponte para o Postgres de produção.')
        os.makedirs(app.instance_path, exist_ok=True)
        return 'sqlite:///' + os.path.join(app.instance_path, 'facilities.db')
    # Heroku/Supabase às vezes entregam o esquema antigo.
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


def _eh_sqlite(uri):
    return make_url(uri).get_backend_name() == 'sqlite'


def _garantir_segredo(app, sqlite):
    """``SECRET_KEY`` faltando: recusa subir fora do SQLite de desenvolvimento.

    Sem ela cada worker do gunicorn sorteava a SUA chave: o cookie assinado
    por um era recusado pelo outro, e o login dava erro de CSRF e as sessões
    caíam ao acaso (reproduzido com 2 workers). No SQLite de desenvolvimento
    (um processo só) a chave aleatória continua valendo, com aviso no log.
    """
    if app.config.get('SECRET_KEY'):
        return
    # A imagem de produção (EXIGIR_DATABASE_URL) nunca aceita chave sorteada,
    # nem se alguém apontar o DATABASE_URL para um SQLite.
    if not sqlite or _flag('EXIGIR_DATABASE_URL', False):
        raise RuntimeError(
            'SECRET_KEY não definida. Fora do SQLite de desenvolvimento ela é '
            'obrigatória: sem ela cada processo do servidor sorteia a sua, e o '
            'login e as sessões falham ao acaso. Defina SECRET_KEY (o mesmo valor '
            'em todos os processos).')
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    log.warning('SECRET_KEY não definida: usando uma aleatória (as sessões '
                'caem a cada reinício). Defina SECRET_KEY em produção.')


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    cookie_seguro = _flag('SESSION_COOKIE_SECURE', True)
    app.config.update(
        SECRET_KEY=(os.environ.get('SECRET_KEY') or '').strip() or None,
        SQLALCHEMY_DATABASE_URI=_url_do_banco(app),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        UPLOAD_FOLDER=os.environ.get('UPLOAD_FOLDER')
        or os.path.join(app.instance_path, 'uploads'),
        MAX_CONTENT_LENGTH=30 * 1024 * 1024,
        WTF_CSRF_TIME_LIMIT=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=cookie_seguro,
        # O "Manter conectado" é uma credencial de 14 dias sozinho (abre o
        # sistema sem o cookie de sessão): as mesmas travas do cookie de sessão.
        REMEMBER_COOKIE_DURATION=timedelta(days=14),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=cookie_seguro,
        REMEMBER_COOKIE_SAMESITE='Lax',
        RATELIMIT_ENABLED=_flag('RATELIMIT_ENABLED', True),
        # Auditoria SEC-001: gestão e diretoria só entram com a segunda etapa.
        # Desligar é só para os testes automatizados.
        MFA_OBRIGATORIO_GESTAO=_flag('MFA_OBRIGATORIO_GESTAO', True),
        # memory:// conta POR PROCESSO: com N workers o limite real é N vezes
        # maior. Para valer igual em todos, aponte para um Redis
        # (redis://host:6379) — ver README.
        RATELIMIT_STORAGE_URI=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
        # Fase 9B: o portal do cliente. Desligado até o jurídico entregar os
        # termos (Grupo C): a conta de cliente não entra.
        CLIENTE_EXTERNO_LIBERADO=_flag('CLIENTE_EXTERNO_LIBERADO', False),
    )
    if config:
        app.config.update(config)
        if 'REMEMBER_COOKIE_SECURE' not in config:
            app.config['REMEMBER_COOKIE_SECURE'] = app.config['SESSION_COOKIE_SECURE']

    sqlite = _eh_sqlite(app.config['SQLALCHEMY_DATABASE_URI'])
    _garantir_segredo(app, sqlite)
    _conferir_limites_compartilhados(app)
    # Antes das extensões: configuração recusada não toca em nada.
    storage = get_storage(app.config['UPLOAD_FOLDER'], local_implicito=sqlite)
    _atras_de_proxy(app, _saltos_de_proxy())

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Entre para continuar.'
    login_manager.login_message_category = 'warning'

    app.extensions['facilities_storage'] = storage

    _modelos(app)
    _rotas(app)
    _sessao(app)
    _jinja(app)
    _comandos(app)
    from facilities.core.erros import registrar as registrar_erros
    registrar_erros(app)
    return app


def _modelos(app):
    # Importar registra as tabelas na metadata única.
    from facilities.core import models  # noqa: F401
    from facilities.passagem import models as _p  # noqa: F401
    from facilities.chamados import models as _c  # noqa: F401
    from facilities.cadastros import models as _cad  # noqa: F401
    from facilities.rotas import models as _rot  # noqa: F401
    from facilities.preventiva import models as _prev  # noqa: F401
    from facilities.equipes import models as _eq  # noqa: F401
    from facilities.visitas import models as _vis  # noqa: F401
    from facilities.materiais import models as _mat  # noqa: F401
    from facilities.integracao import models as _int  # noqa: F401
    from facilities.portal import models as _por  # noqa: F401
    from facilities.relatorios import models as _rel  # noqa: F401


def _rotas(app):
    from facilities.core.admin import bp as admin_bp
    from facilities.core.app_instalavel import bp as app_bp
    from facilities.core.auth import bp as auth_bp
    from facilities.core.rotas import bp as core_bp
    from facilities.passagem.rotas import bp as passagem_bp
    from facilities.chamados.rotas import bp as chamados_bp
    from facilities.cadastros.rotas import bp as cadastros_bp
    from facilities.campo.rotas import bp as campo_bp
    from facilities.rotas.telas import bp as rotas_bp
    from facilities.rotas.publico import bp as publico_bp
    from facilities.preventiva.telas import bp as preventiva_bp
    from facilities.demandas import bp as demandas_bp
    from facilities.equipes.telas import bp as equipes_bp
    from facilities.visitas.telas import bp as visitas_bp
    from facilities.materiais.telas import bp as materiais_bp
    from facilities.paineis.telas import bp as paineis_bp
    from facilities.integracao.api import bp as integracao_api_bp
    from facilities.integracao.telas import bp as integracao_bp
    from facilities.portal.telas import bp as portal_bp, bp_interno as cobrancas_bp
    from facilities.relatorios.telas import bp as relatorios_bp
    for bp in (core_bp, auth_bp, admin_bp, app_bp, passagem_bp, chamados_bp, cadastros_bp,
               campo_bp, rotas_bp, publico_bp, preventiva_bp, demandas_bp,
               equipes_bp, visitas_bp, materiais_bp, paineis_bp, integracao_api_bp,
               integracao_bp, portal_bp, cobrancas_bp, relatorios_bp):
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
    def _porta_do_cliente():
        """Fase 9B: a conta de cliente fica no portal — tudo o mais é negado
        por padrão (rota nova do sistema não se abre ao cliente por descuido).
        Portal desligado derruba a sessão; sem a segunda etapa, só a tela de
        segurança."""
        if not current_user.is_authenticated or current_user._effective_role() != 'cliente':
            return None
        from facilities.core.auth import MSG_CLIENTE_SEM_ACESSO
        from facilities.portal.servico import liberado
        quer_json = request.is_json or request.method != 'GET'
        if not liberado() or not current_user.cliente_id:
            logout_user()
            session.clear()
            if quer_json:
                return jsonify({'error': MSG_CLIENTE_SEM_ACESSO}), 401
            flash(MSG_CLIENTE_SEM_ACESSO, 'warning')
            return redirect(url_for('auth.login'))
        ep = request.endpoint or ''
        if not current_user.totp_ativo:
            if ep in _LIVRES_SEM_SEGUNDA_ETAPA:
                return None
            msg = ('Para usar o portal, ative antes a segunda etapa do login (o código do '
                   'aplicativo autenticador).')
            if quer_json:
                return jsonify({'error': msg}), 403
            flash(msg, 'warning')
            return redirect(url_for('auth.seguranca'))
        if ep.startswith('portal.') or ep in _LIVRES_DO_CLIENTE:
            return None
        if ep == 'core.inicio':
            return redirect(url_for('portal.inicio'))
        if quer_json:
            return jsonify({'error': MSG_SO_DA_EQUIPE}), 403
        raise Forbidden(MSG_SO_DA_EQUIPE)

    @app.before_request
    def _segunda_etapa_obrigatoria():
        """Auditoria SEC-001 (decisão do dono, 19/10/2026): quem enxerga
        vários locais (gestão e diretoria) não usa o sistema só com a senha.
        Até cadastrar o código do aplicativo autenticador, só abre a tela de
        segurança (e trocar a senha, sair). O cliente tem a porta própria."""
        if not current_user.is_authenticated or current_user._effective_role() == 'cliente':
            return None
        from facilities.core.auth import exige_segunda_etapa
        if current_user.totp_ativo or not exige_segunda_etapa(current_user):
            return None
        if (request.endpoint or '') in _LIVRES_SEM_SEGUNDA_ETAPA:
            return None
        msg = ('Para continuar, ative a segunda etapa do login: o código do aplicativo '
               'autenticador no seu celular. Leva um minuto.')
        if request.is_json or request.method != 'GET':
            return jsonify({'error': msg}), 403
        flash(msg, 'warning')
        return redirect(url_for('auth.seguranca'))

    @app.before_request
    def _troca_obrigatoria():
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint not in _LIVRES_NA_TROCA):
            if request.is_json or request.method != 'GET':
                return jsonify({'error': 'Troque a sua senha antes de continuar.'}), 403
            return redirect(url_for('auth.trocar_senha'))

    @app.after_request
    def _cabecalhos(resp):
        # Tela e arquivo de quem está logado não ficam no cache do navegador:
        # no celular do posto, compartilhado, o próximo não vê pelo "voltar"
        # nem pelo cache o que o anterior abriu (auditoria SEC-014). A cópia
        # do modo sem sinal é do service worker, que se apaga ao sair.
        ep = request.endpoint or ''
        if (current_user.is_authenticated and ep != 'static'
                and not ep.startswith('app_instalavel.') and ep != 'campo.manifesto'):
            resp.headers['Cache-Control'] = 'no-store'
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        # Câmera só para o próprio sistema (foto da passagem e do chamado);
        # microfone e localização, para ninguém.
        resp.headers.setdefault('Permissions-Policy',
                                'camera=(self), microphone=(), geolocation=()')
        # HSTS: depois do primeiro acesso em https o navegador não tenta mais
        # http — onde o cookie "Manter conectado" iria em texto claro. Vai
        # também quando o https termina no proxy (cookie Secure ligado); o
        # navegador ignora o cabeçalho recebido por http, então não prende o
        # desenvolvimento local.
        if request.is_secure or app.config.get('SESSION_COOKIE_SECURE'):
            resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
        # CSP (Fase 9A): script só dos arquivos do próprio sistema — nada de
        # <script> embutido nem onclick= (ver static/js/acoes.js). Um texto
        # injetado numa tela não roda. O estilo ainda aceita 'unsafe-inline'
        # (as telas da Passagem têm style= e <style>): o risco é bem menor que
        # o de script e a retirada fica para depois. A fonte Inter vem do
        # Google Fonts.
        resp.headers.setdefault('Content-Security-Policy', CSP)
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

    @app.cli.command('admin-inicial')
    def admin_inicial():
        """Primeiro administrador, sem terminal: lido de ``ADMIN_INICIAL_EMAIL``
        (e ``ADMIN_INICIAL_NOME``) a cada subida do site. Só age quando NÃO há
        administrador ativo — com a variável esquecida no painel, não faz nada.
        A senha é temporária (troca obrigatória no primeiro login, e a segunda
        etapa vem logo depois): ``ADMIN_INICIAL_SENHA`` se definida (mínimo de
        8 caracteres), senão uma sorteada, mostrada uma vez no log do deploy."""
        from facilities.core.admin import _senha_temporaria
        from facilities.core.models import User
        email = (os.environ.get('ADMIN_INICIAL_EMAIL') or '').strip().lower()
        if not email:
            return
        if User.query.filter_by(role='master', is_active=True, is_deleted=False).first():
            click.echo('admin-inicial: já existe administrador ativo; nada a fazer.')
            return
        senha = os.environ.get('ADMIN_INICIAL_SENHA') or ''
        informada = len(senha) >= 8
        if senha and not informada:
            click.echo('admin-inicial: ADMIN_INICIAL_SENHA tem menos de 8 caracteres; '
                       'usando uma senha sorteada.')
        if not informada:
            senha = _senha_temporaria()
        u = User.query.filter(db.func.lower(User.email) == email).first()
        if u is None:
            u = User(email=email)
            db.session.add(u)
        u.name = (os.environ.get('ADMIN_INICIAL_NOME') or '').strip() or u.name or email
        u.role = 'master'
        u.is_active, u.is_deleted = True, False
        u.set_password(senha)
        u.must_change_password = True
        u.failed_login_count, u.lockout_until = 0, None
        u.session_epoch = (u.session_epoch or 0) + 1
        db.session.commit()
        if informada:
            click.echo(f'admin-inicial: administrador {u.email} pronto, com a senha de '
                       'ADMIN_INICIAL_SENHA (troca obrigatória no primeiro login).')
        else:
            click.echo(f'admin-inicial: administrador {u.email} pronto. Senha temporária: '
                       f'{senha} (troca obrigatória no primeiro login).')

    @app.cli.group('agendador')
    def agendador():
        """O relógio das rotas: gera as tarefas do dia e fecha as perdidas."""

    @agendador.command('rodar')
    def agendador_rodar():
        """Uma rodada: tarefas de hoje e amanhã; turnos encerrados → perdidas.
        Pode rodar quantas vezes quiser: não duplica nada."""
        from facilities.rotas.servico import rodar
        reg = rodar(origem='comando')
        db.session.commit()
        if reg is None:
            click.echo('Outra rodada já estava em andamento: nada a fazer agora.')
            return
        click.echo(f'{reg.tarefas_geradas} tarefa(s) gerada(s), '
                   f'{reg.tarefas_perdidas} marcada(s) como perdida(s).')

    @app.cli.group('anexos')
    def anexos_cli():
        """Os arquivos enviados (fotos, documentos)."""

    @anexos_cli.command('espelhar')
    def anexos_espelhar():
        """Copia para o R2 o que está no disco (UPLOAD_FOLDER) e ainda não
        está lá. Cópia de segurança dos anexos quando STORAGE_BACKEND=local:
        o banco tem o pg_dump; as fotos só tinham o volume."""
        from facilities.object_storage import espelhar_no_r2
        n, ja, erros = espelhar_no_r2(app.config['UPLOAD_FOLDER'])
        click.echo(f'anexos espelhar: {n} arquivo(s) copiado(s), {ja} já estavam no R2, '
                   f'{erros} erro(s).')
        if erros:
            raise SystemExit(1)

    @app.cli.group('push')
    def push_cli():
        """Avisos no celular (Web Push)."""

    @push_cli.command('chaves')
    def push_chaves():
        """Gera o par de chaves VAPID para pôr no ambiente."""
        from facilities.core.push import gerar_chaves
        privada, publica = gerar_chaves()
        click.echo(f'VAPID_PRIVATE_KEY={privada}')
        click.echo(f'VAPID_PUBLIC_KEY={publica}')
        click.echo('VAPID_SUBJECT=mailto:seu-email@grupotrino.com.br')

    @app.cli.command('semear-checklists')
    def semear_checklists():
        """Instala na biblioteca os checklists prontos de limpeza (não duplica)."""
        from facilities.rotas.biblioteca_pronta import semear
        criados = semear()
        db.session.commit()
        click.echo(f'{len(criados)} modelo(s) instalado(s)' + (': ' + ', '.join(criados)
                                                              if criados else '.'))

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
