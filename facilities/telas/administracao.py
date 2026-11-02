"""API das telas novas das pessoas e dos locais do administrador (Fase 6a da
migração para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:
``/novo/admin/usuarios`` (cadastrar, editar, ativar/desativar, "Gerar senha
temporária" e "Desligar a segunda etapa") e ``/novo/admin/contratos`` (os
locais: cadastrar e editar). Só o administrador, como as antigas
(``admin_required`` na página, na leitura e nos envios).

Os dados vêm da MESMA função que monta a tela antiga
(``core.admin.contexto_usuarios`` e ``contexto_contratos``); os envios vão
ao mesmo caminho abaixo de ``/api/v1`` e chamam a MESMA ação (``acao_*``),
com o mesmo recado, a mesma recusa (400) e o endereço de volta já na tela
nova.

A senha temporária (cadastrar e "Gerar senha temporária") aparece uma vez
só, como a chave da integração: a leitura nunca a traz (nem o hash); o
texto vai só na resposta do envio que a cria (``no-store``, sem recado na
sessão) e a tela nova o guarda só no estado do componente.
"""
from flask import jsonify, url_for
from flask_login import login_required

from facilities.core import admin as adm
from facilities.core.acesso import admin_required
from facilities.core.hierarquia import cadeia_acima
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _recados, _sem_cache, nova


@bp.get('/novo/admin/usuarios')
@bp.get('/novo/admin/contratos')
@login_required
@admin_required
def admin_cadastros():
    return _casca()


# ── Pessoas ──────────────────────────────────────────────────────────────

def _pessoa(u):
    return {
        'id': u.id, 'nome': u.name, 'email': u.email, 'perfil': u.role,
        'perfil_rotulo': u.perfil_rotulo, 'ativo': bool(u.is_active),
        'todos_os_locais': bool(u.all_clients), 'superior_id': u.superior_id,
        'cliente_id': u.cliente_id, 'locais': [c.id for c in u.clients],
        'permissoes': [p for p in u.permissions], 'segunda_etapa': bool(u.totp_ativo),
        'alcance': ('todos os locais' if u.role == 'master' or u.all_clients
                    else f'{len(u.clients)} local(is) direto(s)'),
        'cadeia': [{'nome': p.name, 'perfil': p.perfil_rotulo}
                   for p in reversed(cadeia_acima(u))],
    }


@api.get('/admin/usuarios')
@login_required
@admin_required
def api_admin_usuarios():
    c = adm.contexto_usuarios()
    return _sem_cache({
        'pessoas': [_pessoa(u) for u in c['pessoas']],
        'locais': [{'id': x.id, 'nome': x.name, 'ativo': bool(x.is_active)}
                   for x in c['contratos']],
        'perfis': [[k, v] for k, v in c['perfis'].items()],
        'permissoes': [[k, v] for k, v in c['permissoes'].items()],
        'superiores': [{'id': s.id, 'nome': s.name, 'perfil': s.perfil_rotulo}
                       for s in c['superiores']],
        'clientes': [{'id': k.id, 'nome': k.nome} for k in c['clientes']],
    })


def _com_senha(feito, texto, destino):
    """A resposta do envio que cria a senha temporária: o texto vai só aqui."""
    corpo = {'recados': _recados(), 'destino': nova(destino)}
    if feito is not None:
        u, senha = feito
        corpo['senha'] = {'texto': texto(u, senha), 'senha': senha}
    elif any(r['tipo'] == 'danger' for r in corpo['recados']):
        erro = next(r['texto'] for r in corpo['recados'] if r['tipo'] == 'danger')
        resp = jsonify({**corpo, 'error': erro})
        resp.headers['Cache-Control'] = 'no-store'
        return resp, 400
    resp = jsonify(corpo)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.post('/admin/usuarios')
@login_required
@admin_required
def api_admin_criar_usuario():
    return _com_senha(adm.acao_criar_usuario(_dados()), adm._texto_da_senha_nova,
                      url_for('admin.usuarios'))


@api.post('/admin/usuarios/<int:uid>')
@login_required
@admin_required
def api_admin_editar_usuario(uid):
    return _feito(adm.acao_editar_usuario(uid, _dados()))


@api.post('/admin/usuarios/<int:uid>/nova-senha')
@login_required
@admin_required
def api_admin_nova_senha(uid):
    return _com_senha(adm.acao_nova_senha(uid), adm._texto_da_senha_gerada,
                      url_for('admin.usuarios'))


@api.post('/admin/usuarios/<int:uid>/desligar-codigo')
@login_required
@admin_required
def api_admin_desligar_codigo(uid):
    return _feito(adm.acao_desligar_codigo(uid))


# ── Locais ───────────────────────────────────────────────────────────────

def _local(c):
    return {
        'id': c.id, 'nome': c.name, 'centro_de_custo': c.cost_center or '',
        'endereco': c.endereco or '', 'responsavel_id': c.responsible_user_id,
        'responsavel': c.responsavel.name if c.responsavel else None,
        'cliente_id': c.contratante_id,
        'cliente': c.contratante.nome if c.contratante else None,
        'estado_id': c.estado_id, 'estado': c.estado.sigla if c.estado else None,
        'ativo': bool(c.is_active),
        'links': {'estrutura': nova(url_for('cadastros.local', cid=c.id)),
                  'passagem': nova(url_for('diario_operacional.configuracao',
                                           client_id=c.id))},
    }


@api.get('/admin/contratos')
@login_required
@admin_required
def api_admin_contratos():
    c = adm.contexto_contratos()
    return _sem_cache({
        'locais': [_local(x) for x in c['contratos']],
        'gestores': [{'id': g.id, 'nome': g.name} for g in c['gestores']],
        'clientes': [{'id': k.id, 'nome': k.nome, 'ativo': bool(k.is_active)}
                     for k in c['clientes']],
        'estados': [{'id': e.id, 'nome': e.nome, 'ativo': bool(e.is_active)}
                    for e in c['estados']],
        'links': {'empresas': nova(url_for('cadastros.empresas')),
                  'clientes': nova(url_for('cadastros.clientes')),
                  'estados': nova(url_for('cadastros.estados'))},
    })


@api.post('/admin/contratos')
@login_required
@admin_required
def api_admin_criar_contrato():
    return _feito(adm.acao_criar_contrato(_dados()))


@api.post('/admin/contratos/<int:cid>')
@login_required
@admin_required
def api_admin_editar_contrato(cid):
    return _feito(adm.acao_editar_contrato(cid, _dados()))
