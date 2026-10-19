"""Regras de anexo da casa: o que entra, o tamanho e a assinatura dos bytes.

Extensão E assinatura são conferidas: renomear um executável para .pdf não o
coloca no armazenamento. Passagem de turno e chamados usam a MESMA regra.
"""
import io

from flask import current_app

ANEXO_TIPOS = {
    'pdf':  'application/pdf',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls':  'application/vnd.ms-excel',
    'csv':  'text/csv',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc':  'application/msword',
    'png':  'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp',
}
ANEXO_MAX = 25 * 1024 * 1024
# Os primeiros bytes de cada formato. CSV é texto puro, sem assinatura.
ANEXO_ASSINATURA = {
    'pdf':  (b'%PDF',),
    'xlsx': (b'PK\x03\x04',), 'docx': (b'PK\x03\x04',),
    'xls':  (b'\xd0\xcf\x11\xe0',), 'doc': (b'\xd0\xcf\x11\xe0',),
    'png':  (b'\x89PNG\r\n\x1a\n',),
    'jpg':  (b'\xff\xd8\xff',), 'jpeg': (b'\xff\xd8\xff',),
    'webp': (b'RIFF',),
}

IMAGENS = ('png', 'jpg', 'jpeg', 'webp')
# Câmera de celular comum: 12 a 50 megapixels. Acima disso, ninguém tira foto
# de posto — é arquivo montado para derrubar o servidor ao abrir (uma "bomba"
# de 13000 x 13000 pixels pesava 493 KB e consumia 1,7 GB no PDF do
# relatório; auditoria SEC-005).
PIXELS_MAX = 50_000_000


def imagem_aceitavel(dados, ext):
    """Para imagem, além da assinatura: o arquivo abre (só o cabeçalho, sem
    decodificar) e o tamanho em pixels é de foto de verdade. Outros tipos
    passam direto (a assinatura é conferida por quem chama)."""
    ext = (ext or '').lower()
    if ext not in IMAGENS:
        return True
    if ext == 'webp' and dados[8:12] != b'WEBP':
        return False                    # RIFF também é WAV/AVI
    from PIL import Image
    try:
        with Image.open(io.BytesIO(dados)) as im:
            largura, altura = im.size
    except Exception:
        return False                    # inclui DecompressionBombError
    return 0 < largura * altura <= PIXELS_MAX


def storage():
    """O armazenamento do app (disco local ou R2), pendurado nas extensões."""
    return current_app.extensions['facilities_storage']
