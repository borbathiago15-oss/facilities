"""API da tela "Armazenamento de fotos" (``/novo/admin/armazenamento``), só
do administrador (``master``). As regras são as de
``facilities/arquivo_fotos/servico.py``; aqui só se entrega e recebe.

* ``GET  /api/v1/admin/armazenamento``: o painel (quanto está guardado, por
  mês e por local, o que já foi arquivado, o que passou do prazo, os lotes);
* ``POST /api/v1/admin/armazenamento/prazo``: muda o prazo (``dias``);
* ``POST /api/v1/admin/armazenamento/arquivar``: o administrador confirmou;
  abre o lote, que o agendador leva adiante aos poucos.

O destino do arquivo NÃO vem da tela: é configurado no ambiente do servidor.
"""
from flask import jsonify, request
from flask_login import current_user, login_required

from facilities.core.acesso import admin_required
from facilities.extensions import db
from facilities.telas import api


def _painel():
    from facilities.arquivo_fotos.servico import painel
    resp = jsonify(painel())
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _recusa(erro):
    db.session.rollback()
    return jsonify({'erro': erro.mensagem}), erro.status


@api.get('/admin/armazenamento')
@login_required
@admin_required
def armazenamento():
    return _painel()


@api.post('/admin/armazenamento/prazo')
@login_required
@admin_required
def armazenamento_prazo():
    from facilities.arquivo_fotos.servico import RegraDoArquivo, salvar_dias
    corpo = request.get_json(silent=True) or {}
    try:
        salvar_dias(current_user, corpo.get('dias'))
    except RegraDoArquivo as erro:
        return _recusa(erro)
    db.session.commit()
    return _painel()


@api.post('/admin/armazenamento/arquivar')
@login_required
@admin_required
def armazenamento_arquivar():
    from facilities.arquivo_fotos.servico import RegraDoArquivo, iniciar
    corpo = request.get_json(silent=True) or {}
    if corpo.get('confirmar') is not True:
        return jsonify({'erro': 'Confirme o arquivamento para começar.'}), 400
    try:
        iniciar(current_user)
    except RegraDoArquivo as erro:
        return _recusa(erro)
    db.session.commit()
    return _painel()
