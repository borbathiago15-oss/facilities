"""Etiquetas de QR em PDF (A4, 2 colunas × 4 linhas).

Cada etiqueta: o QR com o endereço ``/q/<código>``, o nome do ponto, o
ambiente e o setor, e o código em texto (para conferir a etiqueta sem ler o
QR). Feita com o reportlab, que o sistema já usa no relatório da Passagem.
"""
import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLUNAS, LINHAS = 2, 4
MARGEM = 12 * mm
LADO_QR = 38 * mm


def _cortar(texto, limite):
    texto = texto or ''
    return texto if len(texto) <= limite else texto[:limite - 1] + '…'


def _qr(c, url, x, y, lado):
    widget = QrCodeWidget(url, barLevel='M')
    x0, y0, x1, y1 = widget.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def gerar(nome_local, itens):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f'Etiquetas de QR — {nome_local}')
    largura, altura = A4
    w = (largura - 2 * MARGEM) / COLUNAS
    h = (altura - 2 * MARGEM) / LINHAS
    por_pagina = COLUNAS * LINHAS
    for i, item in enumerate(itens):
        if i and i % por_pagina == 0:
            c.showPage()
        pos = i % por_pagina
        col, lin = pos % COLUNAS, pos // COLUNAS
        x = MARGEM + col * w
        y = altura - MARGEM - (lin + 1) * h
        c.setDash(2, 3)
        c.setStrokeGray(0.6)
        c.rect(x + 2 * mm, y + 2 * mm, w - 4 * mm, h - 4 * mm)
        c.setDash()
        _qr(c, item["url"], x + (w - LADO_QR) / 2, y + h - LADO_QR - 6 * mm, LADO_QR)
        cx = x + w / 2
        c.setFillGray(0)
        c.setFont('Helvetica-Bold', 11)
        c.drawCentredString(cx, y + 19 * mm, _cortar(item["nome"], 42))
        c.setFont('Helvetica', 8.5)
        c.drawCentredString(cx, y + 14.5 * mm,
                            _cortar(f"{item['setor']} · {item['ambiente']}", 60))
        c.drawCentredString(cx, y + 10.5 * mm, _cortar(nome_local, 60))
        c.setFont('Courier', 7)
        c.setFillGray(0.35)
        c.drawCentredString(cx, y + 6 * mm, item['codigo'])
    c.save()
    buf.seek(0)
    return buf
