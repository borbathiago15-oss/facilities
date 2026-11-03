"""Cadastros do administrador: pessoas e locais (os antigos "contratos").

Nada se apaga: pessoa e contrato são DESATIVADOS. O histórico de passagens,
pendências e chamados aponta para eles, e apagar deixaria o histórico sem
dono ("quem encerrou esta passagem?").
"""
import json
import secrets

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities.extensions import db
from facilities.core.acesso import admin_required
from facilities.core.models import PERFIS, PERFIS_DE_GESTAO, Client, User

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _senha_temporaria():
    # 12 caracteres sem ambiguidade visual (sem 0/O, 1/l/I).
    alfabeto = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alfabeto) for _ in range(12))


# As telas antiga e nova (React, Fase 6a: ``/novo/admin/usuarios``,
# ``/novo/admin/contratos`` e ``/api/v1/admin/...``) saem das MESMAS funções:
# ``contexto_*`` monta a tela; ``acao_*`` faz o envio (a regra, o commit e o
# recado). Só o administrador (``admin_required`` nas rotas das duas telas).
#
# A senha temporária (cadastrar e "Gerar senha temporária"): a ação a
# devolve e NÃO deixa recado com ela. As duas telas a mostram só na resposta
# do envio que a cria (``no-store``), como a chave da integração: a antiga
# desenha a página ali mesmo (``_pagina_com_senha``), sem passar pelo recado.
# O recado (``flash``) mora no cookie da sessão, que o Flask assina mas NÃO
# cifra: a senha ficava legível no cookie até a página seguinte (auditoria
# da Fase 6a, 03/11/2026).

def _texto_da_senha_nova(u, senha):
    return (f'Cadastro de {u.name} criado. Senha temporária: {senha} — entregue '
            f'pessoalmente; no primeiro acesso o sistema pede uma senha nova.')


def _texto_da_senha_gerada(u, senha):
    return f'Senha temporária de {u.name}: {senha}'


# "Gerar senha temporária" e "Desligar a segunda etapa" entregam a conta de
# outra pessoa (inclusive a de outro administrador) a quem estiver com a
# sessão: pedem a senha do PRÓPRIO administrador (auditoria da Fase 6a,
# 03/11/2026). A senha errada conta no mesmo contador do login dele
# (``auth._derrubar_se_bloqueou``): no 5º erro a conta dele bloqueia e a
# sessão cai, nas duas telas.
MSG_SENHA_DO_ADMIN = 'A sua senha não confere. Nada foi alterado.'
MSG_SENHA_PROPRIA = ('A senha temporária é só para outras pessoas. Para mudar a sua, use '
                     '"Trocar senha", no menu da sua conta.')


def _senha_do_admin_errada(dados):
    """None quando a senha do administrador confere; senão ``derrubou``
    (True: a conta dele bloqueou e a sessão caiu, com o recado para o
    login; False: o recado da recusa ficou)."""
    from facilities.core.auth import _derrubar_se_bloqueou
    eu = current_user._get_current_object()
    if eu.check_password(dados.get('senha_atual') or ''):
        return None
    if _derrubar_se_bloqueou(eu):
        return True
    flash(MSG_SENHA_DO_ADMIN, 'danger')
    return False


# ── Pessoas ──────────────────────────────────────────────────────────────

@bp.get('/usuarios')
@login_required
@admin_required
def usuarios():
    from facilities.core.hierarquia import cadeia_acima
    return render_template('core/usuarios.html', cadeia_acima=cadeia_acima,
                           **contexto_usuarios())


def _pagina_com_senha(texto, senha):
    """A tela antiga das pessoas com a senha temporária, desenhada na
    resposta do envio (nada no cookie, nada guardado pelo navegador)."""
    from facilities.core.hierarquia import cadeia_acima
    resp = make_response(render_template(
        'core/usuarios.html', cadeia_acima=cadeia_acima,
        senha_gerada={'texto': texto, 'senha': senha}, **contexto_usuarios()))
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Pragma'] = 'no-cache'
    return resp


def contexto_usuarios():
    from facilities.cadastros.models import Contratante
    from facilities.core.hierarquia import superiores_possiveis
    from sqlalchemy.orm import selectinload
    pessoas = (User.query.filter(User.is_deleted.is_(False))
               .options(selectinload(User.clients))
               .order_by(User.is_active.desc(), User.name).all())
    contratos = Client.query.filter(Client.is_deleted.is_(False)).order_by(Client.name).all()
    return dict(pessoas=pessoas, contratos=contratos, perfis=PERFIS,
                permissoes=User.PERMISSOES_FINAS, superiores=superiores_possiveis(),
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
    feito = acao_criar_usuario(request.form)
    if feito is not None:
        u, senha = feito
        return _pagina_com_senha(_texto_da_senha_nova(u, senha), senha)
    return redirect(url_for('admin.usuarios'))


def acao_criar_usuario(dados):
    """``(pessoa, senha temporária)``; na recusa, o recado e None."""
    u = User()
    _aplicar_formulario(u, dados)
    erro = _validar(u) or _aplicar_cadeia(u, dados)
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return None
    senha = _senha_temporaria()
    u.set_password(senha)
    u.must_change_password = True
    db.session.add(u)
    db.session.commit()
    return u, senha


@bp.post('/usuarios/<int:uid>')
@login_required
@admin_required
def editar_usuario(uid):
    return redirect(acao_editar_usuario(uid, request.form))


def acao_editar_usuario(uid, dados):
    u = db.get_or_404(User, uid)
    era_ativo = u.is_active
    role_antes = u.role
    _aplicar_formulario(u, dados)
    u.is_active = bool(dados.get('is_active'))
    if u.id == current_user.id and (not u.is_active or u.role != 'master'):
        db.session.rollback()
        flash('Você não pode tirar o seu próprio acesso de administrador.', 'danger')
        return url_for('admin.usuarios')
    erro = _validar(u, original_id=u.id) or _aplicar_cadeia(u, dados, role_antes)
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return url_for('admin.usuarios')
    if era_ativo and not u.is_active:
        u.session_epoch = (u.session_epoch or 0) + 1   # derruba as sessões abertas
    db.session.commit()
    flash(f'Cadastro de {u.name} atualizado.', 'success')
    return url_for('admin.usuarios')


@bp.post('/usuarios/<int:uid>/nova-senha')
@login_required
@admin_required
def nova_senha(uid):
    feito, derrubou = acao_nova_senha(uid, request.form)
    if derrubou:
        return redirect(url_for('auth.login'))
    if feito is not None:
        u, senha = feito
        return _pagina_com_senha(_texto_da_senha_gerada(u, senha), senha)
    return redirect(url_for('admin.usuarios'))


def acao_nova_senha(uid, dados):
    """``(feito, derrubou)``: ``feito`` é ``(pessoa, senha temporária)`` (a
    atual deixa de valer e as sessões abertas caem) ou None na recusa (o
    recado diz por quê); ``derrubou`` quando a senha errada do
    administrador bloqueou a conta dele e a sessão caiu."""
    u = db.get_or_404(User, uid)
    if u.id == current_user.id:
        # A própria senha se troca em "Trocar senha" (pede a atual). Gerar a
        # temporária para si derrubava a própria sessão, e a senha nova ia
        # parar na tela de login, à vista de quem estivesse perto.
        flash(MSG_SENHA_PROPRIA, 'danger')
        return None, False
    errada = _senha_do_admin_errada(dados)
    if errada is not None:
        return None, errada
    senha = _senha_temporaria()
    u.set_password(senha)
    u.must_change_password = True
    u.failed_login_count = 0
    u.lockout_until = None
    u.session_epoch = (u.session_epoch or 0) + 1
    db.session.commit()
    return (u, senha), False


@bp.post('/usuarios/<int:uid>/desligar-codigo')
@login_required
@admin_required
def desligar_codigo(uid):
    destino, _derrubou = acao_desligar_codigo(uid, request.form)
    return redirect(destino)


def acao_desligar_codigo(uid, dados):
    """A pessoa perdeu o celular: o administrador desliga a segunda etapa.
    As sessões abertas caem (quem achou o celular não continua dentro).
    ``(destino, derrubou)``, como ``acao_nova_senha``."""
    u = db.get_or_404(User, uid)
    errada = _senha_do_admin_errada(dados)
    if errada:
        return url_for('auth.login'), True
    if errada is False:
        return url_for('admin.usuarios'), False
    u.totp_ativo = False
    u.totp_segredo = None
    u.totp_ultimo_passo = None
    u.session_epoch = (u.session_epoch or 0) + 1
    db.session.commit()
    flash(f'Segunda etapa de {u.name} desligada. No próximo login ela entra só com a '
          f'senha e pode ativar de novo em "Segurança da conta".', 'success')
    return url_for('admin.usuarios'), False


# ── Locais (a tabela ``clients``; o endereço /admin/contratos é o de sempre) ─

@bp.get('/contratos')
@login_required
@admin_required
def contratos():
    return render_template('core/contratos.html', **contexto_contratos())


def contexto_contratos():
    from facilities.cadastros.models import Contratante, Estado
    lista = Client.query.filter(Client.is_deleted.is_(False)).order_by(
        Client.is_active.desc(), Client.name).all()
    gestores = (User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                                  User.role.in_(PERFIS_DE_GESTAO))
                .order_by(User.name).all())
    return dict(contratos=lista, gestores=gestores,
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


def _vincular(c, dados):
    """Cliente e estado do local; o erro volta como mensagem para a tela."""
    from facilities.cadastros.servico import CadastroInvalido, vincular_local
    try:
        vincular_local(c, dados, current_user)
    except CadastroInvalido as erro:
        return str(erro)
    return None


@bp.post('/contratos')
@login_required
@admin_required
def criar_contrato():
    return redirect(acao_criar_contrato(request.form))


def acao_criar_contrato(dados):
    from facilities.cadastros.servico import registrar_local
    c = Client(is_active=True)
    _aplicar_contrato(c, dados)
    erro = ('Informe o nome do local.' if not c.name
            else _responsavel_invalido(c) or _vincular(c, dados))
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return url_for('admin.contratos')
    db.session.add(c)
    registrar_local(c, None, current_user, nova=True)
    db.session.commit()
    flash(f'Local {c.name} cadastrado. Agora cadastre a estrutura dele (setores, '
          f'ambientes e pontos) e configure a passagem de turno.', 'success')
    return url_for('admin.contratos')


@bp.post('/contratos/<int:cid>')
@login_required
@admin_required
def editar_contrato(cid):
    return redirect(acao_editar_contrato(cid, request.form))


def acao_editar_contrato(cid, dados):
    from facilities.cadastros.servico import foto, registrar_local
    c = db.get_or_404(Client, cid)
    antes = foto(c)
    _aplicar_contrato(c, dados)
    c.is_active = bool(dados.get('is_active'))
    erro = ('Informe o nome do local.' if not c.name
            else _responsavel_invalido(c) or _vincular(c, dados))
    if erro:
        db.session.rollback()
        flash(erro, 'danger')
        return url_for('admin.contratos')
    registrar_local(c, antes, current_user)
    db.session.commit()
    flash(f'Local {c.name} atualizado.', 'success')
    return url_for('admin.contratos')
