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


def _numero(nome, padrao):
    try:
        return max(0.1, float(os.environ.get(nome) or padrao))
    except ValueError:
        return padrao


def tempo_limite():
    """Segundos de espera por aparelho (``PUSH_TIMEOUT``, padrão 3). Era 10:
    com o serviço de push engasgado, cada aparelho segurava a requisição."""
    return _numero('PUSH_TIMEOUT', 3)


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
        with urllib.request.urlopen(pedido, timeout=tempo_limite()) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0


def _remetente():
    # Os testes trocam o remetente aqui (nunca chamam serviço de verdade).
    return current_app.extensions.get('facilities_push') or _enviar_de_verdade


def _carga(titulo, texto, link, marca):
    return {'titulo': titulo[:120], 'texto': (texto or '')[:240], 'link': link,
            'marca': marca or link}


def _ids(user_ids):
    ids = {u for u in (user_ids or []) if u}
    if not ids or not (ligado() or 'facilities_push' in current_app.extensions):
        return None
    return ids


def _mandar(inscricoes, carga, enviar=None, app=None):
    """Manda a todos os aparelhos AO MESMO TEMPO (antes: um por vez — 9
    aparelhos com o serviço a 5 s eram 45 s). → [(inscrição, código)];
    código 0 = rede/erro. Exceção no envio vira 0 e log: nunca sobe.

    Espera no máximo ``PUSH_TEMPO_MAXIMO`` (padrão: o tempo limite + 2 s)
    pelo conjunto; o aparelho que não respondeu até lá fica sem anotação."""
    enviar = enviar or _remetente()
    app = app or current_app._get_current_object()

    def um(insc):
        try:
            with app.app_context():
                return insc, enviar(insc, carga)
        except Exception:                    # noqa: BLE001 — o aviso nunca derruba quem chamou
            log.exception('push: falha ao enviar para a inscrição %s', getattr(insc, 'id', '?'))
            return insc, 0

    if len(inscricoes) <= 1:
        return [um(i) for i in inscricoes]
    from concurrent.futures import ThreadPoolExecutor, wait
    paralelo = int(_numero('PUSH_PARALELO', 8))
    maximo = _numero('PUSH_TEMPO_MAXIMO', tempo_limite() + 2)
    grupo = ThreadPoolExecutor(max_workers=max(1, min(paralelo, len(inscricoes))),
                               thread_name_prefix='push')
    try:
        futuros = [grupo.submit(um, i) for i in inscricoes]
        prontos, atrasados = wait(futuros, timeout=maximo)
        if atrasados:
            log.warning('push: %s aparelho(s) sem resposta em %.0f s', len(atrasados), maximo)
        return [f.result() for f in futuros if f in prontos]
    finally:
        grupo.shutdown(wait=False, cancel_futures=True)


def avisar(user_ids, titulo, texto, link='/app/', marca=None):
    """Manda o aviso AGORA a todos os aparelhos das pessoas. Devolve quantos foram.

    As anotações (inscrição morta, falhas) ficam na sessão; o commit é de
    quem chama. Para o aviso de algo que acabou de ser gravado, use
    ``avisar_ao_gravar`` — este aqui não espera a gravação.

    ``marca`` (tag) faz o aviso novo SUBSTITUIR o anterior da mesma coisa no
    celular, em vez de empilhar.
    """
    ids = _ids(user_ids)
    if ids is None:
        return 0
    enviados = 0
    inscricoes = PushInscricao.query.filter(PushInscricao.user_id.in_(ids)).all()
    for insc, codigo in _mandar(inscricoes, _carga(titulo, texto, link, marca)):
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


class _Aparelho:
    """A inscrição copiada para fora da sessão (o envio roda depois do
    commit, sem a sessão)."""
    __slots__ = ('id', 'user_id', 'endpoint', 'p256dh', 'auth', 'aparelho')

    def __init__(self, insc):
        for campo in self.__slots__:
            setattr(self, campo, getattr(insc, campo))


def _anotar(engine, resultados):
    """Anota o resultado do envio numa conexão própria (fora da sessão)."""
    from sqlalchemy import delete, update
    t = PushInscricao.__table__
    mortas = [i.id for i, c in resultados if c in (404, 410)]
    foram = [i.id for i, c in resultados if 200 <= c < 300]
    falharam = [i.id for i, c in resultados if not (200 <= c < 300) and c not in (404, 410)]
    for i, c in resultados:
        if not (200 <= c < 300) and c not in (404, 410):
            log.warning('push recusado (%s) para a inscrição %s', c, i.id)
    if not (mortas or foram or falharam):
        return
    with engine.begin() as con:
        if mortas:
            con.execute(delete(t).where(t.c.id.in_(mortas)))
        if foram:
            con.execute(update(t).where(t.c.id.in_(foram))
                        .values(ultimo_envio_em=datetime.utcnow(), falhas=0))
        if falharam:
            con.execute(update(t).where(t.c.id.in_(falharam))
                        .values(falhas=db.func.coalesce(t.c.falhas, 0) + 1))


def avisar_ao_gravar(user_ids, titulo, texto, link='/app/', marca=None):
    """O aviso no celular de algo gravado NESTA transação: sai só DEPOIS do
    commit (``core.pos_commit``), com a trava e a conexão já soltas.

    Se a gravação for desfeita, o aviso não sai. Se o envio falhar, o que foi
    gravado continua gravado (vira log). Quem chama segue igual: o commit é
    dele. → quantos aparelhos vão receber (0 sem push ligado)."""
    from facilities.core import pos_commit
    ids = _ids(user_ids)
    if ids is None:
        return 0
    aparelhos = [_Aparelho(i) for i in
                 PushInscricao.query.filter(PushInscricao.user_id.in_(ids)).all()]
    if not aparelhos:
        return 0
    carga = _carga(titulo, texto, link, marca)
    enviar, app, engine = _remetente(), current_app._get_current_object(), db.engine

    def mandar():
        _anotar(engine, _mandar(aparelhos, carga, enviar=enviar, app=app))
    pos_commit.depois_de_gravar(mandar)
    return len(aparelhos)


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
