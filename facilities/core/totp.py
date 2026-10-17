"""Código de 6 dígitos que muda a cada 30 s (TOTP, RFC 6238), só com a
biblioteca padrão — o mesmo do Trino Intelligence, com uma trava a mais:
o código aceito não vale de novo (``verificar`` devolve o passo usado, e
quem chama grava em ``User.totp_ultimo_passo``).
"""
import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

DIGITOS = 6
PERIODO = 30
EMISSOR = 'Trino Facilities'


def novo_segredo(tamanho=20):
    return base64.b32encode(os.urandom(tamanho)).decode('ascii').rstrip('=')


def _hotp(segredo, contador):
    chave = base64.b32decode(segredo.upper() + '=' * (-len(segredo) % 8))
    resumo = hmac.new(chave, struct.pack('>Q', contador), hashlib.sha1).digest()
    inicio = resumo[-1] & 0x0F
    numero = struct.unpack('>I', resumo[inicio:inicio + 4])[0] & 0x7FFFFFFF
    return str(numero % (10 ** DIGITOS)).zfill(DIGITOS)


def passo(instante=None):
    return int((instante if instante is not None else time.time()) // PERIODO)


def codigo(segredo, instante=None):
    return _hotp(segredo, passo(instante))


def verificar(segredo, digitado, ultimo_passo=None, instante=None, janela=1):
    """Devolve o passo do código aceito, ou ``None``.

    Aceita o passo atual e um para cada lado (relógio do celular adiantado
    ou atrasado). Recusa passo igual ou anterior ao último aceito: o mesmo
    código, ou um mais velho, não abre a conta duas vezes.
    """
    if not segredo or not digitado:
        return None
    digitado = str(digitado).strip().replace(' ', '')
    if not digitado.isdigit() or len(digitado) != DIGITOS:
        return None
    agora = passo(instante)
    for delta in range(-janela, janela + 1):
        p = agora + delta
        if ultimo_passo is not None and p <= ultimo_passo:
            continue
        if hmac.compare_digest(_hotp(segredo, p), digitado):
            return p
    return None


def uri(segredo, conta):
    rotulo = quote(f'{EMISSOR}:{conta}')
    return (f'otpauth://totp/{rotulo}?secret={segredo}&issuer={quote(EMISSOR)}'
            f'&digits={DIGITOS}&period={PERIODO}')


def qr_svg(texto, lado=200):
    """O QR do cadastro no aplicativo autenticador, como SVG (sem script)."""
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    w = QrCodeWidget(texto, barLevel='M')
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(w)
    svg = renderSVG.drawToString(d)
    return svg[svg.index('<svg'):]
