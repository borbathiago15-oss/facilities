"""API das telas novas do aplicativo de campo: equipe, materiais e visitas
(Fase 1d da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``, na moldura
do aplicativo de campo (a navegação embaixo, como ``/novo/app``):

* ``/novo/app/equipe?data=AAAA-MM-DD`` (a equipe do dia: veio, faltou,
  atrasou e a cobertura da falta);
* ``/novo/app/materiais`` (o "Usei material" e o "Está faltando material",
  com os últimos pedidos da pessoa);
* ``/novo/app/visitas`` (as visitas de supervisão esperando a pessoa) e
  ``/novo/app/visitas/<id>`` (o checklist da visita, com as fotos reduzidas
  no aparelho por ``foto-leve.js``; a visita feita, com as respostas).

Cada página tem a mesma porta da antiga (as mesmas checagens, que moram nas
funções ``contexto_app_*`` de ``equipes.telas``, ``materiais.telas`` e
``visitas.telas``) e entrega a casca React. Os dados vêm da MESMA função
que monta a tela antiga e aqui só viram JSON, em ``/api/v1/campo/...``, com
as datas e as horas já escritas como a antiga escreve. Os envios vão para
``POST /api/v1/campo/...`` e chamam a MESMA ação da antiga (``acao_app_*`` e
``acao_fazer``): a resposta é o recado (o ``flash`` da antiga) e o endereço
de volta, já na tela nova; a recusa da regra é 400 com a mesma frase. As
fotos vão no próprio ``FormData``, com os mesmos nomes de campo. A foto da
visita (``/app/visitas/fotos/<id>``) e a do pedido continuam servidas pelo
servidor.

Sem internet, como as antigas: estas telas não têm cópia no aparelho (o
service worker não as guarda) e o envio sem sinal não entra na fila — a
tela diz que precisa de sinal, e o que a pessoa preencheu continua na tela.
"""
from flask import request, url_for
from flask_login import login_required

from facilities.equipes import telas as eqt
from facilities.materiais import telas as mtt
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova
from facilities.telas.campo import _links
from facilities.visitas import telas as vst


def _hm(t):
    return t.strftime('%H:%M')


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/app/equipe')
@login_required
def equipes_app():
    eqt._pode_lancar()
    return _casca()


@bp.get('/novo/app/materiais')
@login_required
def materiais_app():
    mtt._pode_usar_app()
    return _casca()


@bp.get('/novo/app/visitas')
@login_required
def visitas_app_lista():
    vst.contexto_app_lista()
    return _casca()


@bp.get('/novo/app/visitas/<int:vid>')
@login_required
def visitas_app_ver(vid):
    vst._visita(vid)
    return _casca()


# ── Equipe ────────────────────────────────────────────────────────────────

def _linha_da_equipe(linha):
    e, p = linha['escala'], linha['presenca']
    detalhe = f'{e.posto.nome} · {_hm(e.posto.hora_inicio)} às {_hm(e.posto.hora_fim)}'
    if e.funcionario.funcao:
        detalhe += f' · {e.funcionario.funcao}'
    presenca = None
    if p is not None:
        presenca = {'id': p.id, 'situacao': p.situacao, 'rotulo': p.situacao_rotulo,
                    'cobertura': ({'funcionario': p.cobertura.funcionario.nome,
                                   'motivo': p.cobertura.motivo} if p.cobertura else None)}
    return {'escala_id': e.id, 'funcionario_id': e.funcionario_id,
            'funcionario': e.funcionario.nome, 'detalhe': detalhe, 'presenca': presenca}


@api.get('/campo/equipe')
@login_required
def api_equipes_app():
    c = eqt.contexto_app_equipe(request.args.get('data'))
    return _sem_cache({
        'dia': c['dia'].strftime('%d/%m/%Y'), 'data': c['dia'].isoformat(),
        'ontem': nova(url_for('equipes.app_equipe', data=c['ontem'])),
        'amanha': nova(url_for('equipes.app_equipe', data=c['amanha'])) if c['amanha'] else None,
        'situacoes': [[k, v] for k, v in c['situacoes'].items()],
        'locais': [{'id': loc.id, 'nome': loc.name,
                    'linhas': [_linha_da_equipe(x) for x in c['por_local'][loc.id]],
                    'cobridores': [{'id': f.id, 'nome': f.nome} for f in c['cobridores'][loc.id]]}
                   for loc in c['locais']],
        'links': _links(),
    })


@api.post('/campo/equipe/presenca')
@login_required
def api_equipes_app_presenca():
    dados = _dados()
    return _feito(eqt.acao_app_presenca(dados, dados.get('data') or request.args.get('data')))


@api.post('/campo/equipe/presencas/<int:prid>/cobertura')
@login_required
def api_equipes_app_cobertura(prid):
    return _feito(eqt.acao_app_cobertura(prid, _dados()))


# ── Materiais ─────────────────────────────────────────────────────────────

@api.get('/campo/materiais')
@login_required
def api_materiais_app():
    c = mtt.contexto_app()
    return _sem_cache({
        'locais': [{'id': x.id, 'nome': x.name} for x in c['locais']],
        'materiais': [{'id': m.id, 'nome': m.nome, 'unidade': m.unidade} for m in c['materiais']],
        'chamados': [{'id': ch.id, 'rotulo': f'{ch.numero} · {ch.titulo[:50]}'}
                     for ch in c['chamados']],
        'rotas': [{'id': r.id, 'rotulo': f'{r.local.name} · {r.nome}'} for r in c['rotas']],
        'meus': [{'id': p.id, 'resumo': p.resumo,
                  'detalhe': f"{p.local.name} · {_hora(p.criado_em, '%d/%m %H:%M')} · "
                             f'{p.situacao_rotulo}'} for p in c['meus']],
        'links': _links(),
    })


@api.post('/campo/materiais/consumo')
@login_required
def api_materiais_app_consumo():
    return _feito(mtt.acao_app_consumo(_dados()))


@api.post('/campo/materiais/pedido')
@login_required
def api_materiais_app_pedido():
    return _feito(mtt.acao_app_pedido(_dados(), request.files))


# ── Visitas de supervisão ─────────────────────────────────────────────────

@api.get('/campo/visitas')
@login_required
def api_visitas_app_lista():
    c = vst.contexto_app_lista()
    hoje = c['hoje']
    return _sem_cache({
        'visitas': [{'id': v.id, 'nome': v.programada.nome, 'local': v.local.name,
                     'ate': v.vencimento.strftime('%d/%m'),
                     # O selo: "Atrasada" (venceu) ou "Hoje" (vence hoje).
                     'selo': ('atrasada' if v.vencimento < hoje
                              else 'hoje' if v.vencimento == hoje else None),
                     'url': nova(url_for('visitas.ver', vid=v.id))} for v in c['visitas']],
        'links': _links(),
    })


def _item_da_visita(it, textos):
    se = it.get('mostrar_se')
    return {
        'codigo': it['codigo'], 'texto': it['texto'], 'tipo': it['tipo'],
        'obrigatorio': bool(it.get('obrigatorio')),
        # A frase da antiga: Responda só se "<texto da pergunta>" for "<valor>".
        'mostrar_se': ({'codigo': se['codigo'], 'valor': se['valor'],
                        'texto': textos.get(se['codigo'], se['codigo'])} if se else None),
        # Como a antiga escreve o "Aceitável: de 0.0 até 8.0" (o número do Python).
        'minimo': None if it.get('minimo') is None else str(it['minimo']),
        'maximo': None if it.get('maximo') is None else str(it['maximo']),
        'opcoes': list(it.get('opcoes') or []), 'exige_foto': bool(it.get('exige_foto')),
    }


@api.get('/campo/visitas/<int:vid>')
@login_required
def api_visitas_app_ver(vid):
    c = vst.contexto_app_visita(vid)
    v, versao, textos, respostas = c['v'], c['versao'], c['textos'], c['respostas']
    feita = v.status == 'feita'
    return _sem_cache({
        'visita': {
            'id': v.id, 'nome': v.programada.nome, 'local': v.local.name,
            'status': v.status, 'situacao_rotulo': v.situacao_rotulo,
            'ate': v.vencimento.strftime('%d/%m/%Y') if v.status == 'prevista' else None,
            'quem_fez': (v.quem_fez.name if v.quem_fez else '—') if feita else None,
            'feita_em': _hora(v.feita_em) if feita else None,
            'n_nao_conformes': v.n_nao_conformes or 0,
            'chamado': ({'numero': v.chamado.numero, 'status_rotulo': v.chamado.status_rotulo,
                         'url': nova(url_for('chamados.ver', chamado_id=v.chamado.id))}
                        if feita and v.chamado else None),
            'observacao': (v.observacao or '') if feita else '',
            'supervisor': v.supervisor.name if v.supervisor else None,
        },
        'fotos': ([{'id': f.id, 'url': url_for('visitas.foto', vfid=f.id),
                    'alt': f'Foto {f.momento_rotulo.lower()}',
                    'legenda': (textos.get(f.item_codigo, f.momento_rotulo)
                                if f.momento == 'item' else f.momento_rotulo)}
                   for f in v.fotos] if feita else []),
        'respostas': ([{'codigo': it['codigo'], 'texto': it['texto'],
                        'valor': respostas.get(it['codigo'], '—')} for it in c['itens']]
                      if feita else []),
        'itens': [_item_da_visita(it, textos) for it in c['itens']] if c['pode_fazer'] else [],
        'exige_foto_antes': bool(versao and versao.exige_foto_antes),
        'exige_foto_depois': bool(versao and versao.exige_foto_depois),
        'pode_fazer': c['pode_fazer'],
        'links': _links(),
    })


@api.post('/campo/visitas/<int:vid>')
@login_required
def api_visitas_app_fazer(vid):
    return _feito(vst.acao_fazer(vid, _dados(), request.files))
