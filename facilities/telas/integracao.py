"""API da tela nova das chaves da integração (Fase 4c da migração para React).

A tela, no mesmo endereço da antiga, abaixo de ``/novo``:
``/novo/admin/integracao/`` (as chaves, o "Criar chave", o "Revogar" e os
últimos acessos). Só o administrador, como a antiga (``admin_required`` na
página, na leitura e nos envios).

Segurança da chave (a mesma regra da antiga: ela aparece UMA vez):

* a leitura (``GET``) nunca traz o texto nem o hash de chave nenhuma — só o
  prefixo, como a lista antiga;
* o texto da chave nova só existe na resposta do ``POST`` que a cria
  (``Cache-Control: no-store``); nada de recado (o recado vai no cookie da
  sessão), de endereço, de histórico do navegador nem de cópia: a tela nova
  o guarda só na memória do componente e o perde ao sair dali.

Os dados vêm da MESMA função que monta a tela antiga
(``integracao.telas.contexto_chaves``); os envios chamam a MESMA ação
(``acao_criar`` e ``acao_revogar``). Sem cópia no aparelho (administração).
"""
from flask import jsonify, url_for
from flask_login import login_required

from facilities.core.acesso import admin_required
from facilities.integracao import telas as itt
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _recados, _sem_cache, nova


@bp.get('/novo/admin/integracao/')
@login_required
@admin_required
def integracao_chaves():
    return _casca()


def _chave(c):
    """Uma linha da lista, como a antiga escreve (sem o texto nem o hash)."""
    return {'id': c.id, 'nome': c.nome, 'prefixo': f'fac_{c.prefixo}_…',
            'locais': ('todos os locais' if c.todos_os_locais
                       else ', '.join(x.name for x in c.locais)),
            'criada_em': _hora(c.criada_em, '%d/%m/%Y'),
            'ultimo_uso_em': _hora(c.ultimo_uso_em), 'ativa': bool(c.is_active)}


@api.get('/admin/integracao/')
@login_required
@admin_required
def api_integracao_chaves():
    c = itt.contexto_chaves()
    return _sem_cache({
        'chaves': [_chave(x) for x in c['chaves']],
        'acessos': [{'id': a.id, 'em': _hora(a.em),
                     'chave': a.chave.nome if a.chave else 'chave inválida',
                     'rota': a.rota, 'parametros': a.parametros or '', 'status': a.status,
                     'itens': a.itens if a.itens is not None else ''} for a in c['acessos']],
        'locais': [{'id': x.id, 'nome': x.name} for x in c['locais']],
    })


@api.post('/admin/integracao/')
@login_required
@admin_required
def api_integracao_criar():
    feito = itt.acao_criar(_dados())
    if feito is None:
        return _feito(url_for('integracao.chaves'))
    ch, texto = feito
    # O texto vai só nesta resposta, que não fica guardada em lugar nenhum.
    resp = jsonify({'recados': _recados(), 'destino': nova(url_for('integracao.chaves')),
                    'chave': {'nome': ch.nome, 'texto': texto}})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.post('/admin/integracao/<int:kid>/revogar')
@login_required
@admin_required
def api_integracao_revogar(kid):
    return _feito(itt.acao_revogar(kid))
