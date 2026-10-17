"""A cadeia de pessoas e a carteira de locais que sai dela (Fase 2).

    Gerente ── responsável por clientes (``contratantes.gerente_id``)
    └─ Coordenador
       └─ Supervisor
          └─ Encarregado / ASG · Técnico

Regras (decisões D44, D46, P9 a P12, P15):

* Cada pessoa tem UM superior direto, num nível acima (pular nível vale).
  Como o nível do superior é sempre menor, a cadeia não fecha ciclo.
* A carteira de uma pessoa é: os locais vinculados a ela (``user_clients``)
  + para o gerente, todos os locais dos clientes pelos quais responde
  + a carteira de cada pessoa ATIVA abaixo dela, em qualquer profundidade.
  Ou seja: quem está acima vê tudo o que os de baixo veem.
* Administrador e quem tem "todos os locais" (a diretoria) não têm carteira:
  veem tudo (``None``).

A conta é feita uma vez por requisição para quem está logado (``g``).
"""
from flask import g, has_request_context

from facilities.extensions import db
from facilities.core.models import NIVEL_NA_CADEIA, Client, User, user_clients


class CadeiaInvalida(ValueError):
    """Superior impossível (mensagem pronta para a tela)."""


def subordinados(user_id, so_ativos=True):
    """Ids das pessoas abaixo de ``user_id``, em qualquer profundidade.

    A busca ATRAVESSA quem está desativado (o supervisor que saiu ainda liga
    o coordenador aos encarregados dele, até alguém ser reposto), mas por
    padrão só devolve os ativos.
    """
    vistos, ativos = set(), set()
    fronteira = {user_id}
    while fronteira:
        filhos = db.session.query(User.id, User.is_active).filter(
            User.superior_id.in_(fronteira), User.is_deleted.is_(False)).all()
        novos = {uid for uid, _ in filhos} - vistos - {user_id}
        ativos |= {uid for uid, ativo in filhos if ativo and uid in novos}
        vistos |= novos
        fronteira = novos
    return ativos if so_ativos else vistos


def _locais_diretos(user_ids):
    """Locais vinculados às pessoas + os dos clientes de quem é gerente."""
    if not user_ids:
        return set()
    from facilities.cadastros.models import Contratante
    ids = {cid for (cid,) in db.session.query(user_clients.c.client_id).filter(
        user_clients.c.user_id.in_(user_ids))}
    ids |= {cid for (cid,) in db.session.query(Client.id).join(
        Contratante, Client.contratante_id == Contratante.id).filter(
        Contratante.gerente_id.in_(user_ids),
        User.query.filter(User.id == Contratante.gerente_id,
                          User.role == 'gerente').exists())}
    return ids


def carteira(user):
    """``None`` = vê tudo; senão o conjunto de ids de locais que a pessoa vê."""
    if user._effective_role() == 'master' or getattr(user, 'all_clients', False):
        return None
    if has_request_context():
        cache = g.setdefault('_carteiras', {})
        if user.id in cache:
            return cache[user.id]
    pessoas = {user.id} | subordinados(user.id)
    ids = _locais_diretos(pessoas)
    if has_request_context():
        g._carteiras[user.id] = ids
    return ids


def validar_superior(user, superior_id):
    """Confere o superior escolhido para ``user``; devolve o id (ou None)."""
    if not superior_id:
        return None
    nivel = NIVEL_NA_CADEIA.get(user.role)
    if nivel is None:
        raise CadeiaInvalida('Administrador, diretoria e cliente ficam fora da cadeia: '
                             'não têm superior.')
    sup = db.session.get(User, int(superior_id))
    if sup is None or sup.is_deleted or not sup.is_active:
        raise CadeiaInvalida('Escolha um superior ativo.')
    if sup.id == user.id:
        raise CadeiaInvalida('A pessoa não pode ser superior de si mesma.')
    nivel_sup = NIVEL_NA_CADEIA.get(sup.role)
    if nivel_sup is None or nivel_sup >= nivel:
        raise CadeiaInvalida('O superior precisa estar num nível acima '
                             '(gerente › coordenador › supervisor › encarregado e técnico).')
    return sup.id


def superiores_possiveis(role=None):
    """Quem pode ser superior (gerente, coordenador e supervisor ativos)."""
    q = User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                          User.role.in_(('gerente', 'pleno', 'supervisor')))
    pessoas = q.order_by(User.name).all()
    nivel = NIVEL_NA_CADEIA.get(role) if role else None
    if nivel is None:
        return pessoas
    return [p for p in pessoas if NIVEL_NA_CADEIA[p.role] < nivel]


def problema_ao_mudar_perfil(user, novo_role):
    """Quem já está abaixo da pessoa precisa continuar abaixo do nível novo."""
    nivel = NIVEL_NA_CADEIA.get(novo_role)
    for sub in User.query.filter(User.superior_id == user.id, User.is_deleted.is_(False)):
        nivel_sub = NIVEL_NA_CADEIA.get(sub.role)
        if nivel is None or nivel_sub is None or nivel_sub <= nivel:
            return (f'{sub.name} está abaixo desta pessoa na cadeia. Mude antes o superior '
                    f'dele (e de quem mais estiver abaixo) e depois troque o perfil.')
    return None


def cadeia_acima(user):
    """[superior direto, o superior dele, ...] — para mostrar na tela."""
    cadeia, vistos, atual = [], {user.id}, user.superior
    while atual is not None and atual.id not in vistos:
        cadeia.append(atual)
        vistos.add(atual.id)
        atual = atual.superior
    return cadeia
