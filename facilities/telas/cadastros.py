"""API das telas novas dos Cadastros (Fase 3a da migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/cadastros/`` (início), ``/empresas``, ``/clientes``, ``/estados``,
  ``/trilha``, ``/locais/<id>`` (a estrutura do local) e
  ``/locais/<id>/trilha``;
* ``/novo/clientes``, ``/novo/clientes/<id>``, ``/novo/centros/<id>`` e
  ``/novo/centros/<id>/rotas/<id>`` (o cadastro simplificado: cliente,
  centro de custo, áreas e rotas);
* ``/novo/novo-contrato``, ``/novo-contrato/cliente/<id>/local``,
  ``/novo-contrato/<id>/estrutura``, ``/novo-contrato/<id>/equipe`` e
  ``/novo/convites`` (o assistente e os convites).

Cada página tem a mesma porta da antiga (``login_required``,
``admin_required`` e as checagens de carteira e de perfil de cada módulo) e
entrega a casca React. Os dados vêm da MESMA função que monta a tela antiga
(``cadastros.rotas.contexto_*``, ``centros_telas.contexto_*`` e
``novo_contrato.contexto_*``) e aqui só viram JSON, em
``/api/v1/cadastros/...``.

As telas antigas enviam formulários HTML (que redirecionam). As novas enviam
para ``POST /api/v1/cadastros/...``: o MESMO caminho das antigas, chamando a
MESMA ação (``acao_*``: a regra, o commit e o recado). A resposta é o recado
(o ``flash`` da antiga) e o endereço de volta, já na tela nova; recusa da
regra é 400 com a mesma frase. O CSRF vai no cabeçalho, como em toda a
``/api/v1``. As etiquetas de QR (o PDF), o ``/q/<código>``, a logo e o link
público do convite continuam no servidor. Sem cópia no aparelho (gestão).
"""
from flask import current_app, get_flashed_messages, jsonify, request, url_for
from flask_login import current_user, login_required
from werkzeug.datastructures import MultiDict

from facilities.cadastros import centros_telas as centros
from facilities.cadastros import novo_contrato as nc
from facilities.cadastros import rotas as cad
from facilities.cadastros.servico import CadastroInvalido
from facilities.core.acesso import admin_required
from facilities.extensions import limiter
from facilities.telas import _casca, api, bp

# Os endereços já migrados: dentro das telas novas, levam às novas (a
# rotina dos locais entrou na Fase 3b; os chamados, as demandas e a
# preventiva, na 4a).
MIGRADOS = ('/cadastros/', '/clientes', '/centros/', '/novo-contrato', '/convites', '/rotas/',
            '/chamados/', '/demandas/', '/preventiva/locais/')
FORA = ('/etiquetas.pdf', '/logo.png')
# Da rotina dos locais, os arquivos (POP/FIT, fotos, referências) e o
# agendador continuam no servidor; dos chamados, as fotos e os PDFs.
FORA_DAS_ROTAS = ('/rotas/documentos/', '/rotas/fotos/', '/rotas/referencias/',
                  '/rotas/ocorrencias/', '/rotas/agendador', '/chamados/anexos/')


def nova(url):
    """O endereço da tela nova para um endereço antigo já migrado; os outros
    (as etiquetas, os arquivos, as pessoas) ficam como estão."""
    if url and url.startswith(MIGRADOS) and not url.split('?')[0].endswith(FORA) \
            and not url.startswith(FORA_DAS_ROTAS):
        return '/novo' + url
    return url


def _hora(dt, fmt='%d/%m/%Y %H:%M'):
    """A mesma hora que a tela antiga escreve (o filtro ``hora_local``)."""
    return current_app.jinja_env.filters['hora_local'](dt, fmt) if dt else None


def _sem_cache(dados):
    resp = jsonify(dados)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _dados():
    """O corpo do envio como o formulário antigo: JSON vira um ``MultiDict``
    (lista = o mesmo campo várias vezes, como as caixas de marcar); o
    formulário (``FormData``, com arquivo) vai como está."""
    if not request.is_json:
        return request.form
    corpo = request.get_json(silent=True)
    pares = []
    for k, v in (corpo.items() if isinstance(corpo, dict) else ()):
        for x in (v if isinstance(v, list) else [v]):
            if x is not None and not isinstance(x, (dict, list)):
                pares.append((k, x if isinstance(x, str) else str(x)))
    return MultiDict(pares)


def _recados():
    return [{'tipo': 'danger' if t == 'error' else t, 'texto': x}
            for t, x in get_flashed_messages(with_categories=True)]


def _feito(destino):
    """O que a ação deixou (o recado e o endereço) em JSON: 400 quando a
    regra recusou, com a mesma frase."""
    recados = _recados()
    erro = next((r['texto'] for r in recados if r['tipo'] == 'danger'), None)
    corpo = {'recados': recados, 'destino': nova(destino)}
    if erro:
        return jsonify({**corpo, 'error': erro}), 400
    return jsonify(corpo)


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/cadastros/')
@login_required
def cadastros_inicio():
    cad.exigir_consulta()
    return _casca()


@bp.get('/novo/cadastros/empresas')
@bp.get('/novo/cadastros/clientes')
@bp.get('/novo/cadastros/estados')
@bp.get('/novo/cadastros/trilha')
@login_required
@admin_required
def cadastros_do_administrador():
    return _casca()


@bp.get('/novo/cadastros/locais/<int:cid>')
@bp.get('/novo/cadastros/locais/<int:cid>/trilha')
@login_required
def cadastros_local(cid):
    cad._local_para_ler(cid)
    return _casca()


@bp.get('/novo/clientes')
@login_required
def centros_clientes():
    centros._exigir()
    return _casca()


@bp.get('/novo/clientes/<int:ctid>')
@login_required
def centros_cliente(ctid):
    centros._cliente(ctid)
    return _casca()


@bp.get('/novo/centros/<int:cid>')
@login_required
def centros_centro(cid):
    centros._centro(cid)
    return _casca()


@bp.get('/novo/centros/<int:cid>/rotas/<int:rid>')
@login_required
def centros_rota(cid, rid):
    centros._rota(centros._centro(cid), rid)
    return _casca()


@bp.get('/novo/novo-contrato')
@bp.get('/novo/convites')
@login_required
def montagem_inicio():
    nc._exigir_montagem()
    return _casca()


@bp.get('/novo/novo-contrato/cliente/<int:ctid>/local')
@login_required
def montagem_novo_local(ctid):
    nc._cliente(ctid)
    return _casca()


@bp.get('/novo/novo-contrato/<int:cid>/estrutura')
@bp.get('/novo/novo-contrato/<int:cid>/equipe')
@login_required
def montagem_local(cid):
    nc._local(cid)
    return _casca()


# ── Cadastros: os dados ───────────────────────────────────────────────────

def dados_do_inicio(c):
    papel = current_user._effective_role()
    return {
        'locais': [{'id': x.id, 'nome': x.name,
                    'cliente': x.contratante.nome if x.contratante else None,
                    'estado': x.estado.sigla if x.estado else None} for x in c['locais']],
        'e_admin': c['e_admin'],
        # A pergunta que a tela antiga faz ao ``current_user``.
        'pode_novo_contrato': papel in ('master', 'gerente', 'pleno'),
        'n_empresas': c['n_empresas'], 'n_clientes': c['n_clientes'],
        'n_estados': c['n_estados'],
        'links': {'locais_admin': url_for('admin.contratos')},
    }


@api.get('/cadastros/inicio')
@login_required
def api_cadastros_inicio():
    return _sem_cache(dados_do_inicio(cad.contexto_inicio()))


@api.get('/cadastros/empresas')
@login_required
@admin_required
def api_cadastros_empresas():
    c = cad.contexto_empresas()
    return _sem_cache({'empresas': [{'id': e.id, 'nome': e.nome, 'cnpj': e.cnpj or '',
                                     'ativo': bool(e.is_active)} for e in c['empresas']]})


def dados_dos_clientes(c):
    return {
        'clientes': [{
            'id': x.id, 'nome': x.nome, 'centro_custo': x.centro_custo or '',
            'empresa_id': x.empresa_id, 'gerente_id': x.gerente_id,
            'gerente': x.gerente.name if x.gerente else None, 'ativo': bool(x.is_active),
            'prazo_pedido_insumo_horas': x.prazo_pedido_insumo_horas,
            'mostrar_nome_executor': bool(x.mostrar_nome_executor),
            'regua': c['regua_de'](x), 'prazos': c['prazos_de'](x),
            'locais': [{'id': loc.id, 'nome': loc.name,
                        'estado': loc.estado.sigla if loc.estado else None} for loc in x.locais],
        } for x in c['clientes']],
        'empresas': [{'id': e.id, 'nome': e.nome, 'ativo': bool(e.is_active)}
                     for e in c['empresas']],
        'gerentes': [{'id': g.id, 'nome': g.name} for g in c['gerentes']],
        'tipos_ocorrencia': [[k, v] for k, v in c['tipos_ocorrencia'].items()],
        'prioridades': [[k, v] for k, v in c['prioridades'].items()],
        'regua_padrao': c['regua_padrao'],
        'pode_mostrar_nome': current_user._effective_role() == 'master',
    }


@api.get('/cadastros/clientes')
@login_required
@admin_required
def api_cadastros_clientes():
    return _sem_cache(dados_dos_clientes(cad.contexto_clientes()))


@api.get('/cadastros/estados')
@login_required
@admin_required
def api_cadastros_estados():
    c = cad.contexto_estados()
    return _sem_cache({'estados': [{'id': e.id, 'nome': e.nome, 'sigla': e.sigla,
                                    'ativo': bool(e.is_active)} for e in c['estados']]})


def _setor(s):
    return {
        'id': s.id, 'nome': s.nome, 'ativo': bool(s.is_active),
        'ambientes': [{
            'id': a.id, 'nome': a.nome, 'descricao': a.descricao or '', 'ativo': bool(a.is_active),
            'pontos': [{'id': p.id, 'nome': p.nome, 'descricao': p.descricao or '',
                        'ativo': bool(p.is_active), 'equipamento_id': p.equipamento_id,
                        'equipamento': p.equipamento.nome if p.equipamento else None}
                       for p in a.pontos],
            'equipamentos': [{'id': e.id, 'nome': e.nome, 'patrimonio': e.patrimonio or '',
                              'fabricante': e.fabricante or '', 'modelo': e.modelo or '',
                              'ativo': bool(e.is_active)} for e in a.equipamentos],
        } for a in s.ambientes],
    }


def dados_do_local(c):
    loc = c['local']
    return {
        'local': {'id': loc.id, 'nome': loc.name,
                  'cliente': loc.contratante.nome if loc.contratante else None,
                  'estado': loc.estado.nome if loc.estado else None,
                  'subcentro': loc.cost_center or ''},
        'setores': [_setor(s) for s in c['setores']],
        # Os destinos de "mudar de setor/ambiente": só os ativos.
        'todos_setores': [{'id': s.id, 'nome': s.nome,
                           'ambientes': [{'id': a.id, 'nome': a.nome}
                                         for a in s.ambientes if a.is_active]}
                          for s in c['todos_setores']],
        'com_inativos': c['com_inativos'],
        'pode_alterar': c['pode_alterar'],
        'links': {'etiquetas': url_for('cadastros.etiquetas', cid=loc.id)},
    }


@api.get('/cadastros/locais/<int:cid>')
@login_required
def api_cadastros_local(cid):
    return _sem_cache(dados_do_local(cad.contexto_local(cid, request.args.get('inativos') == '1')))


def _texto_jinja(v):
    """O valor como o ``{{ v }}`` da tela antiga escreve (``None`` → —)."""
    return '—' if v is None else str(v)


def dados_da_trilha(c):
    loc = c['local']
    return {
        'local': {'id': loc.id, 'nome': loc.name} if loc else None,
        'entidade': c['entidade'],
        'entidades': [[k, v] for k, v in c['entidades'].items()],
        'eventos': [{
            'id': ev.id,
            'entidade': c['entidades'].get(ev.entidade, ev.entidade),
            'acao': c['acoes'].get(ev.acao, ev.acao), 'entidade_id': ev.entidade_id,
            'quando': _hora(ev.criado_em), 'autor': ev.autor.name if ev.autor else 'sistema',
            'com_antes': bool(ev.antes_json),
            'mudancas': [[campo, _texto_jinja(antes), _texto_jinja(depois)]
                         for campo, antes, depois in c['diferencas'](ev)],
        } for ev in c['eventos']],
    }


@api.get('/cadastros/trilha')
@login_required
@admin_required
def api_cadastros_trilha():
    return _sem_cache(dados_da_trilha(cad.contexto_trilha(request.args.get('entidade') or None)))


@api.get('/cadastros/locais/<int:cid>/trilha')
@login_required
def api_cadastros_trilha_local(cid):
    return _sem_cache(dados_da_trilha(cad.contexto_trilha(cid=cid)))


# ── Cadastros: os envios (a mesma ação das telas antigas) ─────────────────

@api.post('/cadastros/empresas')
@login_required
@admin_required
def api_criar_empresa():
    return _feito(cad.acao_criar_empresa(_dados()))


@api.post('/cadastros/empresas/<int:eid>')
@login_required
@admin_required
def api_editar_empresa(eid):
    return _feito(cad.acao_editar_empresa(eid, _dados()))


@api.post('/cadastros/empresas/<int:eid>/ativo')
@login_required
@admin_required
def api_ativo_empresa(eid):
    return _feito(cad.acao_ativo_empresa(eid, _dados()))


@api.post('/cadastros/clientes')
@login_required
@admin_required
def api_criar_cliente():
    return _feito(cad.acao_criar_cliente(_dados()))


@api.post('/cadastros/clientes/<int:cid>')
@login_required
@admin_required
def api_editar_cliente(cid):
    return _feito(cad.acao_editar_cliente(cid, _dados()))


@api.post('/cadastros/clientes/<int:cid>/ativo')
@login_required
@admin_required
def api_ativo_cliente(cid):
    return _feito(cad.acao_ativo_cliente(cid, _dados()))


@api.post('/cadastros/estados/<int:eid>/ativo')
@login_required
@admin_required
def api_ativo_estado(eid):
    return _feito(cad.acao_ativo_estado(eid, _dados()))


@api.post('/cadastros/locais/<int:cid>/<entidade>')
@login_required
def api_criar_item(cid, entidade):
    return _feito(cad.acao_criar_item(cid, entidade, _dados()))


@api.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>')
@login_required
def api_editar_item(cid, entidade, oid):
    return _feito(cad.acao_editar_item(cid, entidade, oid, _dados()))


@api.post('/cadastros/locais/<int:cid>/<entidade>/<int:oid>/ativo')
@login_required
def api_ativo_item(cid, entidade, oid):
    return _feito(cad.acao_ativo_item(cid, entidade, oid, _dados()))


# ── Cliente, centro de custo, áreas e rotas: os dados ─────────────────────

def _hm(t):
    return t.strftime('%H:%M') if t else ''


@api.get('/cadastros/centros/clientes')
@login_required
def api_centros_clientes():
    c = centros.contexto_clientes()
    return _sem_cache({
        'clientes': [{'id': x.id, 'nome': x.nome,
                      'centros': [{'id': loc.id, 'nome': loc.name,
                                   'centro_custo': loc.cost_center or ''}
                                  for loc in c['centros'][x.id]]} for x in c['clientes']],
        'pode_criar': c['pode_criar'],
    })


@api.get('/cadastros/centros/clientes/<int:ctid>')
@login_required
def api_centros_cliente(ctid):
    c = centros.contexto_cliente(ctid)
    return _sem_cache({
        'cliente': {'id': c['cliente'].id, 'nome': c['cliente'].nome},
        'centros': [{'id': loc.id, 'nome': loc.name, 'centro_custo': loc.cost_center or '',
                     **c['resumo'][loc.id]} for loc in c['centros']],
        'estados': [{'id': e.id, 'nome': e.nome} for e in c['estados']],
    })


def dados_do_centro(c):
    loc = c['local']
    return {
        'local': {'id': loc.id, 'nome': loc.name, 'centro_custo': loc.cost_center or '',
                  'cliente': ({'id': loc.contratante_id, 'nome': loc.contratante.nome}
                              if loc.contratante else None),
                  'marcada': loc.latitude is not None,
                  'marcada_em': (_hora(loc.posicao_marcada_em) or '—')
                  if loc.latitude is not None else None},
        'aba': c['aba'],
        'areas': [{'id': p.id, 'nome': p.nome, 'numero': c['numeros'].get(p.id, 0),
                   'entrada': bool(p.entrada_do_local), 'checklist_id': p.checklist_id}
                  for p in c['areas']],
        'checklists': [{'id': m.id, 'nome': m.nome} for m in c['checklists']],
        'raio': c['raio'],
        'rotas': [{'id': r.id, 'nome': r.nome, 'turno': r.turno, 'inicio': _hm(r.hora_inicio),
                   'fim': _hm(r.hora_fim), 'ativa': bool(r.is_active),
                   'areas': len([i for i in r.itens if i.is_active])} for r in c['rotas']],
        'links': {'etiquetas': url_for('cadastros.etiquetas', cid=loc.id)},
    }


@api.get('/cadastros/centros/<int:cid>')
@login_required
def api_centros_centro(cid):
    return _sem_cache(dados_do_centro(
        centros.contexto_centro(cid, request.args.get('aba') or 'areas')))


def dados_da_rota(c):
    loc, r = c['local'], c['rota']
    return {
        'local': {'id': loc.id, 'nome': loc.name},
        'rota': {'id': r.id, 'nome': r.nome, 'turno': r.turno, 'inicio': _hm(r.hora_inicio),
                 'fim': _hm(r.hora_fim), 'dias': [c['dias'][d] for d in (r.dias_semana or '')
                                                  if d in c['dias']]},
        'linhas': [{'hora': x['hora'], 'item_id': x['item'].id, 'area': x['ponto'].nome,
                    'checklist': x['checklist'].nome if x['checklist'] else ''}
                   for x in c['linhas']],
        'areas': [{'id': p.id, 'nome': p.nome} for p in c['areas']],
        'pessoas': [{'id': p.id, 'nome': p.name} for p in c['pessoas']],
        'escalados': [{'nome': e.pessoa.name, 'desde': e.data_inicio.strftime('%d/%m/%Y')}
                      for e in r.escalas if e.is_active],
        'hoje': c['hoje'],
        'vazias': len(c['vazias']),
        'links': {'avancado': nova(url_for('rotas.rota', rid=r.id))},
    }


@api.get('/cadastros/centros/<int:cid>/rotas/<int:rid>')
@login_required
def api_centros_rota(cid, rid):
    return _sem_cache(dados_da_rota(centros.contexto_rota(cid, rid)))


# ── Cliente, centro de custo, áreas e rotas: os envios ────────────────────

@api.post('/cadastros/centros/clientes/<int:ctid>/centros')
@login_required
def api_centros_criar_centro(ctid):
    return _feito(centros.acao_criar_centro(ctid, _dados()))


@api.post('/cadastros/centros/<int:cid>/areas')
@login_required
def api_centros_criar_areas(cid):
    return _feito(centros.acao_criar_areas(cid, _dados()))


@api.post('/cadastros/centros/<int:cid>/areas/<int:pid>/checklist')
@login_required
def api_centros_trocar_checklist(cid, pid):
    return _feito(centros.acao_trocar_checklist(cid, pid, _dados()))


@api.post('/cadastros/centros/<int:cid>/posicao')
@login_required
def api_centros_marcar_posicao(cid):
    return _feito(centros.acao_marcar_posicao(cid, _dados()))


@api.post('/cadastros/centros/<int:cid>/rotas')
@login_required
def api_centros_criar_rota(cid):
    return _feito(centros.acao_criar_rota(cid, _dados()))


@api.post('/cadastros/centros/<int:cid>/rotas/<int:rid>/linhas')
@login_required
def api_centros_adicionar_linhas(cid, rid):
    return _feito(centros.acao_adicionar_linhas(cid, rid, _dados()))


@api.post('/cadastros/centros/<int:cid>/rotas/<int:rid>/linhas/<int:iid>/remover')
@login_required
def api_centros_remover_linha(cid, rid, iid):
    return _feito(centros.acao_remover_linha(cid, rid, iid, _dados()))


@api.post('/cadastros/centros/<int:cid>/rotas/<int:rid>/escala')
@login_required
def api_centros_escalar(cid, rid):
    return _feito(centros.acao_escalar(cid, rid, _dados()))


# ── Novo contrato e convites: os dados ────────────────────────────────────

def _logo(cli):
    return url_for('montagem.logo', ctid=cli.id) if cli and cli.logo_key else None


def _passos(p):
    loc, cli = p['local'], p['cliente']
    return {'atual': p['atual'],
            'local': {'id': loc.id, 'nome': loc.name} if loc else None,
            'cliente': {'id': cli.id, 'nome': cli.nome} if cli else None}


@api.get('/cadastros/novo-contrato')
@login_required
def api_montagem_inicio():
    c = nc.contexto_inicio()
    return _sem_cache({
        'clientes': [{
            'id': x.id, 'nome': x.nome, 'centro_custo': x.centro_custo or '', 'logo': _logo(x),
            'locais': [{'id': loc.id, 'nome': loc.name, 'andamento': c['andamento'](loc)}
                       for loc in c['por_cliente'].get(x.id, [])],
        } for x in c['clientes']],
        'pode_criar': c['pode_criar'],
        'empresas': [{'id': e.id, 'nome': e.nome} for e in c['empresas']],
        'passos': _passos(c['passos']),
    })


@api.get('/cadastros/novo-contrato/cliente/<int:ctid>/local')
@login_required
def api_montagem_novo_local(ctid):
    c = nc.contexto_novo_local(ctid)
    cli = c['cliente']
    return _sem_cache({
        'cliente': {'id': cli.id, 'nome': cli.nome, 'logo': _logo(cli)},
        'estados': [{'id': e.id, 'nome': e.nome} for e in c['estados']],
        'pode_logo': c['pode_logo'],
        'passos': _passos(c['passos']),
    })


@api.get('/cadastros/novo-contrato/<int:cid>/estrutura')
@login_required
def api_montagem_estrutura(cid):
    c = nc.contexto_estrutura(cid)
    loc = c['local']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'setores': [{'id': s.id, 'nome': s.nome, 'ambientes': [{
            'nome': a.nome,
            'pontos': [{'numero': c['numeros'].get(p.id, 0), 'nome': p.nome,
                        'entrada': bool(p.entrada_do_local)}
                       for p in sorted(a.pontos, key=lambda p: p.id) if p.is_active],
        } for a in s.ambientes if a.is_active]} for s in c['setores']],
        'andamento': c['andamento'],
        'passos': _passos(c['passos']),
        'links': {'importar': nova(url_for('rotas.importar_plano', cid=loc.id)),
                  'etiquetas': url_for('cadastros.etiquetas', cid=loc.id),
                  'rotas': nova(url_for('rotas.local', cid=loc.id))},
    })


def dados_da_equipe(c):
    loc = c['local']
    eu = current_user
    return {
        'local': {'id': loc.id, 'nome': loc.name, 'cliente_id': loc.contratante_id},
        'perfis': [[v, r] for v, r in c['perfis']],
        # A primeira opção de "Responde a" e a lista sem a própria pessoa,
        # como a tela antiga escreve.
        'eu': {'nome': eu.name, 'e_admin': eu._effective_role() == 'master'},
        'superiores': [{'id': s.id, 'nome': s.name, 'perfil': s.perfil_rotulo}
                       for s in c['superiores'] if s.id != eu.id],
        'locais': [{'id': x.id, 'nome': x.name} for x in c['locais']],
        'clientes': [{'id': x.id, 'nome': x.nome} for x in c['clientes']],
        'convites': [{'id': x.id, 'nome': x.nome,
                      'perfil': c['perfis_nome'].get(x.role, x.role), 'situacao': x.situacao()}
                     for x in c['convites']],
        'equipe': [{'nome': u.name, 'perfil': u.perfil_rotulo} for u in c['equipe']],
        'passos': _passos(c['passos']),
        'links': {'concluir': nova(url_for('rotas.local', cid=loc.id))},
    }


@api.get('/cadastros/novo-contrato/<int:cid>/equipe')
@login_required
def api_montagem_equipe(cid):
    return _sem_cache(dados_da_equipe(nc.contexto_equipe(nc._local(cid))))


@api.get('/cadastros/convites')
@login_required
def api_montagem_convites():
    c = nc.contexto_convites()
    return _sem_cache({'convites': [{
        'id': x.id, 'nome': x.nome, 'email': x.email,
        'perfil': c['perfis_nome'].get(x.role, x.role), 'situacao': x.situacao(),
        'onde': ', '.join(loc.name for loc in c['locais_do'](x))
        or (x.cliente.nome if x.cliente else ''),
        'criado_por': x.criado_por.name, 'criado_em': _hora(x.criado_em),
    } for x in c['convites']]})


def dados_do_convite_criado(c):
    """A página "Convite pronto" (a resposta do envio, como na antiga: o link
    não passa por endereço nem pelo histórico)."""
    conv, loc = c['convite'], c['local']
    return {
        'convite': {'nome': conv.nome, 'email': conv.email},
        'perfil': c['perfil'], 'locais': [x.name for x in c['locais']],
        'enviado': c['enviado'], 'link': c['link'], 'whatsapp': c['whatsapp'],
        'email': c['email'],
        'local': {'id': loc.id, 'nome': loc.name} if loc else None,
        'passos': _passos(c['passos']) if c['passos'] else None,
    }


# ── Novo contrato e convites: os envios ───────────────────────────────────

@api.post('/cadastros/novo-contrato/cliente')
@login_required
def api_montagem_criar_cliente():
    return _feito(nc.acao_criar_cliente(_dados(), request.files))


@api.post('/cadastros/novo-contrato/cliente/<int:ctid>/logo')
@login_required
def api_montagem_trocar_logo(ctid):
    return _feito(nc.acao_trocar_logo(ctid, request.files))


@api.post('/cadastros/novo-contrato/cliente/<int:ctid>/local')
@login_required
def api_montagem_criar_local(ctid):
    return _feito(nc.acao_criar_local(ctid, _dados()))


@api.post('/cadastros/novo-contrato/<int:cid>/estrutura')
@login_required
def api_montagem_criar_estrutura(cid):
    return _feito(nc.acao_criar_estrutura(cid, _dados()))


@api.post('/cadastros/novo-contrato/<int:cid>/equipe')
@login_required
@limiter.limit('60 per hour')
def api_montagem_convidar(cid):
    loc = nc._local(cid)
    try:
        convite, token, enviado = nc.gravar_convite(_dados())
    except CadastroInvalido as erro:
        return jsonify({'error': str(erro)}), 400
    return _sem_cache(dados_do_convite_criado(
        nc.contexto_convite_criado(convite, token, local=loc, enviado=enviado)))


@api.post('/cadastros/convites/<int:conv_id>/cancelar')
@login_required
def api_montagem_cancelar_convite(conv_id):
    return _feito(nc.acao_cancelar_convite(conv_id))


@api.post('/cadastros/convites/<int:conv_id>/novo-link')
@login_required
def api_montagem_novo_link(conv_id):
    c = nc._convite(conv_id)
    try:
        token, enviado = nc.gravar_novo_link(c)
    except CadastroInvalido as erro:
        return jsonify({'error': str(erro), 'destino': nova(url_for('montagem.convites'))}), 400
    return _sem_cache(dados_do_convite_criado(
        nc.contexto_convite_criado(c, token, enviado=enviado)))
