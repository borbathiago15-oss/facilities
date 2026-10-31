"""API das telas novas do aplicativo de campo (Fase 1 da migração para React).

``/api/v1/campo/inicio`` entrega o que o início do aplicativo mostra, com os
mesmos dados e as mesmas regras da tela antiga (``campo.rotas.contexto_inicio``).
Os endereços apontam para as telas de sempre até cada uma ser migrada.
"""
from flask import jsonify, url_for
from flask_login import current_user, login_required

from facilities import tempo
from facilities.telas import api


def _hora(dt, fmt):
    return tempo.fmt(dt, fmt) if dt else None


def _turno(itens):
    saida = []
    for item in itens:
        local, entrada, chegada, n = item['local'], item['entrada'], item['chegada'], item['tarefas']
        if entrada and not chegada:
            situacao, url = 'sem_chegada', url_for('campo.ler_qr')
        else:
            situacao = 'chegou' if chegada else 'sem_entrada'
            url = url_for('rotas.turno', local=local.id)
        saida.append({
            'local_id': local.id,
            'local': local.name,
            'situacao': situacao,
            'entrada': entrada.nome if entrada else None,
            'chegou_as': _hora(chegada.chegou_em, '%H:%M') if chegada else None,
            'tarefas': n['total'],
            'abertas': n['abertas'],
            'url': url,
        })
    return saida


@api.get('/campo/inicio')
@login_required
def campo_inicio():
    from facilities.campo.rotas import contexto_inicio
    c = contexto_inicio()
    u = current_user
    passagem = u.can_access('diario_operacional')
    ve_chamados = u.can_view('chamados')
    resp = jsonify({
        'hoje': tempo.fmt(tempo.agora(), '%d/%m/%Y'),
        'tem_locais': bool(c['locais']),
        'turno': _turno(c['turno_por_local']),
        'material': url_for('materiais.app') if c['usa_material'] else None,
        'equipe': url_for('equipes.app_equipe') if c['lanca_presenca'] else None,
        'visitas': ({'url': url_for('visitas.app_lista'), 'abertas': c['visitas_abertas']}
                    if c['lanca_presenca'] else None),
        'ocorrencias': [{
            'id': o.id,
            'local': o.ponto.ambiente.setor.local.name,
            'ambiente': o.ponto.ambiente.nome,
            'titulo': o.titulo,
            'ponto': o.ponto.nome,
            'hora': _hora(o.criada_em, '%H:%M'),
            'texto': o.texto or '',
            'sua': o.responsavel_id == u.id,
            'url': url_for('rotas.turno', ponto=o.ponto.codigo_qr),
        } for o in c['ocorrencias']],
        'tarefas': [{
            'id': t.id, 'titulo': t.titulo, 'turno': t.turno,
            'data': t.data_turno.strftime('%d/%m'),
            'url': url_for('diario_operacional.turno', client_id=t.client_id),
        } for t in c['tarefas']],
        'pendencias': [{
            'id': p.id, 'titulo': p.titulo, 'desde': _hora(p.created_at, '%d/%m'),
            'url': url_for('diario_operacional.turno', client_id=p.client_id)
            + f'#pendencia-{p.id}',
        } for p in c['pendencias']],
        'chamados': ([{
            'id': ch.id, 'titulo': ch.titulo, 'prazo': _hora(ch.prazo, '%d/%m %H:%M'),
            'url': url_for('chamados.ver', chamado_id=ch.id),
        } for ch in c['chamados']] if ve_chamados else None),
        'passagem': ([{'nome': loc.name,
                       'url': url_for('diario_operacional.turno', client_id=loc.id)}
                      for loc in c['locais']] if passagem else None),
        'links': {
            'ler_qr': url_for('campo.ler_qr'),
            'site': url_for('core.inicio'),
            'instalar': url_for('campo.instalar'),
            'passagem': url_for('diario_operacional.turno') if passagem else None,
            'chamados': url_for('chamados.index') if ve_chamados else None,
        },
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp
