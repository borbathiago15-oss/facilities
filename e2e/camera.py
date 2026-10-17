"""Uma "câmera de mentira" para o Chromium: um vídeo .y4m com um QR no meio."""


def gerar_video_com_qr(texto, destino, lado=480, quadros=10):
    img = _qr_em_imagem(texto, lado)
    ycbcr = img.convert('YCbCr')
    y, cb, cr = ycbcr.split()
    meio = (lado // 2, lado // 2)
    cb, cr = cb.resize(meio), cr.resize(meio)
    with open(destino, 'wb') as f:
        f.write(f'YUV4MPEG2 W{lado} H{lado} F10:1 Ip A1:1 C420jpeg\n'.encode())
        for _ in range(quadros):
            f.write(b'FRAME\n')
            f.write(y.tobytes() + cb.tobytes() + cr.tobytes())


def _qr_em_imagem(texto, lado):
    """O QR desenhado módulo a módulo (sem depender de renderizador)."""
    from PIL import Image, ImageDraw
    from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
    qr = QRCode(None, QRErrorCorrectLevel.M)
    qr.addData(texto)
    qr.make()
    n = qr.getModuleCount()
    borda = 4
    escala = lado // (n + 2 * borda)
    img = Image.new('L', (lado, lado), 255)
    d = ImageDraw.Draw(img)
    x0 = (lado - n * escala) // 2
    for linha in range(n):
        for coluna in range(n):
            if qr.isDark(linha, coluna):
                d.rectangle([x0 + coluna * escala, x0 + linha * escala,
                             x0 + (coluna + 1) * escala - 1, x0 + (linha + 1) * escala - 1],
                            fill=0)
    return img.convert('RGB')
