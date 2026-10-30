"""Assistente "Novo contrato": cliente → local → estrutura → equipe.

Decisões do dono (22/10/2026):

* O GERENTE cria cliente (e vira o gerente responsável por ele) e locais nos
  clientes dele. O COORDENADOR cria locais só nos clientes do gerente dele
  (o primeiro gerente acima na cadeia). O administrador faz tudo.
* Convites seguem a hierarquia: o gerente convida coordenador, supervisor,
  encarregado/ASG, técnico e cliente; o coordenador convida supervisor,
  encarregado/ASG e técnico. Ninguém convida administrador nem diretoria
  (só o administrador, pela tela de pessoas, ou convidando a diretoria).
* O convite é um link de uso único, válido por 7 dias, sem senha
  temporária: a pessoa cria a própria senha. Só o hash do link fica no banco.
* Os locais do convite ficam dentro da carteira de quem convida; o superior
  é quem convida ou alguém da equipe dele, num nível acima do perfil.

As regras ficam aqui; as rotas só leem o formulário. O commit é de quem chama.
"""
import hashlib
import io
import json
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from facilities.core import senhas
from facilities.extensions import db
from facilities.core.models import NIVEL_NA_CADEIA, PERFIS, Client, Notification, User
from facilities.cadastros.models import Contratante, Convite, Empresa, Estado
from facilities.cadastros.servico import (CadastroInvalido, registrar, registrar_local,
                                          salvar_contratante, foto)

PERFIS_QUE_MONTAM = ('master', 'gerente', 'pleno')

# Quem convida quem (D: hierarquia, 22/10/2026).
CONVIDA = {
    'master': ('visualizador', 'gerente', 'pleno', 'supervisor', 'encarregado', 'tecnico',
               'cliente'),
    'gerente': ('pleno', 'supervisor', 'encarregado', 'tecnico', 'cliente'),
    'pleno': ('supervisor', 'encarregado', 'tecnico'),
}

DIAS_DO_CONVITE = 7
SENHA_MINIMA = 8
LOGO_MAX = 2 * 1024 * 1024
LOGO_LADO = 800


def _papel(user):
    return user._effective_role()


def pode_montar(user):
    return _papel(user) in PERFIS_QUE_MONTAM


def pode_criar_cliente(user):
    return _papel(user) in ('master', 'gerente')


def gerente_acima(user):
    """O gerente do coordenador: o primeiro gerente subindo a cadeia."""
    from facilities.core.hierarquia import cadeia_acima
    for p in cadeia_acima(user):
        if p.role == 'gerente' and p.is_active and not p.is_deleted:
            return p
    return None


def clientes_da_montagem(user):
    """Os clientes (contratantes ativos) em que a pessoa pode montar locais."""
    q = Contratante.query.filter(Contratante.is_active.is_(True))
    papel = _papel(user)
    if papel == 'master':
        pass
    elif papel == 'gerente':
        q = q.filter(Contratante.gerente_id == user.id)
    elif papel == 'pleno':
        g = gerente_acima(user)
        q = q.filter(Contratante.gerente_id == (g.id if g else -1))
    else:
        return []
    return q.order_by(Contratante.nome).all()


def _cliente_permitido(user, cid):
    c = db.session.get(Contratante, cid) if cid else None
    if c is None or c.id not in {x.id for x in clientes_da_montagem(user)}:
        raise CadastroInvalido('Escolha um dos seus clientes.')
    return c


# ── Passo 1: o cliente ────────────────────────────────────────────────────

def criar_cliente(dados, autor):
    """Cliente novo. O gerente vira o gerente responsável."""
    if not pode_criar_cliente(autor):
        raise CadastroInvalido('Cliente novo é cadastrado pelo gerente ou pelo administrador.')
    dados = dict(dados)
    if _papel(autor) == 'gerente':
        dados['gerente_id'] = str(autor.id)
    if not dados.get('empresa_id'):
        ativas = Empresa.query.filter_by(is_active=True).all()
        if len(ativas) == 1:
            dados['empresa_id'] = str(ativas[0].id)
    if not Empresa.query.filter_by(is_active=True).count():
        raise CadastroInvalido('Ainda não há empresa do grupo cadastrada. Peça ao '
                               'administrador para cadastrar em Cadastros › Empresas.')
    return salvar_contratante(None, dados, autor)


def salvar_logo(contratante, arquivo, autor):
    """Recebe a logo (PNG, JPG ou WebP até 2 MB), reduz e guarda como PNG."""
    from PIL import Image
    from facilities.core.anexos import ANEXO_ASSINATURA, IMAGENS, imagem_aceitavel, storage
    if arquivo is None or not getattr(arquivo, 'filename', ''):
        return None
    ext = arquivo.filename.rsplit('.', 1)[-1].lower() if '.' in arquivo.filename else ''
    dados = arquivo.read(LOGO_MAX + 1)
    if ext not in IMAGENS:
        raise CadastroInvalido('A logo precisa ser uma imagem PNG, JPG ou WebP.')
    if len(dados) > LOGO_MAX:
        raise CadastroInvalido('A logo passa de 2 MB. Use uma imagem menor.')
    if not dados.startswith(ANEXO_ASSINATURA[ext]) or not imagem_aceitavel(dados, ext):
        raise CadastroInvalido('Não foi possível abrir esta imagem. Envie a logo em PNG ou JPG.')
    with Image.open(io.BytesIO(dados)) as im:
        im = im.convert('RGBA')
        im.thumbnail((LOGO_LADO, LOGO_LADO))
        saida = io.BytesIO()
        im.save(saida, format='PNG', optimize=True)
    antes = foto(contratante)
    antiga = contratante.logo_key
    chave = f'logos/cliente-{contratante.id}-{secrets.token_hex(6)}.png'
    storage().save(chave, saida.getvalue(), 'image/png')
    contratante.logo_key = chave
    registrar('contratante', contratante, 'alterado', antes, autor)
    if antiga:
        try:
            storage().delete(antiga)
        except Exception:   # a logo antiga que sobra no armazenamento não quebra nada
            pass
    return chave


def logo_de(contratante):
    """Os bytes da logo (PNG) ou None."""
    from facilities.core.anexos import storage
    if contratante is None or not contratante.logo_key:
        return None
    try:
        return storage().load(contratante.logo_key)
    except Exception:
        return None


# ── Passo 2: o local ──────────────────────────────────────────────────────

def criar_local(contratante, dados, autor):
    if not pode_montar(autor):
        raise CadastroInvalido('O local é cadastrado pela gestão.')
    _cliente_permitido(autor, contratante.id)
    nome = (dados.get('name') or '').strip()[:120]
    if not nome:
        raise CadastroInvalido('Informe o nome do local.')
    repetido = Client.query.filter(db.func.lower(Client.name) == nome.lower(),
                                   Client.is_deleted.is_(False)).first()
    if repetido is not None:
        raise CadastroInvalido(f'Já existe um local chamado "{repetido.name}". Use um nome que '
                               'diferencie (ex.: a cidade ou o número do armazém).')
    eid = str(dados.get('estado_id') or '').strip()
    estado = db.session.get(Estado, int(eid)) if eid.isdigit() else None
    if estado is None or not estado.is_active:
        raise CadastroInvalido('Escolha o estado do local.')
    local = Client(name=nome, is_active=True, contratante_id=contratante.id,
                   estado_id=estado.id,
                   cost_center=(dados.get('cost_center') or '').strip()[:50] or None,
                   endereco=(dados.get('endereco') or '').strip()[:255] or None)
    if _papel(autor) in ('gerente', 'pleno'):
        local.responsible_user_id = autor.id
    db.session.add(local)
    db.session.flush()
    if _papel(autor) == 'pleno':
        # O coordenador passa a ver o local que montou (a carteira dele).
        autor.clients.append(local)
    registrar_local(local, None, autor, nova=True)
    return local


def estados_ativos():
    return Estado.query.filter_by(is_active=True).order_by(Estado.nome).all()


def andamento(local):
    """O que já está pronto no local, para os passos do assistente."""
    from facilities.cadastros.models import PontoInspecao
    from facilities.cadastros.servico import ponto_de_entrada
    pontos = PontoInspecao.query.filter_by(client_id=local.id, is_active=True).count()
    equipe = User.query.filter(User.clients.any(Client.id == local.id),
                               User.is_active.is_(True), User.is_deleted.is_(False)).count()
    pendentes = [c for c in convites_do_local(local) if c.situacao() == 'pendente']
    from facilities.rotas.models import Rota
    rotas = Rota.query.filter_by(client_id=local.id).count()
    return {'pontos': pontos, 'entrada': ponto_de_entrada(local.id) is not None,
            'rotas': rotas, 'equipe': equipe, 'convites': len(pendentes)}


def numeros_dos_pontos(local_id):
    """{ponto_id: número} na ordem em que os pontos foram cadastrados.

    Pontos nunca se apagam (só desativam) nem mudam de local, então o número
    de uma etiqueta impressa não muda: QR 001 é sempre o primeiro do local.
    """
    from facilities.cadastros.models import PontoInspecao
    ids = [pid for (pid,) in db.session.query(PontoInspecao.id)
           .filter(PontoInspecao.client_id == local_id).order_by(PontoInspecao.id)]
    return {pid: i for i, pid in enumerate(ids, start=1)}


# ── Passo 4: convites ─────────────────────────────────────────────────────

def perfis_que_convida(user):
    return CONVIDA.get(_papel(user), ())


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def superiores_para(autor):
    """Quem pode ser superior num convite deste autor: ele e a equipe dele."""
    from facilities.core.hierarquia import subordinados
    q = User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                          User.role.in_(('gerente', 'pleno', 'supervisor')))
    if _papel(autor) != 'master':
        ids = {autor.id} | subordinados(autor.id)
        q = q.filter(User.id.in_(ids))
    return q.order_by(User.name).all()


def _locais_permitidos(autor):
    from facilities.core.hierarquia import carteira
    ids = carteira(autor)
    q = Client.query.filter(Client.is_active.is_(True), Client.is_deleted.is_(False))
    if ids is not None:
        q = q.filter(Client.id.in_(ids or [-1]))
    return q.order_by(Client.name).all()


def _email_valido(email):
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email or ''))


def _telefone(bruto):
    digitos = re.sub(r'\D', '', bruto or '')
    if not digitos:
        return None
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    if not 12 <= len(digitos) <= 13:
        raise CadastroInvalido('Celular com DDD, só números (ex.: 71 99999-0000).')
    return digitos


def criar_convite(autor, dados, agora=None):
    """Valida e grava o convite. Devolve ``(convite, token)``; o token só existe aqui."""
    agora = agora or datetime.utcnow()
    role = (dados.get('role') or '').strip()
    if role not in perfis_que_convida(autor):
        raise CadastroInvalido('Você não pode convidar alguém com este perfil.')
    nome = (dados.get('nome') or '').strip()[:100]
    email = (dados.get('email') or '').strip().lower()[:150]
    if not nome:
        raise CadastroInvalido('Informe o nome da pessoa.')
    if not _email_valido(email):
        raise CadastroInvalido('Informe um e-mail válido: é com ele que a pessoa vai entrar.')
    if User.por_email(email) is not None:
        raise CadastroInvalido('Já existe uma pessoa com este e-mail no sistema. Se ela precisa '
                               'deste local, peça ao administrador para incluir.')
    telefone = _telefone(dados.get('telefone'))

    permitidos = {c.id for c in _locais_permitidos(autor)}
    getlist = getattr(dados, 'getlist', None)
    brutos = getlist('locais') if getlist else (dados.get('locais') or [])
    locais = sorted({int(x) for x in brutos if str(x).isdigit()})
    if any(cid not in permitidos for cid in locais):
        raise CadastroInvalido('Um dos locais escolhidos não está entre os seus.')

    cliente_id = None
    superior_id = None
    if role == 'cliente':
        bruto = str(dados.get('cliente_id') or '').strip()
        cliente = _cliente_permitido(autor, int(bruto) if bruto.isdigit() else None)
        cliente_id = cliente.id
        locais = []
    elif role == 'visualizador':
        locais = []
    else:
        # O gerente vê os locais pelos clientes dele: local no convite é opcional.
        if not locais and role != 'gerente':
            raise CadastroInvalido('Escolha ao menos um local para a pessoa.')
        bruto = str(dados.get('superior_id') or '').strip()
        superior_id = int(bruto) if bruto.isdigit() else None
        if superior_id is None and NIVEL_NA_CADEIA.get(_papel(autor), 99) \
                < NIVEL_NA_CADEIA[role]:
            superior_id = autor.id
        if superior_id is not None:
            sup = db.session.get(User, superior_id)
            if sup is None or sup.id not in {p.id for p in superiores_para(autor)}:
                raise CadastroInvalido('Escolha como superior você ou alguém da sua equipe.')
            if NIVEL_NA_CADEIA.get(sup.role, 99) >= NIVEL_NA_CADEIA[role]:
                raise CadastroInvalido('O superior precisa estar num nível acima '
                                       '(gerente › coordenador › supervisor › encarregado e '
                                       'técnico).')

    # Um convite aberto por e-mail e por quem convida: o novo substitui o
    # anterior (o convite de outra pessoa da gestão continua valendo).
    for velho in Convite.query.filter(Convite.email == email,
                                      Convite.criado_por_id == autor.id,
                                      Convite.aceito_em.is_(None),
                                      Convite.cancelado_em.is_(None)):
        velho.cancelado_em = agora
    token = secrets.token_urlsafe(32)
    convite = Convite(token_hash=_hash(token), nome=nome, email=email, telefone=telefone,
                      role=role, superior_id=superior_id, cliente_id=cliente_id,
                      locais_json=json.dumps(locais), criado_por_id=autor.id,
                      criado_em=agora, expira_em=agora + timedelta(days=DIAS_DO_CONVITE))
    db.session.add(convite)
    db.session.flush()
    return convite, token


def locais_do_convite(convite):
    ids = json.loads(convite.locais_json or '[]')
    if not ids:
        return []
    return Client.query.filter(Client.id.in_(ids)).order_by(Client.name).all()


def convites_do_local(local):
    """Convites que incluem o local (o JSON é filtrado em Python: são poucos)."""
    marca = str(local.id)
    lista = (Convite.query.filter(Convite.locais_json.contains(marca))
             .order_by(Convite.criado_em.desc()).all())
    return [c for c in lista if local.id in json.loads(c.locais_json or '[]')]


def convites_visiveis(autor):
    """O administrador vê todos; os outros, os que criaram."""
    q = Convite.query
    if _papel(autor) != 'master':
        q = q.filter(Convite.criado_por_id == autor.id)
    return q.order_by(Convite.criado_em.desc()).limit(200).all()


def cancelar(convite, autor, agora=None):
    if _papel(autor) != 'master' and convite.criado_por_id != autor.id:
        raise CadastroInvalido('Só quem convidou pode cancelar este convite.')
    if convite.situacao(agora) != 'pendente':
        raise CadastroInvalido('Este convite já não está aberto.')
    convite.cancelado_em = agora or datetime.utcnow()


def renovar(convite, autor, agora=None):
    """Link novo para o mesmo convite (o anterior deixa de valer)."""
    agora = agora or datetime.utcnow()
    if _papel(autor) != 'master' and convite.criado_por_id != autor.id:
        raise CadastroInvalido('Só quem convidou pode gerar um link novo.')
    if convite.aceito_em:
        raise CadastroInvalido('Este convite já foi aceito.')
    token = secrets.token_urlsafe(32)
    convite.token_hash = _hash(token)
    convite.cancelado_em = None
    convite.expira_em = agora + timedelta(days=DIAS_DO_CONVITE)
    return token


def convite_pelo_token(token, agora=None):
    """O convite aberto deste link, ou None (vencido, usado ou inventado)."""
    if not token or len(token) > 100:
        return None
    c = Convite.query.filter_by(token_hash=_hash(token)).first()
    if c is None or c.situacao(agora) != 'pendente':
        return None
    autor = c.criado_por
    if autor is None or not autor.is_active or autor.is_deleted:
        return None
    return c


def aceitar(token, senha, confirma, agora=None):
    """Cria a conta do convite. Devolve o ``User``."""
    agora = agora or datetime.utcnow()
    c = convite_pelo_token(token, agora)
    if c is None:
        raise CadastroInvalido('Este convite não vale mais. Peça um link novo a quem convidou.')
    if len(senha or '') < SENHA_MINIMA:
        raise CadastroInvalido(f'A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.')
    if senha != confirma:
        raise CadastroInvalido('A confirmação não é igual à senha.')
    if senha.lower() in (c.email.lower(), c.email.split('@')[0].lower()):
        raise CadastroInvalido('Use uma senha diferente do seu e-mail.')
    if senhas.problema(senha, c.email):
        raise CadastroInvalido(senhas.problema(senha, c.email))
    if User.por_email(c.email) is not None:
        raise CadastroInvalido('Já existe uma conta com este e-mail. Entre pela tela de login.')
    locais = [loc for loc in locais_do_convite(c) if loc.is_active and not loc.is_deleted]
    sup = c.superior if c.superior and c.superior.is_active else None
    u = User(name=c.nome, email=c.email, role=c.role, is_active=True,
             must_change_password=False, superior_id=sup.id if sup else None,
             cliente_id=c.cliente_id, all_clients=c.role == 'visualizador',
             permissions_json='[]')
    u.set_password(senha)
    u.clients = locais
    db.session.add(u)
    db.session.flush()
    c.aceito_em = agora
    c.usuario_id = u.id
    db.session.add(Notification(
        user_id=c.criado_por_id, notification_type='convite',
        title=f'{c.nome} aceitou o convite',
        message=f'{c.nome} criou a conta como {PERFIS.get(c.role, c.role)}.',
        link='/convites'))
    return u


# ── Texto do convite (WhatsApp e e-mail) ──────────────────────────────────

def texto_do_convite(convite, link):
    locais = ', '.join(loc.name for loc in locais_do_convite(convite)) \
        or (convite.cliente.nome if convite.cliente else '')
    onde = f' em {locais}' if locais else ''
    return (f'Olá, {convite.nome}! {convite.criado_por.name} convidou você para o Trino '
            f'Facilities como {PERFIS.get(convite.role, convite.role)}{onde}.\n\n'
            f'Abra o link para criar a sua senha (vale {DIAS_DO_CONVITE} dias e só funciona '
            f'uma vez):\n{link}\n\nDepois, entre com o e-mail {convite.email}.')


def link_whatsapp(convite, link):
    destino = convite.telefone or ''
    return f'https://wa.me/{destino}?text={quote(texto_do_convite(convite, link))}'


def link_email(convite, link):
    assunto = 'Seu acesso ao Trino Facilities'
    return (f'mailto:{convite.email}?subject={quote(assunto)}'
            f'&body={quote(texto_do_convite(convite, link))}')
