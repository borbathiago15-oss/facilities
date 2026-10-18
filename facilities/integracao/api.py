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
from datetime import datetime

from flask import Blueprint, jsonify, request

from facilities.extensions import db, limiter
from facilities.integracao import servico
from facilities.integracao.servico import RegraDaIntegracao

bp = Blueprint('integracao_api', __name__, url_prefix='/api/integracao/v1')


def _chave_do_limite():
    cab = request.headers.get('Authorization') or ''
    partes = cab[7:].split('_') if cab.startswith('Bearer ') else []
    return f'integracao:{partes[1]}' if len(partes) >= 3 else (request.remote_addr or '-')


def _responder(rota, gerar, com_periodo=True):
    chave = servico.chave_do_cabecalho(request.headers.get('Authorization'))
    ip = request.remote_addr
    if chave is None:
        servico.registrar_acesso(None, rota, request.args, 401, ip=ip)
        db.session.commit()
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


@bp.get('/locais')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def locais():
    return _responder('locais', servico.dados_locais, com_periodo=False)


@bp.get('/chamados')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def chamados():
    return _responder('chamados', servico.dados_chamados)


@bp.get('/aderencia')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def aderencia():
    return _responder('aderencia', servico.dados_aderencia)


@bp.get('/nao-conformidades')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def nao_conformidades():
    return _responder('nao-conformidades', servico.dados_nao_conformidades)


@bp.get('/visitas')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def visitas():
    return _responder('visitas', servico.dados_visitas)


@bp.get('/nota')
@limiter.limit(LIMITE, key_func=_chave_do_limite)
def nota():
    return _responder('nota', servico.dados_nota)
