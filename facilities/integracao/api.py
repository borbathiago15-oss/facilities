"""``/api/integracao/v1`` — só leitura, com chave de servidor (Fase 8).

    GET /api/integracao/v1/locais
    GET /api/integracao/v1/chamados?de=AAAA-MM-DD&ate=AAAA-MM-DD[&local=ID]
    GET /api/integracao/v1/aderencia?de=…&ate=…[&local=ID]
    GET /api/integracao/v1/nao-conformidades?de=…&ate=…[&local=ID]
    GET /api/integracao/v1/visitas?de=…&ate=…[&local=ID]
    GET /api/integracao/v1/nota?de=…&ate=…[&local=ID]

Cabeçalho: ``Authorization: Bearer fac_<prefixo>_<segredo>``. Cada chave só
lê os seus locais. Todo acesso fica registrado (sem a chave). Os números
são os MESMOS das telas (as funções são as mesmas). O corpo é determinístico
— a mesma consulta devolve o mesmo corpo; a hora da geração vai no
cabeçalho ``X-Gerado-Em``.
"""
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from facilities.extensions import db, limiter
from facilities.integracao import servico
from facilities.integracao.servico import RegraDaIntegracao

bp = Blueprint('integracao_api', __name__, url_prefix='/api/integracao/v1')


def _chave_validada():
    """A chave do cabeçalho, validada UMA vez por pedido (o limite e a
    resposta usam a mesma)."""
    if 'integracao_chave' not in g:
        g.integracao_chave = servico.chave_do_cabecalho(request.headers.get('Authorization'))
    return g.integracao_chave


def _chave_do_limite():
    # Só a chave VÁLIDA ganha o próprio balde. Antes, qualquer prefixo
    # inventado no cabeçalho virava um balde novo (nunca dava 429) e o
    # prefixo real, visível ao administrador, esgotava a cota da chave
    # legítima sem conhecer o segredo (auditoria SEC-006 / N-03).
    ch = _chave_validada()
    return f'integracao:{ch.id}' if ch is not None else f'ip:{request.remote_addr or "-"}'


def _sem_chave_valida():
    return _chave_validada() is None


JANELA_DO_401 = timedelta(hours=1)


def _registrar_401(rota, ip):
    """Um registro por endereço por hora: o histórico mostra a tentativa
    sem virar uma linha por pedido (a tabela não cresce sem limite)."""
    from facilities.integracao.models import IntegracaoAcesso
    recente = (IntegracaoAcesso.query
               .filter(IntegracaoAcesso.chave_id.is_(None), IntegracaoAcesso.status == 401,
                       IntegracaoAcesso.ip == (ip or '')[:45],
                       IntegracaoAcesso.em >= datetime.utcnow() - JANELA_DO_401)
               .first())
    if recente is None:
        servico.registrar_acesso(None, rota, request.args, 401, ip=ip)
        db.session.commit()


def _responder(rota, gerar, com_periodo=True):
    chave = _chave_validada()
    ip = request.remote_addr
    if chave is None:
        _registrar_401(rota, ip)
        return jsonify({'erro': 'Chave ausente, inválida ou revogada.'}), 401
    try:
        locais = servico.locais_da_chave(chave, request.args.get('local'))
        de = ate = None
        if com_periodo:
            de, ate = servico.periodo(request.args)
            itens = gerar(locais, de, ate)
        else:
            itens = gerar(locais)
    except RegraDaIntegracao as erro:
        db.session.rollback()
        servico.registrar_acesso(chave, rota, request.args, erro.codigo, ip=ip)
        db.session.commit()
        return jsonify({'erro': erro.mensagem}), erro.codigo
    truncado = len(itens) > servico.MAX_ITENS
    itens = itens[:servico.MAX_ITENS]
    servico.registrar_acesso(chave, rota, request.args, 200, itens=len(itens), ip=ip)
    db.session.commit()
    corpo = {'versao': 1, 'itens': itens, 'truncado': truncado}
    if com_periodo:
        corpo.update(de=de.isoformat(), ate=ate.isoformat())
    resp = jsonify(corpo)
    resp.headers['X-Gerado-Em'] = datetime.utcnow().isoformat() + 'Z'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


LIMITE = '600 per hour'
# Sem chave válida, o limite é por endereço e bem menor: quem está tentando
# adivinhar não tem direito à cota de quem integra.
LIMITE_SEM_CHAVE = '30 per hour'


@bp.get('/locais')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def locais():
    return _responder('locais', servico.dados_locais, com_periodo=False)


@bp.get('/chamados')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def chamados():
    return _responder('chamados', servico.dados_chamados)


@bp.get('/aderencia')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def aderencia():
    return _responder('aderencia', servico.dados_aderencia)


@bp.get('/nao-conformidades')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def nao_conformidades():
    return _responder('nao-conformidades', servico.dados_nao_conformidades)


@bp.get('/visitas')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def visitas():
    return _responder('visitas', servico.dados_visitas)


@bp.get('/nota')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
@limiter.limit(LIMITE_SEM_CHAVE, key_func=lambda: f'ip:{request.remote_addr or "-"}',
               exempt_when=lambda: not _sem_chave_valida())
def nota():
    return _responder('nota', servico.dados_nota)
