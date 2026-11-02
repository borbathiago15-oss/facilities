"""API das telas novas da rotina dos locais (Fase 3b da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/rotas/`` (o início: um cartão por local) e
  ``/novo/rotas/locais/<id>`` (checklists e rotas do local);
* ``/novo/rotas/biblioteca``, ``/novo/rotas/biblioteca/rotas/nova`` e
  ``/novo/rotas/biblioteca/rotas/<id>`` (a biblioteca da Trino e as rotas
  prontas);
* ``/novo/rotas/locais/<id>/rota-pronta`` (aplicar uma rota pronta) e
  ``/novo/rotas/locais/<id>/importar-plano`` (a planilha do cliente);
* ``/novo/rotas/modelos/<id>`` (o checklist: perguntas, POP/FIT e versões);
* ``/novo/rotas/<id>`` (a rota: atividades, escala e turno);
* ``/novo/rotas/locais/<id>/feriados``, ``/novo/rotas/locais/<id>/dia`` e
  ``/novo/rotas/execucoes/<id>`` (o acompanhamento).

Cada página tem a mesma porta da antiga e entrega a casca React. Os dados
vêm da MESMA função que monta a tela antiga (``rotas.telas.contexto_*``) e
aqui só viram JSON, em ``/api/v1/rotas/...``. Os envios vão para o MESMO
caminho da antiga abaixo de ``/api/v1``, que chama a MESMA ação
(``acao_*``): a resposta é o recado e o endereço de volta, já na tela nova;
a recusa da regra é 400 com a mesma frase. A prévia da planilha volta como
dados (na antiga, é a página da resposta do envio). Os arquivos (POP/FIT, as
fotos e as referências) continuam no servidor. Sem cópia no aparelho.
"""
from flask import request, url_for
from flask_login import login_required

from facilities.rotas import publico
from facilities.rotas import telas as rt
from facilities.rotas.gps import texto as texto_gps
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _recados, _sem_cache, nova


def _hm(t):
    return t.strftime('%H:%M') if t else ''


def _dias(dias):
    return [[k, v] for k, v in dias.items()]


def _jinja(v):
    """O valor como o ``{{ v }}`` da tela antiga escreve."""
    return str(v)


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/rotas/')
@login_required
def rotas_inicio():
    rt.contexto_inicio()
    return _casca()


@bp.get('/novo/rotas/biblioteca')
@login_required
def rotas_biblioteca():
    rt.contexto_biblioteca()
    return _casca()


@bp.get('/novo/rotas/biblioteca/rotas/nova')
@login_required
def rotas_rota_pronta_nova():
    rt.contexto_rota_pronta(None)
    return _casca()


@bp.get('/novo/rotas/biblioteca/rotas/<int:rmid>')
@login_required
def rotas_rota_pronta(rmid):
    rt._rota_pronta(rmid)
    return _casca()


@bp.get('/novo/rotas/locais/<int:cid>')
@bp.get('/novo/rotas/locais/<int:cid>/feriados')
@bp.get('/novo/rotas/locais/<int:cid>/dia')
@login_required
def rotas_local(cid):
    rt._local(cid)
    return _casca()


@bp.get('/novo/rotas/locais/<int:cid>/rota-pronta')
@bp.get('/novo/rotas/locais/<int:cid>/importar-plano')
@login_required
def rotas_local_montar(cid):
    rt._local(cid, montar=True)
    return _casca()


@bp.get('/novo/rotas/modelos/<int:mid>')
@login_required
def rotas_modelo(mid):
    rt._modelo(mid)
    return _casca()


@bp.get('/novo/rotas/<int:rid>')
@login_required
def rotas_rota(rid):
    rt._rota(rid)
    return _casca()


@bp.get('/novo/rotas/execucoes/<int:eid>')
@login_required
def rotas_execucao(eid):
    rt._execucao(eid)
    return _casca()


# ── Início, local e biblioteca: os dados ──────────────────────────────────

def _links_do_local(cid):
    """As telas de outros módulos, já novas (a estrutura; a preventiva desde
    a Fase 4a; a equipe e as visitas desde a 4b)."""
    return {'preventiva': nova(url_for('preventiva.local', cid=cid)),
            'equipe': nova(url_for('equipes.local', cid=cid)),
            'visitas': nova(url_for('visitas.local', cid=cid)),
            'estrutura': nova(url_for('cadastros.local', cid=cid))}


@api.get('/rotas/inicio')
@login_required
def api_rotas_inicio():
    c = rt.contexto_inicio()
    return _sem_cache({
        'locais': [{'id': x.id, 'nome': x.name,
                    'cliente': x.contratante.nome if x.contratante else None,
                    'links': _links_do_local(x.id)} for x in c['locais']],
        'pode_montar': c['pode_montar'],
    })


def _versao(m):
    return m.versao_atual.numero if m.versao_atual else None


@api.get('/rotas/locais/<int:cid>')
@login_required
def api_rotas_local(cid):
    c = rt.contexto_local(cid)
    loc = c['local']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'modelos': [{'id': m.id, 'nome': m.nome, 'versao': _versao(m),
                     'copia': bool(m.origem_id)} for m in c['modelos']],
        'biblioteca': [{'id': b.id, 'nome': b.nome} for b in c['biblioteca']],
        'rotas': [{'id': r.id, 'nome': r.nome, 'turno': r.turno, 'inicio': _hm(r.hora_inicio),
                   'fim': _hm(r.hora_fim), 'atividades': len(r.itens),
                   'ativa': bool(r.is_active)} for r in c['rotas']],
        'pode_montar': c['pode_montar'],
        've_estrutura': c['ve_estrutura'],
        'dias': _dias(c['dias']),
        'links': _links_do_local(loc.id),
    })


@api.get('/rotas/biblioteca')
@login_required
def api_rotas_biblioteca():
    c = rt.contexto_biblioteca()
    return _sem_cache({
        'modelos': [{'id': m.id, 'nome': m.nome, 'versao': _versao(m)} for m in c['modelos']],
        'rotas_prontas': [{'id': r.id, 'segmento': r.segmento, 'nome': r.nome,
                           'ambientes': len(r.itens), 'inicio': _hm(r.hora_inicio),
                           'fim': _hm(r.hora_fim), 'ativa': bool(r.is_active)}
                          for r in c['rotas_prontas']],
        'pode_montar': c['pode_montar'],
    })


# ── Rotas prontas: os dados ───────────────────────────────────────────────

def _rota_modelo(m):
    if m is None:
        return None
    return {'id': m.id, 'nome': m.nome, 'segmento': m.segmento, 'descricao': m.descricao or '',
            'turno': m.turno, 'inicio': _hm(m.hora_inicio), 'fim': _hm(m.hora_fim),
            'tolerancia_min': m.tolerancia_min, 'dias_semana': m.dias_semana or '',
            'ativa': bool(m.is_active)}


def _api_rota_pronta(rmid):
    c = rt.contexto_rota_pronta(rmid)
    return _sem_cache({
        'modelo': _rota_modelo(c['modelo']),
        # As linhas do formulário (as em branco no fim), como a antiga escreve.
        'linhas': [{'setor': ln.get('setor') or '', 'ambiente': ln.get('ambiente') or '',
                    'checklist_id': ln.get('checklist_id'),
                    'horarios': ln.get('horarios') or '',
                    'quantidade': ln.get('quantidade') or 1,
                    'tempo_previsto_min': ln.get('tempo_previsto_min') or ''}
                   for ln in c['linhas']],
        'checklists': [{'id': m.id, 'nome': m.nome} for m in c['checklists']],
        'dias': _dias(c['dias']),
        'pode_montar': c['pode_montar'],
    })


@api.get('/rotas/biblioteca/rotas/nova')
@login_required
def api_rotas_rota_pronta_nova():
    return _api_rota_pronta(None)


@api.get('/rotas/biblioteca/rotas/<int:rmid>')
@login_required
def api_rotas_rota_pronta(rmid):
    return _api_rota_pronta(rmid)


@api.get('/rotas/locais/<int:cid>/rota-pronta')
@login_required
def api_rotas_aplicar_rota_pronta(cid):
    c = rt.contexto_aplicar_rota_pronta(cid, request.args.get('modelo', ''))
    return _sem_cache({
        'local': {'id': c['local'].id, 'nome': c['local'].name},
        'opcoes': [{'id': o.id, 'segmento': o.segmento, 'nome': o.nome} for o in c['opcoes']],
        'modelo': _rota_modelo(c['modelo']),
        'linhas': [{'setor': ln['setor'], 'ambiente': ln['ambiente'],
                    'checklist_id': ln['checklist_id'], 'checklist': ln['checklist'],
                    'horarios': ln['horarios'],
                    'tempo_previsto_min': ln.get('tempo_previsto_min') or ''}
                   for ln in c['linhas']],
        'dias': _dias(c['dias']),
    })


# ── Plano de limpeza (planilha): os dados ─────────────────────────────────

@api.get('/rotas/locais/<int:cid>/importar-plano')
@login_required
def api_rotas_importar_plano(cid):
    c = rt.contexto_importar_plano(cid)
    return _sem_cache({'local': {'id': c['local'].id, 'nome': c['local'].name},
                       'dias': _dias(c['dias'])})


def dados_da_previa(c):
    p = c['previa']
    return {
        'avisos': list(p.avisos),
        'blocos': [{'setor': b.setor, 'nome': b.nome, 'atividades': b.atividades,
                    'existe': bool(b.existe)} for b in p.blocos],
        'checklists': [{'nome': k.nome, 'itens': [it['texto'] for it in k.itens],
                        'materiais': k.materiais or '', 'epi': k.epi or '',
                        'existe': bool(k.existe)} for k in p.checklists],
        'rotas': [{
            'nome': r.nome, 'existe': bool(r.existe), 'turno': r.turno,
            'hora_inicio': r.hora_inicio, 'hora_fim': r.hora_fim,
            'intervalo_inicio': r.intervalo_inicio, 'intervalo_fim': r.intervalo_fim,
            'dias_semana': r.dias_semana, 'tolerancia_min': r.tolerancia_min,
            'responsavel': r.responsavel or '', 'observacoes': r.observacoes or '',
            'itens': [{'ordem': it.ordem, 'horario': it.horario,
                       'tempo_previsto_min': it.tempo_previsto_min, 'bloco': it.bloco.rotulo,
                       'checklist': it.checklist.nome, 'dias_semana': it.dias_semana or '',
                       'horarios_por_dia': [[d, h] for d, h in it.horarios_por_dia.items()]}
                      for it in r.itens],
        } for r in p.rotas],
    }


# ── Checklist: os dados ───────────────────────────────────────────────────

def _texto_do_minimo(it, chave):
    v = it.get(chave)
    return '' if v is None else _jinja(v)


@api.get('/rotas/modelos/<int:mid>')
@login_required
def api_rotas_modelo(mid):
    c = rt.contexto_modelo(mid)
    m, pode = c['modelo'], c['pode_montar']
    v = m.versao_atual

    def item(it):
        saida = {
            'codigo': it.get('codigo') or '', 'texto': it.get('texto') or '',
            'tipo': it.get('tipo'), 'obrigatorio': bool(it.get('obrigatorio')),
            'exige_foto': bool(it.get('exige_foto')),
            'opcoes': '; '.join(it.get('opcoes') or []),
            'minimo': _texto_do_minimo(it, 'minimo'), 'maximo': _texto_do_minimo(it, 'maximo'),
            'problema_se': it.get('problema_se') or '',
            'mostrar_se': (f"{it['mostrar_se']['codigo']}={it['mostrar_se']['valor']}"
                           if it.get('mostrar_se') else ''),
            'como_fazer': it.get('como_fazer') or '',
            'referencia': (url_for('rotas.referencia', vid=v.id, codigo=it['codigo'])
                           if it.get('foto_ref') and v else None),
        }
        if pode:
            # O formulário devolve a chave da foto guardada (o campo escondido
            # da tela antiga); quem só lê não recebe.
            saida['foto_ref'] = it.get('foto_ref') or ''
        return saida
    return _sem_cache({
        'modelo': {'id': m.id, 'nome': m.nome, 'descricao': m.descricao or '',
                   'local': ({'id': m.client_id, 'nome': m.local.name} if m.client_id else None),
                   'exige_foto_antes': bool(m.exige_foto_antes),
                   'exige_foto_depois': bool(m.exige_foto_depois)},
        'versao': ({'numero': v.numero, 'publicada_em': _hora(v.publicada_em),
                    'materiais': v.materiais or '', 'epi': v.epi or ''} if v else None),
        'itens': [item(it) for it in c['itens']],
        'linhas_em_branco': rt.LINHAS_EM_BRANCO,
        'tipos': _dias(c['tipos']),
        'pode_montar': pode,
        'documentos': [{'id': d.id, 'nome': d.nome, 'url': url_for('rotas.documento', did=d.id),
                        'enviado_em': _hora(d.enviado_em, '%d/%m/%Y'),
                        'visivel_cliente': bool(d.visivel_cliente)} for d in c['documentos']],
        'limite_docs': c['limite_docs'],
    })


# ── Feriados: os dados ────────────────────────────────────────────────────

@api.get('/rotas/locais/<int:cid>/feriados')
@login_required
def api_rotas_feriados(cid):
    c = rt.contexto_feriados(cid, request.args.get('ano'))
    return _sem_cache({
        'local': {'id': c['local'].id, 'nome': c['local'].name},
        'ano': c['ano'],
        'lista': [{'data': d.strftime('%d/%m'), 'passou': d < c['hoje'], 'nome': nome,
                   'id': f.id if f else None} for d, nome, f in c['lista']],
        'rotas_param': [r.nome for r in c['rotas_param']],
        'pode_montar': c['pode_montar'],
    })


# ── A rota: os dados ──────────────────────────────────────────────────────

@api.get('/rotas/<int:rid>')
@login_required
def api_rotas_rota(rid):
    c = rt.contexto_rota(rid)
    r, dias = c['rota'], c['dias']
    return _sem_cache({
        'rota': {'id': r.id, 'nome': r.nome, 'turno': r.turno, 'inicio': _hm(r.hora_inicio),
                 'fim': _hm(r.hora_fim), 'intervalo_inicio': _hm(r.intervalo_inicio),
                 'intervalo_fim': _hm(r.intervalo_fim), 'tolerancia_min': r.tolerancia_min,
                 'dias_semana': r.dias_semana or '', 'ativa': bool(r.is_active),
                 'observacoes': r.observacoes or '',
                 'presencas_por_turno': r.presencas_por_turno,
                 'presenca_prazo_min': r.presenca_prazo_min,
                 'funciona_em_feriado': bool(r.funciona_em_feriado),
                 'local': {'id': r.client_id, 'nome': r.local.name}},
        'itens': [{
            'id': it.id, 'ativo': bool(it.is_active), 'ponto_id': it.ponto_id,
            'ponto': f'{it.ponto.ambiente.nome} · {it.ponto.nome}', 'modelo_id': it.modelo_id,
            'modelo': it.modelo.nome, 'ordem': it.ordem, 'horarios': it.horarios or '',
            'frequencia_min': it.frequencia_min, 'tempo_previsto_min': it.tempo_previsto_min,
            'dias_semana': it.dias_semana or '',
            'horarios_por_dia': [[dias.get(d, d), hs] for d, hs in it.horarios_por_dia_dict.items()],
            'hoje': [h.strftime('%H:%M') for h in c['horarios'](it)],
        } for it in r.itens],
        'pontos': [{'id': p.id, 'setor': p.ambiente.setor.nome, 'ambiente': p.ambiente.nome,
                    'nome': p.nome} for p in c['pontos']],
        'modelos': [{'id': m.id, 'nome': m.nome} for m in c['modelos']],
        'pessoas': [{'id': p.id, 'nome': p.name, 'perfil': p.perfil_rotulo} for p in c['pessoas']],
        'escalas': [{'id': e.id, 'nome': e.pessoa.name, 'dias_semana': e.dias_semana or '',
                     'desde': e.data_inicio.strftime('%d/%m/%Y'),
                     'ate': e.data_fim.strftime('%d/%m/%Y') if e.data_fim else None}
                    for e in r.escalas if e.is_active],
        'pode_montar': c['pode_montar'],
        'dias': _dias(dias),
        'hoje': c['hoje'],
        'links': {'estrutura': nova(url_for('cadastros.local', cid=r.client_id))},
    })


# ── O dia e a execução: os dados ──────────────────────────────────────────

def _gps(r):
    return {'situacao': r.gps_situacao, 'texto': texto_gps(r.gps_situacao, r.gps_distancia_m),
            'precisao': r.gps_precisao_m}


@api.get('/rotas/locais/<int:cid>/dia')
@login_required
def api_rotas_dia(cid):
    c = rt.contexto_dia(cid, request.args.get('data'))
    agora, troca = c['agora'], c['motivos_troca']

    def execucao(ex):
        return {'id': ex.id, 'pessoa': ex.pessoa.name, 'inicio': _hora(ex.iniciada_em, '%H:%M'),
                'fim': _hora(ex.concluida_em, '%H:%M'), 'sem_sinal': bool(ex.sem_sinal),
                'nao_conformes': ex.n_nao_conformes, 'gps': _gps(ex),
                'adiantada': bool(ex.adiantada),
                'motivo_troca': troca.get(ex.motivo_troca, ex.motivo_troca) if ex.motivo_troca else '',
                'motivo_troca_texto': ex.motivo_troca_texto or ''}

    def tarefa(t):
        s = c['situacao'](t, agora)
        return {
            'id': t.id, 'hora': _hora(t.previsto_para, '%H:%M'), 'ambiente': t.ponto.ambiente.nome,
            'ponto': t.ponto.nome, 'modelo': t.versao.modelo.nome, 'rota': t.rota.nome,
            'situacao': s, 'situacao_rotulo': c['situacoes'].get(s, s),
            'execucao': execucao(t.execucoes[0]) if t.execucoes else None,
            'nao_realizada': ({'motivo': c['motivos'].get(t.motivo, t.motivo),
                               'texto': t.motivo_texto or '',
                               'chamado': (nova(url_for('chamados.ver', chamado_id=t.chamado_id))
                                           if t.chamado_id else None)}
                              if t.status == 'nao_realizada' else None),
            'pessoa': t.pessoa.name if t.pessoa else None,
        }

    def ocorrencia(o):
        return {
            'id': o.id, 'hora': _hora(o.criada_em, '%H:%M'), 'ambiente': o.ponto.ambiente.nome,
            'ponto': o.ponto.nome, 'titulo': o.titulo,
            'responsavel': o.responsavel.name if o.responsavel else None, 'texto': o.texto or '',
            'foto': url_for('publico.foto_da_ocorrencia', oid=o.id) if o.foto_key else None,
            'status': o.status, 'situacao': c['situacoes_ocorrencia'][o.status],
            'atrasada': bool(c['atrasada'](o, agora)),
            'prazo': _hora(o.prazo, '%H:%M') if o.prazo else None,
            'resolvida': ({'quem': o.quem_resolveu.name, 'hora': _hora(o.resolvida_em, '%H:%M'),
                           'resolucao': o.resolucao or ''} if o.status == 'resolvida' else None),
        }
    return _sem_cache({
        'local': {'id': c['local'].id, 'nome': c['local'].name},
        'data': c['data'].isoformat(), 'data_br': c['data'].strftime('%d/%m/%Y'),
        'data_curta': c['data'].strftime('%d/%m'),
        'aderencia': c['aderencia'],
        'tarefas': [tarefa(t) for t in c['tarefas']],
        'ocorrencias': [ocorrencia(o) for o in c['ocorrencias']],
        'elogios': [{'id': e.id, 'hora': _hora(e.criado_em, '%H:%M'),
                     'ambiente': e.ponto.ambiente.nome, 'ponto': e.ponto.nome, 'nota': e.nota,
                     'texto': e.texto or '',
                     'responsavel': e.responsavel.name if e.responsavel else None}
                    for e in c['elogios']],
        'chegadas': [{'id': x.id, 'hora': _hora(x.chegou_em, '%H:%M'), 'pessoa': x.pessoa.name,
                      'com_camera': bool(x.com_camera), 'gps': _gps(x)} for x in c['chegadas']],
        'presencas': [{'id': x.id, 'hora': _hora(x.pedido_em, '%H:%M'), 'pessoa': x.pessoa.name,
                       'rota': x.rota.nome, 'status': x.status,
                       'respondida': _hora(x.respondida_em, '%H:%M') if x.respondida_em else None}
                      for x in c['presencas']],
        'extras': [{'id': ex.id, 'hora': _hora(ex.concluida_em, '%H:%M'), 'ponto': ex.ponto.nome,
                    'modelo': ex.versao.modelo.nome, 'pessoa': ex.pessoa.name, 'gps': _gps(ex),
                    'motivo_troca': troca.get(ex.motivo_troca, ex.motivo_troca) if ex.motivo_troca else '',
                    'motivo_troca_texto': ex.motivo_troca_texto or ''} for ex in c['extras']],
        'pode_atender': c['pode_atender'],
    })


@api.get('/rotas/execucoes/<int:eid>')
@login_required
def api_rotas_execucao(eid):
    c = rt.contexto_execucao(eid)
    ex, respostas, originais = c['ex'], c['respostas'], c['originais']
    t = ex.tarefa
    return _sem_cache({
        'execucao': {
            'id': ex.id, 'client_id': ex.client_id, 'ambiente': ex.ponto.ambiente.nome,
            'ponto': ex.ponto.nome, 'modelo': ex.versao.modelo.nome, 'versao': ex.versao.numero,
            'extra': bool(ex.extra), 'pessoa': ex.pessoa.name, 'lido_em': _hora(ex.lido_em),
            'concluida_em': _hora(ex.concluida_em), 'sem_sinal': bool(ex.sem_sinal),
            'recebida_em': _hora(ex.recebida_em), 'gps': _gps(ex) if ex.gps_situacao else None,
            'tarefa': {'hora': _hora(t.previsto_para, '%H:%M'), 'rota': t.rota.nome} if t else None,
            'adiantada': bool(ex.adiantada),
            'motivo_troca': (c['motivos_troca'].get(ex.motivo_troca, ex.motivo_troca)
                             if ex.motivo_troca else ''),
            'motivo_troca_texto': ex.motivo_troca_texto or '',
            'observacao': ex.observacao or '',
            'dia': _hora(ex.iniciada_em, '%Y-%m-%d'),
        },
        'respostas': [{'codigo': it['codigo'], 'texto': it['texto'],
                       'resposta': _jinja(respostas[it['codigo']]),
                       'corrigida': originais.get(it['codigo']) != respostas.get(it['codigo']),
                       'original': _jinja(originais.get(it['codigo'], '—'))}
                      for it in c['itens'] if it['codigo'] in respostas],
        'itens': [{'codigo': it['codigo'], 'texto': it['texto'],
                   'valor': _jinja(respostas.get(it['codigo'], ''))} for it in c['itens']],
        'fotos': [{'id': f.id, 'url': url_for('rotas.foto', fid=f.id), 'momento': f.momento,
                   'rotulo': {'antes': 'Antes', 'depois': 'Depois'}.get(f.momento, f.item_codigo)}
                  for f in ex.fotos],
        'nao_conformidades': [{'id': nc.id, 'item_texto': nc.item_texto, 'resposta': nc.resposta,
                               'chamado': (nova(url_for('chamados.ver', chamado_id=nc.chamado_id))
                                           if nc.chamado_id else None)}
                              for nc in ex.nao_conformidades],
        'correcoes': [{'quando': _hora(x.created_at), 'autor': x.autor.name, 'motivo': x.motivo}
                      for x in ex.correcoes],
        'pode_corrigir': c['pode_corrigir'],
    })


# ── Os envios: a mesma ação das telas antigas ─────────────────────────────

@api.post('/rotas/biblioteca/rotas/nova')
@login_required
def api_rotas_salvar_rota_pronta_nova():
    return _feito(rt.acao_salvar_rota_pronta(None, _dados()))


@api.post('/rotas/biblioteca/rotas/<int:rmid>')
@login_required
def api_rotas_salvar_rota_pronta(rmid):
    return _feito(rt.acao_salvar_rota_pronta(rmid, _dados()))


@api.post('/rotas/biblioteca/rotas/<int:rmid>/ativo')
@login_required
def api_rotas_ativo_rota_pronta(rmid):
    return _feito(rt.acao_ativo_rota_pronta(rmid))


@api.post('/rotas/locais/<int:cid>/rota-pronta/<int:rmid>')
@login_required
def api_rotas_aplicar_rota_pronta_post(cid, rmid):
    return _feito(rt.acao_aplicar_rota_pronta(cid, rmid, _dados()))


@api.post('/rotas/locais/<int:cid>/importar-plano')
@login_required
def api_rotas_importar_plano_previa(cid):
    """A prévia da planilha: na antiga é a página da resposta; aqui, os dados
    dela (a tela nova desenha a prévia e o "Criar")."""
    destino, c = rt.acao_importar_plano_previa(cid, request.files)
    if destino:
        return _feito(destino)
    return _sem_cache({'previa': dados_da_previa(c), 'chave': c['chave'],
                       'ja_existem': list(c['ja_existem']), 'recados': _recados()})


@api.post('/rotas/locais/<int:cid>/importar-plano/criar')
@login_required
def api_rotas_importar_plano_criar(cid):
    return _feito(rt.acao_importar_plano_criar(cid, _dados()))


@api.post('/rotas/biblioteca/modelos-prontos')
@login_required
def api_rotas_instalar_modelos_prontos():
    return _feito(rt.acao_instalar_modelos_prontos())


@api.post('/rotas/biblioteca')
@login_required
def api_rotas_criar_na_biblioteca():
    return _feito(rt.acao_criar_na_biblioteca(_dados()))


@api.post('/rotas/locais/<int:cid>/modelos')
@login_required
def api_rotas_criar_modelo(cid):
    return _feito(rt.acao_criar_modelo(cid, _dados()))


@api.post('/rotas/locais/<int:cid>/copiar')
@login_required
def api_rotas_copiar(cid):
    return _feito(rt.acao_copiar(cid, _dados()))


@api.post('/rotas/modelos/<int:mid>')
@login_required
def api_rotas_publicar(mid):
    return _feito(rt.acao_publicar(mid, _dados(), request.files))


@api.post('/rotas/modelos/<int:mid>/documentos')
@login_required
def api_rotas_anexar_documento(mid):
    return _feito(rt.acao_anexar_documento(mid, request.files))


@api.post('/rotas/documentos/<int:did>/<acao>')
@login_required
def api_rotas_acao_documento(did, acao):
    return _feito(rt.acao_mudar_documento(did, acao))


@api.post('/rotas/locais/<int:cid>/feriados')
@login_required
def api_rotas_criar_feriado(cid):
    return _feito(rt.acao_criar_feriado(cid, _dados()))


@api.post('/rotas/locais/<int:cid>/feriados/<int:fid>/remover')
@login_required
def api_rotas_remover_feriado(cid, fid):
    return _feito(rt.acao_remover_feriado(cid, fid))


@api.post('/rotas/locais/<int:cid>/rotas')
@login_required
def api_rotas_criar_rota(cid):
    return _feito(rt.acao_criar_rota(cid, _dados()))


@api.post('/rotas/<int:rid>')
@login_required
def api_rotas_editar_rota(rid):
    return _feito(rt.acao_editar_rota(rid, _dados()))


@api.post('/rotas/<int:rid>/ativo')
@login_required
def api_rotas_ativo_rota(rid):
    return _feito(rt.acao_ativo_rota(rid, _dados()))


@api.post('/rotas/<int:rid>/itens')
@login_required
def api_rotas_criar_item(rid):
    return _feito(rt.acao_criar_item(rid, _dados()))


@api.post('/rotas/<int:rid>/itens/<int:iid>')
@login_required
def api_rotas_editar_item(rid, iid):
    return _feito(rt.acao_editar_item(rid, iid, _dados()))


@api.post('/rotas/<int:rid>/escalas')
@login_required
def api_rotas_criar_escala(rid):
    return _feito(rt.acao_criar_escala(rid, _dados()))


@api.post('/rotas/<int:rid>/escalas/<int:eid>/encerrar')
@login_required
def api_rotas_encerrar_escala(rid, eid):
    return _feito(rt.acao_encerrar_escala(rid, eid))


@api.post('/rotas/execucoes/<int:eid>/corrigir')
@login_required
def api_rotas_corrigir(eid):
    return _feito(rt.acao_corrigir(eid, _dados()))


@api.post('/rotas/nao-conformidades/<int:nid>/chamado')
@login_required
def api_rotas_chamado_da_nc(nid):
    return _feito(rt.acao_chamado_da_nc(nid))


@api.post('/rotas/ocorrencias/<int:oid>/<acao>')
@login_required
def api_rotas_ocorrencia(oid, acao):
    return _feito(publico.acao_ocorrencia_no_site(oid, acao, _dados().get('data')))
