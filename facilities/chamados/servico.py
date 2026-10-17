"""As regras do chamado — quem pode o quê, as transições, o prazo e os avisos.

Fica fora das rotas de propósito: cada regra se testa sem subir tela, e a
Passagem de Turno abre chamado (a partir de uma ocorrência) pela MESMA porta
que a tela de chamados usa.

Quem pode o quê (sempre dentro da carteira de contratos da pessoa):

* abrir, comentar e anexar — quem age no módulo (encarregado, técnico,
  gestor, administrador);
* atribuir, mudar prioridade e cancelar — gestor e administrador;
* iniciar, pôr em espera, retomar e resolver — o técnico responsável, o
  gestor e o administrador;
* confirmar ("ficou bom") ou reabrir ("não ficou") — quem pediu, o gestor e
  o administrador;
* a diretoria lê tudo e não altera nada.
"""
from datetime import datetime, timedelta

from facilities.extensions import db
from facilities.core.acesso import allowed_client_ids_or_none
from facilities.core.models import MODULO_CHAMADOS, Client, Notification, User
from facilities.chamados.models import (
    ABERTO, AGUARDANDO, CANCELADO, CATEGORIAS, EM_ATENDIMENTO, FECHADO,
    ORIGEM_MANUAL, ORIGEM_OCORRENCIA, PRAZO_POR_PRIORIDADE, PRIORIDADES,
    RESOLVIDO, STATUS_EM_ABERTO, Chamado, ChamadoEvento)

TIPO_AVISO = 'chamado'
TITULO_MAX = 200


class RecusaChamado(Exception):
    """Pedido recusado por regra (a mensagem vai para a tela)."""

    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


# ── Quem pode o quê ─────────────────────────────────────────────────────

def _na_carteira(user, client_id):
    permitidos = allowed_client_ids_or_none(user)
    return permitidos is None or client_id in permitidos


def e_gestor(user):
    return user._effective_role() in ('master', 'pleno')


def pode_ver(user, ch):
    return user.can_view(MODULO_CHAMADOS) and _na_carteira(user, ch.client_id)


def pode_agir(user, ch):
    return user.can_access(MODULO_CHAMADOS) and _na_carteira(user, ch.client_id)


def pode_gerir(user, ch):
    return pode_agir(user, ch) and e_gestor(user)


def pode_atender(user, ch):
    return pode_agir(user, ch) and (e_gestor(user) or ch.responsavel_id == user.id)


def pode_confirmar(user, ch):
    return pode_agir(user, ch) and (e_gestor(user) or ch.solicitante_id == user.id)


def acoes_disponiveis(user, ch):
    """As ações que a tela oferece a esta pessoa, neste momento do chamado."""
    acoes = []
    if not pode_agir(user, ch):
        return acoes
    if ch.status not in (FECHADO, CANCELADO):
        acoes.append('comentar')
    if pode_gerir(user, ch) and ch.status in STATUS_EM_ABERTO:
        acoes += ['atribuir', 'prioridade', 'cancelar']
    if pode_atender(user, ch):
        if ch.status == ABERTO:
            acoes.append('iniciar')
        if ch.status == EM_ATENDIMENTO:
            acoes += ['aguardar', 'resolver']
        if ch.status == AGUARDANDO:
            acoes += ['retomar', 'resolver']
    if pode_confirmar(user, ch) and ch.status == RESOLVIDO:
        acoes += ['confirmar', 'reabrir']
    return acoes


# ── Pessoas envolvidas ──────────────────────────────────────────────────

def _ativos(q):
    return q.filter(User.is_active.is_(True), User.is_deleted.is_(False))


def pessoas_do_contrato(client_id, papeis):
    """Quem tem o contrato na carteira (vínculo ou "todos"), nos papéis dados."""
    vinculados = _ativos(User.query.filter(User.role.in_(papeis),
                                           User.clients.any(id=client_id)))
    todos = _ativos(User.query.filter(User.role.in_(papeis),
                                      User.all_clients.is_(True)))
    vistos, saida = set(), []
    for u in list(vinculados) + list(todos):
        if u.id not in vistos:
            vistos.add(u.id)
            saida.append(u)
    return sorted(saida, key=lambda u: u.name.lower())


def tecnicos_do_contrato(client_id):
    """Quem pode receber um chamado: técnicos e gestores do contrato."""
    return pessoas_do_contrato(client_id, ('tecnico', 'pleno'))


def gestores_do_contrato(client_id):
    """O gestor responsável e os gestores vinculados — nunca "todos os
    administradores": aviso que chega a quem não cuida do contrato ensina a
    ignorar aviso."""
    ids = {u.id for u in pessoas_do_contrato(client_id, ('pleno',))}
    c = db.session.get(Client, client_id)
    if c is not None and c.responsible_user_id:
        ids.add(c.responsible_user_id)
    return ids


def _avisar(user_ids, ch, titulo, mensagem, exceto=None):
    for uid in {u for u in user_ids if u and u != exceto}:
        db.session.add(Notification(user_id=uid, notification_type=TIPO_AVISO,
                                    title=f'{ch.numero} · {titulo}'[:150],
                                    message=mensagem, link=f'/chamados/{ch.id}',
                                    status='unread'))


def _evento(ch, tipo, por, texto=None):
    db.session.add(ChamadoEvento(chamado=ch, tipo=tipo, texto=texto,
                                 created_by=por.id if por else None))


# ── Abrir ───────────────────────────────────────────────────────────────

def prazo_para(prioridade, a_partir=None):
    return (a_partir or datetime.utcnow()) + PRAZO_POR_PRIORIDADE[prioridade]


def abrir(user, client_id, titulo, descricao='', local='', categoria='outro',
          prioridade='media', area_id=None, origem=ORIGEM_MANUAL, origem_id=None):
    """Abre o chamado, grava o primeiro evento e avisa os gestores do contrato.

    O commit é de quem chama.
    """
    from facilities.passagem.models import DiarioArea
    try:
        client_id = int(client_id)
    except (TypeError, ValueError):
        raise RecusaChamado('Escolha o contrato.')
    if not user.can_access(MODULO_CHAMADOS):
        raise RecusaChamado('Seu perfil pode consultar, mas não abrir chamado.', 403)
    if not _na_carteira(user, client_id):
        raise RecusaChamado('Este contrato não está na sua carteira.', 403)
    contrato = db.session.get(Client, client_id)
    if contrato is None or not contrato.is_active or contrato.is_deleted:
        raise RecusaChamado('Contrato inexistente ou inativo.')
    titulo = (titulo or '').strip()
    if not titulo:
        raise RecusaChamado('Diga em uma linha qual é o problema.')
    if prioridade not in PRIORIDADES:
        raise RecusaChamado('Prioridade inválida.')
    if categoria not in CATEGORIAS:
        categoria = 'outro'
    area = None
    if area_id not in (None, ''):
        try:
            area = db.session.get(DiarioArea, int(area_id))
        except (TypeError, ValueError):
            area = None
        if area is None or area.client_id != client_id:
            raise RecusaChamado('A área escolhida não é deste contrato.')
    agora = datetime.utcnow()
    ch = Chamado(client_id=client_id, area_id=area.id if area else None,
                 titulo=titulo[:TITULO_MAX], descricao=(descricao or '').strip() or None,
                 local=(local or '').strip()[:200] or None, categoria=categoria,
                 prioridade=prioridade, status=ABERTO, solicitante_id=user.id,
                 prazo=prazo_para(prioridade, agora), origem=origem,
                 origem_id=origem_id, aberto_em=agora)
    db.session.add(ch)
    db.session.flush()
    _evento(ch, 'aberto', user, f'Prioridade {PRIORIDADES[prioridade].lower()}.')
    _avisar(gestores_do_contrato(client_id), ch, f'Novo chamado: {ch.titulo}',
            f'{contrato.name} · prioridade {PRIORIDADES[prioridade].lower()}'
            f'{" · " + ch.local if ch.local else ""}. Atribua a um técnico.',
            exceto=user.id)
    return ch


def abrir_de_ocorrencia(user, ocorrencia):
    """A ocorrência da passagem vira chamado — uma vez só.

    Idempotente por (origem, origem_id): o botão fica numa lista que o gestor
    relê todo dia, e o segundo clique devolve o chamado do primeiro.
    → ``(chamado, criado)``
    """
    from facilities.passagem.models import DiarioConfiguracao, DiarioTurno, OCORRENCIA_CRITICA
    existente = (Chamado.query.filter_by(origem=ORIGEM_OCORRENCIA, origem_id=ocorrencia.id)
                 .order_by(Chamado.id.desc()).first())
    if existente is not None:
        return existente, False
    area_id = None
    if ocorrencia.turno_id:
        t = db.session.get(DiarioTurno, ocorrencia.turno_id)
        cfg = db.session.get(DiarioConfiguracao, t.configuracao_id) if t else None
        area_id = cfg.area_id if cfg is not None else None
    tipo = (ocorrencia.tipo or 'Ocorrência').strip()
    descricao = (ocorrencia.descricao or '').strip()
    titulo = f'{tipo}: {descricao}' if descricao else tipo
    prioridade = 'alta' if (ocorrencia.gravidade or '') == OCORRENCIA_CRITICA else 'media'
    texto = descricao
    if ocorrencia.referencia:
        texto = f'{texto}\n\nReferência: {ocorrencia.referencia}'.strip()
    texto = f'{texto}\n\nAberto a partir da ocorrência registrada na passagem de turno.'.strip()
    ch = abrir(user, ocorrencia.client_id, titulo, descricao=texto,
               categoria='outro', prioridade=prioridade, area_id=area_id,
               origem=ORIGEM_OCORRENCIA, origem_id=ocorrencia.id)
    return ch, True


# ── Transições ──────────────────────────────────────────────────────────

def _exigir(cond, mensagem, status=403):
    if not cond:
        raise RecusaChamado(mensagem, status)


def executar(user, ch, acao, form):
    """Aplica uma ação da tela ao chamado. O commit é de quem chama."""
    texto = (form.get('texto') or '').strip()
    _exigir(acao in acoes_disponiveis(user, ch),
            'Esta ação não está disponível para você neste momento do chamado.')
    agora = datetime.utcnow()

    if acao == 'comentar':
        _exigir(texto, 'Escreva o comentário.', 400)
        _evento(ch, 'comentario', user, texto)
        interessados = {ch.solicitante_id, ch.responsavel_id} | gestores_do_contrato(ch.client_id)
        _avisar(interessados, ch, 'Novo comentário', texto[:300], exceto=user.id)

    elif acao == 'atribuir':
        try:
            rid = int(form.get('responsavel_id'))
        except (TypeError, ValueError):
            raise RecusaChamado('Escolha quem vai atender.', 400)
        candidatos = {u.id: u for u in tecnicos_do_contrato(ch.client_id)}
        _exigir(rid in candidatos, 'Essa pessoa não atende este contrato.', 400)
        anterior = ch.responsavel
        ch.responsavel_id = rid
        nome = candidatos[rid].name
        _evento(ch, 'atribuido', user,
                f'Responsável: {nome}' + (f' (antes: {anterior.name})' if anterior else ''))
        _avisar([rid], ch, f'Chamado atribuído a você: {ch.titulo}',
                f'Prioridade {ch.prioridade_rotulo.lower()} · prazo {_prazo_txt(ch)}.',
                exceto=user.id)

    elif acao == 'prioridade':
        nova = form.get('prioridade')
        _exigir(nova in PRIORIDADES, 'Prioridade inválida.', 400)
        if nova != ch.prioridade:
            # O prazo acompanha a prioridade, contado da ABERTURA: subir para
            # urgente um chamado de três dias o põe atrasado na hora — e é
            # verdade, ele está.
            ch.prioridade = nova
            ch.prazo = prazo_para(nova, ch.aberto_em)
            _evento(ch, 'prioridade', user,
                    f'Prioridade {PRIORIDADES[nova].lower()}' + (f' — {texto}' if texto else ''))

    elif acao == 'iniciar':
        if ch.responsavel_id is None:
            ch.responsavel_id = user.id
        ch.status = EM_ATENDIMENTO
        ch.iniciado_em = ch.iniciado_em or agora
        _evento(ch, 'iniciado', user, texto or None)

    elif acao == 'aguardar':
        _exigir(texto, 'Diga o que está faltando (peça, terceiro, acesso…).', 400)
        ch.status = AGUARDANDO
        ch.motivo_espera = texto[:300]
        _evento(ch, 'aguardando', user, texto)

    elif acao == 'retomar':
        ch.status = EM_ATENDIMENTO
        ch.motivo_espera = None
        _evento(ch, 'retomado', user, texto or None)

    elif acao == 'resolver':
        _exigir(texto, 'Descreva o que foi feito.', 400)
        ch.status = RESOLVIDO
        ch.solucao = texto
        ch.resolvido_em = agora
        ch.motivo_espera = None
        if ch.responsavel_id is None:
            ch.responsavel_id = user.id
        _evento(ch, 'resolvido', user, texto)
        _avisar([ch.solicitante_id], ch, f'Chamado resolvido: {ch.titulo}',
                'Confira no local e confirme — ou reabra se não ficou bom.',
                exceto=user.id)

    elif acao == 'confirmar':
        ch.status = FECHADO
        ch.fechado_em = agora
        _evento(ch, 'fechado', user, texto or 'Solução confirmada.')

    elif acao == 'reabrir':
        _exigir(texto, 'Diga o que ainda não ficou bom.', 400)
        ch.status = EM_ATENDIMENTO
        ch.resolvido_em = None
        _evento(ch, 'reaberto', user, texto)
        _avisar([ch.responsavel_id] if ch.responsavel_id else gestores_do_contrato(ch.client_id),
                ch, f'Chamado reaberto: {ch.titulo}', texto[:300], exceto=user.id)

    elif acao == 'cancelar':
        _exigir(texto, 'Diga por que o chamado está sendo cancelado.', 400)
        ch.status = CANCELADO
        ch.cancelado_em = agora
        _evento(ch, 'cancelado', user, texto)
        _avisar([ch.solicitante_id, ch.responsavel_id], ch,
                f'Chamado cancelado: {ch.titulo}', texto[:300], exceto=user.id)

    else:  # pragma: no cover - acoes_disponiveis já barra
        raise RecusaChamado('Ação desconhecida.', 400)


def _prazo_txt(ch):
    from facilities import tempo
    return tempo.fmt(ch.prazo) if ch.prazo else '—'


# ── Números ─────────────────────────────────────────────────────────────

def indicadores(client_ids, dias=30, agora=None):
    """O resumo do topo da tela de chamados, para a carteira dada.

    * agora: em aberto, atrasados, aguardando confirmação;
    * nos últimos ``dias``: resolvidos, % resolvidos dentro do prazo e o
      tempo médio da abertura à solução (em horas).
    """
    agora = agora or datetime.utcnow()
    base = Chamado.query
    if client_ids is not None:
        base = base.filter(Chamado.client_id.in_(client_ids or [-1]))
    abertos = base.filter(Chamado.status.in_(STATUS_EM_ABERTO)).all()
    atrasados = [c for c in abertos if c.atrasado(agora)]
    aguardando_conf = base.filter(Chamado.status == RESOLVIDO).count()
    desde = agora - timedelta(days=dias)
    resolvidos = base.filter(Chamado.resolvido_em.isnot(None),
                             Chamado.resolvido_em >= desde).all()
    no_prazo = [c for c in resolvidos if c.prazo is None or c.resolvido_em <= c.prazo]
    horas = [(c.resolvido_em - c.aberto_em).total_seconds() / 3600 for c in resolvidos]
    return {
        'em_aberto': len(abertos),
        'atrasados': len(atrasados),
        'aguardando_confirmacao': aguardando_conf,
        'resolvidos': len(resolvidos),
        'pct_no_prazo': round(100.0 * len(no_prazo) / len(resolvidos), 1) if resolvidos else None,
        'horas_medias': round(sum(horas) / len(horas), 1) if horas else None,
        'dias': dias,
    }
