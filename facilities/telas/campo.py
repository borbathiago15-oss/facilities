"""API das telas novas do aplicativo de campo (Fase 1 da migração para React).

* ``/api/v1/campo/inicio``: o que o início do aplicativo mostra, com os mesmos
  dados e as mesmas regras da tela antiga (``campo.rotas.contexto_inicio``);
* ``/api/v1/campo/turno``: o "Meu turno", o MESMO JSON que a tela antiga leva
  embutido (``rotas.telas._dados_do_turno``);
* ``/api/v1/campo/links``: os endereços da moldura (o leitor de QR não tem
  outro dado).

Os endereços do turno, do leitor de QR e da passagem de turno apontam para
as telas novas (``/novo/app/...``, ``/novo/passagem-de-turno/...``): quem
está nelas continua nelas. Os demais, para as telas
de sempre, até cada uma ser migrada. As ações continuam nas APIs do
aplicativo que já existem (``/app/api/...``).
"""
from flask import jsonify, url_for
from flask_login import current_user, login_required

from facilities import tempo
from facilities.telas import api


def _hora(dt, fmt):
    return tempo.fmt(dt, fmt) if dt else None


def _nova(caminho, **params):
    """O endereço da tela nova (``/novo/app/...``) que substitui a antiga."""
    return url_for('telas.casca', caminho=caminho, **params)


def _passagem(caminho, **params):
    """A passagem de turno nas telas novas (Fase 2a)."""
    from facilities.telas.passagem import nova
    return nova(caminho, **params)


def _chamados(url):
    """Os chamados nas telas novas (Fase 4a)."""
    from facilities.telas.cadastros import nova
    return nova(url)


def _links():
    u = current_user
    return {
        'ler_qr': _nova('app/ler-qr'),
        'site': url_for('core.inicio'),
        'instalar': url_for('campo.instalar'),
        'passagem': _passagem('turno') if u.can_access('diario_operacional') else None,
        'chamados': _chamados(url_for('chamados.index')) if u.can_view('chamados') else None,
    }


def _turno(itens):
    saida = []
    for item in itens:
        local, entrada, chegada, n = item['local'], item['entrada'], item['chegada'], item['tarefas']
        if entrada and not chegada:
            situacao, url = 'sem_chegada', _nova('app/ler-qr')
        else:
            situacao = 'chegou' if chegada else 'sem_entrada'
            url = _nova('app/turno', local=local.id)
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
            'url': _nova('app/turno', ponto=o.ponto.codigo_qr),
        } for o in c['ocorrencias']],
        'tarefas': [{
            'id': t.id, 'titulo': t.titulo, 'turno': t.turno,
            'data': t.data_turno.strftime('%d/%m'),
            'url': _passagem('turno', client_id=t.client_id),
        } for t in c['tarefas']],
        'pendencias': [{
            'id': p.id, 'titulo': p.titulo, 'desde': _hora(p.created_at, '%d/%m'),
            'url': _passagem('turno', client_id=p.client_id) + f'#pendencia-{p.id}',
        } for p in c['pendencias']],
        'chamados': ([{
            'id': ch.id, 'titulo': ch.titulo, 'prazo': _hora(ch.prazo, '%d/%m %H:%M'),
            'url': _chamados(url_for('chamados.ver', chamado_id=ch.id)),
        } for ch in c['chamados']] if ve_chamados else None),
        'passagem': ([{'nome': loc.name,
                       'url': _passagem('turno', client_id=loc.id)}
                      for loc in c['locais']] if passagem else None),
        'links': _links(),
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.get('/campo/turno')
@login_required
def campo_turno():
    """O "Meu turno": os locais (entrada e chegada de hoje), as tarefas, os
    checklists, os pontos pelo QR, as preventivas e os avisos do público —
    a mesma função (e as mesmas checagens de acesso) da tela antiga."""
    from facilities.core.acesso import clientes_visiveis
    from facilities.rotas.telas import _dados_do_turno
    resp = jsonify({'dados': _dados_do_turno(clientes_visiveis()), 'links': _links()})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.get('/campo/links')
@login_required
def campo_links():
    resp = jsonify(_links())
    resp.headers['Cache-Control'] = 'no-store'
    return resp
