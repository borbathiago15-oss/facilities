"""Erros HTTP em português: página com o menu para quem navega, JSON para
quem chamou por JavaScript.

Sem isto o Werkzeug respondia 403/404/413/429 com a página padrão dele, em
inglês e sem o menu — a pessoa ficava sem caminho de volta. E pior: as telas
e a fila sem internet (``static/js/fila-offline.js``) leem a resposta como
JSON. Um 403 em HTML virava "sem conexão" na tela e "sessão vencida" na
fila, que parava naquele item para sempre: as passagens guardadas depois
dele nunca subiam. Em JSON a fila sabe o que fazer — 403/404 é conflito,
413 é recusado — e segue para o próximo.

O 401 de API continua com o ``unauthorized_handler`` da fábrica (JSON
"Sessão expirada"); aqui ficam os erros que chegam como exceção.
"""
from flask import current_app, jsonify, render_template, request

from facilities.extensions import db

TITULOS = {
    400: 'Formulário vencido',
    403: 'Sem acesso',
    404: 'Página não encontrada',
    405: 'Ação indisponível por este caminho',
    413: 'Envio grande demais',
    429: 'Muitas tentativas',
    500: 'Erro no sistema',
}

MENSAGENS = {
    403: 'Você não tem acesso a esta tela ou a esta ação. Se precisa, peça ao '
         'administrador.',
    404: 'Não encontramos o que você procurou. O link pode estar velho, ou o '
         'registro não existe mais.',
    405: 'Esta ação só funciona pelo botão da tela. Volte e use o botão.',
    429: 'Muitas tentativas em pouco tempo. Espere um minuto e tente de novo.',
    500: 'Algo deu errado do nosso lado, e o que você fez pode não ter sido '
         'gravado. Tente de novo em instantes; se continuar, avise o '
         'administrador.',
}

# Só nestes a mensagem própria do ``abort``/exceção vai para a tela (ex.: o
# ``require_client``). Nos outros a descrição é a do Werkzeug, em inglês, ou
# a do Flask-Limiter ("20 per 1 minute").
_COM_MENSAGEM_PROPRIA = (403, 404)


def pede_json():
    """Quem chamou quer JSON (e não uma página)?

    * caminho com ``/api/``, corpo JSON ou ``X-Requested-With`` → sim;
    * ``Sec-Fetch-Mode`` (todo navegador atual manda): só a NAVEGAÇÃO —
      abrir um link, enviar um formulário — recebe página; ``fetch`` recebe
      JSON, seja qual for o caminho;
    * sem esse cabeçalho (navegador antigo, script): página só se o
      ``Accept`` pedir ``text/html`` com todas as letras, como o navegador
      faz ao abrir uma tela — o ``fetch`` manda ``*/*``.
    """
    if request.is_json or '/api/' in request.path:
        return True
    if request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest':
        return True
    modo = request.headers.get('Sec-Fetch-Mode')
    if modo:
        return modo not in ('navigate', 'nested-navigate')
    return not any(tipo in ('text/html', 'application/xhtml+xml')
                   for tipo, _q in request.accept_mimetypes)


def _mensagem(e):
    codigo = e.code
    if codigo in _COM_MENSAGEM_PROPRIA and e.description \
            and e.description != type(e).description:
        return e.description
    if codigo == 413:
        limite = current_app.config.get('MAX_CONTENT_LENGTH') or 0
        mb = max(1, round(limite / (1024 * 1024)))
        return (f'O envio passou do limite de {mb} MB e não foi gravado. Mande '
                'menos arquivos de cada vez (ou fotos menores) e tente de novo.')
    return MENSAGENS.get(codigo, MENSAGENS[500])


def _responder(codigo, mensagem):
    if pede_json():
        return jsonify({'error': mensagem}), codigo
    return render_template('core/erro.html', codigo=codigo,
                           titulo=TITULOS.get(codigo, 'Erro'), mensagem=mensagem), codigo


def _erro_http(e):
    # Arquivo estático que falta (favicon, mapa de fonte) não monta a tela
    # inteira com o menu — a resposta curta do Werkzeug basta.
    if e.code == 404 and request.path.startswith('/static/'):
        return e
    resposta = _responder(e.code, _mensagem(e))
    if e.code == 405 and getattr(e, 'valid_methods', None):
        # O HTTP manda dizer o que vale nesse caminho (cabeçalho Allow).
        corpo, codigo = resposta
        return corpo, codigo, {'Allow': ', '.join(e.valid_methods)}
    return resposta


def _erro_interno(e):
    """500: devolve a sessão do banco ao normal e responde sem depender dele.

    Depois de um erro de banco a transação fica abortada (no Postgres, toda
    consulta seguinte falha) — e a página de erro consulta o banco (o usuário
    logado, o número do sino). Se nem assim der, sai texto puro em português.
    """
    try:
        db.session.rollback()
    except Exception:  # o banco pode estar fora — a resposta sai mesmo assim
        current_app.logger.exception('rollback falhou ao tratar um erro 500')
    try:
        return _responder(500, MENSAGENS[500])
    except Exception:
        current_app.logger.exception('a página de erro 500 não pôde ser montada')
        return MENSAGENS[500], 500, {'Content-Type': 'text/plain; charset=utf-8'}


MSG_CSRF = ('A tela ficou aberta tempo demais e o envio não foi aceito, por segurança. '
            'Recarregue a página e tente de novo.')


def _erro_csrf(_e):
    """O token anti-falsificação (CSRF) faltou ou venceu: antes saía a página
    do Werkzeug, em inglês e em HTML — as telas em JavaScript liam como
    "sem conexão"."""
    return _responder(400, MSG_CSRF)


def registrar(app):
    from flask_wtf.csrf import CSRFError
    for codigo in (403, 404, 405, 413, 429):
        app.register_error_handler(codigo, _erro_http)
    app.register_error_handler(CSRFError, _erro_csrf)
    app.register_error_handler(500, _erro_interno)
