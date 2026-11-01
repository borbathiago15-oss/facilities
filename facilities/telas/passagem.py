"""API das telas novas da Passagem de turno (Fase 2a da migração para React).

* ``/novo/passagem-de-turno/turno``: a nova passagem (o encarregado preenche);
* ``/novo/passagem-de-turno/turno/<id>``: a passagem já lançada, para leitura.

As duas páginas têm a mesma porta das antigas (``login_required``,
``module_required`` e, na nova passagem, o ``can_access``; na leitura, a
carteira do ``_turno_autorizado``) e entregam a casca React. Os dados vêm da
MESMA função que monta a tela antiga (``passagem.rotas.contexto_turno`` e
``contexto_ver_turno``), aqui só viram JSON:

* ``/api/v1/passagem/turno?client_id=``  → a nova passagem;
* ``/api/v1/passagem/turno/<id>``        → a leitura.

As ações continuam nas APIs de sempre (``/passagem-de-turno/api/...``), como
estão; a fila sem internet é a mesma (``fila-offline.js``, carregada pela
casca). O painel, o relatório e a configuração (Fase 2b) seguem nas telas
antigas: os endereços deles aqui são os de sempre.
"""
from flask import abort, current_app, jsonify, request, url_for
from flask_login import current_user, login_required

from facilities.core.acesso import module_required
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
            # O painel é da Fase 2b: continua na tela de sempre.
            'painel': url_for('diario_operacional.index', client_id=c['client_id']),
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
            'painel': url_for('diario_operacional.index', client_id=t.client_id),
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
