"""Regras de anexo da casa: o que entra, o tamanho e a assinatura dos bytes.

Extensão E assinatura são conferidas: renomear um executável para .pdf não o
coloca no armazenamento. Passagem de turno e chamados usam a MESMA regra.
"""
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


def storage():
    """O armazenamento do app (disco local ou R2), pendurado nas extensões."""
    return current_app.extensions['facilities_storage']
