"""E-mail de saída (opcional): hoje só o convite usa.

Sem ``SMTP_HOST`` no ambiente, nada é enviado pelo servidor: a tela oferece
o botão que abre o e-mail do próprio aparelho com o texto pronto. Com o
SMTP configurado, o convite sai sozinho.

Variáveis: ``SMTP_HOST``, ``SMTP_PORT`` (587), ``SMTP_USUARIO``,
``SMTP_SENHA``, ``SMTP_REMETENTE`` (padrão: o usuário) e ``SMTP_SSL=1``
para a porta 465.

Nos testes, ``app.extensions['facilities_correio']`` (uma função
``(para, assunto, texto)``) substitui o envio: nenhum teste fala com
servidor de e-mail de verdade.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def configurado():
    return 'facilities_correio' in current_app.extensions \
        or bool((os.environ.get('SMTP_HOST') or '').strip())


def enviar(para, assunto, texto):
    """Envia; devolve True se saiu. Falha vira log, nunca erro na tela."""
    falso = current_app.extensions.get('facilities_correio')
    if falso is not None:
        falso(para, assunto, texto)
        return True
    host = (os.environ.get('SMTP_HOST') or '').strip()
    if not host:
        return False
    usuario = (os.environ.get('SMTP_USUARIO') or '').strip()
    remetente = (os.environ.get('SMTP_REMETENTE') or '').strip() or usuario
    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = para
    msg.set_content(texto)
    try:
        porta = int(os.environ.get('SMTP_PORT') or 587)
        contexto = ssl.create_default_context()
        if os.environ.get('SMTP_SSL') == '1':
            servidor = smtplib.SMTP_SSL(host, porta, context=contexto, timeout=15)
        else:
            servidor = smtplib.SMTP(host, porta, timeout=15)
            servidor.starttls(context=contexto)
        with servidor:
            if usuario:
                servidor.login(usuario, os.environ.get('SMTP_SENHA') or '')
            servidor.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as erro:
        log.warning('E-mail para %s não saiu: %s', para.split('@')[-1], erro)
        return False
