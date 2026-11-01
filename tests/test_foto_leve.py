"""Foto leve (decisão do dono, 01/11/2026: o volume de fotos é o que mais cresce).

* toda foto da equipe guardada fica com no máximo 1280 px no lado maior,
  mesmo que o celular não tenha reduzido (aparelho antigo, redução que falhou);
* o formato não muda (JPEG continua JPEG, PNG continua PNG): o nome do arquivo
  e o controle de reenvio da passagem continuam valendo;
* foto que já é leve, arquivo que não é imagem ou redução que falhou passam
  como vieram — nunca se perde a foto por causa da redução;
* a foto reduzida perde a localização GPS e os outros dados da câmera.
"""
import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from facilities.core import anexos


def _imagem(lado=(4000, 3000), formato='JPEG', exif=None):
    im = Image.effect_noise(lado, 60).convert('RGB')   # ruído: não comprime à toa
    saida = io.BytesIO()
    kw = {'quality': 95} if formato in ('JPEG', 'WEBP') else {}
    if exif is not None:
        kw['exif'] = exif
    im.save(saida, format=formato, **kw)
    return saida.getvalue()


def _abrir(dados):
    return Image.open(io.BytesIO(dados))


@pytest.mark.parametrize('ext, formato', [('jpg', 'JPEG'), ('png', 'PNG'), ('webp', 'WEBP')])
def test_foto_grande_sai_com_1280_no_mesmo_formato(app_module, ext, formato):
    dados = _imagem(formato=formato)
    with app_module.app.app_context():
        leve = anexos.foto_leve(dados, ext)
    im = _abrir(leve)
    assert max(im.size) == 1280 and im.format == formato
    assert len(leve) < len(dados)


def test_foto_ja_leve_passa_como_veio(app_module):
    dados = _imagem((500, 375))
    assert len(dados) <= anexos.FOTO_LEVE_BYTES
    with app_module.app.app_context():
        assert anexos.foto_leve(dados, 'jpg') is dados


def test_pdf_e_arquivo_quebrado_passam_como_vieram(app_module):
    with app_module.app.app_context():
        assert anexos.foto_leve(b'%PDF-1.4 conteudo', 'pdf') == b'%PDF-1.4 conteudo'
        quebrado = b'\xff\xd8\xff' + b'x' * 500_000
        assert anexos.foto_leve(quebrado, 'jpg') == quebrado


def test_foto_reduzida_perde_a_localizacao_da_camera(app_module):
    exif = Image.Exif()
    exif[0x8825] = {2: (12.0, 58.0, 0.0)}           # GPSInfo: latitude
    dados = _imagem(exif=exif.tobytes())
    with app_module.app.app_context():
        leve = anexos.foto_leve(dados, 'jpg')
    assert 0x8825 not in _abrir(leve).getexif()


def test_foto_da_execucao_e_da_visita_e_reduzida_no_servidor(app_module):
    """``ler_imagem`` é a porta das fotos da execução, da referência do
    checklist e da visita de supervisão."""
    from facilities.rotas.servico import ler_imagem
    arq = FileStorage(stream=io.BytesIO(_imagem()), filename='foto.jpg',
                      content_type='image/jpeg')
    with app_module.app.app_context():
        dados, ext, mime = ler_imagem(arq)
    assert ext == 'jpg' and mime == 'image/jpeg' and max(_abrir(dados).size) == 1280


def test_os_numeros_do_celular_sao_os_do_servidor():
    import os
    js = open(os.path.join(os.path.dirname(__file__), '..', 'facilities', 'static', 'js',
                           'foto-leve.js'), encoding='utf-8').read()
    assert f'var LADO_MAX = {anexos.LADO_MAX_FOTO};' in js
    assert f'var LEVE_BYTES = {anexos.FOTO_LEVE_BYTES // 1024} * 1024;' in js
    assert f'var QUALIDADE = {anexos.QUALIDADE_FOTO / 100};' in js
