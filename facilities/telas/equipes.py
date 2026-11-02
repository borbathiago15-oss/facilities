"""API das telas novas da equipe e das visitas de supervisão (Fase 4b da
migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/equipes/locais/<id>`` (funcionários, postos e a escala em vigor)
  e ``/novo/equipes/locais/<id>/mes?m=AAAA-MM`` (a grade do mês: escala e
  presença);
* ``/novo/visitas/locais/<id>`` (a programação e as visitas recentes).

Cada página tem a mesma porta da antiga (as mesmas checagens, que moram em
``equipes.telas._local`` e ``visitas.telas._local``) e entrega a casca
React. Os dados vêm da MESMA função que monta a tela antiga
(``contexto_*``) e aqui só viram JSON, com as horas e as datas já escritas
como a tela antiga escreve. Os envios vão para o MESMO caminho da antiga
abaixo de ``/api/v1`` e chamam a MESMA ação (``acao_*``): a resposta é o
recado e o endereço de volta, já na tela nova; a recusa da regra é 400 com
a mesma frase. O aplicativo do supervisor (``/app/equipe`` e
``/app/visitas``) continua nas telas antigas. Sem cópia no aparelho
(gestão).
"""
from flask import request, url_for
from flask_login import login_required

from facilities.equipes import telas as eqt
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _sem_cache, nova
from facilities.visitas import telas as vst


def _hm(t):
    return t.strftime('%H:%M')


def _data(d):
    return d.strftime('%d/%m/%Y') if d else None


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/equipes/locais/<int:cid>')
@bp.get('/novo/equipes/locais/<int:cid>/mes')
@login_required
def equipes_local(cid):
    eqt._local(cid)
    return _casca()


@bp.get('/novo/visitas/locais/<int:cid>')
@login_required
def visitas_local(cid):
    vst._local(cid)
    return _casca()


# ── Equipe: os dados ──────────────────────────────────────────────────────

def dias_da_escala(e, dias):
    """Os dias da escala como a antiga escreve: "Seg Ter Qua " (com o espaço
    depois de cada dia, antes do "· desde")."""
    return ''.join(f'{v} ' for k, v in dias if k in e.dias_semana)


@api.get('/equipes/locais/<int:cid>')
@login_required
def api_equipes_local(cid):
    c = eqt.contexto_local(cid)
    loc = c['local']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'hoje': c['hoje'], 'dias': [list(x) for x in c['dias']],
        'funcionarios': [{'id': f.id, 'nome': f.nome, 'funcao': f.funcao or '',
                          'matricula': f.matricula or '', 'user_id': f.user_id,
                          'usa_app': f.usuario is not None, 'ativo': bool(f.is_active)}
                         for f in c['funcionarios']],
        'postos': [{'id': p.id, 'nome': p.nome, 'hora_inicio': _hm(p.hora_inicio),
                    'hora_fim': _hm(p.hora_fim), 'rota_id': p.rota_id,
                    'rota': p.rota.nome if p.rota else None, 'ativo': bool(p.is_active)}
                   for p in c['postos']],
        'escalas': [{'id': e.id, 'funcionario': e.funcionario.nome, 'posto': e.posto.nome,
                     'dias': dias_da_escala(e, c['dias']),
                     'data_inicio': _data(e.data_inicio), 'data_fim': _data(e.data_fim)}
                    for e in c['escalas']],
        'rotas': [{'id': r.id, 'nome': r.nome} for r in c['rotas']],
        'logins': [{'id': u.id, 'nome': u.name, 'email': u.email} for u in c['logins']],
        'pode_montar': c['pode_montar'],
        'links': {'local': nova(url_for('rotas.local', cid=loc.id)),
                  'mes': nova(url_for('equipes.mes', cid=loc.id)),
                  'visitas': nova(url_for('visitas.local', cid=loc.id))},
    })


def celula_do_mes(c):
    """O que a célula da grade mostra (a mesma letra, a mesma classe e o
    mesmo ``title`` da antiga); ``None`` = célula vazia."""
    p = c['presenca']
    if p is not None:
        if p.situacao == 'faltou' and p.cobertura:
            return {'tipo': 'coberta', 'letra': 'C', 'titulo': (
                f'Faltou; cobriu {p.cobertura.funcionario.nome} ({p.cobertura.motivo})')}
        if p.situacao == 'faltou':
            return {'tipo': 'faltou', 'letra': 'F', 'titulo': 'Faltou'}
        if p.situacao == 'atrasou':
            return {'tipo': 'atrasou', 'letra': 'A', 'titulo': 'Atrasou'}
        return {'tipo': 'veio', 'letra': 'V', 'titulo': 'Veio'}
    if c['pendente']:
        return {'tipo': 'pendente', 'letra': '·', 'titulo': 'Escalado, sem presença lançada'}
    if c['previsto']:
        return {'tipo': 'previsto', 'letra': '○', 'titulo': 'Escalado (dia ainda não chegou)'}
    return None


@api.get('/equipes/locais/<int:cid>/mes')
@login_required
def api_equipes_mes(cid):
    c = eqt.contexto_mes(cid, request.args)
    loc, grade = c['local'], c['grade']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'mes': c['primeiro'].strftime('%m/%Y'), 'm': c['primeiro'].strftime('%Y-%m'),
        'anterior': c['anterior'], 'seguinte': c['seguinte'],
        'totais': grade['totais'],
        'dias': [d.day for d in grade['dias']],
        'linhas': [{'funcionario': x['escala'].funcionario.nome, 'posto': x['escala'].posto.nome,
                    'celulas': [celula_do_mes(cel) for cel in x['celulas']]}
                   for x in grade['linhas']],
        'links': {'equipe': nova(url_for('equipes.local', cid=loc.id))},
    })


# ── Equipe: os envios (a mesma ação das telas antigas) ────────────────────

@api.post('/equipes/locais/<int:cid>/funcionarios')
@login_required
def api_equipes_criar_funcionario(cid):
    return _feito(eqt.acao_criar_funcionario(cid, _dados()))


@api.post('/equipes/funcionarios/<int:fid>')
@login_required
def api_equipes_editar_funcionario(fid):
    return _feito(eqt.acao_editar_funcionario(fid, _dados()))


@api.post('/equipes/locais/<int:cid>/postos')
@login_required
def api_equipes_criar_posto(cid):
    return _feito(eqt.acao_criar_posto(cid, _dados()))


@api.post('/equipes/postos/<int:pid>')
@login_required
def api_equipes_editar_posto(pid):
    return _feito(eqt.acao_editar_posto(pid, _dados()))


@api.post('/equipes/locais/<int:cid>/escalas')
@login_required
def api_equipes_criar_escala(cid):
    return _feito(eqt.acao_criar_escala(cid, _dados()))


@api.post('/equipes/escalas/<int:eid>/encerrar')
@login_required
def api_equipes_encerrar_escala(eid):
    return _feito(eqt.acao_encerrar_escala(eid, _dados()))


# ── Visitas: os dados e os envios ─────────────────────────────────────────

@api.get('/visitas/locais/<int:cid>')
@login_required
def api_visitas_local(cid):
    c = vst.contexto_local(cid)
    loc = c['local']
    return _sem_cache({
        'local': {'id': loc.id, 'nome': loc.name},
        'modelos': [{'id': m.id, 'nome': m.nome} for m in c['modelos']],
        'programadas': [{'id': p.id, 'nome': p.nome, 'ativo': bool(p.is_active),
                         'modelo_id': p.modelo_id, 'modelo': p.modelo.nome,
                         'intervalo_dias': p.intervalo_dias,
                         'proxima_em': _data(p.proxima_em),
                         'proxima_em_iso': p.proxima_em.isoformat(),
                         'supervisor_id': p.supervisor_id,
                         'supervisor': p.supervisor.name if p.supervisor else None}
                        for p in c['programadas']],
        'recentes': [{'id': v.id, 'nome': v.programada.nome, 'vencimento': _data(v.vencimento),
                      'quem_fez': v.quem_fez.name if v.quem_fez else None,
                      'status': v.status, 'situacao_rotulo': v.situacao_rotulo,
                      'n_nao_conformes': v.n_nao_conformes or 0,
                      # A visita em si é do aplicativo do supervisor (tela antiga).
                      'url': url_for('visitas.ver', vid=v.id)} for v in c['recentes']],
        'supervisores': [{'id': s.id, 'nome': s.name, 'perfil': s.perfil_rotulo}
                         for s in c['supervisores']],
        'hoje': c['hoje'], 'pode_montar': c['pode_montar'],
        'links': {'checklists': nova(url_for('rotas.local', cid=loc.id))},
    })


@api.post('/visitas/locais/<int:cid>')
@login_required
def api_visitas_criar(cid):
    return _feito(vst.acao_criar(cid, _dados()))


@api.post('/visitas/programadas/<int:pid>')
@login_required
def api_visitas_editar(pid):
    return _feito(vst.acao_editar(pid, _dados()))

