"""Ocorrência do QR público (D47; Q1 a Q3).

* Qualquer pessoa no local lê o QR do banheiro e abre uma reclamação ou
  ocorrência, SEM login: tipo da lista, texto curto e foto opcional. Não se
  pede nem se guarda dado de quem abriu.
* Vira pendência para quem está na rota daquele ponto no turno (escalado
  numa tarefa de hoje ainda em aberto) e alerta o supervisor; sem ninguém
  escalado, alerta o supervisor e o coordenador do local (Q1).
* Prazo por tipo, configurável por cliente; sem valor configurado, fica
  sem prazo (Q2: o valor padrão é decisão do proprietário).
* Quem abriu acompanha pelo link com o código de acompanhamento (Q3).
"""
import json
import secrets
import uuid
from datetime import datetime, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.rotas.models import (OCORRENCIA_ABERTA, OCORRENCIA_EM_ATENDIMENTO,
                                     OCORRENCIA_RESOLVIDA, PREVISTA, TIPOS_OCORRENCIA_PUBLICA,
                                     OcorrenciaPublica, TarefaDia)

TEXTO_MAX = 300
FOTO_MAX = 8 * 1024 * 1024


def prazo_minutos(ponto, tipo):
    cli = ponto.ambiente.setor.local.contratante if ponto.ambiente else None
    if cli is None or not cli.prazos_ocorrencia_json:
        return None
    try:
        valor = json.loads(cli.prazos_ocorrencia_json).get(tipo)
        return int(valor) if valor else None
    except (ValueError, TypeError, AttributeError):
        return None


def _destinatarios(ponto, agora_utc):
    """(quem está na rota agora, quem acompanha) — Q1."""
    from facilities.core.hierarquia import carteira
    from facilities.core.models import User
    hoje = tempo.local(agora_utc).date()
    na_rota = {t.user_id for t in TarefaDia.query.filter(
        TarefaDia.ponto_id == ponto.id, TarefaDia.status == PREVISTA,
        TarefaDia.data.in_([hoje, hoje - timedelta(days=1)]),
        TarefaDia.fim_do_turno >= agora_utc, TarefaDia.user_id.isnot(None))}
    papeis = ('supervisor',) if na_rota else ('supervisor', 'pleno')
    acompanham = set()
    for u in User.query.filter(User.role.in_(papeis), User.is_active.is_(True),
                               User.is_deleted.is_(False)):
        cart = carteira(u)
        if cart is not None and ponto.client_id in cart:
            acompanham.add(u.id)
    return na_rota, acompanham


def abrir(ponto, tipo, texto, foto=None, agora_utc=None):
    from facilities.core import push
    from facilities.core.rotas import avisar as avisar_no_sino
    from facilities.rotas.servico import RegraDaRota
    agora_utc = agora_utc or datetime.utcnow()
    if not ponto.is_active:
        raise RegraDaRota('Este ponto não recebe mais ocorrências.', 409)
    if tipo not in TIPOS_OCORRENCIA_PUBLICA:
        raise RegraDaRota('Escolha o que está acontecendo.')
    texto = (texto or '').strip()[:TEXTO_MAX] or None
    if tipo == 'outro' and not texto:
        raise RegraDaRota('Conte em poucas palavras o que está acontecendo.')
    oc = OcorrenciaPublica(ponto_id=ponto.id, client_id=ponto.client_id, tipo=tipo, texto=texto,
                           token=secrets.token_urlsafe(16), criada_em=agora_utc,
                           status=OCORRENCIA_ABERTA)
    minutos = prazo_minutos(ponto, tipo)
    if minutos:
        oc.prazo = agora_utc + timedelta(minutes=minutos)
    if foto is not None and getattr(foto, 'filename', ''):
        _guardar_foto(oc, foto)
    db.session.add(oc)
    db.session.flush()
    na_rota, acompanham = _destinatarios(ponto, agora_utc)
    titulo = f'Ocorrência: {TIPOS_OCORRENCIA_PUBLICA[tipo]}'
    onde = f'{ponto.ambiente.nome} · {ponto.nome}'
    link_campo = f'/app/turno?ponto={ponto.codigo_qr}'
    link_gestao = f'/rotas/locais/{ponto.client_id}/dia'
    if na_rota:
        avisar_no_sino(na_rota, titulo, onde, link_campo, tipo='ocorrencia')
        push.avisar(na_rota, titulo, onde, link_campo, marca=f'ocorrencia-{oc.id}')
    so_gestao = acompanham - na_rota
    avisar_no_sino(so_gestao, titulo, onde, link_gestao, tipo='ocorrencia')
    push.avisar(so_gestao, titulo, onde, link_gestao, marca=f'ocorrencia-{oc.id}')
    return oc


def _guardar_foto(oc, foto):
    from facilities.core.anexos import ANEXO_ASSINATURA, ANEXO_TIPOS, storage
    from facilities.rotas.servico import RegraDaRota
    nome = (foto.filename or '').lower()
    ext = nome.rsplit('.', 1)[-1] if '.' in nome else 'jpg'
    ext = 'jpg' if ext == 'jpeg' else ext
    dados = foto.read(FOTO_MAX + 1)
    if not dados:
        return
    if ext not in ('jpg', 'png', 'webp') or len(dados) > FOTO_MAX or \
            not any(dados.startswith(a) for a in ANEXO_ASSINATURA[ext]):
        raise RegraDaRota('A foto não foi aceita (formato ou tamanho). Envie sem foto ou '
                          'tire outra.')
    oc.foto_key = f'ocorrencias/{uuid.uuid4().hex}.{ext}'
    oc.foto_mime = ANEXO_TIPOS[ext]
    storage().save(oc.foto_key, dados, oc.foto_mime)


def atender(oc, user, agora_utc=None):
    from facilities.rotas.servico import RegraDaRota
    if oc.status == OCORRENCIA_RESOLVIDA:
        raise RegraDaRota('Esta ocorrência já foi resolvida.', 409)
    if oc.status == OCORRENCIA_ABERTA:
        oc.status = OCORRENCIA_EM_ATENDIMENTO
        oc.atendida_por = user.id
        oc.atendida_em = agora_utc or datetime.utcnow()
    return oc


def resolver(oc, user, resolucao='', agora_utc=None):
    from facilities.rotas.servico import RegraDaRota
    if oc.status == OCORRENCIA_RESOLVIDA:
        raise RegraDaRota('Esta ocorrência já foi resolvida.', 409)
    agora_utc = agora_utc or datetime.utcnow()
    if oc.status == OCORRENCIA_ABERTA:
        oc.atendida_por, oc.atendida_em = user.id, agora_utc
    oc.status = OCORRENCIA_RESOLVIDA
    oc.resolvida_por, oc.resolvida_em = user.id, agora_utc
    oc.resolucao = (resolucao or '').strip()[:300] or None
    return oc


def abertas(client_ids):
    return (OcorrenciaPublica.query
            .filter(OcorrenciaPublica.client_id.in_(list(client_ids) or [-1]),
                    OcorrenciaPublica.status != OCORRENCIA_RESOLVIDA)
            .order_by(OcorrenciaPublica.criada_em).all())


def atrasada(oc, agora_utc=None):
    return bool(oc.prazo and oc.status != OCORRENCIA_RESOLVIDA
                and (agora_utc or datetime.utcnow()) > oc.prazo)
