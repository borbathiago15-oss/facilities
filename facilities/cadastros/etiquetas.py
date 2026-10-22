"""Etiquetas de QR em PDF (A4, 2 colunas × 4 linhas): o padrão Trino Facilities.

Cada etiqueta (decisão do dono, 22/10/2026):

* no alto, a logo do Trino Facilities e a logo do cliente (ou o nome dele,
  enquanto não houver logo);
* o QR com o endereço ``/q/<código>`` e, ao lado, o NÚMERO do ponto no local
  (QR 001, 002… na ordem de cadastro: é a ordem de colar no posto), o nome do
  ponto, o setor e o ambiente e o nome do local;
* embaixo, o que fazer com o QR ("aponte a câmera…") e o código em texto,
  para conferir a etiqueta sem ler o QR;
* o QR da ENTRADA do local sai com uma faixa escura: "Entrada — leia ao chegar".

Feita com o reportlab, que o sistema já usa no relatório da Passagem.
"""
import io
import os

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

COLUNAS, LINHAS = 2, 4
MARGEM = 12 * mm
LADO_QR = 36 * mm
ALTURA_LOGO = 8 * mm

# A marca vem do arquivo oficial (static/marca); a cor da faixa de entrada é
# a moldura preta do Trino.
MARCA = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'marca',
                     'trino-facilities.png')
COR_FAIXA = (0.043, 0.051, 0.059)      # #0b0d0f
COR_DESTAQUE = (0.616, 0.125, 0.173)   # #9d202c


def _caber(texto, fonte, tamanho, largura):
    """Corta com reticências até o texto caber na largura (em pontos)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    texto = texto or ''
    if stringWidth(texto, fonte, tamanho) <= largura:
        return texto
    while texto and stringWidth(texto + '…', fonte, tamanho) > largura:
        texto = texto[:-1]
    return texto.rstrip() + '…'


def _qr(c, url, x, y, lado):
    widget = QrCodeWidget(url, barLevel='M')
    x0, y0, x1, y1 = widget.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def _imagem(dados):
    if not dados:
        return None
    try:
        return ImageReader(io.BytesIO(dados))
    except Exception:
        return None


def _desenhar_logo(c, img, x, y, largura_max, alinhar_direita=False):
    """Desenha a logo com ALTURA_LOGO de altura, sem passar de ``largura_max``."""
    lw, lh = img.getSize()
    altura = ALTURA_LOGO
    largura = altura * lw / lh
    if largura > largura_max:
        largura, altura = largura_max, largura_max * lh / lw
    if alinhar_direita:
        x = x - largura
    c.drawImage(img, x, y + (ALTURA_LOGO - altura) / 2, largura, altura,
                mask='auto', preserveAspectRatio=True)


def gerar(nome_local, itens, cliente=None, logo_cliente=None):
    """``itens``: dicionários com nome, setor, ambiente, codigo, url e, se
    houver, numero e entrada."""
    marca = _imagem(open(MARCA, 'rb').read()) if os.path.exists(MARCA) else None
    logo = _imagem(logo_cliente)
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
        _etiqueta(c, x, y, w, h, item, nome_local, cliente, marca, logo)
    c.save()
    buf.seek(0)
    return buf


def _etiqueta(c, x, y, w, h, item, nome_local, cliente, marca, logo):
    # Linha de corte.
    c.setDash(2, 3)
    c.setStrokeGray(0.6)
    c.rect(x + 2 * mm, y + 2 * mm, w - 4 * mm, h - 4 * mm)
    c.setDash()
    esq, dir_ = x + 6 * mm, x + w - 6 * mm
    topo = y + h - 6 * mm

    # Cabeçalho: as duas logos.
    y_logo = topo - ALTURA_LOGO
    if marca is not None:
        _desenhar_logo(c, marca, esq, y_logo, (w - 12 * mm) / 2 - 2 * mm)
    else:
        c.setFont('Helvetica-Bold', 10)
        c.drawString(esq, y_logo + 2 * mm, 'Trino Facilities')
    if logo is not None:
        _desenhar_logo(c, logo, dir_, y_logo, (w - 12 * mm) / 2 - 2 * mm, alinhar_direita=True)
    elif cliente:
        c.setFillGray(0)
        c.setFont('Helvetica-Bold', 10)
        c.drawRightString(dir_, y_logo + 2.5 * mm,
                          _caber(cliente, 'Helvetica-Bold', 10, (w - 12 * mm) / 2 - 2 * mm))

    # Faixa da entrada.
    y_corpo = y_logo - 3 * mm
    if item.get('entrada'):
        c.setFillColorRGB(*COR_FAIXA)
        c.rect(esq, y_corpo - 6 * mm, dir_ - esq, 6 * mm, stroke=0, fill=1)
        c.setFillGray(1)
        c.setFont('Helvetica-Bold', 9.5)
        c.drawCentredString((esq + dir_) / 2, y_corpo - 4.2 * mm,
                            'ENTRADA DO LOCAL — leia ao chegar')
        y_corpo -= 8 * mm

    # QR à esquerda; número e textos à direita.
    lado = min(LADO_QR, y_corpo - (y + 14 * mm))
    _qr(c, item['url'], esq - 2 * mm, y_corpo - lado, lado)
    tx = esq + lado + 1 * mm
    largura_texto = dir_ - tx
    c.setFillColorRGB(*COR_DESTAQUE)
    c.setFont('Helvetica-Bold', 20)
    numero = item.get('numero')
    c.drawString(tx, y_corpo - 8 * mm, f'QR {numero:03d}' if numero else 'QR')
    c.setFillGray(0)
    # O nome do ponto é o que a pessoa procura: até duas linhas.
    linhas = simpleSplit(item['nome'] or '', 'Helvetica-Bold', 10.5, largura_texto)
    if len(linhas) > 2:
        linhas = [linhas[0], _caber(' '.join(linhas[1:]), 'Helvetica-Bold', 10.5,
                                    largura_texto)]
    c.setFont('Helvetica-Bold', 10.5)
    for n, linha in enumerate(linhas or ['']):
        c.drawString(tx, y_corpo - (14 + 4.5 * n) * mm, linha)
    base = y_corpo - (14 + 4.5 * max(len(linhas), 1)) * mm
    c.setFont('Helvetica', 8.5)
    c.drawString(tx, base - 0.5 * mm, _caber(f"{item['ambiente']} · {item['setor']}",
                                               'Helvetica', 8.5, largura_texto))
    c.setFillGray(0.35)
    c.drawString(tx, base - 5 * mm, _caber(nome_local, 'Helvetica', 8.5, largura_texto))

    # Rodapé: o que fazer e o código.
    c.setFillGray(0)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(x + w / 2, y + 10 * mm,
                        'Viu um problema aqui? Aponte a câmera do celular para o QR.')
    c.setFont('Courier', 6.5)
    c.setFillGray(0.35)
    c.drawCentredString(x + w / 2, y + 6 * mm, item['codigo'])
