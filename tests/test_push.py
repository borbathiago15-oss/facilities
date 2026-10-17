"""Fase 4B — o aviso no celular (Web Push), sem serviço de verdade.

* só endereço https dos serviços de push conhecidos (nada de rede interna);
* a assinatura VAPID confere com a chave pública; o corpo é cifrado para o
  celular (e só ele decifra);
* o serviço respondeu 404/410: a inscrição sai; outro aparelho continua.
"""
import base64
import json

import pytest

from facilities.core import push
from tests import fabrica


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _celular():
    """Um "celular": chaves de recebimento como o navegador gera."""
    import os
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    chave = ec.generate_private_key(ec.SECP256R1())
    pub = chave.public_key().public_bytes(serialization.Encoding.X962,
                                          serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    return chave, {'endpoint': 'https://fcm.googleapis.com/fcm/send/abc123',
                   'keys': {'p256dh': _b64(pub), 'auth': _b64(auth)}}, auth


@pytest.mark.parametrize('url,ok', [
    ('https://fcm.googleapis.com/fcm/send/x', True),
    ('https://updates.push.services.mozilla.com/wpush/v2/x', True),
    ('https://web.push.apple.com/x', True),
    ('https://db5p.notify.windows.com/w/?token=x', True),
    ('http://fcm.googleapis.com/x', False),
    ('https://169.254.169.254/latest/meta-data', False),
    ('https://fcm.googleapis.com.golpe.io/x', False),
    ('https://localhost/x', False),
])
def test_so_servicos_de_push_conhecidos(url, ok):
    assert push.endereco_aceito(url) is ok


def test_vapid_assinado_e_corpo_cifrado_so_para_o_celular(monkeypatch, app_module):
    import http_ece
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    privada, publica = push.gerar_chaves()
    monkeypatch.setenv('VAPID_PRIVATE_KEY', privada)
    monkeypatch.setenv('VAPID_PUBLIC_KEY', publica)
    assert push.ligado()
    cab = push._vapid('https://fcm.googleapis.com/fcm/send/x', push._chave_privada())
    jwt = cab.split('t=')[1].split(',')[0]
    h, c, a = jwt.split('.')
    corpo = json.loads(push._de_b64(c))
    assert corpo['aud'] == 'https://fcm.googleapis.com'
    assert cab.endswith(f'k={publica}')
    assinatura = push._de_b64(a)
    r, s = int.from_bytes(assinatura[:32], 'big'), int.from_bytes(assinatura[32:], 'big')
    chave_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push._de_b64(publica))
    chave_pub.verify(encode_dss_signature(r, s), f'{h}.{c}'.encode(), ec.ECDSA(hashes.SHA256()))

    receptor, dados, auth = _celular()

    class Insc:
        p256dh = dados['keys']['p256dh']
        auth = dados['keys']['auth']
    cifrado = push._cifrar(Insc, b'{"titulo": "09:00"}')
    claro = http_ece.decrypt(cifrado, private_key=receptor, auth_secret=auth, version='aes128gcm')
    assert claro == b'{"titulo": "09:00"}'


def test_inscrever_valida_e_celular_compartilhado_passa_para_quem_usa(app_module):
    from app import User, db
    with app_module.app.app_context():
        ana = db.session.get(User, fabrica.pessoa(app_module, 'ana.push@trino.com', 'encarregado'))
        mar = db.session.get(User, fabrica.pessoa(app_module, 'mar.push@trino.com', 'encarregado'))
        _r, dados, _a = _celular()
        push.inscrever(ana, dados)
        db.session.commit()
        push.inscrever(mar, dados)
        db.session.commit()
        from facilities.core.models import PushInscricao
        assert [i.user_id for i in PushInscricao.query] == [mar.id]
        with pytest.raises(ValueError):
            push.inscrever(ana, dict(dados, endpoint='https://intranet.trino.local/x'))
        with pytest.raises(ValueError):
            push.inscrever(ana, {'endpoint': dados['endpoint'], 'keys': {'p256dh': 'x', 'auth': 'y'}})


def test_avisar_remove_inscricao_morta(app_module):
    from app import User, db
    from facilities.core.models import PushInscricao
    with app_module.app.app_context():
        ana = db.session.get(User, fabrica.pessoa(app_module, 'ana.push2@trino.com', 'encarregado'))
        _r, d1, _a = _celular()
        _r, d2, _a = _celular()
        d2['endpoint'] = 'https://updates.push.services.mozilla.com/wpush/v2/morto'
        push.inscrever(ana, d1)
        push.inscrever(ana, d2)
        db.session.commit()
        enviados = []

        def falso(insc, carga):
            enviados.append((insc.endpoint, carga))
            return 410 if 'morto' in insc.endpoint else 201
        app_module.app.extensions['facilities_push'] = falso
        assert push.avisar([ana.id], '09:00 · Porta', 'Limpeza', '/app/turno?ponto=x') == 1
        db.session.commit()
        assert [i.endpoint for i in PushInscricao.query] == [d1['endpoint']]
        assert enviados[0][1]['link'] == '/app/turno?ponto=x'


def test_rotas_de_inscricao(app_module, monkeypatch):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'ana.push3@trino.com', 'encarregado')
    c = fabrica.entrar(app_module, 'ana.push3@trino.com')
    monkeypatch.delenv('VAPID_PUBLIC_KEY', raising=False)
    assert c.get('/app/api/push/chave').get_json() == {'chave': None}
    _r, dados, _a = _celular()
    assert c.post('/app/api/push', json=dados).status_code == 200
    assert c.post('/app/api/push', json={'endpoint': 'https://10.0.0.1/x'}).status_code == 400
    assert c.delete('/app/api/push', json={'endpoint': dados['endpoint']}).status_code == 200
    assert app_module.app.test_client().post('/app/api/push', json=dados).status_code == 401
