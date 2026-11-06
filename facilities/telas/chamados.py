"""API das telas novas dos chamados, do painel de demandas e da preventiva
(Fase 4a da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/chamados/`` (a lista: os números do topo, os filtros e as abas),
  ``/novo/chamados/novo`` (abrir, com as fotos) e ``/novo/chamados/<id>`` (o
  chamado: as ações, o histórico, as fotos e o material usado);
* ``/novo/demandas/`` (tudo que espera alguém, numa fila só);
* ``/novo/preventiva/locais/<id>`` (os planos preventivos do local).

Cada página tem a mesma porta da antiga (os mesmos decoradores e as mesmas
checagens, que moram nas funções ``contexto_*``) e entrega a casca React. Os
dados vêm da MESMA função que monta a tela antiga (``chamados.rotas``,
``demandas`` e ``preventiva.telas``) e aqui só viram JSON, em
``/api/v1/...``, com as horas, as datas e os números já escritos como a tela
antiga escreve. Os envios vão para o MESMO caminho da antiga abaixo de
``/api/v1`` e chamam a MESMA ação (``acao_*``): a resposta é o recado e o
endereço de volta, já na tela nova; a recusa da regra é 400 com a mesma
frase. As fotos do chamado vão no próprio ``FormData``; o arquivo (a foto, o
PDF) continua servido pelo servidor (``/chamados/anexos/<id>``). O "Material
usado" do chamado chama a mesma ação do formulário antigo
(``materiais.telas.acao_consumo``). Sem cópia no aparelho (gestão).
"""
from flask import current_app, request, url_for
from flask_login import current_user, login_required

from facilities import demandas as dem
from facilities.chamados import rotas as chr_
from facilities.core.acesso import module_required
from facilities.preventiva import telas as prv
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova

MODULO = chr_.MODULO

# O que a trilha do chamado escreve depois do nome de quem fez (o
# ``ROTULO_EVENTO`` de templates/chamados/ver.html).
ROTULO_EVENTO = {
    'aberto': 'abriu o chamado', 'atribuido': 'atribuiu', 'prioridade': 'mudou a prioridade',
    'iniciado': 'iniciou o atendimento', 'aguardando': 'pôs em espera',
    'retomado': 'retomou o atendimento', 'resolvido': 'resolveu',
    'fechado': 'confirmou a solução', 'reaberto': 'reabriu', 'cancelado': 'cancelou',
    'comentario': 'comentou', 'lembrete': 'lembrou quem abriu de conferir e confirmar',
}


def _pares(d):
    return [[k, v] for k, v in d.items()]


def _filtro(nome, *args):
    return current_app.jinja_env.filters[nome](*args)


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/chamados/')
@login_required
@module_required(MODULO)
def chamados_lista():
    chr_.contexto_index(request.args)
    return _casca()


@bp.get('/novo/chamados/novo')
@login_required
@module_required(MODULO)
def chamados_novo():
    chr_.contexto_novo(request.args)
    return _casca()


@bp.get('/novo/chamados/<int:chamado_id>')
@login_required
@module_required(MODULO)
def chamados_ver(chamado_id):
    chr_._chamado_autorizado(chamado_id)
    return _casca()


@bp.get('/novo/demandas/')
@login_required
def demandas_painel():
    dem.exigir_acesso()
    return _casca()


@bp.get('/novo/preventiva/locais/<int:cid>')
@login_required
def preventiva_local(cid):
    prv._local(cid)
    return _casca()


# ── Os selos do chamado (templates/chamados/_selo.html) ───────────────────

def selo_do_prazo(ch, agora):
    """O selo do prazo, com o texto que a tela antiga escreve (``selo.prazo``).

    Em "Aguardando" o relógio do prazo está parado (D8): o selo diz isso, e
    não "atrasado há" nem "vence em" — como a borda vermelha da lista e os
    contadores (``Chamado.atrasado``)."""
    if ch.status in ('fechado', 'cancelado'):
        return None
    if ch.status == 'resolvido':
        return {'tipo': 'ok', 'perto': False,
                'texto': 'resolvido ' + _filtro('hora_local', ch.resolvido_em, '%d/%m %H:%M')}
    if ch.status == 'aguardando' and ch.prazo:
        return {'tipo': 'parado', 'perto': False, 'texto': 'prazo parado'}
    if ch.prazo and agora > ch.prazo:
        h = int((agora - ch.prazo).total_seconds() // 3600)
        if h < 24:
            quanto = f"{h if h > 0 else 'menos de 1'}h"
        else:
            quanto = f"{h // 24} {'dia' if h // 24 == 1 else 'dias'}"
        return {'tipo': 'atrasado', 'perto': False, 'texto': f'atrasado há {quanto}'}
    if ch.prazo:
        h = int((ch.prazo - agora).total_seconds() // 3600)
        if h < 24:
            quando = f"em {h if h > 0 else 'menos de 1'}h"
        else:
            quando = _filtro('hora_local', ch.prazo, '%d/%m %H:%M')
        return {'tipo': 'vence', 'perto': h < 4, 'texto': f'vence {quando}'}
    return None


def _resumo(ch, agora):
    return {
        'id': ch.id, 'numero': ch.numero, 'titulo': ch.titulo,
        'prioridade': ch.prioridade, 'prioridade_rotulo': ch.prioridade_rotulo,
        'status': ch.status, 'status_rotulo': ch.status_rotulo,
        'prazo_selo': selo_do_prazo(ch, agora), 'atrasado': ch.atrasado(agora),
        'contrato': ch.contrato.name, 'area': ch.area.nome if ch.area else None,
        'local': ch.local or '', 'categoria_rotulo': ch.categoria_rotulo,
        'responsavel': ch.responsavel.name if ch.responsavel else None,
    }


def numeros_escritos(n):
    """Os números do topo, escritos como a tela antiga escreve."""
    pct = n['pct_no_prazo']
    horas = n['horas_medias']
    if horas is None:
        tempo_medio = '—'
    elif horas < 1:
        tempo_medio = 'menos de 1h'
    elif horas < 48:
        tempo_medio = '%.0fh' % horas
    else:
        tempo_medio = ('%.1f' % (horas / 24)).replace('.', ',') + ' dias'
    return {
        'em_aberto': n['em_aberto'], 'atrasados': n['atrasados'],
        'aguardando_confirmacao': n['aguardando_confirmacao'], 'dias': n['dias'],
        'pct_no_prazo': '—' if pct is None else ('%.1f' % pct).replace('.', ',') + '%',
        'tempo_medio': tempo_medio,
    }


# ── Chamados: os dados ────────────────────────────────────────────────────

@api.get('/chamados/')
@login_required
@module_required(MODULO)
def api_chamados_lista():
    c = chr_.contexto_index(request.args)
    agora = c['agora']
    return _sem_cache({
        'chamados': [_resumo(ch, agora) for ch in c['chamados']],
        'cortada': c['cortada'], 'por_pagina': c['por_pagina'],
        'contratos': [{'id': x.id, 'nome': x.name} for x in c['contratos']],
        'client_id': c['client_id'], 'visao': c['visao'], 'visoes': _pares(c['visoes']),
        'prioridade': c['prioridade'], 'categoria': c['categoria'],
        'prioridades': _pares(c['prioridades']), 'categorias': _pares(c['categorias']),
        'numeros': numeros_escritos(c['numeros']),
        'pode_abrir': c['pode_abrir'],
    })


@api.get('/chamados/novo')
@login_required
@module_required(MODULO)
def api_chamados_novo():
    c = chr_.contexto_novo(request.args)
    return _sem_cache({
        'contratos': [{'id': x.id, 'nome': x.name} for x in c['contratos']],
        'areas': {str(k): v for k, v in c['areas'].items()},
        'client_id': c['client_id'],
        'prioridades': _pares(c['prioridades']), 'categorias': _pares(c['categorias']),
    })


def _pausa(seg):
    return f'{seg // 3600} h {(seg % 3600) // 60} min aguardando (somado ao prazo)'


@api.get('/chamados/<int:chamado_id>')
@login_required
@module_required(MODULO)
def api_chamados_ver(chamado_id):
    from facilities.materiais import servico as materiais
    from facilities.materiais.models import fmt_qtd
    c = chr_.contexto_ver(chamado_id)
    ch, agora, ve_custo = c['ch'], c['agora'], c['ve_custo']

    def consumo(x):
        mov = x.movimento
        return {'quantidade': fmt_qtd(-mov.quantidade), 'unidade': mov.material.unidade,
                'material': mov.material.nome, 'pessoa': mov.pessoa.name,
                'quando': _hora(mov.criado_em, '%d/%m %H:%M'),
                'valor': ((materiais.reais(mov.valor) if mov.valor is not None else 'sem preço')
                          if ve_custo else None)}
    return _sem_cache({
        'chamado': {
            **_resumo(ch, agora),
            'client_id': ch.client_id,
            'solicitante': ch.solicitante.name, 'aberto_em': _hora(ch.aberto_em),
            'responsavel_id': ch.responsavel_id,
            'prazo': _hora(ch.prazo) if ch.prazo else '—',
            'origem': ch.origem,
            'visita': (nova(url_for('visitas.ver', vid=ch.origem_id))
                       if ch.origem == 'visita' else None),
            'pausa': _pausa(ch.pausa_total_seg) if ch.pausa_total_seg else None,
            'descricao': ch.descricao or '', 'motivo_espera': ch.motivo_espera or '',
            'solucao': ch.solucao or '',
        },
        'acoes': c['acoes'],
        'tecnicos': [{'id': t.id, 'nome': t.name, 'perfil': t.perfil_rotulo}
                     for t in c['tecnicos']],
        'prioridades': _pares(c['prioridades']),
        'eventos': [{'tipo': e.tipo, 'autor': e.autor.name if e.autor else 'Sistema',
                     'rotulo': ROTULO_EVENTO.get(e.tipo, e.tipo), 'quando': _hora(e.created_at),
                     'texto': e.texto or ''} for e in ch.eventos],
        'anexos': [{'id': a.id, 'nome': a.nome, 'momento': a.momento,
                    'imagem': (a.mime or '').startswith('image/'),
                    'url': url_for('chamados.baixar_anexo', anexo_id=a.id)} for a in ch.anexos],
        'pode_anexar': c['pode_anexar'],
        'consumos': [consumo(x) for x in c['consumos']],
        've_custo': ve_custo,
        'materiais': [{'id': m.id, 'nome': m.nome, 'unidade': m.unidade} for m in c['materiais']],
    })


# ── Chamados: os envios (a mesma ação das telas antigas) ──────────────────

@api.post('/chamados/')
@login_required
@module_required(MODULO)
def api_chamados_criar():
    return _feito(chr_.acao_criar(_dados(), request.files))


@api.post('/chamados/<int:chamado_id>/acao')
@login_required
@module_required(MODULO)
def api_chamados_acao(chamado_id):
    return _feito(chr_.acao_executar(chamado_id, _dados(), request.files))


@api.post('/chamados/<int:chamado_id>/anexos')
@login_required
@module_required(MODULO)
def api_chamados_anexar(chamado_id):
    return _feito(chr_.acao_anexar(chamado_id, _dados(), request.files))


@api.post('/materiais/locais/<int:cid>/consumo')
@login_required
def api_materiais_consumo(cid):
    from facilities.materiais.telas import acao_consumo
    return _feito(acao_consumo(cid, _dados()))


# ── Demandas: os dados ────────────────────────────────────────────────────

@api.get('/demandas/')
@login_required
def api_demandas_painel():
    c = dem.contexto_painel(request.args)
    tipos, situacoes = c['tipos'], c['situacoes']
    return _sem_cache({
        'itens': [{'tipo': i['tipo'], 'tipo_rotulo': tipos[i['tipo']],
                   'situacao': i['situacao'], 'situacao_rotulo': situacoes[i['situacao']],
                   'numero': i['numero'] or '', 'titulo': i['titulo'], 'local': i['local'],
                   'estado': i['estado'], 'responsavel': i['responsavel'] or '',
                   'prazo': _hora(i['prazo'], '%d/%m %H:%M') if i['prazo'] else None,
                   'link': nova(i['link'])} for i in c['itens']],
        'locais': [{'id': x.id, 'nome': x.name} for x in c['locais']],
        'local': c['cid'], 'tipo': c['tipo'], 'situacao': c['situacao'],
        'tipos': _pares(tipos), 'situacoes': _pares(situacoes),
        'contagem': c['contagem'],
        'links': {'cobrancas': url_for('cobrancas.lista')},
    })


# ── Preventiva: os dados e os envios ──────────────────────────────────────

@api.get('/preventiva/locais/<int:cid>')
@login_required
def api_preventiva_local(cid):
    c = prv.contexto_local(cid)
    loc, prioridades = c['local'], c['prioridades']

    def ciclo(x):
        ch = x.chamado
        return {'vencimento': x.vencimento.strftime('%d/%m/%Y'),
                'chamado': ({'url': nova(url_for('chamados.ver', chamado_id=ch.id)),
                             'numero': ch.numero, 'status_rotulo': ch.status_rotulo}
                            if ch else None)}

    def plano(p):
        return {
            'id': p.id, 'nome': p.nome, 'ativo': bool(p.is_active),
            'ponto_id': p.ponto_id, 'ponto': f'{p.ponto.ambiente.nome} · {p.ponto.nome}',
            'equipamento_id': p.equipamento_id,
            'equipamento': p.equipamento.nome if p.equipamento else None,
            'modelo_id': p.modelo_id, 'modelo': p.modelo.nome,
            'intervalo_dias': p.intervalo_dias, 'antecedencia_dias': p.antecedencia_dias,
            'proxima_em': p.proxima_em.strftime('%d/%m/%Y'),
            'proxima_em_iso': p.proxima_em.isoformat(),
            'prioridade': p.prioridade, 'prioridade_rotulo': prioridades[p.prioridade],
            'responsavel_id': p.responsavel_id,
            'responsavel': p.responsavel.name if p.responsavel else None,
            'ciclos': [ciclo(x) for x in p.ciclos[:3]],
        }
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'planos': [plano(p) for p in c['planos']],
        # Com o item desativado que um plano ainda usa (só no "Editar" dele).
        'modelos': [{'id': m.id, 'nome': m.nome, 'ativo': bool(m.is_active)} for m in c['modelos']],
        'pontos': [{'id': p.id, 'rotulo': f'{p.ambiente.nome} · {p.nome}', 'ativo': bool(p.is_active)}
                   for p in c['pontos']],
        'equipamentos': [{'id': e.id, 'nome': e.nome, 'ativo': bool(e.is_active)}
                         for e in c['equipamentos']],
        'tecnicos': [{'id': t.id, 'nome': t.name} for t in c['tecnicos']],
        'prioridades': _pares(prioridades), 'hoje': c['hoje'],
        'pode_montar': c['pode_montar'],
        'links': {'pontos': nova(url_for('cadastros.local', cid=loc.id)),
                  'checklists': nova(url_for('rotas.local', cid=loc.id))},
    })


@api.post('/preventiva/locais/<int:cid>')
@login_required
def api_preventiva_criar(cid):
    return _feito(prv.acao_criar(cid, _dados()))


@api.post('/preventiva/<int:pid>')
@login_required
def api_preventiva_editar(pid):
    return _feito(prv.acao_editar(pid, _dados()))
