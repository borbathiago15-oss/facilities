"""Bloco D + B (antes da produção, revisão de 22/10/2026).

* a imagem não roda o app como root e o código é só leitura;
* a API de integração só dá balde próprio à chave VÁLIDA; sem chave, o
  limite é por endereço e o 401 é registrado uma vez por hora por endereço;
* a foto do QR público é reduzida no servidor e tem teto por dia;
* o agendador apaga o que passou do prazo de retenção (só foto de
  ocorrência resolvida, acessos da API e rodadas do agendador);
* limites em memória com vários workers viram aviso (ou recusa) na
  imagem de produção;
* o espelho dos anexos no R2 copia só o que falta.
"""
import io
import os
from datetime import datetime, timedelta

import pytest
from PIL import Image

from tests import fabrica

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arquivo(*partes):
    with open(os.path.join(RAIZ, *partes), encoding='utf-8') as f:
        return f.read()


def _jpeg(lado=3000):
    im = Image.new('RGB', (lado, lado * 2 // 3), (120, 160, 200))
    saida = io.BytesIO()
    im.save(saida, format='JPEG', quality=95)
    return saida.getvalue()


# ── Imagem e CI ───────────────────────────────────────────────────────────

def test_imagem_larga_o_privilegio_e_codigo_e_so_leitura():
    dockerfile = _arquivo('Dockerfile')
    assert 'gosu' in dockerfile
    assert 'USER facilities' not in dockerfile          # o entrypoint larga o privilégio
    assert 'COPY --chown' not in dockerfile             # código do root, só leitura
    entrypoint = _arquivo('docker-entrypoint.sh')
    assert 'exec gosu facilities "$0" "$@"' in entrypoint
    assert 'chown -R facilities "$UPLOAD_FOLDER"' in entrypoint
    assert 'anexos espelhar' in entrypoint
    guia = _arquivo('docs', 'DEPLOY_RAILWAY.md')
    assert 'RAILWAY_RUN_UID=0' not in guia


def test_ci_com_permissao_minima_actions_fixadas_e_auditoria():
    ci = _arquivo('.github', 'workflows', 'ci.yml')
    assert 'permissions:\n  contents: read' in ci
    assert '@v4\n' not in ci and '@v5\n' not in ci     # fixadas por SHA
    assert 'pip-audit -r requirements.txt' in ci
    assert 'redis==' in _arquivo('requirements.txt')


# ── API de integração ─────────────────────────────────────────────────────

@pytest.fixture()
def cena(app_module):
    from app import db
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        db.session.commit()
    return ids


def _chave(app_module, cena):
    from app import User, db
    from facilities.integracao import servico
    with app_module.app.app_context():
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        ch, texto = servico.criar_chave('Intelligence', [cena['local']], False, admin)
        db.session.commit()
        return ch.id, texto


def test_balde_do_limite_so_para_chave_valida(app_module, cena):
    from facilities.integracao.api import _chave_do_limite, _sem_chave_valida
    kid, texto = _chave(app_module, cena)
    app = app_module.app
    with app.test_request_context('/api/integracao/v1/locais',
                                  headers={'Authorization': f'Bearer {texto}'}):
        assert _chave_do_limite() == f'integracao:{kid}' and not _sem_chave_valida()
    prefixo = texto.split('_')[1]
    for falso in (f'Bearer fac_{prefixo}_segredoerrado', 'Bearer fac_zzzzzzzz_x', 'nada'):
        with app.test_request_context('/api/integracao/v1/locais',
                                      headers={'Authorization': falso},
                                      environ_base={'REMOTE_ADDR': '10.0.0.9'}):
            # Prefixo real com segredo errado NÃO consome a cota da chave.
            assert _chave_do_limite() == 'ip:10.0.0.9' and _sem_chave_valida()


def test_401_registrado_uma_vez_por_endereco_por_hora(app_module, cena):
    from facilities.integracao.models import IntegracaoAcesso
    c = app_module.app.test_client()
    for _ in range(5):
        r = c.get('/api/integracao/v1/locais', headers={'Authorization': 'Bearer fac_a_b'},
                  environ_base={'REMOTE_ADDR': '10.0.0.7'})
        assert r.status_code == 401
    r = c.get('/api/integracao/v1/locais', headers={'Authorization': 'Bearer fac_a_b'},
              environ_base={'REMOTE_ADDR': '10.0.0.8'})
    assert r.status_code == 401
    with app_module.app.app_context():
        linhas = IntegracaoAcesso.query.filter_by(status=401).all()
        assert sorted(a.ip for a in linhas) == ['10.0.0.7', '10.0.0.8']


# ── QR público ────────────────────────────────────────────────────────────

def test_foto_do_publico_e_reduzida_no_servidor(app_module, cena):
    from facilities.core.anexos import storage
    from facilities.rotas.models import OcorrenciaPublica
    original = _jpeg(3000)
    assert len(original) > 50_000
    c = app_module.app.test_client()
    r = c.post(f"/q/{cena['qr']}/ocorrencia",
               data={'tipo': 'sujo', 'texto': 'piso', 'foto': (io.BytesIO(original), 'f.jpg')},
               content_type='multipart/form-data')
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    with app_module.app.app_context():
        oc = OcorrenciaPublica.query.one()
        assert oc.foto_key.endswith('.jpg') and oc.foto_mime == 'image/jpeg'
        guardada = storage().load(oc.foto_key)
        assert len(guardada) < len(original)
        with Image.open(io.BytesIO(guardada)) as im:
            assert max(im.size) <= 1600


def test_qr_publico_tem_teto_por_dia():
    fonte = _arquivo('facilities', 'rotas', 'publico.py')
    assert "@limiter.limit('100 per day', key_func=_chave_do_qr)" in fonte
    assert 'FOTO_MAX = 3 * 1024 * 1024' in _arquivo('facilities', 'rotas', 'ocorrencias.py')


# ── Retenção ──────────────────────────────────────────────────────────────

def test_retencao_apaga_so_o_que_passou_do_prazo(app_module, cena):
    from app import User, db
    from facilities.cadastros.models import PontoInspecao
    from facilities.core import retencao
    from facilities.core.anexos import storage
    from facilities.integracao.models import IntegracaoAcesso
    from facilities.rotas import ocorrencias
    from facilities.rotas.models import AgendadorExecucao, OcorrenciaPublica
    from facilities.object_storage import NotFound
    agora = datetime(2026, 10, 22, 12, 0)
    with app_module.app.app_context():
        ponto = db.session.get(PontoInspecao, cena['ponto'])
        admin = User.query.filter_by(email='admin@grupotrino.com.br').one()
        velha = ocorrencias.abrir(ponto, 'sujo', 'antiga', agora_utc=agora - timedelta(days=200))
        nova = ocorrencias.abrir(ponto, 'sujo', 'recente', agora_utc=agora - timedelta(days=10))
        aberta = ocorrencias.abrir(ponto, 'sujo', 'aberta', agora_utc=agora - timedelta(days=200))
        for oc in (velha, nova, aberta):
            oc.foto_key = f'ocorrencias/teste-{oc.texto}.jpg'
            oc.foto_mime = 'image/jpeg'
            storage().save(oc.foto_key, b'\xff\xd8\xff', 'image/jpeg')
        ocorrencias.resolver(velha, admin, agora_utc=agora - timedelta(days=120))
        ocorrencias.resolver(nova, admin, agora_utc=agora - timedelta(days=5))
        db.session.add(IntegracaoAcesso(chave_id=None, em=agora - timedelta(days=400),
                                        rota='locais', status=401, ip='1.1.1.1'))
        db.session.add(IntegracaoAcesso(chave_id=None, em=agora - timedelta(days=10),
                                        rota='locais', status=401, ip='1.1.1.2'))
        db.session.add(AgendadorExecucao(origem='comando', iniciada_em=agora - timedelta(days=100),
                                         concluida_em=agora - timedelta(days=100), ok=True))
        db.session.add(AgendadorExecucao(origem='comando', iniciada_em=agora - timedelta(days=1),
                                         concluida_em=agora - timedelta(days=1), ok=True))
        db.session.commit()
        resumo = retencao.aplicar(agora)
        db.session.commit()
        assert resumo == {'fotos': 1, 'acessos': 1, 'rodadas': 1}
        velha, nova, aberta = [db.session.get(OcorrenciaPublica, o.id) for o in (velha, nova, aberta)]
        assert velha.foto_key is None and velha.status == 'resolvida'   # o registro fica
        assert nova.foto_key and aberta.foto_key                          # dentro do prazo / não resolvida
        with pytest.raises(NotFound):
            storage().load('ocorrencias/teste-antiga.jpg')
        assert IntegracaoAcesso.query.count() == 1
        assert AgendadorExecucao.query.count() == 1
        # Desligado por ambiente: não toca em nada.
        os.environ['RETENCAO_FOTO_OCORRENCIA_DIAS'] = '0'
        try:
            assert retencao.prazo('FOTO_OCORRENCIA_DIAS') == 0
        finally:
            del os.environ['RETENCAO_FOTO_OCORRENCIA_DIAS']


def test_agendador_chama_a_retencao():
    assert 'retencao.aplicar(agora_utc)' in _arquivo('facilities', 'rotas', 'servico.py')


# ── Limites compartilhados ────────────────────────────────────────────────

def test_memoria_com_varios_workers_avisa_ou_recusa_na_imagem_de_producao(monkeypatch, caplog):
    import logging

    from flask import Flask

    from facilities import _conferir_limites_compartilhados
    app = Flask('x')
    app.config.update(RATELIMIT_STORAGE_URI='memory://', RATELIMIT_ENABLED=True)
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    monkeypatch.delenv('EXIGIR_DATABASE_URL', raising=False)
    _conferir_limites_compartilhados(app)             # fora da imagem: silêncio
    monkeypatch.setenv('EXIGIR_DATABASE_URL', '1')
    with caplog.at_level(logging.WARNING):
        _conferir_limites_compartilhados(app)
    assert 'memory://' in caplog.text and 'Redis' in caplog.text
    monkeypatch.setenv('RATELIMIT_EXIGIR_COMPARTILHADO', '1')
    with pytest.raises(RuntimeError, match='Redis'):
        _conferir_limites_compartilhados(app)
    app.config['RATELIMIT_STORAGE_URI'] = 'redis://redis:6379/0'
    _conferir_limites_compartilhados(app)             # com Redis: nada a dizer


# ── Espelho dos anexos ────────────────────────────────────────────────────

def test_espelho_copia_so_o_que_falta_no_r2(monkeypatch, tmp_path):
    from facilities import object_storage

    class R2Falso:
        objetos = {}

        def __init__(self, *a, **k):
            pass

        def exists(self, key):
            return key in self.objetos

        def save(self, key, data, content_type=None):
            self.objetos[key] = (data, content_type)

    monkeypatch.setattr(object_storage, 'R2Storage', R2Falso)
    for v in ('R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET'):
        monkeypatch.setenv(v, 'x')
    (tmp_path / 'execucoes' / '1').mkdir(parents=True)
    (tmp_path / 'execucoes' / '1' / 'a.jpg').write_bytes(b'foto')
    (tmp_path / 'chamados').mkdir()
    (tmp_path / 'chamados' / 'b.pdf').write_bytes(b'pdf')
    R2Falso.objetos = {'chamados/b.pdf': (b'pdf', 'application/pdf')}
    assert object_storage.espelhar_no_r2(str(tmp_path)) == (1, 1, 0)
    assert R2Falso.objetos['execucoes/1/a.jpg'] == (b'foto', 'image/jpeg')
    assert object_storage.espelhar_no_r2(str(tmp_path)) == (0, 2, 0)   # idempotente
    monkeypatch.delenv('R2_BUCKET')
    with pytest.raises(object_storage.StorageError, match='R2_BUCKET'):
        object_storage.espelhar_no_r2(str(tmp_path))
