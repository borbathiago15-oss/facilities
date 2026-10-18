"""Confirmação de presença em horário aleatório (D48, Q4).

* Cada rota diz quantas por turno (padrão 2; 0 desliga) e o prazo para
  responder (padrão 10 min).
* Os horários são sorteados dentro do turno, longe do começo e do fim
  (30 min de folga), para quem está ESCALADO naquele dia. O sorteio usa uma
  semente fixa (rota, dia, pessoa): rodar o agendador de novo dá os mesmos
  horários — não duplica.
* Chegou a hora: aviso no celular e no sino. Respondeu no prazo: confirmada
  (hora do servidor). Passou do prazo: "sem resposta", e o superior direto da
  pessoa (ou o supervisor do local) recebe o alerta.

ATENÇÃO (risco registrado em DECISOES v8): o registro serve à ROTINA, não
ao ponto eletrônico. Validar com RH e jurídico antes do piloto, e constar
no aviso de privacidade aos colaboradores.
"""
import random
from datetime import datetime, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.rotas.models import (PRESENCA_CONFIRMADA, PRESENCA_NAO_ENVIADA,
                                     PRESENCA_PENDENTE, PRESENCA_SEM_RESPOSTA,
                                     ConfirmacaoPresenca, Rota)

FOLGA = timedelta(minutes=30)


def horarios_sorteados(rota, dia, user_id):
    """Os instantes (horas locais) dos pedidos do turno de ``dia``."""
    from facilities.rotas.servico import _janela
    n = rota.presencas_por_turno or 0
    if n <= 0:
        return []
    ini, fim = _janela(rota, dia)
    prazo = timedelta(minutes=rota.presenca_prazo_min or 10)
    de, ate = ini + FOLGA, fim - FOLGA - prazo
    if ate <= de:
        return []
    sorteio = random.Random(f'{rota.id}:{dia.isoformat()}:{user_id}')
    minutos = int((ate - de).total_seconds() // 60)
    # Divide o turno em n faixas e sorteia um minuto em cada: os pedidos não
    # caem todos juntos.
    faixa = max(1, minutos // n)
    return [de + timedelta(minutes=i * faixa + sorteio.randrange(faixa)) for i in range(n)]


def gerar(rota, dia, user_id, agora_utc=None):
    """Cria os pedidos do dia. Horário que JÁ PASSOU não vira pedido (rota
    criada ou cobertura lançada no meio do turno): ninguém pode responder a um
    pedido que nunca chegou."""
    if not user_id:
        return 0
    agora_utc = agora_utc or datetime.utcnow()
    criados = 0
    existentes = {c.pedido_em for c in ConfirmacaoPresenca.query.filter_by(
        rota_id=rota.id, user_id=user_id, data=dia)}
    prazo = timedelta(minutes=rota.presenca_prazo_min or 10)
    for m in horarios_sorteados(rota, dia, user_id):
        pedido = tempo.para_utc(m.date(), m.time())
        if pedido in existentes or pedido < agora_utc:
            continue
        db.session.add(ConfirmacaoPresenca(rota_id=rota.id, client_id=rota.client_id,
                                           user_id=user_id, data=dia, pedido_em=pedido,
                                           prazo_ate=pedido + prazo))
        criados += 1
    return criados


def _quem_alertar(c):
    """O superior direto; sem ele, os supervisores (e coordenadores) do local."""
    from facilities.core.hierarquia import carteira
    from facilities.core.models import User
    if c.pessoa and c.pessoa.superior_id and c.pessoa.superior.is_active:
        return [c.pessoa.superior_id]
    ids = []
    for u in User.query.filter(User.role.in_(('supervisor', 'pleno')), User.is_active.is_(True),
                               User.is_deleted.is_(False)):
        cart = carteira(u)
        if cart is not None and c.client_id in cart:
            ids.append(u.id)
    return ids


def avisar_e_fechar(agora_utc):
    """A parte do agendador: avisa o que chegou a hora; fecha o que venceu."""
    from facilities.core import push
    from facilities.core.rotas import avisar as avisar_no_sino
    avisados = fechados = 0
    for c in ConfirmacaoPresenca.query.filter(
            ConfirmacaoPresenca.status == PRESENCA_PENDENTE,
            ConfirmacaoPresenca.avisado_em.is_(None),
            ConfirmacaoPresenca.pedido_em <= agora_utc,
            ConfirmacaoPresenca.prazo_ate >= agora_utc).all():
        link = f'/app/?presenca={c.id}'
        quem = avisar_no_sino([c.user_id], 'Confirme que você está no posto',
                              f'Toque para confirmar até {tempo.fmt(c.prazo_ate, "%H:%M")}.',
                              link, tipo='presenca', client_id=c.client_id)
        push.avisar(quem, 'Confirme que você está no posto',
                    f'Toque para confirmar até {tempo.fmt(c.prazo_ate, "%H:%M")}.', link,
                    marca=f'presenca-{c.id}')
        c.avisado_em = agora_utc
        avisados += 1
    for c in ConfirmacaoPresenca.query.filter(
            ConfirmacaoPresenca.status == PRESENCA_PENDENTE,
            ConfirmacaoPresenca.prazo_ate < agora_utc).all():
        if c.avisado_em is None:
            # O agendador atrasou e o pedido nunca saiu: não há falta de
            # resposta de ninguém (risco trabalhista — análise de 18/10/2026).
            c.status = PRESENCA_NAO_ENVIADA
            fechados += 1
            continue
        c.status = PRESENCA_SEM_RESPOSTA
        if not c.supervisor_avisado:
            quem = _quem_alertar(c)
            texto = (f'{c.pessoa.name} não confirmou a presença das '
                     f'{tempo.fmt(c.pedido_em, "%H:%M")} ({c.rota.nome}).')
            quem = avisar_no_sino(quem, 'Presença sem resposta', texto,
                                  f'/rotas/locais/{c.client_id}/dia', tipo='presenca',
                                  client_id=c.client_id)
            push.avisar(quem, 'Presença sem resposta', texto,
                        f'/rotas/locais/{c.client_id}/dia', marca=f'sem-resposta-{c.id}')
            c.supervisor_avisado = True
        fechados += 1
    return avisados, fechados


def pendente_de(user, agora_utc=None):
    """O pedido em aberto da pessoa agora (ou None)."""
    agora_utc = agora_utc or datetime.utcnow()
    return (ConfirmacaoPresenca.query
            .filter(ConfirmacaoPresenca.user_id == user.id,
                    ConfirmacaoPresenca.status == PRESENCA_PENDENTE,
                    ConfirmacaoPresenca.pedido_em <= agora_utc,
                    ConfirmacaoPresenca.prazo_ate >= agora_utc)
            .order_by(ConfirmacaoPresenca.pedido_em).first())


def confirmar(c, user, agora_utc=None):
    """Confirma com a hora do SERVIDOR. Fora do prazo, fica registrado que
    respondeu tarde, mas continua "sem resposta"."""
    from facilities.rotas.servico import RegraDaRota
    agora_utc = agora_utc or datetime.utcnow()
    if c.user_id != user.id:
        raise RegraDaRota('Este pedido é de outra pessoa.', 403)
    if c.status == PRESENCA_CONFIRMADA:
        return c
    if agora_utc < c.pedido_em:
        raise RegraDaRota('Ainda não há pedido de presença agora.', 409)
    c.respondida_em = agora_utc
    if agora_utc <= c.prazo_ate and c.status == PRESENCA_PENDENTE:
        c.status = PRESENCA_CONFIRMADA
    return c


def da_rota_no_dia(client_id, dia):
    return (ConfirmacaoPresenca.query
            .filter(ConfirmacaoPresenca.client_id == client_id, ConfirmacaoPresenca.data == dia)
            .join(Rota).order_by(ConfirmacaoPresenca.pedido_em).all())
