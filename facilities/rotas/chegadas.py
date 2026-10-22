"""Chegada no local (bloco do técnico, decisões do dono de 22/10/2026).

* O local pode ter UM ponto marcado como ENTRADA (``PontoInspecao.
  entrada_do_local``). Quem está no posto lê esse QR ao chegar: fica a
  ``Chegada`` do dia (pessoa, local, dia local). Ler de novo no mesmo dia
  devolve a mesma, sem duplicar.
* Com entrada cadastrada, nenhum checklist do local é aceito no dia sem a
  chegada (``servico.registrar_execucao``). Local SEM entrada segue como
  antes: sem exigência.
* O QR da entrada não pôde ser lido (etiqueta rasgada, celular sem câmera)?
  A gestão LIBERA a chegada da pessoa no dia (``liberar``), marcada
  ``com_camera=False`` e com quem liberou.

O commit é sempre de quem chama.
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from facilities import tempo
from facilities.extensions import db
from facilities.cadastros.servico import ponto_de_entrada
from facilities.rotas.models import Chegada


def _regra(mensagem, codigo=400, **extra):
    from facilities.rotas.servico import RegraDaRota
    return RegraDaRota(mensagem, codigo, **extra)


def _carteira(user, client_id):
    from facilities.core.acesso import allowed_client_ids_or_none
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and client_id not in permitidos:
        raise _regra('Este local não está entre os seus.', 403)


def de_hoje(user, client_id, agora_utc=None):
    """A chegada da pessoa neste local no dia LOCAL de ``agora_utc`` (ou None)."""
    dia = tempo.local(agora_utc or datetime.utcnow()).date()
    return no_dia(user, client_id, dia)


def no_dia(user, client_id, dia):
    uid = user if isinstance(user, int) else user.id
    return Chegada.query.filter_by(user_id=uid, client_id=client_id, data=dia).first()


def exige_chegada(client_id):
    """O local tem ponto de entrada ativo? Então o checklist exige a chegada."""
    return ponto_de_entrada(client_id) is not None


def _gravar(user_id, ponto, dia, chegou_em, com_camera, liberada_por=None):
    """Insere a chegada do dia; se já existe (ou outra leitura entrou ao
    mesmo tempo), devolve a existente. → (chegada, nova)"""
    ja = no_dia(user_id, ponto.client_id, dia)
    if ja is not None:
        return ja, False
    c = Chegada(user_id=user_id, client_id=ponto.client_id, ponto_id=ponto.id, data=dia,
                chegou_em=chegou_em, com_camera=com_camera, liberada_por=liberada_por)
    try:
        with db.session.begin_nested():
            db.session.add(c)
    except IntegrityError:
        ja = no_dia(user_id, ponto.client_id, dia)
        if ja is None:
            raise
        return ja, False
    return c, True


def registrar(user, ponto, agora_utc=None, com_camera=True):
    """A pessoa leu o QR da entrada. → (chegada, nova)

    ``agora_utc`` é a hora da leitura (o selo do servidor, quando houver).
    """
    from facilities.rotas.servico import PERFIS_QUE_EXECUTAM
    agora_utc = agora_utc or datetime.utcnow()
    if ponto is None or not ponto.is_active:
        raise _regra('QR não reconhecido. Leia a etiqueta da entrada de novo.', 404)
    if not ponto.entrada_do_local:
        raise _regra('Este QR não é o da entrada do local. Leia a etiqueta da entrada '
                     'para confirmar a chegada.', 409, codigo_app='nao_e_entrada')
    _carteira(user, ponto.client_id)
    if user._effective_role() not in PERFIS_QUE_EXECUTAM:
        raise _regra('Seu perfil não registra chegada.', 403)
    dia = tempo.local(agora_utc).date()
    return _gravar(user.id, ponto, dia, agora_utc, bool(com_camera))


def liberar(gestor, user, local, dia=None, agora_utc=None):
    """A gestão libera a chegada de ``user`` em ``local`` no ``dia`` (padrão
    hoje) sem a leitura do QR. → (chegada, nova)"""
    from facilities.core.models import User
    agora_utc = agora_utc or datetime.utcnow()
    if not gestor.e_gestao():
        raise _regra('Só a gestão libera a chegada.', 403)
    _carteira(gestor, local.id)
    if isinstance(user, int):
        user = db.session.get(User, user)
    if user is None or not user.is_active or user.is_deleted:
        raise _regra('Escolha uma pessoa ativa.')
    try:
        _carteira(user, local.id)
    except Exception:
        raise _regra('Esta pessoa não trabalha neste local.')
    ponto = ponto_de_entrada(local.id)
    if ponto is None:
        raise _regra('Este local não tem ponto de entrada: a chegada não é exigida aqui.', 409)
    dia = dia or tempo.local(agora_utc).date()
    return _gravar(user.id, ponto, dia, agora_utc, False, liberada_por=gestor.id)


def do_dia(client_id, dia):
    """As chegadas do local no dia (para a tela da gestão)."""
    return (Chegada.query.filter_by(client_id=client_id, data=dia)
            .order_by(Chegada.chegou_em).all())
