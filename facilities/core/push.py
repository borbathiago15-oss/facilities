"""Aviso no celular com o aplicativo fechado (Web Push, Fase 4B).

Feito só com ``cryptography`` (a assinatura VAPID, ES256) e ``http_ece`` (a
cifra aes128gcm do corpo, RFC 8291) — sem a pywebpush, que traria aiohttp e
requests junto.

Configuração (ver README): ``VAPID_PRIVATE_KEY`` (PEM, ou a chave em
base64url), ``VAPID_PUBLIC_KEY`` (base64url do ponto não comprimido) e
``VAPID_SUBJECT`` (``mailto:``). ``flask push chaves`` gera o par. Sem as
chaves, o push fica desligado e o resto do sistema segue (os avisos ficam
no sino e nas telas).

Segurança: o servidor faz POST no endereço que o navegador entregou. Por
isso só aceita endereço https dos serviços de push conhecidos
(``SERVICOS``) — sem isso, a inscrição viraria um jeito de fazer o servidor
chamar qualquer endereço da rede interna.
"""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from flask import current_app

from facilities.extensions import db
from facilities.core.models import PushInscricao

log = logging.getLogger(__name__)

SERVICOS = ('fcm.googleapis.com', 'android.googleapis.com', 'updates.push.services.mozilla.com',
            'push.apple.com', 'notify.windows.com')
TEMPO_DE_VIDA = 3600       # segundos que o serviço guarda o aviso se o celular estiver fora


def _b64(dados):
    return base64.urlsafe_b64encode(dados).rstrip(b'=').decode('ascii')


def _de_b64(texto):
    texto = (texto or '').strip()
    return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))


def endereco_aceito(endpoint):
    try:
        u = urlparse(endpoint or '')
    except ValueError:
        return False
    host = (u.hostname or '').lower()
    return u.scheme == 'https' and any(host == s or host.endswith('.' + s) for s in SERVICOS)


def gerar_chaves():
    """(privada em base64url, pública em base64url) para o VAPID."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    chave = ec.generate_private_key(ec.SECP256R1())
    privada = chave.private_numbers().private_value.to_bytes(32, 'big')
    publica = chave.public_key().public_bytes(serialization.Encoding.X962,
                                              serialization.PublicFormat.UncompressedPoint)
    return _b64(privada), _b64(publica)


def chave_publica():
    return (os.environ.get('VAPID_PUBLIC_KEY') or '').strip() or None


def _chave_privada():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    bruta = (os.environ.get('VAPID_PRIVATE_KEY') or '').strip()
    if not bruta:
        return None
    if 'BEGIN' in bruta:
        return serialization.load_pem_private_key(bruta.replace('\\n', '\n').encode(), None)
    return ec.derive_private_key(int.from_bytes(_de_b64(bruta), 'big'), ec.SECP256R1())


def ligado():
    return bool(chave_publica() and (os.environ.get('VAPID_PRIVATE_KEY') or '').strip())


def _vapid(endpoint, chave):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    u = urlparse(endpoint)
    cabecalho = _b64(json.dumps({'typ': 'JWT', 'alg': 'ES256'}).encode())
    corpo = _b64(json.dumps({
        'aud': f'{u.scheme}://{u.netloc}', 'exp': int(time.time()) + 12 * 3600,
        'sub': (os.environ.get('VAPID_SUBJECT') or 'mailto:facilities@grupotrino.com.br'),
    }).encode())
    assinado = f'{cabecalho}.{corpo}'.encode()
    r, s = decode_dss_signature(chave.sign(assinado, ec.ECDSA(hashes.SHA256())))
    jwt = f'{cabecalho}.{corpo}.{_b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}'
    return f'vapid t={jwt}, k={chave_publica()}'


def _cifrar(inscricao, dados):
    import http_ece
    from cryptography.hazmat.primitives.asymmetric import ec
    efemera = ec.generate_private_key(ec.SECP256R1())
    return http_ece.encrypt(dados, private_key=efemera, dh=_de_b64(inscricao.p256dh),
                            auth_secret=_de_b64(inscricao.auth), version='aes128gcm')


def _enviar_de_verdade(inscricao, carga):
    """POST no serviço de push. → código HTTP (0 = rede)."""
    chave = _chave_privada()
    corpo = _cifrar(inscricao, json.dumps(carga).encode())
    pedido = urllib.request.Request(inscricao.endpoint, data=corpo, method='POST', headers={
        'Authorization': _vapid(inscricao.endpoint, chave),
        'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream',
        'TTL': str(TEMPO_DE_VIDA), 'Urgency': 'high'})
    try:
        with urllib.request.urlopen(pedido, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0


def _remetente():
    # Os testes trocam o remetente aqui (nunca chamam serviço de verdade).
    return current_app.extensions.get('facilities_push') or _enviar_de_verdade


def avisar(user_ids, titulo, texto, link='/app/', marca=None):
    """Manda o aviso a todos os aparelhos das pessoas. Devolve quantos foram.

    ``marca`` (tag) faz o aviso novo SUBSTITUIR o anterior da mesma coisa no
    celular, em vez de empilhar.
    """
    ids = {u for u in (user_ids or []) if u}
    if not ids or not (ligado() or 'facilities_push' in current_app.extensions):
        return 0
    carga = {'titulo': titulo[:120], 'texto': (texto or '')[:240], 'link': link,
             'marca': marca or link}
    enviados = 0
    enviar = _remetente()
    for insc in PushInscricao.query.filter(PushInscricao.user_id.in_(ids)).all():
        codigo = enviar(insc, carga)
        if codigo in (404, 410):
            db.session.delete(insc)             # o navegador desfez a inscrição
            continue
        if 200 <= codigo < 300:
            insc.ultimo_envio_em = datetime.utcnow()
            insc.falhas = 0
            enviados += 1
        else:
            insc.falhas = (insc.falhas or 0) + 1
            log.warning('push recusado (%s) para a inscrição %s', codigo, insc.id)
    return enviados


def inscrever(user, dados, aparelho=''):
    endpoint = str((dados or {}).get('endpoint') or '')
    chaves = (dados or {}).get('keys') or {}
    p256dh, auth = str(chaves.get('p256dh') or ''), str(chaves.get('auth') or '')
    if not endereco_aceito(endpoint) or len(endpoint) > 600:
        raise ValueError('Endereço de aviso não reconhecido.')
    try:
        if len(_de_b64(p256dh)) != 65 or len(_de_b64(auth)) < 16:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Chaves de aviso inválidas.')
    uid = user.id
    insc = PushInscricao.query.filter_by(endpoint=endpoint).first()
    if insc is None:
        insc = PushInscricao(endpoint=endpoint, user_id=uid, p256dh=p256dh, auth=auth)
        db.session.add(insc)
    # O mesmo celular com outra pessoa logada: a inscrição passa para quem
    # está usando agora (celular compartilhado do posto).
    insc.user_id, insc.p256dh, insc.auth = uid, p256dh, auth
    insc.aparelho = (aparelho or '')[:120]
    insc.falhas = 0
    return insc
