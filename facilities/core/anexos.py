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


# Foto leve (decisão do dono, 01/11/2026: o volume de fotos é o que mais
# cresce no sistema). Toda foto guardada fica com no máximo este lado maior —
# o celular já reduz antes de enviar (static/js/foto-leve.js, os mesmos
# números) e o servidor reduz de novo o que chegar maior (aparelho antigo,
# redução que falhou, foto do público). 1280 px ainda mostram sujeira, piso e
# etiqueta de equipamento; a foto sai com cerca de metade do peso de antes.
LADO_MAX_FOTO = 1280
QUALIDADE_FOTO = 75
# Foto que já é leve passa como veio: não se perde qualidade à toa.
FOTO_LEVE_BYTES = 350 * 1024
LADO_MAX_PUBLICO = LADO_MAX_FOTO


def foto_leve(dados, ext):
    """A foto da equipe reduzida a ``LADO_MAX_FOTO`` no lado maior, no MESMO
    formato (JPEG continua JPEG, PNG continua PNG): o nome do arquivo e o
    controle de reenvio de quem chama não mudam. Não é imagem, já é leve, ou
    a redução falhou (ou ficou maior) → os dados como vieram: nunca se perde
    a foto por causa da redução. Quem chama já conferiu assinatura e tamanho
    em pixels (``imagem_aceitavel``)."""
    ext = (ext or '').lower()
    if ext not in IMAGENS:
        return dados
    from PIL import Image, ImageOps
    try:
        with Image.open(io.BytesIO(dados)) as im:
            if max(im.size) <= LADO_MAX_FOTO and len(dados) <= FOTO_LEVE_BYTES:
                return dados
            im = ImageOps.exif_transpose(im)
            im.thumbnail((LADO_MAX_FOTO, LADO_MAX_FOTO))
            saida = io.BytesIO()
            if ext in ('jpg', 'jpeg'):
                if im.mode not in ('RGB', 'L'):
                    im = im.convert('RGB')
                im.save(saida, format='JPEG', quality=QUALIDADE_FOTO, optimize=True)
            elif ext == 'webp':
                im.save(saida, format='WEBP', quality=QUALIDADE_FOTO)
            else:
                im.save(saida, format='PNG', optimize=True)
    except Exception:
        current_app.logger.warning('foto leve: não foi possível reduzir (%s, %d bytes)',
                                   ext, len(dados))
        return dados
    reduzida = saida.getvalue()
    return reduzida if len(reduzida) < len(dados) else dados


def reduzir_imagem(dados, ext, lado_max=LADO_MAX_PUBLICO):
    """Devolve (dados, ext) com a imagem reduzida a ``lado_max`` pixels no
    lado maior e regravada como JPEG. Quem chama já conferiu assinatura e
    tamanho em pixels (``imagem_aceitavel``)."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(dados)) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        im.thumbnail((lado_max, lado_max))
        saida = io.BytesIO()
        im.save(saida, format='JPEG', quality=QUALIDADE_FOTO, optimize=True)
    return saida.getvalue(), 'jpg'


def storage():
    """O armazenamento do app (disco local ou R2), pendurado nas extensões."""
    return current_app.extensions['facilities_storage']
