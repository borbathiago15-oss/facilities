"""Portal do cliente (Fase 9B): o que o cliente vê e a cobrança.

O que o cliente VÊ (F9-1): os indicadores do local (a mesma nota do painel),
os chamados (situação, prazo, solução e fotos) e as fotos dos checklists.
NÃO vê custo, material, comentário interno nem a trilha do chamado. Quem fez
o checklist aparece pela função; o nome só com o interruptor do cliente
ligado (R5 — depois do aval do jurídico, D25).

Tudo atrás de ``CLIENTE_EXTERNO_LIBERADO`` (padrão desligado): até o jurídico
entregar o Grupo C, a conta de cliente continua sem entrar.
"""
from datetime import datetime, time, timedelta

from flask import current_app

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import Client
from facilities.portal.models import (ABERTA, EVENTO_ABERTA, EVENTO_CONFIRMADA,
                                      EVENTO_REABERTA, EVENTO_RESPOSTA, FECHADA, RESPONDIDA,
                                      Cobranca, CobrancaEvento)

PERFIL_CLIENTE = 'cliente'
ANTECEDENCIA_MINIMA = timedelta(hours=24)
TITULO_MAX = 200
TEXTO_MAX = 4000
# Até onde o cliente pode marcar a data (evita um prazo para 2099).
PRAZO_MAXIMO = timedelta(days=180)
DIAS_DOS_CHAMADOS = 90
DIAS_DOS_CHECKLISTS = 30
EXECUCOES_NA_TELA = 60
COORDENACAO = 'Coordenação'


class RegraDaCobranca(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def liberado(app=None):
    return bool((app or current_app).config.get('CLIENTE_EXTERNO_LIBERADO'))


def e_cliente(user):
    return user._effective_role() == PERFIL_CLIENTE


def locais_do_cliente(user):
    """Os locais ATIVOS do cliente (contratante) da conta — a carteira dele."""
    if not user.cliente_id:
        return []
    return (Client.query.filter(Client.contratante_id == user.cliente_id,
                                Client.is_active.is_(True), Client.is_deleted.is_(False))
            .order_by(Client.name).all())


# ── O prazo que o cliente escolhe ─────────────────────────────────────────

def prazo_minimo(agora=None):
    """A primeira data que o cliente pode escolher (o fim dela fica ≥ 24 h)."""
    agora = agora or datetime.utcnow()
    dia = tempo.local(agora + ANTECEDENCIA_MINIMA).date()
    if tempo.para_utc(dia, time(23, 59)) < agora + ANTECEDENCIA_MINIMA:
        dia += timedelta(days=1)
    return dia


def prazo_escolhido(bruto, agora=None):
    """``AAAA-MM-DD`` → o fim daquele dia em Brasília, em UTC."""
    agora = agora or datetime.utcnow()
    try:
        dia = datetime.strptime((bruto or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        raise RegraDaCobranca('Escolha a data em que quer a resposta.')
    minimo = prazo_minimo(agora)
    if dia < minimo:
        raise RegraDaCobranca('A coordenação precisa de pelo menos 24 horas: escolha uma data '
                              f'a partir de {minimo.strftime("%d/%m/%Y")}.')
    if dia > tempo.local(agora + PRAZO_MAXIMO).date():
        raise RegraDaCobranca('Escolha uma data dentro dos próximos 6 meses.')
    return tempo.para_utc(dia, time(23, 59))


def _texto(form, campo, maximo, obrigatorio):
    valor = (form.get(campo) or '').strip()
    if obrigatorio and not valor:
        raise RegraDaCobranca(obrigatorio)
    if len(valor) > maximo:
        raise RegraDaCobranca(f'Texto longo demais (até {maximo} caracteres).')
    return valor


# ── Quem responde ─────────────────────────────────────────────────────────

def coordenacao_do_local(client_id):
    """Quem recebe a cobrança: os gestores do contrato (a mesma conta dos
    avisos de chamado) e o gerente responsável pelo cliente."""
    from facilities.chamados.servico import gestores_do_contrato
    ids = set(gestores_do_contrato(client_id))
    loc = db.session.get(Client, client_id)
    ger = loc.contratante.gerente if loc is not None and loc.contratante else None
    if ger is not None and ger.is_active and not ger.is_deleted and ger.role == 'gerente':
        ids.add(ger.id)
    return ids


def pode_responder(user, cob):
    from facilities.core.acesso import allowed_client_ids_or_none
    if not user.e_gestao():
        return False
    ids = allowed_client_ids_or_none(user)
    return ids is None or cob.client_id in ids


def _avisar_coordenacao(cob, titulo, texto):
    from facilities.core import push
    from facilities.core.rotas import avisar
    ids = coordenacao_do_local(cob.client_id)
    link = f'/cobrancas/{cob.id}'
    avisar(ids, f'{cob.numero} · {titulo}', texto, link=link, tipo='cobranca')
    push.avisar(ids, f'{titulo} — {cob.local.name}', cob.titulo, link=link,
                marca=f'cobranca-{cob.id}')
    return ids


def _avisar_cliente(cob, titulo, texto):
    from facilities.core.rotas import avisar
    autor = cob.autor
    if autor is None or not autor.is_active or autor.is_deleted:
        return set()
    avisar({autor.id}, f'{cob.numero} · {titulo}', texto, link=f'/cliente/cobrancas/{cob.id}',
           tipo='cobranca')
    return {autor.id}


def _evento(cob, tipo, autor, texto=None, agora=None):
    db.session.add(CobrancaEvento(cobranca=cob, tipo=tipo, texto=texto or None,
                                  prazo=cob.prazo, autor_id=autor.id,
                                  created_at=agora or datetime.utcnow()))


def _travar(cob):
    """Uma resposta (ou confirmação) por vez: dois cliques não gravam duas."""
    return db.session.execute(db.select(Cobranca).where(Cobranca.id == cob.id)
                              .with_for_update().execution_options(populate_existing=True)
                              ).scalar_one()


# ── O ciclo ───────────────────────────────────────────────────────────────

def abrir(user, form, agora=None):
    agora = agora or datetime.utcnow()
    if not e_cliente(user):
        raise RegraDaCobranca('A cobrança é aberta pelo cliente.', 403)
    try:
        cid = int(form.get('client_id') or 0)
    except (TypeError, ValueError):
        cid = 0
    loc = next((c for c in locais_do_cliente(user) if c.id == cid), None)
    if loc is None:
        raise RegraDaCobranca('Escolha um dos seus locais.')
    titulo = _texto(form, 'titulo', TITULO_MAX, 'Diga em poucas palavras o que está cobrando.')
    texto = _texto(form, 'texto', TEXTO_MAX, 'Descreva o que precisa ser feito.')
    cob = Cobranca(client_id=loc.id, titulo=titulo, texto=texto, autor_id=user.id,
                   prazo=prazo_escolhido(form.get('prazo'), agora), status=ABERTA,
                   criada_em=agora)
    cob.local = loc
    db.session.add(cob)
    db.session.flush()
    _evento(cob, EVENTO_ABERTA, user, texto, agora)
    _avisar_coordenacao(cob, 'Cobrança do cliente',
                        f'{user.name} pediu: {titulo}. Prazo: {tempo.fmt(cob.prazo, "%d/%m/%Y")}.')
    return cob


def responder(user, cob, form, agora=None):
    agora = agora or datetime.utcnow()
    if not pode_responder(user, cob):
        raise RegraDaCobranca('Quem responde a cobrança é a coordenação do contrato.', 403)
    cob = _travar(cob)
    if cob.status != ABERTA:
        raise RegraDaCobranca('Esta cobrança já foi respondida. Espere o cliente confirmar '
                              'ou reabrir.', 409)
    texto = _texto(form, 'texto', TEXTO_MAX, 'Escreva a resposta para o cliente.')
    cob.status = RESPONDIDA
    cob.respondida_em = agora
    _evento(cob, EVENTO_RESPOSTA, user, texto, agora)
    _avisar_cliente(cob, 'A coordenação respondeu',
                    'Veja a resposta e confirme se ficou bom, ou reabra.')
    return cob


def _do_cliente(user, cob):
    if not e_cliente(user) or cob.client_id not in {c.id for c in locais_do_cliente(user)}:
        raise RegraDaCobranca('Só o cliente encerra ou reabre a cobrança.', 403)


def confirmar(user, cob, form, agora=None):
    agora = agora or datetime.utcnow()
    _do_cliente(user, cob)
    cob = _travar(cob)
    if cob.status != RESPONDIDA:
        raise RegraDaCobranca('Só dá para confirmar depois da resposta da coordenação.', 409)
    cob.status = FECHADA
    cob.fechada_em = agora
    _evento(cob, EVENTO_CONFIRMADA, user, _texto(form, 'texto', TEXTO_MAX, None), agora)
    _avisar_coordenacao(cob, 'Cliente confirmou', f'{cob.titulo}: encerrada pelo cliente.')
    return cob


def reabrir(user, cob, form, agora=None):
    agora = agora or datetime.utcnow()
    _do_cliente(user, cob)
    cob = _travar(cob)
    if cob.status != RESPONDIDA:
        raise RegraDaCobranca('Só dá para reabrir depois da resposta da coordenação.', 409)
    texto = _texto(form, 'texto', TEXTO_MAX, 'Diga o que ainda não ficou bom.')
    cob.prazo = prazo_escolhido(form.get('prazo'), agora)
    cob.status = ABERTA
    cob.respondida_em = None
    cob.reaberturas = (cob.reaberturas or 0) + 1
    _evento(cob, EVENTO_REABERTA, user, texto, agora)
    _avisar_coordenacao(cob, 'Cliente reabriu',
                        f'{cob.titulo}: não ficou bom. Novo prazo: '
                        f'{tempo.fmt(cob.prazo, "%d/%m/%Y")}.')
    return cob


def em_aberto(client_ids):
    """As cobranças que esperam a coordenação (a fila de Demandas)."""
    q = Cobranca.query.filter(Cobranca.status == ABERTA)
    if client_ids is not None:
        q = q.filter(Cobranca.client_id.in_(client_ids or [-1]))
    return q.order_by(Cobranca.prazo).all()


def autor_para_o_cliente(evento):
    """O cliente vê o nome de quem é do cliente; da nossa equipe, "Coordenação"."""
    a = evento.autor
    if a is not None and a._effective_role() == PERFIL_CLIENTE:
        return a.name
    return COORDENACAO


# ── O que o cliente vê ────────────────────────────────────────────────────

def chamados_do_local(client_id, agora=None):
    """Os em aberto e os abertos nos últimos 90 dias."""
    from facilities.chamados.models import STATUS_EM_ABERTO, Chamado
    agora = agora or datetime.utcnow()
    corte = agora - timedelta(days=DIAS_DOS_CHAMADOS)
    return (Chamado.query.filter(Chamado.client_id == client_id,
                                 db.or_(Chamado.status.in_(STATUS_EM_ABERTO),
                                        Chamado.aberto_em >= corte))
            .order_by(Chamado.aberto_em.desc()).limit(200).all())


def fotos_do_chamado(ch):
    """Só imagem: PDF anexado pode ser orçamento ou nota (custo)."""
    return [a for a in ch.anexos if (a.mime or '').startswith('image/')]


def execucoes_do_local(client_id, agora=None):
    from facilities.rotas.models import Execucao
    agora = agora or datetime.utcnow()
    corte = agora - timedelta(days=DIAS_DOS_CHECKLISTS)
    return (Execucao.query.filter(Execucao.client_id == client_id,
                                  Execucao.concluida_em >= corte)
            .order_by(Execucao.concluida_em.desc()).limit(EXECUCOES_NA_TELA).all())


def visitas_do_local(client_id, agora=None):
    """Fase 10: as visitas de supervisão FEITAS nos últimos 30 dias."""
    from facilities.visitas.models import FEITA, Visita
    agora = agora or datetime.utcnow()
    corte = agora - timedelta(days=DIAS_DOS_CHECKLISTS)
    return (Visita.query.filter(Visita.client_id == client_id, Visita.status == FEITA,
                                Visita.feita_em >= corte)
            .order_by(Visita.feita_em.desc()).limit(EXECUCOES_NA_TELA).all())


def quem_fez(registro, local):
    """R5: a função; o nome só com o interruptor do cliente ligado. Serve à
    execução do checklist (``pessoa``) e à visita (``quem_fez``)."""
    pessoa = getattr(registro, 'pessoa', None) or getattr(registro, 'quem_fez', None)
    if pessoa is None:
        return '—'
    c = local.contratante
    if c is not None and c.mostrar_nome_executor:
        return pessoa.name
    return pessoa.perfil_rotulo


def local_do_cliente(user, cid):
    return next((c for c in locais_do_cliente(user) if c.id == cid), None)


def cobrancas_do_cliente(user):
    ids = [c.id for c in locais_do_cliente(user)] or [-1]
    return (Cobranca.query.filter(Cobranca.client_id.in_(ids))
            .order_by(Cobranca.status != RESPONDIDA, Cobranca.status == FECHADA,
                      Cobranca.criada_em.desc()).limit(200).all())
