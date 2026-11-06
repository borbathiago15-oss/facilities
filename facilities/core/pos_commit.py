"""O que só pode acontecer DEPOIS que o banco gravou (auditoria, Fase 4, L2).

Dois casos na casa:

* **avisos para fora** (push no celular): só saem quando a gravação vingou
  (commit). Saíam no meio da transação, com a trava do local segura — o
  serviço de push lento fazia todo chamado do mesmo local esperar, e uma
  falha no envio desfazia o chamado; e o aviso de um chamado que depois era
  desfeito chegava assim mesmo;
* **arquivos já enviados** ao armazenamento (fotos): se a gravação da linha
  for desfeita, o arquivo é apagado — nenhum arquivo sobrando, nenhuma linha
  apontando para o nada.

Como funciona: ``depois_de_gravar(acao, se_desfeito)`` prende o par à
transação aberta (ou à próxima, se não houver nenhuma). Quando a transação
de fora termina com commit, ``acao()`` roda; desfeita, roda ``se_desfeito()``.
Ponto de salvamento (``begin_nested``) desfeito leva junto o que foi preso
dentro dele; confirmado, passa para a transação de cima.

As duas funções rodam DEPOIS que a conexão já voltou ao pool, dentro do
``commit()`` de quem chamou: não podem usar ``db.session`` (o que precisarem
gravar, gravam numa conexão própria, ``db.engine.begin()``). Qualquer erro
delas vira log — nunca desfaz nem impede o que já foi gravado.
"""
import logging

from flask_sqlalchemy.session import Session
from sqlalchemy import event

log = logging.getLogger(__name__)

_CHAVE = 'facilities_pos_commit'


def _estado(sessao):
    return sessao.info.setdefault(_CHAVE, {'itens': [], 'confirmadas': set(),
                                           'escreveu': False})


def _sessao():
    from facilities.extensions import db
    return db.session()


def depois_de_gravar(acao, se_desfeito=None):
    """Prende ``acao`` (e ``se_desfeito``) à transação atual da sessão."""
    s = _sessao()
    alvo = s.get_nested_transaction() or s.get_transaction()
    _estado(s)['itens'].append([alvo, acao, se_desfeito])


def tem_escrita_pendente(sessao=None):
    """Há algo nesta transação que ainda não foi gravado (ou foi enviado ao
    banco e não confirmado)?"""
    s = sessao or _sessao()
    return bool(s.new or s.dirty or s.deleted or _estado(s)['escreveu'])


def soltar_conexao():
    """Termina a transação de SÓ LEITURA aberta pela checagem de acesso, para
    a conexão voltar ao pool enquanto a requisição espera um serviço de fora
    (subir uma foto). Com escrita pendente, não faz nada (o commit é de quem
    chama). Cuidado: um ``FOR UPDATE`` já tomado cairia aqui — chame ANTES de
    travar a linha. → True se soltou."""
    s = _sessao()
    if not s.in_transaction() or tem_escrita_pendente(s):
        return False
    s.commit()
    return True


def _rodar(funcao, nome):
    if funcao is None:
        return
    try:
        funcao()
    except Exception:                        # noqa: BLE001 — nunca desfaz o que foi gravado
        log.exception('pos_commit: %s falhou (o que foi gravado continua gravado)', nome)


@event.listens_for(Session, 'after_flush')
def _escreveu(sessao, _contexto):
    _estado(sessao)['escreveu'] = True


@event.listens_for(Session, 'after_commit')
def _confirmada(sessao):
    # Aqui a transação que confirma ainda é a "atual": a aninhada, se houver;
    # senão a de fora.
    alvo = sessao.get_nested_transaction() or sessao.get_transaction()
    if alvo is not None:
        _estado(sessao)['confirmadas'].add(id(alvo))


@event.listens_for(Session, 'after_transaction_end')
def _terminou(sessao, transacao):
    est = sessao.info.get(_CHAVE)
    if est is None:
        return
    confirmada = id(transacao) in est['confirmadas']
    est['confirmadas'].discard(id(transacao))
    if transacao.parent is not None:
        # Ponto de salvamento (ou subtransação): confirmado passa para a de
        # cima; desfeito leva junto o que estava preso a ele.
        if transacao.nested and not confirmada:
            ficam = []
            for item in est['itens']:
                if item[0] is transacao:
                    _rodar(item[2], 'desfazer')
                else:
                    ficam.append(item)
            est['itens'] = ficam
        else:
            for item in est['itens']:
                if item[0] is transacao:
                    item[0] = transacao.parent
        return
    # A transação de fora terminou: o que era dela (ou de nenhuma, preso
    # antes de ela começar) roda agora.
    meus = [i for i in est['itens'] if i[0] is transacao or i[0] is None]
    est['itens'] = [i for i in est['itens'] if not (i[0] is transacao or i[0] is None)]
    est['escreveu'] = False
    for _alvo, acao, se_desfeito in meus:
        if confirmada:
            _rodar(acao, 'acao')
        else:
            _rodar(se_desfeito, 'desfazer')


def descartar_pendentes(sessao):
    """Fim da requisição sem transação nenhuma aberta: o que foi preso "para
    a próxima" não vai ter próxima — desfaz (apaga os arquivos)."""
    est = sessao.info.get(_CHAVE)
    if not est or sessao.in_transaction():
        return
    sobra = [i for i in est['itens'] if i[0] is None]
    est['itens'] = [i for i in est['itens'] if i[0] is not None]
    for _alvo, _acao, se_desfeito in sobra:
        _rodar(se_desfeito, 'desfazer')
