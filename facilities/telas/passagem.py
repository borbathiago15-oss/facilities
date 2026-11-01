"""API das telas novas da Passagem de turno (Fases 2a e 2b da migração para React).

* ``/novo/passagem-de-turno/turno``: a nova passagem (o encarregado preenche);
* ``/novo/passagem-de-turno/turno/<id>``: a passagem já lançada, para leitura;
* ``/novo/passagem-de-turno/``: o painel da gestão (2b);
* ``/novo/passagem-de-turno/relatorio-mensal``: o fechamento do mês (2b);
* ``/novo/passagem-de-turno/configuracao``: os modelos de passagem (2b).

Cada página tem a mesma porta da antiga (``login_required``,
``module_required`` e, na nova passagem, o ``can_access``; na leitura, a
carteira do ``_turno_autorizado``; na configuração, a permissão fina
``diario_config``) e entrega a casca React. Os dados vêm da MESMA função que
monta a tela antiga (``passagem.rotas.contexto_*``), aqui só viram JSON:

* ``/api/v1/passagem/turno?client_id=``  → a nova passagem;
* ``/api/v1/passagem/turno/<id>``        → a leitura;
* ``/api/v1/passagem/painel?...``        → o painel (o mesmo recorte da antiga);
* ``/api/v1/passagem/relatorio-mensal?client_id=&mes=&ano=&area_id=`` → o relatório;
* ``/api/v1/passagem/configuracao?client_id=&editar=`` → a configuração.

As ações continuam nas APIs de sempre (``/passagem-de-turno/api/...``), como
estão; a fila sem internet é a mesma (``fila-offline.js``, carregada pela
casca). O PDF do relatório continua no servidor (``?format=pdf`` da rota
antiga). As telas da gestão não têm cópia no aparelho (sw.js).
"""
from flask import abort, current_app, get_flashed_messages, jsonify, request, url_for
from flask_login import current_user, login_required

from facilities.core.acesso import module_required, permissao_requerida
from facilities.passagem import rotas as passagem
from facilities.telas import _casca, api, bp

MODULO = passagem.MODULO


def _hora(dt, fmt='%d/%m/%Y %H:%M'):
    """A mesma hora que a tela antiga escreve (o filtro ``hora_local``)."""
    return current_app.jinja_env.filters['hora_local'](dt, fmt)


def _dia(d, fmt='%d/%m'):
    return d.strftime(fmt) if d else None


def nova(caminho, **params):
    """O endereço da tela nova da passagem (``/novo/passagem-de-turno/...``)."""
    return url_for('telas.casca', caminho='passagem-de-turno/' + caminho, **params)


def _anexo(a, quem_anexou=None):
    return {'id': a.id, 'nome': a.nome or '', 'mime': a.mime or '',
            'url': url_for('diario_operacional.baixar_anexo', anexo_id=a.id),
            'anexado_por': (quem_anexou or {}).get(a.uploaded_by)}


def _sem_cache(dados):
    resp = jsonify(dados)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/passagem-de-turno/turno')
@login_required
@module_required(MODULO)
def passagem_turno():
    if not current_user.can_access(MODULO):
        abort(403)
    return _casca()


@bp.get('/novo/passagem-de-turno/turno/<int:turno_id>')
@login_required
@module_required(MODULO)
def passagem_ver_turno(turno_id):
    passagem._turno_autorizado(turno_id)
    return _casca()


# ── Os dados ──────────────────────────────────────────────────────────────

def dados_do_turno(c):
    """O contexto de ``contexto_turno`` (o da tela antiga) em JSON."""
    u = current_user
    return {
        'usuario': {'nome': u.name or '', 'perfil': u.perfil_rotulo},
        'clients': [{'id': x.id, 'nome': x.name} for x in c['clients']],
        'client_id': c['client_id'],
        'centro_custo': c['centro_custo'],
        'configs': c['configs'],
        'areas': c['areas'],
        'hoje': c['hoje'],
        'encerrados': c['encerrados'],
        'anterior_inicial': c['anterior_inicial'],
        'anteriores': [{'chave': b['chave'], 'turno': None} if not b['turno'] else {
            'chave': b['chave'],
            'turno': {'turno': b['turno'].turno, 'data': _dia(b['turno'].data_turno),
                      'observacao': b['turno'].observacao or ''},
            'area': b['area'], 'autor': b['autor'], 'tem_o_que_ler': b['tem_o_que_ler'],
            'ocorrencias': [{'tipo': o.tipo, 'referencia': o.referencia or '',
                             'gravidade': o.gravidade, 'descricao': o.descricao or ''}
                            for o in b['ocorrencias']],
            'anexos': [_anexo(a) for a in b['anexos']],
        } for b in c['anteriores']],
        'pendencias': [{
            'id': p['id'], 'titulo': p['titulo'], 'referencia': p['referencia'],
            'descricao': p['descricao'], 'origem_turno': p['origem_turno'],
            'origem_data': _dia(p['origem_data']), 'horas': p['horas'], 'dias': p['dias'],
            'vencida': p['vencida'], 'alta': p['alta'], 'passagens': p['passagens'],
            'ultima_tentativa': ({'texto': p['ultima_tentativa']['texto'],
                                  'quem': p['ultima_tentativa']['quem'],
                                  'quando': _hora(p['ultima_tentativa']['quando'],
                                                  '%d/%m %H:%M')}
                                 if p['ultima_tentativa'] else None),
        } for p in c['pending']],
        'links': {
            'painel': nova('', client_id=c['client_id']),
            'trocar_contrato': nova('turno') + '?client_id=',
            'ver_turno': nova('turno') + '/',
        },
    }


@api.get('/passagem/turno')
@login_required
@module_required(MODULO)
def api_passagem_turno():
    """A nova passagem: o mesmo ``contexto_turno`` da tela antiga, com a
    mesma porta (só quem GRAVA no módulo)."""
    if not current_user.can_access(MODULO):
        abort(403)
    c = passagem.contexto_turno(request.args.get('client_id', type=int))
    return _sem_cache(dados_do_turno(c))


def dados_da_leitura(c):
    """O contexto de ``contexto_ver_turno`` (o da tela antiga) em JSON."""
    t = c['turno']
    quem_anexou = c['quem_anexou']
    no_aparelho = passagem.encerramento_no_aparelho(t)
    if no_aparelho:
        fmt = '%H:%M' if no_aparelho['mesmo_dia'] else '%d/%m às %H:%M'
        no_aparelho = {'prep': 'às' if no_aparelho['mesmo_dia'] else 'em',
                       'aparelho': _hora(no_aparelho['aparelho'], fmt),
                       'chegada': _hora(no_aparelho['chegada'], fmt)}
    return {
        'turno': {'id': t.id, 'client_id': t.client_id, 'turno': t.turno,
                  'data': _dia(t.data_turno), 'data_longa': _dia(t.data_turno, '%d/%m/%Y'),
                  'data_iso': t.data_turno.isoformat(), 'status': t.status,
                  'observacao': t.observacao or '',
                  'encerrado_em': _hora(t.submitted_at) if t.submitted_at else None},
        'cliente': c['cliente'].name if c['cliente'] else None,
        'configuracao': c['configuracao'].nome if c['configuracao'] else None,
        'autor': c['autor'].name if c['autor'] else None,
        'no_aparelho': no_aparelho,
        'congelada': c['congelada'],
        'pode_corrigir': c['pode_corrigir'],
        'correcoes': [{'quem': c['quem_corrigiu'].get(x.created_by, '—'),
                       'quando': _hora(x.created_at), 'campos': x.campos or '—',
                       'motivo': x.motivo or ''} for x in c['correcoes']],
        'campos': [{'nome': x['nome'],
                    # O texto que a tela antiga escreve (``{{ valor }}``).
                    'valor': '—' if x['valor'] in (None, '') else str(x['valor']),
                    'anexos': [_anexo(a, quem_anexou) for a in x['anexos']]}
                   for x in c['campos']],
        'linhas': [{'codigo': x['codigo'], 'nome': x['nome'], 'feito': x['feito'],
                    'observacao': x['observacao'], 'opcional': x['opcional'],
                    'anexos': [_anexo(a, quem_anexou) for a in x['anexos']]}
                   for x in c['linhas']],
        'anexos_gerais': [_anexo(a, quem_anexou) for a in c['anexos_gerais']],
        'pendencias': [{
            'titulo': x['p'].titulo, 'referencia': x['p'].referencia or '',
            'status': x['p'].status, 'descricao': x['p'].descricao or '',
            'trilha': [{'tipo': e['tipo'], 'quem': e['quem'], 'turno': e['turno'],
                        'data': _dia(e['data_turno']),
                        'quando': _hora(e['quando'], '%d/%m %H:%M'), 'texto': e['texto']}
                       for e in x['trilha']],
        } for x in c['pendencias']],
        'ocorrencias': [{'tipo': o.tipo, 'referencia': o.referencia or '',
                         'gravidade': o.gravidade, 'descricao': o.descricao or ''}
                        for o in c['ocorrencias']],
        'links': {
            'painel': nova('', client_id=t.client_id),
            'corrigir': url_for('diario_operacional.corrigir_turno', turno_id=t.id),
        },
    }


@api.get('/passagem/turno/<int:turno_id>')
@login_required
@module_required(MODULO)
def api_passagem_ver_turno(turno_id):
    """A passagem já lançada: o mesmo ``contexto_ver_turno`` da tela antiga
    (que confere a carteira antes de ler qualquer coisa)."""
    return _sem_cache(dados_da_leitura(passagem.contexto_ver_turno(turno_id)))


# ── Fase 2b: o painel, o relatório mensal e a configuração ─────────────────

def _pct(v):
    return None if v is None else float(v)


@bp.get('/novo/passagem-de-turno/')
@login_required
@module_required(MODULO)
def passagem_painel():
    return _casca()


@bp.get('/novo/passagem-de-turno/relatorio-mensal')
@login_required
@module_required(MODULO)
def passagem_relatorio_mensal():
    return _casca()


@bp.get('/novo/passagem-de-turno/configuracao')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def passagem_configuracao():
    return _casca()


def dados_do_painel(c):
    """O contexto de ``contexto_painel`` (o da tela antiga) em JSON."""
    u = current_user
    d = c['dados']
    chamados = c['chamados_das_ocorrencias']
    dados = None
    if d:
        dados = {
            'periodo_label': d['periodo_label'],
            'inicio': _dia(d['inicio'], '%d/%m/%Y'), 'fim': _dia(d['fim'], '%d/%m/%Y'),
            'turno': d['turno'], 'n_turnos': d['n_turnos'],
            'turnos_disponiveis': d['turnos_disponiveis'],
            'areas_disponiveis': [{'id': a.id, 'nome': a.nome} for a in d['areas_disponiveis']],
            'aderencia': {**d['aderencia'], 'pct': _pct(d['aderencia']['pct']),
                          'meta': _pct(d['aderencia']['meta'])},
            'resolucao': {**d['resolucao'], 'pct': _pct(d['resolucao']['pct'])},
            'n_criticas': d['n_criticas'],
            'indice_ocorrencias': {k: d['indice_ocorrencias'][k]
                                   for k in ('valor', 'delta', 'turnos', 'ocorrencias')},
            'pareto': d['pareto'],
            'turnos_comparativo': d['turnos_comparativo'],
            'burndown': d['burndown'],
            'rotinas': d['rotinas'],
            'ocorrencias': [{
                'id': o.id, 'tipo': o.tipo, 'referencia': o.referencia or '',
                'descricao': o.descricao or '', 'gravidade': o.gravidade,
                'quando': {'dia': _dia(d['quando_ocorrencias'].get(o.id, {}).get('dia')),
                           'turno': d['quando_ocorrencias'].get(o.id, {}).get('turno')},
                'chamado': ({'id': chamados[o.id].id, 'numero': chamados[o.id].numero,
                             'status_rotulo': chamados[o.id].status_rotulo,
                             'url': f'/chamados/{chamados[o.id].id}'}
                            if o.id in chamados else None),
            } for o in d['ocorrencias']],
            'criticas': [{
                'id': x['pendencia'].id, 'titulo': x['pendencia'].titulo,
                'descricao': x['pendencia'].descricao or '',
                'prioridade': x['pendencia'].prioridade or '',
                'alta': x['alta'], 'vencida': x['vencida'],
                'horas': x['horas'], 'dias': x['dias'],
            } for x in d['criticas']],
        }
    cid = c['client_id']
    return {
        'clients': [{'id': x.id, 'nome': x.name} for x in c['clients']],
        'client_id': cid,
        'periodo': c['periodo'], 'turno_sel': c['turno_sel'],
        'periodos': [[k, v] for k, v in c['periodos'].items()],
        'area_sel': c['area_sel'], 'todas_as_areas': c['todas_as_areas'],
        'de': c['de'], 'ate': c['ate'], 'hoje': c['hoje'].isoformat(),
        'dados': dados,
        'turnos': [{'id': x['t'].id, 'data': _dia(x['t'].data_turno, '%d/%m/%Y'),
                    'area': x['area'], 'turno': x['t'].turno, 'status': x['t'].status}
                   for x in c['turnos']],
        'modelos': c['modelos'],
        'pode_gravar': c['pode_gravar'], 'pode_chamado': c['pode_chamado'],
        'pode_ver_chamado': c['pode_ver_chamado'],
        # As duas perguntas que a tela antiga faz ao ``current_user``.
        'e_gestao': u.e_gestao(), 'pode_configurar': u.pode('diario_config'),
        'nome_do_sistema': current_app.jinja_env.globals.get('NOME_DO_SISTEMA', ''),
        'links': {
            'nova_passagem': nova('turno', client_id=cid),
            'relatorio': nova('relatorio-mensal', client_id=cid) if cid else None,
            'configurar': nova('configuracao', client_id=cid),
            'ver_turno': nova('turno') + '/',
        },
    }


@api.get('/passagem/painel')
@login_required
@module_required(MODULO)
def api_passagem_painel():
    """O painel: o mesmo ``contexto_painel`` da tela antiga, com a mesma
    porta (quem LÊ o módulo) e o mesmo recorte da query string."""
    return _sem_cache(dados_do_painel(passagem.contexto_painel()))


def _faixa(d):
    return {**d, 'pct': _pct(d.get('pct'))}


def dados_do_relatorio(c):
    """O contexto de ``contexto_relatorio_mensal`` (o da tela antiga) em JSON."""
    rel, cliente = c['rel'], c['cliente']
    area = c['area_sel'] if c['area_sel'] and c['area_sel'] != c['todas_as_areas'] else None
    pend = rel['pendencias']
    oc = rel['ocorrencias']

    def _ocorrencia(x):
        return {'data': _dia(x['data'], '%d/%m/%Y'), 'dia': _dia(x['data']), 'turno': x['turno'],
                'tipo': x['o'].tipo, 'referencia': x['o'].referencia or '',
                'descricao': x['o'].descricao or '', 'gravidade': x['o'].gravidade}

    return {
        'cliente': {'id': cliente.id, 'nome': cliente.name},
        'meses': [[n, nome] for n, nome in c['meses']], 'anos': c['anos'],
        'mes': c['mes'], 'ano': c['ano'],
        'areas': c['areas'], 'area_sel': c['area_sel'], 'todas_as_areas': c['todas_as_areas'],
        'nome_do_sistema': current_app.jinja_env.globals.get('NOME_DO_SISTEMA', ''),
        'rel': {
            'area': rel['area'], 'competencia': rel['competencia'],
            'emitido_em': rel['emitido_em'].strftime('%d/%m/%Y %H:%M'),
            'emitido_por': rel['emitido_por'],
            'inicio': _dia(rel['inicio'], '%d/%m/%Y'),
            'fim_apurado': _dia(rel['fim_apurado'], '%d/%m/%Y'),
            'em_andamento': rel['em_andamento'],
            'turnos': {'total': rel['turnos']['total'],
                       'por_turno': [[n, q] for n, q in rel['turnos']['por_turno']]},
            'aderencia': {**_faixa(rel['aderencia']), 'meta': _pct(rel['aderencia']['meta'])},
            'pendencias': {
                'abertas': pend['abertas'], 'resolvidas': pend['resolvidas'],
                'pct': _pct(pend['pct']), 'faixa': pend['faixa'],
                'lista_resolvidas': [{
                    'titulo': x['p'].titulo, 'referencia': x['p'].referencia or '',
                    'prioridade': x['p'].prioridade or '', 'resolucao': x['resolucao'],
                    'turno': x['turno'], 'passagens': x['passagens'],
                    'encerrada': _hora(x['p'].resolved_at, '%d/%m %H:%M'),
                    'resolvida_por': x['resolvida_por'],
                } for x in pend['lista_resolvidas']],
                'lista_em_aberto': [{
                    'titulo': x['p'].titulo, 'referencia': x['p'].referencia or '',
                    'prioridade': x['p'].prioridade or '', 'descricao': x['p'].descricao or '',
                    'anterior': x['anterior'], 'ultima_tentativa': x['ultima_tentativa'],
                    'turno': x['turno'], 'passagens': x['passagens'], 'dias': x['dias'],
                } for x in pend['lista_em_aberto']],
            },
            'ocorrencias': {
                'total': oc['total'],
                'mais_frequente': ({'tipo': oc['pareto'][0]['tipo'], 'qtd': oc['pareto'][0]['qtd']}
                                   if oc['pareto'] else None),
                'lista': [_ocorrencia(x) for x in oc['lista']],
                'atencao': [_ocorrencia(x) for x in oc['atencao']],
            },
            'rotinas': [_faixa(r) for r in rel['rotinas']],
            'bordo': [{'data': _dia(f['data'], '%d/%m/%Y'), 'turno': f['turno'], 'texto': f['texto']}
                      for f in rel['bordo']],
        },
        'links': {
            'painel': nova('', client_id=cliente.id),
            'pdf': url_for('diario_operacional.relatorio_mensal', client_id=cliente.id,
                           mes=c['mes'], ano=c['ano'], format='pdf', area_id=area),
        },
    }


@api.get('/passagem/relatorio-mensal')
@login_required
@module_required(MODULO)
def api_passagem_relatorio_mensal():
    """O fechamento do mês: o mesmo ``contexto_relatorio_mensal`` da tela
    antiga (sem contrato, 400; contrato de fora, 403; competência fora da
    régua, 400 — antes de qualquer consulta). O 400 sai em JSON, com a
    mesma frase da antiga ("Informe o contrato", "Competência inválida")."""
    from werkzeug.exceptions import BadRequest
    try:
        c = passagem.contexto_relatorio_mensal()
    except BadRequest as e:
        return jsonify({'error': e.description}), 400
    return _sem_cache(dados_do_relatorio(c))


def dados_da_configuracao(c):
    """O contexto de ``contexto_configuracao`` (o da tela antiga) em JSON."""
    cid = c['client_id']
    return {
        'clients': [{'id': x.id, 'nome': x.name} for x in c['clients']],
        'client_id': cid,
        'configs': c['configs'],
        'areas': c['areas'],
        # A chave do JSON é texto: ``{"7": 3}``.
        'usos': {str(k): v for k, v in c['usos'].items()},
        'editar': c['editar'],
        'modelos_prontos': [{'chave': k, 'area': m['area'], 'turnos': list(m['turnos'])}
                            for k, m in c['modelos_prontos'].items()],
        # O recado do "Criar modelos" (formulário antigo, que redireciona):
        # na tela antiga ele sai no topo da página seguinte (flash).
        'recados': [{'tipo': t, 'texto': x} for t, x in get_flashed_messages(with_categories=True)],
        'links': {
            'painel': nova('', client_id=cid),
            'aqui': nova('configuracao'),
            'modelos_prontos': url_for('diario_operacional.usar_modelos_prontos'),
        },
    }


@api.get('/passagem/configuracao')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def api_passagem_configuracao():
    """Os modelos de passagem: o mesmo ``contexto_configuracao`` da tela
    antiga, com a mesma porta (a permissão fina ``diario_config``)."""
    return _sem_cache(dados_da_configuracao(
        passagem.contexto_configuracao(request.args.get('client_id', type=int))))
