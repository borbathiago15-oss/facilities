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

Pedido repetido não estraga nada: o celular do posto repete POST quando a
rede oscila, e o duplo clique é o normal de quem está de luva. Por isso a
ação trava o chamado antes de conferir o estado (``chamado_para_alterar``),
o reenvio da mesma ação vira "já feito" (``_reenvio``) e abrir o mesmo
chamado duas vezes devolve o primeiro (``abrir_sem_duplicar``).
"""
from collections import namedtuple
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from facilities.extensions import db
from facilities.core.acesso import allowed_client_ids_or_none
from facilities.core.models import MODULO_CHAMADOS, Client, Notification, User
from facilities.chamados.models import (
    ABERTO, AGUARDANDO, CANCELADO, CATEGORIAS, EM_ATENDIMENTO, FECHADO,
    ORIGEM_MANUAL, ORIGEM_OCORRENCIA, PRAZO_POR_PRIORIDADE, PRIORIDADES,
    RESOLVIDO, STATUS_EM_ABERTO, Chamado, ChamadoEvento)

TIPO_AVISO = 'chamado'
TITULO_MAX = 200

# A mesma ação, da mesma pessoa, com o mesmo texto, dentro desta janela, é o
# MESMO pedido chegando duas vezes (duplo clique, rede que repete o POST).
JANELA_REENVIO = timedelta(minutes=2)

# Que passo da trilha cada ação grava — é por ele que se reconhece o reenvio.
EVENTO_DA_ACAO = {
    'comentar': 'comentario', 'iniciar': 'iniciado', 'aguardar': 'aguardando',
    'retomar': 'retomado', 'resolver': 'resolvido', 'confirmar': 'fechado',
    'reabrir': 'reaberto', 'cancelar': 'cancelado',
}
# Ações em que o texto é o conteúdo: dois comentários DIFERENTES seguidos são
# dois comentários; o mesmo texto de novo, em segundos, é o duplo clique.
ACOES_COM_TEXTO = ('comentar', 'aguardar', 'resolver', 'reabrir', 'cancelar')

# O que a tela diz depois de cada ação — no celular, o cartão de ações fica
# abaixo do cabeçalho, e sem a frase a pessoa não sabe se o toque valeu.
CONFIRMACAO = {
    'comentar': 'Comentário registrado.',
    'iniciar': 'Atendimento iniciado.',
    'aguardar': 'Chamado posto em espera.',
    'retomar': 'Atendimento retomado.',
    'resolver': 'Chamado marcado como resolvido.',
    'confirmar': 'Chamado fechado. Obrigado por confirmar.',
    'reabrir': 'Chamado reaberto.',
    'cancelar': 'Chamado cancelado.',
}

# O que ``executar`` devolve à rota: a frase da tela, se algo foi gravado
# (pedido repetido e "nada mudou" não gravam — e não recebem anexo) e o tom.
Feito = namedtuple('Feito', 'mensagem gravou categoria')


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
    return user.e_gestao()


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
    return pessoas_do_contrato(client_id, ('tecnico', 'pleno', 'gerente'))


def gestores_do_contrato(client_id):
    """O gestor responsável e os gestores VINCULADOS ao contrato — nunca
    "todos os administradores", nem o gestor que só tem "todos os contratos"
    (o regional, a diretoria): aviso que chega a quem não cuida do contrato
    ensina a ignorar aviso. É a mesma conta da Passagem de Turno.

    O responsável cadastrado no contrato só entra se AINDA é gestor (ou
    administrador), está ativo e tem o contrato na carteira: a tela de
    contratos aceita qualquer gestor, e quem mudou de papel, saiu da empresa
    ou perdeu o contrato receberia título e local de um chamado que não
    consegue abrir (o link dá 403).
    """
    ids = {u.id for u in _ativos(User.query.filter(User.role.in_(('pleno', 'gerente')),
                                                   User.clients.any(id=client_id)))}
    c = db.session.get(Client, client_id)
    resp = db.session.get(User, c.responsible_user_id) \
        if c is not None and c.responsible_user_id else None
    if (resp is not None and resp.is_active and not resp.is_deleted
            and e_gestor(resp) and _na_carteira(resp, client_id)):
        ids.add(resp.id)
    return ids


def _avisar(user_ids, ch, titulo, mensagem, exceto=None):
    """Grava o aviso (sino) para cada pessoa — e devolve quem foi avisado.

    Só recebe quem ABRE o chamado hoje: ativo, com o módulo e com o contrato
    na carteira (``pode_ver``). O solicitante que foi transferido de
    contrato, o técnico desligado, o gestor que perdeu o contrato: todos
    continuariam lendo comentário e título de um contrato que já não é deles.
    A conferência fica AQUI, e não em cada chamador, para nenhum aviso novo
    esquecê-la.
    """
    ids = {u for u in user_ids if u and u != exceto}
    if not ids:
        return set()
    avisados = set()
    for u in _ativos(User.query.filter(User.id.in_(ids))):
        if not pode_ver(u, ch):
            continue
        db.session.add(Notification(user_id=u.id, notification_type=TIPO_AVISO,
                                    title=f'{ch.numero} · {titulo}'[:150],
                                    message=mensagem, link=f'/chamados/{ch.id}',
                                    status='unread'))
        avisados.add(u.id)
    return avisados


def _evento(ch, tipo, por, texto=None):
    db.session.add(ChamadoEvento(chamado=ch, tipo=tipo, texto=texto,
                                 created_by=por.id if por else None))


# ── Abrir ───────────────────────────────────────────────────────────────

def regua_do_contrato(client_id):
    """A régua de prazo (D9): a do cliente do local, se ele tiver uma; senão
    a padrão (``PRAZO_POR_PRIORIDADE``). Prioridade sem valor no cliente
    também cai na padrão."""
    import json
    regua = dict(PRAZO_POR_PRIORIDADE)
    c = db.session.get(Client, client_id) if client_id else None
    contratante = getattr(c, 'contratante', None)
    if contratante is not None and contratante.prazos_chamado_json:
        try:
            for prioridade, horas in json.loads(contratante.prazos_chamado_json).items():
                if prioridade in regua and int(horas) > 0:
                    regua[prioridade] = timedelta(hours=int(horas))
        except (ValueError, TypeError, AttributeError):
            pass
    return regua


def prazo_para(prioridade, a_partir=None, client_id=None):
    return (a_partir or datetime.utcnow()) + regua_do_contrato(client_id)[prioridade]


def _pausar(ch, agora):
    """Entrou em "Aguardando": o relógio do prazo para (D8)."""
    ch.pausado_desde = agora


def _retomar_relogio(ch, agora):
    """Saiu de "Aguardando": o tempo parado empurra o prazo para frente."""
    if ch.pausado_desde is None:
        return
    parado = max(timedelta(0), agora - ch.pausado_desde)
    ch.pausa_total_seg = (ch.pausa_total_seg or 0) + int(parado.total_seconds())
    if ch.prazo is not None:
        ch.prazo = ch.prazo + parado
        _prazo_mudou(ch, agora)
    ch.pausado_desde = None


def _prazo_mudou(ch, agora):
    """O prazo andou para frente: os avisos de prazo valem de novo."""
    if ch.prazo is not None and ch.prazo > agora:
        ch.aviso_vencendo_em = None
        ch.aviso_vencido_em = None


def _travar_contrato(client_id):
    """Põe em fila quem abre chamado no MESMO contrato, até o commit.

    É o que deixa a conferência "já abri este?" valer com dois pedidos ao
    mesmo tempo: o segundo só olha depois que o primeiro gravou. ``NO KEY``
    não segura quem só grava registro filho do contrato (passagem, ocorrência,
    pendência). No SQLite (testes) a cláusula é ignorada.
    """
    db.session.execute(db.select(Client.id).where(Client.id == client_id)
                       .with_for_update(key_share=True))


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
        raise RecusaChamado('Este contrato não está entre os seus contratos.', 403)
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
                 prazo=prazo_para(prioridade, agora, client_id), origem=origem,
                 origem_id=origem_id, aberto_em=agora)
    db.session.add(ch)
    db.session.flush()
    _evento(ch, 'aberto', user, f'Prioridade {PRIORIDADES[prioridade].lower()}.')
    _avisar(gestores_do_contrato(client_id), ch, f'Novo chamado: {ch.titulo}',
            f'{contrato.name} · prioridade {PRIORIDADES[prioridade].lower()}'
            f'{" · " + ch.local if ch.local else ""}. Atribua a um técnico.',
            exceto=user.id)
    return ch


def abrir_sem_duplicar(user, client_id, titulo, **campos):
    """A porta da tela "Abrir chamado": ``abrir`` à prova de duplo envio.

    O mesmo chamado (mesma pessoa, mesmo contrato, mesmo título) aberto de
    novo dentro de ``JANELA_REENVIO`` é o formulário enviado duas vezes —
    devolve o primeiro, sem segunda OS e sem segundo aviso aos gestores.
    → ``(chamado, criado)``. O commit é de quem chama.
    """
    try:
        cid = int(client_id)
    except (TypeError, ValueError):
        cid = None
    texto = (titulo or '').strip()[:TITULO_MAX]
    if cid is not None and texto and user.can_access(MODULO_CHAMADOS) \
            and _na_carteira(user, cid):
        _travar_contrato(cid)
        igual = (Chamado.query
                 .filter(Chamado.client_id == cid, Chamado.solicitante_id == user.id,
                         Chamado.origem == ORIGEM_MANUAL, Chamado.titulo == texto,
                         Chamado.status != CANCELADO,
                         Chamado.aberto_em >= datetime.utcnow() - JANELA_REENVIO)
                 .order_by(Chamado.id.desc()).first())
        if igual is not None:
            return igual, False
    return abrir(user, client_id, titulo, **campos), True


def _chamado_vivo_da_ocorrencia(ocorrencia_id):
    return (Chamado.query
            .filter(Chamado.origem == ORIGEM_OCORRENCIA, Chamado.origem_id == ocorrencia_id,
                    Chamado.status != CANCELADO)
            .order_by(Chamado.id.desc()).first())


def chamados_das_ocorrencias(ocorrencia_ids):
    """``{ocorrencia_id: chamado}`` das ocorrências que JÁ viraram chamado.

    Para o painel da Passagem trocar "Abrir chamado" por "Ver OS-00012": o
    gestor relê a lista todo dia e precisa saber, sem clicar, o que já está
    com a manutenção. Chamado cancelado não conta — a ocorrência volta a
    poder virar chamado (a mesma regra de ``abrir_de_ocorrencia``).
    """
    ids = {i for i in (ocorrencia_ids or []) if i}
    if not ids:
        return {}
    return {ch.origem_id: ch for ch in
            Chamado.query.filter(Chamado.origem == ORIGEM_OCORRENCIA,
                                 Chamado.origem_id.in_(ids),
                                 Chamado.status != CANCELADO)
            .order_by(Chamado.id)}


def abrir_de_ocorrencia(user, ocorrencia):
    """A ocorrência da passagem vira chamado — uma vez só.

    Idempotente por (origem, origem_id): o botão fica numa lista que o gestor
    relê todo dia, e o segundo clique devolve o chamado do primeiro. Vale
    também para dois cliques AO MESMO TEMPO (duas abas, a gestora e o
    encarregado): a consulta sozinha deixava os dois passarem, e quem segura
    é o índice único ``uq_chamados_origem_viva`` — o segundo INSERT esbarra
    nele e recebe o chamado do primeiro.

    Chamado CANCELADO não prende a ocorrência: "vamos esperar a reforma" não
    pode deixá-la para sempre apontando para uma OS morta.

    Ocorrência de passagem ainda em rascunho é recusada: só o turno ENCERRADO
    é registro entregue (é o que o painel mostra); o rascunho ainda é do
    encarregado.
    → ``(chamado, criado)``
    """
    from facilities.passagem.analitico import TURNO_ENCERRADO
    from facilities.passagem.models import DiarioConfiguracao, DiarioTurno, OCORRENCIA_CRITICA
    existente = _chamado_vivo_da_ocorrencia(ocorrencia.id)
    if existente is not None:
        return existente, False
    t = db.session.get(DiarioTurno, ocorrencia.turno_id) if ocorrencia.turno_id else None
    if t is not None and t.status != TURNO_ENCERRADO:
        raise RecusaChamado('Esta ocorrência é de uma passagem de turno que ainda não foi '
                            'encerrada. Encerre a passagem e depois abra o chamado.', 409)
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
    try:
        # SAVEPOINT: se o índice recusar, desfaz só este chamado (evento e
        # avisos juntos), e o resto do pedido de quem chamou continua de pé.
        with db.session.begin_nested():
            ch = abrir(user, ocorrencia.client_id, titulo, descricao=texto,
                       categoria='outro', prioridade=prioridade, area_id=area_id,
                       origem=ORIGEM_OCORRENCIA, origem_id=ocorrencia.id)
    except IntegrityError:
        existente = _chamado_vivo_da_ocorrencia(ocorrencia.id)
        if existente is None:
            raise
        return existente, False
    return ch, True


# ── Transições ──────────────────────────────────────────────────────────

def _exigir(cond, mensagem, status=403):
    if not cond:
        raise RecusaChamado(mensagem, status)


def chamado_para_alterar(chamado_id):
    """O chamado TRAVADO até o commit (``SELECT … FOR NO KEY UPDATE``).

    Duas pessoas agindo no mesmo chamado ao mesmo tempo — o duplo clique em
    "Marcar como resolvido", a gestora cancelando enquanto o encarregado
    comenta — fazem fila aqui: o segundo pedido só lê o chamado depois que o
    primeiro gravou, e ``executar`` confere a ação contra o estado NOVO. Sem
    a trava, os dois liam "em atendimento" e os dois gravavam (e um
    "resolver" atrasado ressuscitava chamado cancelado). ``populate_existing``
    relê mesmo que o chamado já esteja na sessão. No SQLite (testes) a
    cláusula é ignorada — lá as escritas já são em fila.
    """
    return db.session.get(Chamado, chamado_id, with_for_update={'key_share': True},
                          populate_existing=True)


def _reenvio(user, ch, acao, texto):
    """O mesmo pedido chegando de novo (duplo clique, rede que repete o POST,
    "voltar" e reenviar)?

    É reenvio quando o ÚLTIMO passo da trilha é esta mesma ação, desta mesma
    pessoa, com o mesmo texto, há menos de ``JANELA_REENVIO``. Aí nada se
    grava — nem segundo evento, nem segundo aviso, nem segunda foto — e a
    tela confirma como se fosse o primeiro: para quem tocou, foi.
    """
    tipo = EVENTO_DA_ACAO.get(acao)
    if tipo is None or ch.id is None:
        return False
    ultimo = (ChamadoEvento.query.filter_by(chamado_id=ch.id)
              .order_by(ChamadoEvento.id.desc()).first())
    if ultimo is None or ultimo.tipo != tipo or ultimo.created_by != user.id:
        return False
    if datetime.utcnow() - ultimo.created_at > JANELA_REENVIO:
        return False
    return acao not in ACOES_COM_TEXTO or (ultimo.texto or '') == texto


def executar(user, ch, acao, form):
    """Aplica uma ação da tela ao chamado. O commit é de quem chama.

    Quem chama deve ter carregado o chamado com ``chamado_para_alterar``: a
    conferência abaixo só vale contra o estado de AGORA. → ``Feito``.
    """
    texto = (form.get('texto') or '').strip()
    if _reenvio(user, ch, acao, texto):
        return Feito(CONFIRMACAO[acao], False, 'success')
    _exigir(acao in acoes_disponiveis(user, ch),
            'Esta ação não está disponível para você neste momento do chamado '
            f'(situação atual: {ch.status_rotulo.lower()}).')
    agora = datetime.utcnow()
    mensagem = CONFIRMACAO.get(acao)

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
        nome = candidatos[rid].name
        if rid == ch.responsavel_id:
            # A lista "Trocar responsável" já abre com o atual escolhido:
            # salvar sem mexer gravava "Responsável: Caio (antes: Caio)" e um
            # segundo "atribuído a você".
            return Feito(f'{nome} já é o responsável por este chamado.', False, 'info')
        anterior = ch.responsavel
        ch.responsavel_id = rid
        _evento(ch, 'atribuido', user,
                f'Responsável: {nome}' + (f' (antes: {anterior.name})' if anterior else ''))
        avisados = _avisar([rid], ch, f'Chamado atribuído a você: {ch.titulo}',
                           f'Prioridade {ch.prioridade_rotulo.lower()} · prazo {_prazo_txt(ch)}.',
                           exceto=user.id)
        if anterior is not None:
            # Quem perdeu o chamado precisa saber — senão continua achando
            # que é dele e vai ao local à toa.
            _avisar([anterior.id], ch, f'Chamado passou para {nome}: {ch.titulo}',
                    'Você não é mais o responsável por este chamado.', exceto=user.id)
        mensagem = (f'Chamado atribuído a {nome}, que já recebeu o aviso.' if rid in avisados
                    else f'Chamado atribuído a {nome}.')

    elif acao == 'prioridade':
        nova = form.get('prioridade')
        _exigir(nova in PRIORIDADES, 'Prioridade inválida.', 400)
        if nova == ch.prioridade:
            return Feito('A prioridade já era essa; nada mudou.', False, 'info')
        # O prazo acompanha a prioridade, contado da ABERTURA: subir para
        # urgente um chamado de três dias o põe atrasado na hora — e é
        # verdade, ele está.
        ch.prioridade = nova
        # As pausas já encerradas continuam valendo (D8).
        ch.prazo = prazo_para(nova, ch.aberto_em, ch.client_id) + \
            timedelta(seconds=ch.pausa_total_seg or 0)
        _prazo_mudou(ch, agora)
        _evento(ch, 'prioridade', user,
                f'Prioridade {PRIORIDADES[nova].lower()}' + (f' — {texto}' if texto else ''))
        # Quem atende precisa saber que a régua mudou: o urgente que ninguém
        # avisou fica na fila do "média" até estourar.
        atrasado = ' — já está atrasado' if ch.atrasado(agora) else ''
        # Quem pediu também: o prazo que lhe foi prometido mudou.
        _avisar([ch.responsavel_id, ch.solicitante_id], ch, f'Prioridade mudou: {ch.titulo}',
                f'Agora {PRIORIDADES[nova].lower()} · prazo {_prazo_txt(ch)}{atrasado}.'
                + (f' Motivo: {texto[:200]}' if texto else ''), exceto=user.id)
        mensagem = (f'Prioridade alterada para {PRIORIDADES[nova].lower()}. '
                    f'Novo prazo: {_prazo_txt(ch)}.')

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
        _pausar(ch, agora)
        _evento(ch, 'aguardando', user, texto + ' — o prazo fica parado enquanto espera.')

    elif acao == 'retomar':
        ch.status = EM_ATENDIMENTO
        ch.motivo_espera = None
        _retomar_relogio(ch, agora)
        _evento(ch, 'retomado', user, (texto + ' — ' if texto else '') +
                f'novo prazo: {_prazo_txt(ch)}.')

    elif acao == 'resolver':
        _exigir(texto, 'Descreva o que foi feito.', 400)
        _retomar_relogio(ch, agora)
        ch.status = RESOLVIDO
        ch.solucao = texto
        ch.resolvido_em = agora
        ch.motivo_espera = None
        if ch.responsavel_id is None:
            ch.responsavel_id = user.id
        _evento(ch, 'resolvido', user, texto)
        if _avisar([ch.solicitante_id], ch, f'Chamado resolvido: {ch.titulo}',
                   'Confira no local e confirme — ou reabra se não ficou bom.',
                   exceto=user.id):
            mensagem = 'Chamado marcado como resolvido. Quem pediu foi avisado para conferir.'

    elif acao == 'confirmar':
        ch.status = FECHADO
        ch.fechado_em = agora
        _evento(ch, 'fechado', user, texto or 'Solução confirmada.')
        # O técnico fica sabendo que o serviço foi aceito — e que não volta.
        _avisar([ch.responsavel_id], ch, f'Chamado fechado: {ch.titulo}',
                f'{user.name} confirmou que ficou bom.', exceto=user.id)

    elif acao == 'reabrir':
        _exigir(texto, 'Diga o que ainda não ficou bom.', 400)
        ch.status = EM_ATENDIMENTO
        ch.resolvido_em = None
        _evento(ch, 'reaberto', user, texto)
        _avisar([ch.responsavel_id] if ch.responsavel_id else gestores_do_contrato(ch.client_id),
                ch, f'Chamado reaberto: {ch.titulo}', texto[:300], exceto=user.id)

    elif acao == 'cancelar':
        _exigir(texto, 'Diga por que o chamado está sendo cancelado.', 400)
        _retomar_relogio(ch, agora)
        ch.status = CANCELADO
        ch.cancelado_em = agora
        _evento(ch, 'cancelado', user, texto)
        _avisar([ch.solicitante_id, ch.responsavel_id], ch,
                f'Chamado cancelado: {ch.titulo}', texto[:300], exceto=user.id)

    else:  # pragma: no cover - acoes_disponiveis já barra
        raise RecusaChamado('Ação desconhecida.', 400)
    return Feito(mensagem, True, 'success')


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
    aguardando = sum(1 for c in abertos if c.status == AGUARDANDO)
    aguardando_conf = base.filter(Chamado.status == RESOLVIDO).count()
    desde = agora - timedelta(days=dias)
    resolvidos = base.filter(Chamado.resolvido_em.isnot(None),
                             Chamado.resolvido_em >= desde).all()
    no_prazo = [c for c in resolvidos if c.prazo is None or c.resolvido_em <= c.prazo]
    horas = [(c.resolvido_em - c.aberto_em).total_seconds() / 3600 for c in resolvidos]
    return {
        'em_aberto': len(abertos),
        'atrasados': len(atrasados),
        'aguardando': aguardando,
        'aguardando_confirmacao': aguardando_conf,
        'resolvidos': len(resolvidos),
        'pct_no_prazo': round(100.0 * len(no_prazo) / len(resolvidos), 1) if resolvidos else None,
        'horas_medias': round(sum(horas) / len(horas), 1) if horas else None,
        'dias': dias,
    }


# ── Avisos de prazo (Fase 5) ─────────────────────────────────────────────

ANTECEDENCIA_MAX = timedelta(hours=2)
ANTECEDENCIA_MIN = timedelta(minutes=30)
# Venceu há mais que isto (chamado antigo, agendador parado): marca como
# avisado sem disparar — senão o primeiro rodar despeja um aviso por chamado
# velho de uma vez.
VENCIDO_HA_MUITO = timedelta(hours=24)


def _antecedencia(ch):
    """Quanto antes avisar: um quarto do prazo, entre 30 min e 2 h."""
    total = (ch.prazo - ch.aberto_em) if ch.prazo and ch.aberto_em else ANTECEDENCIA_MAX
    return min(ANTECEDENCIA_MAX, max(ANTECEDENCIA_MIN, total / 4))


def avisar_prazos(agora=None):
    """Vence em breve: avisa quem atende. Venceu: avisa quem atende e a gestão.
    Cada aviso uma vez só; em "Aguardando" o relógio está parado (D8)."""
    from facilities import tempo
    from facilities.core import push
    from facilities.chamados.models import STATUS_CONTA_PRAZO
    agora = agora or datetime.utcnow()
    n = 0
    for ch in Chamado.query.filter(Chamado.status.in_(STATUS_CONTA_PRAZO),
                                   Chamado.prazo.isnot(None),
                                   Chamado.aviso_vencido_em.is_(None)).all():
        link = f'/chamados/{ch.id}'
        quem = {ch.responsavel_id} if ch.responsavel_id else gestores_do_contrato(ch.client_id)
        if agora - ch.prazo > VENCIDO_HA_MUITO:
            ch.aviso_vencido_em = agora
            ch.aviso_vencendo_em = ch.aviso_vencendo_em or agora
        elif agora > ch.prazo:
            todos = quem | gestores_do_contrato(ch.client_id)
            # O push vai só a quem o sino aceitou (ativo, com o local na carteira).
            avisados = _avisar(todos, ch, f'Prazo vencido: {ch.titulo}',
                               f'{ch.numero} venceu às {tempo.fmt(ch.prazo, "%d/%m %H:%M")}.')
            push.avisar(avisados, f'Prazo vencido: {ch.numero}', ch.titulo, link,
                        marca=f'prazo-{ch.id}')
            ch.aviso_vencido_em = agora
            ch.aviso_vencendo_em = ch.aviso_vencendo_em or agora
            n += 1
        elif ch.aviso_vencendo_em is None and ch.prazo - agora <= _antecedencia(ch):
            avisados = _avisar(quem, ch, f'Vence às {tempo.fmt(ch.prazo, "%H:%M")}: {ch.titulo}',
                               f'{ch.numero} · prioridade {ch.prioridade_rotulo.lower()}.')
            push.avisar(avisados, f'Vence às {tempo.fmt(ch.prazo, "%H:%M")}: {ch.numero}',
                        ch.titulo, link, marca=f'prazo-{ch.id}')
            ch.aviso_vencendo_em = agora
            n += 1
    return n
