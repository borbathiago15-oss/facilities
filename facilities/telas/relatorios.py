"""API das telas novas dos relatórios do cliente e do painel (Fase 4c da
migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/relatorios/?mes=AAAA-MM`` (um por local: liberado ou não) e
  ``/novo/relatorios/cliente/<id>/<AAAA-MM>`` (o relatório do mês: os
  números, o recado, a escolha das fotos, liberar e recolher);
* ``/novo/painel?de=&ate=`` (a nota de cada local da carteira e o que está
  atrasado agora).

Cada página tem a mesma porta da antiga (as mesmas checagens, que moram em
``relatorios.telas.contexto_*`` e ``paineis.telas.contexto_painel``) e
entrega a casca React. Os dados vêm da MESMA função que monta a tela antiga
e aqui só viram JSON, com os números (``85,3``, ``85,3%``), as horas e as
datas já escritos como a tela antiga escreve. Os envios do relatório vão
para o MESMO caminho da antiga abaixo de ``/api/v1`` e chamam a MESMA ação
(``acao_agir``): a resposta é o recado e o endereço de volta, já na tela
nova; a recusa da regra é 400 com a mesma frase. O PDF, o Excel e as fotos
continuam servidos pelo servidor (só links). O portal do cliente
(``/cliente/relatorios/...``) continua na tela antiga (Fase 5). Sem cópia no
aparelho (gestão).
"""
from flask import request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities.paineis import telas as pnt
from facilities.relatorios import telas as rlt
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova


def numero(v, casas=1, sufixo=''):
    """A macro ``numero`` de ``relatorios/_relatorio.html``: vírgula decimal
    e "—" quando não há valor."""
    if v is None:
        return '—'
    return (f'%.{casas}f' % v).replace('.', ',') + sufixo


def _um(v):
    """O ``'%.1f'|format(v)|replace('.', ',')`` do painel."""
    return ('%.1f' % v).replace('.', ',')


def _como_o_jinja(v):
    """``{{ v if v is not none else '—' }}``: o valor como o Jinja escreve
    (o ``str`` do Python, com ponto decimal)."""
    return '—' if v is None else str(v)


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/relatorios/')
@login_required
def relatorios_inicio():
    rlt._so_quem_le()
    return _casca()


@bp.get('/novo/relatorios/cliente/<int:cid>/<mes>')
@login_required
def relatorios_cliente(cid, mes):
    rlt._so_quem_le()
    rlt._local(cid)
    return _casca()


@bp.get('/novo/painel')
@login_required
def painel():
    if not pnt.ve_painel(current_user):
        raise Forbidden('O painel é da supervisão, da gestão e da diretoria.')
    return _casca()


# ── Relatórios: os dados ──────────────────────────────────────────────────

@api.get('/relatorios/')
@login_required
def api_relatorios_inicio():
    c = rlt.contexto_inicio(request.args)
    mes = c['primeiro'].strftime('%Y-%m')
    registros = c['registros']

    def local(loc):
        r = registros.get(loc.id)
        liberado = bool(r and r.liberado_em)
        return {'id': loc.id, 'nome': loc.name,
                'cliente': loc.contratante.nome if loc.contratante else 'Sem cliente',
                'liberado': liberado,
                'liberado_em': _hora(r.liberado_em, '%d/%m %H:%M') if liberado else None,
                'url': nova(url_for('relatorios.cliente', cid=loc.id, mes=mes))}
    return _sem_cache({
        'mes': mes, 'nome_do_mes': c['nome_do_mes'].capitalize(),
        'locais': [local(loc) for loc in c['locais']],
        'links': {'anterior': nova(url_for('relatorios.inicio', mes=c['anterior'])),
                  'seguinte': nova(url_for('relatorios.inicio', mes=c['seguinte']))},
    })


def _variacao(v):
    if v is None:
        return 'sem comparação com o mês anterior'
    if v == 0:
        return 'igual ao mês anterior'
    return f"{'+' if v > 0 else ''}{numero(v)} ponto(s) sobre o mês anterior"


def _situacao_do_chamado(x):
    texto = x['situacao']
    if x['no_prazo']:
        texto += ' · no prazo'
    elif x['no_prazo'] is False:
        texto += ' · fora do prazo'
    return texto


def corpo_do_relatorio(d, fotos, url_da_foto, portal):
    """O corpo do relatório (a macro ``corpo`` de ``_relatorio.html``), com
    os números já escritos como ela escreve."""
    nota = d['nota']
    c, oc = d['chamados'], d['ocorrencias']
    el = d['elogios']
    return {
        'nota': ({'texto': f"{numero(nota['nota'])} · {d['faixas'][nota['faixa']]}",
                  'faixa': nota['faixa']} if nota['nota'] is not None else None),
        'variacao': _variacao(d['variacao']),
        'indicadores': [{'chave': k, 'rotulo': rot,
                         'pct': numero(nota['indicadores'][k]['pct'], 1, '%'),
                         'base': (f"{nota['indicadores'][k]['bom']} de {nota['indicadores'][k]['base']}"
                                  if nota['indicadores'][k]['base'] else 'sem movimento')}
                        for k, rot in d['indicadores'].items()],
        'rotinas': [{'ambiente': r['ambiente'], 'previstas': r['previstas'],
                     'no_prazo': r['no_prazo'], 'com_atraso': r['com_atraso'],
                     'nao_feitas': r['nao_feitas'], 'pct': numero(r['pct'], 1, '%')}
                    for r in d['rotinas']],
        'chamados': {
            'abertos': c['abertos'], 'resolvidos': c['resolvidos'],
            'pct_no_prazo': numero(c['pct_no_prazo'], 1, '%'),
            'tempo_medio': numero(c['tempo_medio_h'], 1, ' h'),
            'pendentes_no_fim': c['pendentes_no_fim'],
            'lista': [{'numero': x['numero'], 'titulo': x['titulo'], 'categoria': x['categoria'],
                       'aberto_em': _hora(x['aberto_em'], '%d/%m %H:%M'),
                       'resolvido_em': (_hora(x['resolvido_em'], '%d/%m %H:%M')
                                        if x['resolvido_em'] else '—'),
                       'situacao': _situacao_do_chamado(x)} for x in c['lista']],
            'lista_cortada': bool(c['lista_cortada'])},
        'ncs': {'total': d['ncs']['total'], 'corrigidas': d['ncs']['corrigidas'],
                'itens': [[item, vezes] for item, vezes in d['ncs']['itens']]},
        'ocorrencias': {'total': oc['total'], 'resolvidas': oc['resolvidas'],
                        'pct_no_prazo': numero(oc['pct_no_prazo'], 1, '%'),
                        'tempo_medio': numero(oc['tempo_medio_min'], 0, ' min')},
        'visitas': dict(d['visitas']),
        'cobrancas': dict(d['cobrancas']),
        # ``{% if d.elogios %}``: a seção só some quando não há o bloco.
        'elogios': ({'total': el['total'], 'media': numero(el['media'], 1, ''),
                     'comentarios': [{'texto': x['texto'], 'nota': x['nota'],
                                      'estrelas': 'estrelas' if x['nota'] > 1 else 'estrela',
                                      'onde': x['onde'], 'quando': _hora(x['quando'], '%d/%m')}
                                     for x in el['comentarios']]} if el else None),
        'fotos': [{'ref': f['ref'], 'legenda': f['legenda'], 'url': url_da_foto(f, portal)}
                  for f in fotos],
    }


@api.get('/relatorios/cliente/<int:cid>/<mes>')
@login_required
def api_relatorios_cliente(cid, mes):
    c = rlt.contexto_cliente(cid, mes)
    d, registro, mes = c['d'], c['registro'], c['mes']
    loc = d['local']
    liberado = bool(registro and registro.liberado_em)
    pode_gerir = c['pode_gerir']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name}, 'cliente': d['cliente'],
        'mes': mes, 'nome_do_mes': d['nome_do_mes'].capitalize(),
        'liberado_em': _hora(registro.liberado_em) if liberado else None,
        'recado': registro.recado if registro and registro.recado else '',
        'pode_gerir': pode_gerir, 'mes_fechado': c['mes_fechado'],
        'mudou': [[o_que, _como_o_jinja(antes), _como_o_jinja(agora)]
                  for o_que, antes, agora in c['mudou']],
        'corpo': corpo_do_relatorio(d, c['fotos'], c['url_da_foto'], c['portal']),
        # A escolha das fotos é da gestão: quem só lê não recebe a lista.
        'escolha': ({'todas': [{'ref': f['ref'], 'legenda': f['legenda'],
                                'url': c['url_da_foto'](f, False),
                                'escolhida': f['ref'] in c['escolhidas']} for f in c['todas']],
                     'automatica': c['automatica'], 'fotos_max': c['fotos_max']}
                    if pode_gerir else None),
        'links': {'inicio': nova(url_for('relatorios.inicio', mes=mes)),
                  # O PDF e o Excel continuam servidos pelo servidor.
                  'pdf': url_for('relatorios.baixar', cid=loc.id, mes=mes, formato='pdf'),
                  'xlsx': url_for('relatorios.baixar', cid=loc.id, mes=mes, formato='xlsx')},
    })


# ── Relatórios: os envios (a mesma ação da tela antiga) ───────────────────

@api.post('/relatorios/cliente/<int:cid>/<mes>/<acao>')
@login_required
def api_relatorios_agir(cid, mes, acao):
    return _feito(rlt.acao_agir(cid, mes, acao, _dados()))


# ── Painel ────────────────────────────────────────────────────────────────

@api.get('/painel')
@login_required
def api_painel():
    c = pnt.contexto_painel(request.args)
    atrasadas, elogios, faixas = c['atrasadas'], c['elogios'], c['faixas']

    def linha(x):
        lid = x['local'].id
        e = elogios.get(lid)
        return {
            'local_id': lid, 'local': x['local'].name,
            'nota': (f"{_um(x['nota'])} · {faixas[x['faixa']]}" if x['nota'] is not None
                     else None),
            'faixa': x['faixa'],
            'indicadores': [({'pct': f"{_um(i['pct'])}%", 'base': f"{i['bom']} de {i['base']}"}
                             if i['pct'] is not None else None)
                            for i in (x['indicadores'][k] for k in c['indicadores'])],
            'elogios': {'media': _um(e[0]), 'total': e[1]} if e else None,
            'atrasadas': atrasadas.get(lid) or 0,
            'atrasadas_url': nova(url_for('demandas.painel', local=lid, situacao='atrasada')),
        }

    def media(resumo):
        return _um(resumo['media']) if resumo['media'] is not None else '—'
    resumo = c['resumo']
    return _sem_cache({
        'de': c['de'].isoformat(), 'ate': c['ate'].isoformat(),
        'de_br': c['de'].strftime('%d/%m/%Y'), 'ate_br': c['ate'].strftime('%d/%m/%Y'),
        'faixa_critica': c['faixa_critica'], 'faixa_boa': c['faixa_boa'],
        'indicadores': list(c['indicadores'].values()),
        'resumo': {'media': media(resumo),
                   'faixas': [[v, resumo['faixas'][k]] for k, v in faixas.items()],
                   'sem_dado': resumo['sem_dado']},
        'linhas': [linha(x) for x in c['linhas']],
        'grupos': ([{'cliente': g['cliente'], 'media': media(g['resumo']),
                     'linhas': [linha(x) for x in g['linhas']]} for g in c['grupos']]
                   if c['grupos'] else None),
    })
