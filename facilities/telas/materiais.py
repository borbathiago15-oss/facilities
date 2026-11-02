"""API das telas novas dos materiais (Fase 4b da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/materiais/`` (o catálogo e o estoque por local);
* ``/novo/materiais/locais/<id>`` (o saldo, a entrada/saída/ajuste, o
  consumo e os últimos lançamentos) e ``/novo/materiais/locais/<id>/mes``;
* ``/novo/materiais/custo?de=&ate=`` (o custo operacional por cliente,
  estado e local) e ``/novo/materiais/pedidos`` (os pedidos de insumo).

Cada página tem a mesma porta da antiga (as mesmas checagens, que moram nas
funções ``contexto_*`` de ``materiais.telas``) e entrega a casca React. Os
dados vêm da MESMA função que monta a tela antiga e aqui só viram JSON, com
as quantidades (``1,5``), os valores (``R$ 1.234,56``) e as datas já
escritos como a tela antiga escreve. Os envios vão para o MESMO caminho da
antiga abaixo de ``/api/v1`` e chamam a MESMA ação (``acao_*``); o consumo
do local usa a mesma ``/api/v1/materiais/locais/<id>/consumo`` do "Material
usado" do chamado (Fase 4a). A foto do pedido continua servida pelo servidor
(``/materiais/pedidos/<id>/foto``). O aplicativo (``/app/materiais``)
continua na tela antiga. Sem cópia no aparelho (gestão).
"""
from flask import request, url_for
from flask_login import login_required

from facilities.materiais import servico
from facilities.materiais import telas as mtt
from facilities.materiais.models import fmt_qtd
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova


def _reais(v):
    return servico.reais(v)


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/materiais/')
@bp.get('/novo/materiais/custo')
@bp.get('/novo/materiais/pedidos')
@login_required
def materiais_gestao():
    mtt._so_quem_ve_custo()
    return _casca()


@bp.get('/novo/materiais/locais/<int:cid>')
@bp.get('/novo/materiais/locais/<int:cid>/mes')
@login_required
def materiais_local(cid):
    mtt._so_quem_ve_custo()
    mtt._local(cid)
    return _casca()


# ── Os dados ──────────────────────────────────────────────────────────────

def _links():
    return {'catalogo': nova(url_for('materiais.catalogo')),
            'custo': nova(url_for('materiais.custo')),
            'pedidos': nova(url_for('materiais.pedidos'))}


@api.get('/materiais/')
@login_required
def api_materiais_catalogo():
    c = mtt.contexto_catalogo()
    return _sem_cache({
        'materiais': [{'id': m.id, 'nome': m.nome, 'unidade': m.unidade,
                       'preco': _reais(m.preco_unitario) if m.preco_unitario is not None else None,
                       # O campo do formulário de editar: o valor sem o "R$ ".
                       'preco_campo': (_reais(m.preco_unitario).replace('R$ ', '')
                                       if m.preco_unitario is not None else ''),
                       'ativo': bool(m.is_active)} for m in c['materiais']],
        'locais': [{'id': x.id, 'nome': x.name, 'url': nova(url_for('materiais.local', cid=x.id))}
                   for x in c['locais']],
        'pode_montar': c['pode_montar'], 'links': _links(),
    })


@api.get('/materiais/locais/<int:cid>')
@login_required
def api_materiais_local(cid):
    c = mtt.contexto_local(cid)
    loc, saldos = c['local'], c['saldos']

    def movimento(mv):
        return {'dia': mv.data.strftime('%d/%m'), 'tipo_rotulo': mv.tipo_rotulo,
                'material': mv.material.nome,
                'quantidade': f'{fmt_qtd(mv.quantidade)} {mv.material.unidade}',
                'valor': _reais(mv.valor) if mv.valor is not None else '—',
                'pessoa': mv.pessoa.name, 'motivo': mv.motivo or '',
                'autorizou': mv.autorizou.name if mv.autorizou else None}
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'materiais': [{'id': m.id, 'nome': m.nome, 'unidade': m.unidade} for m in c['materiais']],
        'com_saldo': [{'id': m.id, 'nome': m.nome, 'unidade': m.unidade,
                       'saldo': fmt_qtd(saldos[m.id]), 'negativo': saldos[m.id] < 0}
                      for m in c['com_saldo']],
        'movimentos': [movimento(mv) for mv in c['movimentos']],
        'rotas': [{'id': r.id, 'nome': r.nome} for r in c['rotas']],
        'tipos': [[k, v] for k, v in c['tipos'].items() if k != 'consumo'],
        'pode_montar': c['pode_montar'], 'gestor_do_contrato': c['gestor_do_contrato'],
        'links': {**_links(), 'mes': nova(url_for('materiais.mes', cid=loc.id))},
    })


@api.get('/materiais/locais/<int:cid>/mes')
@login_required
def api_materiais_mes(cid):
    c = mtt.contexto_mes(cid, request.args)
    loc = c['local']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'mes': c['primeiro'].strftime('%m/%Y'),
        'anterior': c['anterior'], 'seguinte': c['seguinte'],
        'total': _reais(c['total']),
        'sem_preco': [x['material'].nome for x in c['sem_preco']],
        'linhas': [{'material': x['material'].nome,
                    'quantidade': f"{fmt_qtd(x['quantidade'])} {x['material'].unidade}",
                    'vezes': x['vezes'],
                    'valor': _reais(x['valor']) if x['valor'] is not None else 'sem preço'}
                   for x in c['linhas']],
        'links': {'local': nova(url_for('materiais.local', cid=loc.id))},
    })


@api.get('/materiais/custo')
@login_required
def api_materiais_custo():
    c = mtt.contexto_custo(request.args)
    de, ate, r = c['de'], c['ate'], c['r']
    return _sem_cache({
        'de': de.isoformat(), 'ate': ate.isoformat(),
        'de_br': de.strftime('%d/%m/%Y'), 'ate_br': ate.strftime('%d/%m/%Y'),
        'total': _reais(r['total']), 'sem_preco': r['sem_preco'],
        'clientes': [[k, _reais(v)] for k, v in r['clientes'].items()],
        'estados': [[k, _reais(v)] for k, v in r['estados'].items()],
        'locais': [{'url': nova(url_for('materiais.local', cid=x['local'].id)),
                    'nome': x['local'].name, 'cliente': x['cliente'], 'estado': x['estado'],
                    'consumos': x['consumos'], 'sem_preco': x['sem_preco'],
                    'valor': _reais(x['valor'])} for x in r['locais']],
        'links': _links(),
    })


@api.get('/materiais/pedidos')
@login_required
def api_materiais_pedidos():
    c = mtt.contexto_pedidos()
    agora, gestor_de = c['agora'], c['gestor_de']

    def pedido(p):
        aberto = p.status == 'aberto'
        atrasado = bool(p.prazo and agora > p.prazo)
        return {
            'id': p.id, 'resumo': p.resumo, 'status': p.status,
            'situacao_rotulo': p.situacao_rotulo,
            # O selo: visto (cinza), atrasado (vermelho) ou no prazo — a
            # cor segue só o prazo; o "· atrasado" do texto, também o status.
            'selo': 'visto' if p.status == 'visto' else ('atrasada' if atrasado else 'no_prazo'),
            'atrasado': aberto and atrasado,
            'local': p.local.name, 'pessoa': p.pessoa.name, 'criado_em': _hora(p.criado_em),
            'prazo': _hora(p.prazo, '%d/%m %H:%M') if aberto and p.prazo else None,
            'quem_viu': p.quem_viu.name if p.quem_viu else None,
            'visto_em': _hora(p.visto_em) if p.quem_viu else None,
            'foto': url_for('materiais.foto', pid=p.id) if p.foto_key else None,
            'pode_marcar': aberto and bool(gestor_de[p.client_id]),
        }
    return _sem_cache({'pedidos': [pedido(p) for p in c['pedidos']], 'links': _links()})


# ── Os envios (a mesma ação das telas antigas) ────────────────────────────

@api.post('/materiais/')
@login_required
def api_materiais_criar():
    return _feito(mtt.acao_criar_material(_dados()))


@api.post('/materiais/<int:mid>')
@login_required
def api_materiais_editar(mid):
    return _feito(mtt.acao_editar_material(mid, _dados()))


@api.post('/materiais/locais/<int:cid>/movimento')
@login_required
def api_materiais_movimento(cid):
    return _feito(mtt.acao_movimento(cid, _dados()))


@api.post('/materiais/pedidos/<int:pid>/visto')
@login_required
def api_materiais_visto(pid):
    return _feito(mtt.acao_visto(pid))
