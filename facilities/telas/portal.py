"""API das telas novas do portal do cliente e das cobranças vistas pela
equipe (Fase 5 da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* o portal do cliente: ``/novo/cliente/`` (os locais e a nota do período,
  ``?de=&ate=``), ``/novo/cliente/locais/<id>`` (indicadores, chamados,
  checklists, visitas e os POP/FIT), ``/novo/cliente/chamados/<id>``,
  ``/novo/cliente/relatorios`` e ``/novo/cliente/relatorios/<id>/<AAAA-MM>``
  (o relatório liberado, na versão que o cliente recebeu),
  ``/novo/cliente/cobrancas`` (as duas abas: a cobrança e, com ``?aba=qr``,
  os avisos pelo QR) e ``/novo/cliente/cobrancas/<id>`` (confirmar ou
  reabrir);
* a equipe: ``/novo/cobrancas/`` (as duas abas) e ``/novo/cobrancas/<id>``
  (responder).

Cada página tem a mesma porta da antiga (as checagens moram em
``portal.telas.contexto_*``: só a conta de cliente entra no portal; o local,
o chamado, o relatório e a cobrança de outro cliente dão 404; a equipe vê a
cobrança da carteira). Os dados vêm da MESMA função que monta a tela antiga
e aqui só viram JSON, com as datas, as horas e as notas (``85,3``) já
escritas como a antiga escreve — e só o que a antiga mostra (nada de custo,
comentário interno ou nome de quem é da equipe para o cliente). Os envios
vão para o MESMO caminho da antiga abaixo de ``/api/v1`` e chamam a MESMA
ação (``acao_*``), com o mesmo limite (30 cobranças por hora), o mesmo
recado, a mesma recusa (400) e o endereço de volta já na tela nova. As
fotos, os POP/FIT, o PDF e o Excel continuam servidos pelo servidor (só
links). Sem cópia no aparelho.

A porta do cliente (``facilities/__init__._porta_do_cliente``) deixa a conta
de cliente abrir só estas páginas e estas APIs das telas novas (e o
``/api/v1/eu`` da casca): ``ENDPOINTS_DO_CLIENTE``.
"""
from flask import request, url_for
from flask_login import login_required

from facilities.extensions import limiter
from facilities.portal import telas as ptl
from facilities.portal.models import ABERTA, FECHADA, RESPONDIDA
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova
from facilities.telas.relatorios import _um, corpo_do_relatorio, numero


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/cliente/')
@bp.get('/novo/cliente/relatorios')
@bp.get('/novo/cliente/cobrancas')
@login_required
def portal_paginas():
    ptl._so_cliente()
    return _casca()


@bp.get('/novo/cliente/locais/<int:cid>')
@login_required
def portal_local(cid):
    ptl._so_cliente()
    ptl._local(cid)
    return _casca()


@bp.get('/novo/cliente/chamados/<int:chamado_id>')
@login_required
def portal_chamado(chamado_id):
    ptl.contexto_chamado(chamado_id)
    return _casca()


@bp.get('/novo/cliente/relatorios/<int:cid>/<mes>')
@login_required
def portal_relatorio(cid, mes):
    ptl._so_cliente()
    ptl._relatorio_liberado(cid, mes)
    return _casca()


@bp.get('/novo/cliente/cobrancas/<int:cobid>')
@login_required
def portal_cobranca(cobid):
    ptl._so_cliente()
    ptl._cobranca_do_cliente(cobid)
    return _casca()


@bp.get('/novo/cobrancas/')
@login_required
def cobrancas_lista():
    ptl._ve_cobrancas()
    return _casca()


@bp.get('/novo/cobrancas/<int:cobid>')
@login_required
def cobrancas_ver(cobid):
    ptl._ve_cobrancas()
    ptl._cobranca_interna(cobid)
    return _casca()


# ── O que as telas escrevem igual às antigas ──────────────────────────────

def _nota(x, faixas):
    """A macro ``nota`` de ``portal/_nota.html``."""
    if x['nota'] is None:
        return None
    return {'texto': f"{_um(x['nota'])} · {faixas[x['faixa']]}", 'faixa': x['faixa']}


def _situacao_da_cobranca(c, agora):
    """A macro ``situacao_cobranca`` de ``portal/_nota.html``."""
    if c.atrasada(agora):
        classe = 'fc-dem fc-dem-atrasada'
    elif c.status == RESPONDIDA:
        classe = 'text-bg-primary'
    elif c.status == FECHADA:
        classe = 'text-bg-light'
    else:
        classe = 'text-bg-warning'
    return {'classe': classe, 'texto': 'Prazo vencido' if c.atrasada(agora) else c.status_rotulo}


def _cobranca_na_lista(c, agora):
    return {'id': c.id, 'numero': c.numero, 'titulo': c.titulo, 'local': c.local.name,
            'prazo': _hora(c.prazo, '%d/%m/%Y'), 'situacao': _situacao_da_cobranca(c, agora),
            'url': nova(url_for('portal.cobranca', cobid=c.id))}


def _abas(rota):
    """As duas abas e os filtros da situação (``portal/_abas_cobrancas.html``)."""
    return {'cobrancas': nova(url_for(rota)), 'qr': nova(url_for(rota, aba='qr'))}


def _avisos(c, rota, interno):
    situacoes = c['situacoes']

    def aviso(o):
        p = o.ponto
        onde = f'{p.ambiente.setor.local.name} · {p.ambiente.nome} · {p.nome}'
        x = {'id': o.id, 'status': o.status, 'situacao': situacoes[o.status], 'titulo': o.titulo,
             'onde': onde, 'texto': o.texto or None,
             'quando': _hora(o.criada_em, '%d/%m %H:%M')}
        if interno:
            x.update(atrasada=bool(c['atrasada'](o)),
                     responsavel=o.responsavel.name if o.responsavel else None,
                     url=nova(url_for('rotas.dia', cid=o.client_id,
                                      data=_hora(o.criada_em, '%Y-%m-%d'))))
        else:
            # O cliente vê quando foi resolvido e o que a equipe escreveu; não
            # vê quem ficou com a tarefa (o nome é da equipe).
            x.update(resolvido=_hora(o.resolvida_em, '%d/%m %H:%M') if o.resolvida_em else None,
                     resolucao=o.resolucao or None)
        return x
    return {
        'aba': 'qr', 'situacao': c['situacao'],
        'filtros': ([['Todos', nova(url_for(rota, aba='qr')), not c['situacao']]]
                    + [[v, nova(url_for(rota, aba='qr', situacao=k)), c['situacao'] == k]
                       for k, v in situacoes.items()]),
        'avisos': [aviso(o) for o in c['avisos']],
        'abas': _abas(rota),
    }


def _evento(e, autor):
    return {'id': e.id, 'quando': _hora(e.created_at), 'autor': autor(e),
            'tipo': e.tipo_rotulo,
            'prazo': (_hora(e.prazo, '%d/%m/%Y')
                      if e.tipo in ('aberta', 'reaberta') and e.prazo else None),
            'texto': e.texto or None}


# ── Portal do cliente: os dados ───────────────────────────────────────────

@api.get('/cliente/')
@login_required
def api_portal_inicio():
    c = ptl.contexto_inicio()
    de, ate, agora = c['de'], c['ate'], c['agora']
    return _sem_cache({
        'de': de.isoformat(), 'ate': ate.isoformat(),
        'de_br': de.strftime('%d/%m/%Y'), 'ate_br': ate.strftime('%d/%m/%Y'),
        'cobrancas': [_cobranca_na_lista(x, agora) for x in c['cobrancas']],
        'linhas': [{'id': x['local'].id, 'nome': x['local'].name,
                    'nota': _nota(x, c['faixas']),
                    'abertos': c['abertos'].get(x['local'].id, 0),
                    'url': nova(url_for('portal.local', cid=x['local'].id, de=de.isoformat(),
                                        ate=ate.isoformat()))} for x in c['linhas']],
        'links': {'cobrancas': nova(url_for('portal.cobrancas'))},
    })


@api.get('/cliente/locais/<int:cid>')
@login_required
def api_portal_local(cid):
    c = ptl.contexto_local(cid)
    loc, nota, agora, quem_fez = c['local'], c['nota'], c['agora'], c['quem_fez']

    def indicador(k, rotulo):
        i = nota['indicadores'][k]
        return {'chave': k, 'rotulo': rotulo,
                'pct': numero(i['pct'], 1, '%'),
                'base': f"{i['bom']} de {i['base']}" if i['base'] else 'sem movimento'}

    def chamado(ch):
        if ch.resolvido_em:
            quando = 'resolvido ' + _hora(ch.resolvido_em, '%d/%m %H:%M')
        elif ch.prazo:
            quando = 'prazo ' + _hora(ch.prazo, '%d/%m %H:%M')
        else:
            quando = ''
        atrasado = ch.atrasado(agora)
        return {'id': ch.id, 'numero': ch.numero, 'titulo': ch.titulo,
                'situacao': 'Atrasado' if atrasado else ch.status_rotulo, 'atrasado': atrasado,
                'fotos': len(c['fotos'][ch.id]), 'quando': quando,
                'url': nova(url_for('portal.chamado', chamado_id=ch.id))}

    def execucao(ex):
        return {'id': ex.id, 'onde': f'{ex.ponto.ambiente.nome} · {ex.ponto.nome}',
                'detalhe': f'{ex.versao.modelo.nome} · {_hora(ex.concluida_em)} · '
                           f'{quem_fez(ex, loc)}',
                'nao_conformes': ex.n_nao_conformes or 0,
                'fotos': [{'id': f.id, 'url': url_for('portal.foto_checklist', fid=f.id),
                           'alt': f'Foto {f.momento} do checklist'} for f in ex.fotos]}

    def visita(v):
        return {'id': v.id, 'nome': v.programada.nome,
                'detalhe': f'{_hora(v.feita_em)} · {quem_fez(v, loc)}',
                'nao_conformes': v.n_nao_conformes or 0,
                'fotos': [{'id': f.id, 'url': url_for('portal.foto_visita', vfid=f.id),
                           'alt': 'Foto da visita de supervisão'} for f in v.fotos]}
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'de': c['de'].isoformat(), 'ate': c['ate'].isoformat(),
        'nota': _nota(nota, c['faixas']),
        'indicadores': [indicador(k, v) for k, v in c['indicadores'].items()],
        'chamados': [chamado(ch) for ch in c['chamados']],
        'execucoes': [execucao(ex) for ex in c['execucoes']],
        'visitas': [visita(v) for v in c['visitas']],
        # Os POP/FIT continuam servidos pelo servidor (o link de baixar).
        'documentos': [{'id': d.id, 'modelo': d.modelo.nome, 'nome': d.nome,
                        'url': url_for('portal.documento', did=d.id)} for d in c['documentos']],
        'links': {'inicio': nova(url_for('portal.inicio')),
                  'cobrar': nova(url_for('portal.cobrancas', local=loc.id))},
    })


@api.get('/cliente/chamados/<int:chamado_id>')
@login_required
def api_portal_chamado(chamado_id):
    c = ptl.contexto_chamado(chamado_id)
    ch, loc = c['ch'], c['local']
    return _sem_cache({
        'id': ch.id, 'numero': ch.numero, 'titulo': ch.titulo,
        'situacao': 'Atrasado' if ch.atrasado(c['agora']) else ch.status_rotulo,
        'categoria': ch.categoria_rotulo, 'onde': ch.local or None,
        'aberto_em': _hora(ch.aberto_em),
        'prazo': _hora(ch.prazo) if ch.prazo else 'sem prazo',
        'aguardando': ch.status == 'aguardando',
        'resolvido_em': _hora(ch.resolvido_em) if ch.resolvido_em else None,
        'solucao': ch.solucao or None,
        # Só as fotos (o PDF anexado pode ser orçamento: custo).
        'fotos': [{'id': a.id, 'url': url_for('portal.foto_chamado', anexo_id=a.id),
                   'alt': 'Foto ' + ('do serviço feito' if a.momento == 'depois'
                                     else 'do problema'),
                   'legenda': 'Depois' if a.momento == 'depois' else 'Antes'}
                  for a in c['fotos']],
        'local': {'id': loc.id, 'nome': loc.name},
        'links': {'inicio': nova(url_for('portal.inicio')),
                  'local': nova(url_for('portal.local', cid=loc.id)),
                  'cobrar': nova(url_for('portal.cobrancas', local=loc.id))},
    })


@api.get('/cliente/relatorios')
@login_required
def api_portal_relatorios():
    c = ptl.contexto_relatorios()
    return _sem_cache({'relatorios': [{
        'id': r.id, 'mes': c['nome_do_mes'](r.mes).capitalize(), 'local': r.local.name,
        'url': nova(url_for('portal.relatorio', cid=r.client_id, mes=r.mes.strftime('%Y-%m'))),
        'pdf': url_for('portal.relatorio_arquivo', cid=r.client_id,
                       mes=r.mes.strftime('%Y-%m'), formato='pdf')}
        for r in c['relatorios']]})


@api.get('/cliente/relatorios/<int:cid>/<mes>')
@login_required
def api_portal_relatorio(cid, mes):
    c = ptl.contexto_relatorio(cid, mes)
    d, mes = c['d'], c['mes']
    loc = d['local']
    # Só o corpo que o cliente recebeu (congelado na liberação) e o recado
    # dele: nada da gestão (a escolha das fotos, o "mudou", liberar).
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name}, 'mes': mes,
        'nome_do_mes': d['nome_do_mes'].capitalize(),
        'recado': c['recado'] or '',
        'corpo': corpo_do_relatorio(d, c['fotos'], c['url_da_foto'], c['portal']),
        'links': {'inicio': nova(url_for('portal.relatorios')),
                  'pdf': url_for('portal.relatorio_arquivo', cid=loc.id, mes=mes, formato='pdf'),
                  'xlsx': url_for('portal.relatorio_arquivo', cid=loc.id, mes=mes,
                                  formato='xlsx')},
    })


@api.get('/cliente/cobrancas')
@login_required
def api_portal_cobrancas():
    c = ptl.contexto_cobrancas(request.args)
    if c['aba'] == 'qr':
        return _sem_cache(_avisos(c, 'portal.cobrancas', interno=False))
    agora = c['agora']
    escolhido = c['local_escolhido']
    return _sem_cache({
        'aba': 'cobrancas',
        'locais': [{'id': x.id, 'nome': x.name} for x in c['locais']],
        'cobrancas': [_cobranca_na_lista(x, agora) for x in c['cobrancas']],
        'minimo': c['minimo'].isoformat(), 'minimo_br': c['minimo'].strftime('%d/%m/%Y'),
        'local_escolhido': escolhido,
        'abrir_aberto': bool(not c['cobrancas'] or escolhido),
        'abas': _abas('portal.cobrancas'),
    })


@api.get('/cliente/cobrancas/<int:cobid>')
@login_required
def api_portal_cobranca(cobid):
    c = ptl.contexto_cobranca(cobid)
    cob = c['cob']
    return _sem_cache({
        'id': cob.id, 'numero': cob.numero, 'titulo': cob.titulo, 'local': cob.local.name,
        'situacao': _situacao_da_cobranca(cob, c['agora']),
        'prazo': _hora(cob.prazo, '%d/%m/%Y'),
        'respondida': c['respondida'], 'aberta': cob.status == ABERTA,
        'minimo': c['minimo'].isoformat(), 'minimo_br': c['minimo'].strftime('%d/%m/%Y'),
        # O nome de quem é da equipe sai como "Coordenação" (autor_para_o_cliente).
        'eventos': [_evento(e, c['autor']) for e in cob.eventos],
        'links': {'cobrancas': nova(url_for('portal.cobrancas'))},
    })


# ── Portal do cliente: os envios (a mesma ação da tela antiga) ────────────

@api.post('/cliente/cobrancas')
@login_required
@limiter.shared_limit(ptl.LIMITE_DE_COBRANCAS, scope=ptl.ESCOPO_DO_LIMITE_DE_COBRANCAS)
def api_portal_abrir_cobranca():
    return _feito(ptl.acao_abrir_cobranca(_dados()))


@api.post('/cliente/cobrancas/<int:cobid>/<acao>')
@login_required
def api_portal_acao_cobranca(cobid, acao):
    return _feito(ptl.acao_na_cobranca(cobid, acao, _dados()))


# ── A cobrança vista pela equipe ──────────────────────────────────────────

def _situacao_interna(c, agora):
    """O selo da lista da equipe (``portal/interno_lista.html``)."""
    if c.atrasada(agora):
        classe = 'fc-dem fc-dem-atrasada'
    elif c.status == ABERTA:
        classe = 'text-bg-warning'
    else:
        classe = 'text-bg-light'
    return {'classe': classe, 'texto': 'Atrasada' if c.atrasada(agora) else c.status_rotulo}


@api.get('/cobrancas/')
@login_required
def api_cobrancas_lista():
    c = ptl.contexto_lista(request.args)
    if c['aba'] == 'qr':
        return _sem_cache(_avisos(c, 'cobrancas.lista', interno=True))
    agora, status = c['agora'], c['status']
    return _sem_cache({
        'aba': 'cobrancas', 'status': status,
        'filtros': ([['Todas', nova(url_for('cobrancas.lista')), not status]]
                    + [[v, nova(url_for('cobrancas.lista', status=k)), status == k]
                       for k, v in c['rotulos'].items()]),
        'itens': [{'id': x.id, 'numero': x.numero, 'titulo': x.titulo,
                   'local': x.local.name, 'autor': x.autor.name,
                   'prazo': _hora(x.prazo, '%d/%m/%Y'),
                   'situacao': _situacao_interna(x, agora),
                   'url': nova(url_for('cobrancas.ver', cobid=x.id))} for x in c['itens']],
        'abas': _abas('cobrancas.lista'),
    })


@api.get('/cobrancas/<int:cobid>')
@login_required
def api_cobrancas_ver(cobid):
    c = ptl.contexto_ver(cobid)
    cob = c['cob']
    return _sem_cache({
        'id': cob.id, 'numero': cob.numero, 'titulo': cob.titulo, 'local': cob.local.name,
        'autor': cob.autor.name,
        'situacao': 'Atrasada' if cob.atrasada(c['agora']) else cob.status_rotulo,
        'prazo': _hora(cob.prazo, '%d/%m/%Y'), 'reaberturas': cob.reaberturas or 0,
        'status': cob.status, 'pode_responder': bool(c['pode_responder']),
        'eventos': [_evento(e, lambda ev: ev.autor.name) for e in cob.eventos],
        'links': {'lista': nova(url_for('cobrancas.lista'))},
    })


@api.post('/cobrancas/<int:cobid>/responder')
@login_required
def api_cobrancas_responder(cobid):
    return _feito(ptl.acao_responder(cobid, _dados()))


# A porta do cliente: o que a conta de cliente abre nas telas novas (as
# páginas e as APIs do portal acima e o ``/eu`` da casca). O resto das
# telas novas continua fechado para ela.
ENDPOINTS_DO_CLIENTE = frozenset(
    {'api_v1.eu'}
    | {f'telas.{n}' for n in ('portal_paginas', 'portal_local', 'portal_chamado',
                              'portal_relatorio', 'portal_cobranca')}
    | {f'api_v1.{n}' for n in ('api_portal_inicio', 'api_portal_local', 'api_portal_chamado',
                               'api_portal_relatorios', 'api_portal_relatorio',
                               'api_portal_cobrancas', 'api_portal_cobranca',
                               'api_portal_abrir_cobranca', 'api_portal_acao_cobranca')})
