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
* Administrador e diretoria (``visualizador``) não têm carteira: veem tudo
  (``None``). A diretoria vê tudo SEMPRE, venha do convite ou da tela
  "Pessoas e acessos", com ou sem a caixinha (R5, 05/11/2026).
* "Acesso a todos os locais" (``all_clients``) só abre o grupo inteiro para
  a gestão (gerente e coordenador). Para supervisor, encarregado e técnico
  (R1, 05/11/2026) a caixinha vale os locais da gestão logo ACIMA dela na
  cadeia (o primeiro gerente ou coordenador subindo): o técnico volante do
  coordenador cobre todos os locais do coordenador, não os do grupo. Sem
  gestão acima, fica só com a carteira dela.
* O cliente (Fase 9B) vê os locais ativos do SEU cliente (``cliente_id``) —
  nunca "todos os locais", mesmo com a caixinha marcada por engano.

A conta é feita uma vez por requisição para quem está logado (``g``).
"""
from flask import g, has_request_context

from facilities.extensions import db
from facilities.core.models import (NIVEL_NA_CADEIA, PERFIS_DE_GESTAO, Client, User,
                                    user_clients)

# Quem tem cadeia de gestão própria: a gestão acima de alguém na cadeia.
GESTAO_NA_CADEIA = ('gerente', 'pleno')


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


def _carteira_da_cadeia(user_id):
    """Os locais da pessoa pela cadeia: os dela + os de quem está abaixo."""
    return _locais_diretos({user_id} | subordinados(user_id))


def _locais_da_gestao_acima(user):
    """R1: os locais da gestão logo acima da pessoa — o primeiro gerente ou
    coordenador subindo a cadeia (a leitura mais estreita da regra: o
    técnico volante do coordenador cobre os locais do coordenador, não os de
    todo o gerente)."""
    for p in cadeia_acima(user):
        if p.role in GESTAO_NA_CADEIA and not p.is_deleted:
            return _carteira_da_cadeia(p.id)
    return set()


def carteira(user):
    """``None`` = vê tudo; senão o conjunto de ids de locais que a pessoa vê."""
    papel = user._effective_role()
    if papel == 'cliente':
        from facilities.portal.servico import locais_do_cliente
        return {c.id for c in locais_do_cliente(user)}
    if papel in ('master', 'visualizador'):
        return None
    todos = bool(getattr(user, 'all_clients', False))
    if todos and papel in PERFIS_DE_GESTAO:
        return None
    if has_request_context():
        cache = g.setdefault('_carteiras', {})
        if user.id in cache:
            return cache[user.id]
    ids = _carteira_da_cadeia(user.id)
    if todos:
        ids |= _locais_da_gestao_acima(user)
    if has_request_context():
        g._carteiras[user.id] = ids
    return ids


def quem_ve_o_local(client_id):
    """Os ids de quem tem o local na carteira — a MESMA conta de ``carteira``,
    feita de baixo para cima (uma consulta, não uma carteira por pessoa).

    É a régua de "quem cuida do local" para avisos e para quem pode receber
    um chamado (R4): o gerente pelo cliente, o coordenador e o supervisor
    pela cadeia, o volante com "todos" pela gestão acima dele (R1). Fica de
    fora o "vê tudo" sem cadeia — administrador, diretoria e o gestor que só
    tem a caixinha "todos os locais": aviso de todo local da casa a quem não
    cuida dele ensina a ignorar aviso. Quem chama filtra ativos e papéis.
    """
    from facilities.cadastros.models import Contratante
    pessoas = {p.id: p for p in db.session.query(
        User.id, User.superior_id, User.role, User.is_active, User.is_deleted,
        User.all_clients)}
    diretos = {uid for (uid,) in db.session.query(user_clients.c.user_id).filter(
        user_clients.c.client_id == client_id)}
    gerente_id = (db.session.query(Contratante.gerente_id)
                  .join(Client, Client.contratante_id == Contratante.id)
                  .filter(Client.id == client_id).scalar())
    if gerente_id in pessoas and pessoas[gerente_id].role == 'gerente':
        diretos.add(gerente_id)
    veem = set()
    for uid in diretos:
        p = pessoas.get(uid)
        if p is None:
            continue
        veem.add(uid)
        # Só a pessoa ATIVA (e não excluída) leva o local para cima; a subida
        # atravessa o desativado e para no excluído (``subordinados``).
        if not p.is_active or p.is_deleted:
            continue
        vistos, atual = {uid}, p
        while atual.superior_id and atual.superior_id not in vistos:
            sup = pessoas.get(atual.superior_id)
            if sup is None:
                break
            veem.add(sup.id)
            vistos.add(sup.id)
            if sup.is_deleted:
                break
            atual = sup
    # R1: o supervisor/encarregado/técnico com "todos" vê o que a gestão
    # logo acima dele vê (``_locais_da_gestao_acima``).
    for p in pessoas.values():
        if not p.all_clients or p.role in PERFIS_DE_GESTAO or p.role in (
                'visualizador', 'cliente') or p.id in veem:
            continue
        vistos, atual = {p.id}, p
        while atual.superior_id and atual.superior_id not in vistos:
            sup = pessoas.get(atual.superior_id)
            if sup is None:
                break
            if sup.role in GESTAO_NA_CADEIA and not sup.is_deleted:
                if sup.id in veem:
                    veem.add(p.id)
                break
            vistos.add(sup.id)
            atual = sup
    return veem


def alcance(user):
    """O que a lista de pessoas diz do alcance de cada uma (R1, R5)."""
    papel = user._effective_role()
    if papel in ('master', 'visualizador') or (user.all_clients and papel in PERFIS_DE_GESTAO):
        return 'todos os locais'
    if user.all_clients and papel != 'cliente':
        return 'todos os locais da gestão acima'
    return f'{len(user.clients)} local(is) direto(s)'


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
