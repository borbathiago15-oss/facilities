"""Telas do assistente "Novo contrato" e dos convites.

Passos: 1. Cliente → 2. Local → 3. Estrutura e QR → 4. Equipe. Cada passo
grava na hora: dá para parar e voltar depois pelo mesmo endereço (a lista
de locais leva de volta ao passo que falta).

Quem usa: administrador, gerente e coordenador (``montagem.pode_montar``),
sempre dentro da carteira. As regras ficam em ``cadastros/montagem.py``.

``/convite/<token>`` é público: é o link que a pessoa convidada abre para
criar a senha. O banco guarda só o hash do token, a página não passa o
endereço adiante (``Referrer-Policy: same-origin``) e o POST tem limite por IP.
"""
import io

from flask import (Blueprint, abort, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import Forbidden

from facilities.extensions import db, limiter
from facilities.core.acesso import clientes_visiveis, require_client
from facilities.core.models import PERFIS, Client
from facilities.cadastros import montagem, servico
from facilities.cadastros.models import Contratante, Convite, Empresa
from facilities.cadastros.servico import CadastroInvalido

bp = Blueprint('montagem', __name__)


def _exigir_montagem():
    if not current_user.is_authenticated or not montagem.pode_montar(current_user):
        raise Forbidden('O assistente de novo contrato é da gestão (administrador, gerente '
                        'e coordenador).')


def _cliente(ctid):
    _exigir_montagem()
    c = db.get_or_404(Contratante, ctid)
    if c.id not in {x.id for x in montagem.clientes_da_montagem(current_user)}:
        raise Forbidden('Este cliente não é seu.')
    return c


def _local(cid):
    _exigir_montagem()
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _passos(atual, local=None, cliente=None):
    return {'atual': atual, 'local': local, 'cliente': cliente or (local.contratante
                                                                    if local else None)}


# ── Passo 1: cliente ──────────────────────────────────────────────────────

@bp.get('/novo-contrato')
@login_required
def inicio():
    _exigir_montagem()
    clientes = montagem.clientes_da_montagem(current_user)
    locais = clientes_visiveis()
    por_cliente = {}
    for loc in locais:
        por_cliente.setdefault(loc.contratante_id, []).append(loc)
    return render_template('cadastros/novo_contrato/cliente.html', clientes=clientes,
                           por_cliente=por_cliente, passos=_passos(1),
                           pode_criar=montagem.pode_criar_cliente(current_user),
                           empresas=Empresa.query.filter_by(is_active=True)
                           .order_by(Empresa.nome).all(),
                           andamento=montagem.andamento)


@bp.post('/novo-contrato/cliente')
@login_required
def criar_cliente():
    _exigir_montagem()
    try:
        cli = montagem.criar_cliente(request.form, current_user)
        db.session.flush()
        montagem.salvar_logo(cli, request.files.get('logo'), current_user)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return redirect(url_for('montagem.inicio'))
    flash(f'Cliente {cli.nome} cadastrado. Agora o primeiro local dele.', 'success')
    return redirect(url_for('montagem.novo_local', ctid=cli.id))


@bp.post('/novo-contrato/cliente/<int:ctid>/logo')
@login_required
def trocar_logo(ctid):
    cli = _cliente(ctid)
    if not montagem.pode_criar_cliente(current_user):
        raise Forbidden('A logo do cliente é trocada pelo gerente ou pelo administrador.')
    try:
        if not montagem.salvar_logo(cli, request.files.get('logo'), current_user):
            raise CadastroInvalido('Escolha o arquivo da logo.')
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
    else:
        flash('Logo salva. Ela já sai nas etiquetas de QR deste cliente.', 'success')
    return redirect(url_for('montagem.novo_local', ctid=cli.id))


@bp.get('/cadastros/clientes/<int:ctid>/logo.png')
@login_required
def logo(ctid):
    """A logo do cliente, para as telas da gestão."""
    cli = db.get_or_404(Contratante, ctid)
    from facilities.core.hierarquia import carteira
    ids = carteira(current_user)
    if current_user._effective_role() == 'cliente':
        if current_user.cliente_id != cli.id:
            abort(404)
    elif ids is not None and not any(loc.id in ids for loc in cli.locais) \
            and cli.id not in {x.id for x in montagem.clientes_da_montagem(current_user)}:
        abort(404)
    dados = montagem.logo_de(cli)
    if not dados:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype='image/png', max_age=300)


# ── Passo 2: local ────────────────────────────────────────────────────────

@bp.get('/novo-contrato/cliente/<int:ctid>/local')
@login_required
def novo_local(ctid):
    cli = _cliente(ctid)
    return render_template('cadastros/novo_contrato/local.html', cliente=cli,
                           estados=montagem.estados_ativos(), passos=_passos(2, cliente=cli),
                           pode_logo=montagem.pode_criar_cliente(current_user))


@bp.post('/novo-contrato/cliente/<int:ctid>/local')
@login_required
def criar_local(ctid):
    cli = _cliente(ctid)
    try:
        loc = montagem.criar_local(cli, request.form, current_user)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return redirect(url_for('montagem.novo_local', ctid=cli.id))
    flash(f'Local {loc.name} cadastrado. Agora a estrutura: onde ficam os QR.', 'success')
    return redirect(url_for('montagem.estrutura', cid=loc.id))


# ── Passo 3: estrutura e QR ───────────────────────────────────────────────

@bp.get('/novo-contrato/<int:cid>/estrutura')
@login_required
def estrutura(cid):
    loc = _local(cid)
    return render_template('cadastros/novo_contrato/estrutura.html', local=loc,
                           setores=servico.arvore(loc), andamento=montagem.andamento(loc),
                           numeros=montagem.numeros_dos_pontos(loc.id),
                           passos=_passos(3, local=loc))


@bp.post('/novo-contrato/<int:cid>/estrutura')
@login_required
def criar_estrutura(cid):
    """Cadastro rápido: um setor, um ambiente e os pontos com QR de uma vez."""
    loc = _local(cid)
    f = request.form
    try:
        setor_id = f.get('setor_id') or ''
        if setor_id.isdigit():
            setor = servico.item_do_local('setor', int(setor_id), loc)
        else:
            nome = (f.get('setor_nome') or '').strip()
            existente = next((s for s in servico.arvore(loc)
                              if s.nome.lower() == nome.lower()), None)
            setor = existente or servico.salvar_setor(loc, None, {'nome': nome},
                                                      current_user)
        ambiente = servico.salvar_ambiente(loc, None, {'nome': f.get('ambiente_nome'),
                                                       'setor_id': setor.id}, current_user)
        nomes = [n.strip() for n in (f.get('pontos') or '').splitlines() if n.strip()]
        if not nomes:
            nomes = [ambiente.nome]
        if len(nomes) > 30:
            raise CadastroInvalido('No máximo 30 pontos por vez.')
        entrada = f.get('entrada') == '1'
        for i, nome in enumerate(nomes):
            dados = {'nome': nome, 'ambiente_id': ambiente.id}
            if entrada and i == 0:
                dados['entrada_do_local'] = '1'
            servico.salvar_ponto(loc, None, dados, current_user)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return redirect(url_for('montagem.estrutura', cid=loc.id))
    flash(f'{ambiente.nome}: {len(nomes)} ponto(s) com QR cadastrado(s).', 'success')
    return redirect(url_for('montagem.estrutura', cid=loc.id))


# ── Passo 4: equipe e convites ────────────────────────────────────────────

def _form_convite(loc, erro_dados=None):
    perfis = [(p, PERFIS[p]) for p in montagem.perfis_que_convida(current_user)]
    return render_template('cadastros/novo_contrato/equipe.html', local=loc, perfis=perfis,
                           superiores=montagem.superiores_para(current_user),
                           locais=montagem._locais_permitidos(current_user),
                           clientes=montagem.clientes_da_montagem(current_user),
                           convites=montagem.convites_do_local(loc),
                           equipe=sorted((u for u in loc.linked_users
                                          if u.is_active and not u.is_deleted),
                                         key=lambda u: u.name),
                           andamento=montagem.andamento(loc), perfis_nome=PERFIS,
                           dados=erro_dados or {}, passos=_passos(4, local=loc))


@bp.get('/novo-contrato/<int:cid>/equipe')
@login_required
def equipe(cid):
    return _form_convite(_local(cid))


def _mostrar_link(convite, token, local=None, enviado=None):
    link = url_for('montagem.aceitar', token=token, _external=True)
    return render_template('cadastros/novo_contrato/convite_criado.html', convite=convite,
                           link=link, local=local, enviado=enviado,
                           whatsapp=montagem.link_whatsapp(convite, link),
                           email=montagem.link_email(convite, link),
                           perfil=PERFIS.get(convite.role, convite.role),
                           locais=montagem.locais_do_convite(convite),
                           passos=_passos(4, local=local) if local else None)


def _enviar_por_email(convite, token):
    from facilities.core import correio
    if not correio.configurado():
        return None
    link = url_for('montagem.aceitar', token=token, _external=True)
    return correio.enviar(convite.email, 'Seu acesso ao Trino Facilities',
                          montagem.texto_do_convite(convite, link))


@bp.post('/novo-contrato/<int:cid>/equipe')
@login_required
@limiter.limit('60 per hour')
def convidar(cid):
    loc = _local(cid)
    try:
        convite, token = montagem.criar_convite(current_user, request.form)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return _form_convite(loc, request.form), 400
    enviado = _enviar_por_email(convite, token)
    # A página com o link responde ao POST (sem redirecionar): o link não
    # passa pelo cookie de sessão nem pelo histórico do navegador.
    return _mostrar_link(convite, token, local=loc, enviado=enviado)


@bp.get('/convites')
@login_required
def convites():
    _exigir_montagem()
    return render_template('cadastros/novo_contrato/convites.html',
                           convites=montagem.convites_visiveis(current_user),
                           perfis_nome=PERFIS, locais_do=montagem.locais_do_convite)


def _convite(conv_id):
    _exigir_montagem()
    c = db.get_or_404(Convite, conv_id)
    if current_user._effective_role() != 'master' and c.criado_por_id != current_user.id:
        abort(404)
    return c


@bp.post('/convites/<int:conv_id>/cancelar')
@login_required
def cancelar_convite(conv_id):
    c = _convite(conv_id)
    try:
        montagem.cancelar(c, current_user)
        db.session.commit()
        flash(f'Convite de {c.nome} cancelado: o link não abre mais.', 'success')
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
    return redirect(url_for('montagem.convites'))


@bp.post('/convites/<int:conv_id>/novo-link')
@login_required
def novo_link(conv_id):
    c = _convite(conv_id)
    try:
        token = montagem.renovar(c, current_user)
        db.session.commit()
    except CadastroInvalido as erro:
        db.session.rollback()
        flash(str(erro), 'danger')
        return redirect(url_for('montagem.convites'))
    return _mostrar_link(c, token, enviado=_enviar_por_email(c, token))


# ── O link do convite (público) ───────────────────────────────────────────

@bp.get('/convite/<token>')
def aceitar(token):
    c = montagem.convite_pelo_token(token)
    if c is None:
        return render_template('core/convite_aceitar.html', convite=None), 404
    return render_template('core/convite_aceitar.html', convite=c,
                           perfil=PERFIS.get(c.role, c.role),
                           locais=montagem.locais_do_convite(c))


@bp.post('/convite/<token>')
@limiter.limit('10 per hour')
def aceitar_enviar(token):
    try:
        u = montagem.aceitar(token, request.form.get('senha') or '',
                             request.form.get('confirma') or '')
        db.session.commit()
    except IntegrityError:
        # Dois envios ao mesmo tempo (clique duplo): o primeiro criou a conta.
        db.session.rollback()
        flash('A sua conta já foi criada. Entre com o e-mail e a senha.', 'info')
        return redirect(url_for('auth.login'))
    except CadastroInvalido as erro:
        db.session.rollback()
        c = montagem.convite_pelo_token(token)
        flash(str(erro), 'danger')
        if c is None:
            return render_template('core/convite_aceitar.html', convite=None), 404
        return render_template('core/convite_aceitar.html', convite=c,
                               perfil=PERFIS.get(c.role, c.role),
                               locais=montagem.locais_do_convite(c)), 400
    flash(f'Conta criada, {u.name.split(" ")[0]}. Entre com o seu e-mail e a senha que '
          'acabou de criar.', 'success')
    return redirect(url_for('auth.login', email=u.email))
