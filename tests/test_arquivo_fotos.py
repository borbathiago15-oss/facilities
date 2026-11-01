"""Arquivo das fotos antigas (decisão do dono, 01/11/2026).

* cada foto: lê do principal → grava no arquivo → lê de volta e compara o
  SHA-256 → registra → só na rodada SEGUINTE sai do principal;
* falha na cópia ou na conferência: a foto fica no principal, o erro fica no
  lote, e ela é tentada de novo;
* a foto arquivada continua abrindo pelas rotas de sempre;
* só o administrador vê a tela e a API (401 sem login, 403 para os outros);
* o prazo é o do administrador; PDF e documento nunca saem; repetir não
  duplica nada;
* o destino que é o MESMO lugar do principal é recusado (gravaria por cima e
  apagaria os dois).
"""
import io
from datetime import datetime, timedelta

import pytest

from facilities.object_storage import LocalStorage, NotFound
from tests import fabrica
from tests.test_isolamento_varredura import _png

PDF = b'%PDF-1.4\n%arquivo de teste\n'


@pytest.fixture()
def destino(app_module, tmp_path):
    """Um destino de arquivo numa pasta temporária, só neste teste."""
    st = app_module.app.extensions['facilities_storage']
    antes = st.arquivo, st.info
    st.arquivo = LocalStorage(str(tmp_path / 'arquivo'))
    st.info = {'tipo': 'pasta', 'rotulo': 'Pasta de teste', 'mesmo_disco': True,
               'problema': None}
    yield st
    st.arquivo, st.info = antes


@pytest.fixture()
def chamado_antigo(app_module, auth_client):
    """Um chamado com uma foto e um PDF de 90 dias atrás."""
    from app import db
    from facilities.chamados.models import Chamado, ChamadoAnexo
    with app_module.app.app_context():
        cid = fabrica.local().id
    r = auth_client.post('/chamados/', data={
        'client_id': cid, 'titulo': 'Lâmpada queimada', 'prioridade': 'media',
        'categoria': 'eletrica',
        'arquivo': [(io.BytesIO(_png()), 'foto.png'), (io.BytesIO(PDF), 'laudo.pdf')]},
        content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        ch = Chamado.query.filter_by(titulo='Lâmpada queimada').one()
        anexos = ChamadoAnexo.query.filter_by(chamado_id=ch.id).all()
        for a in anexos:
            a.created_at = datetime.utcnow() - timedelta(days=90)
        db.session.commit()
        foto = next(a for a in anexos if a.mime.startswith('image/'))
        pdf = next(a for a in anexos if a.mime == 'application/pdf')
        return {'foto': foto.id, 'foto_key': foto.storage_key, 'pdf': pdf.id,
                'pdf_key': pdf.storage_key, 'tamanho': foto.tamanho}


def _rodada(app_module, **kw):
    from app import db
    from facilities.arquivo_fotos.servico import rodada
    with app_module.app.app_context():
        r = rodada(**kw)
        db.session.commit()
        return r


def _lote(app_module):
    from facilities.arquivo_fotos.models import LoteArquivo
    with app_module.app.app_context():
        lt = LoteArquivo.query.order_by(LoteArquivo.id.desc()).first()
        return lt and {c: getattr(lt, c) for c in ('situacao', 'arquivadas', 'previstas',
                                                    'nao_arquivadas', 'ultimo_erro',
                                                    'tentativas_com_erro', 'bytes_arquivados')}


def _arquivadas(app_module):
    from facilities.arquivo_fotos.models import FotoArquivada
    with app_module.app.app_context():
        return [(f.storage_key, f.origem, f.removida_do_principal_em is not None)
                for f in FotoArquivada.query.all()]


# ── Quem pode ─────────────────────────────────────────────────────────────

def test_sem_login_e_401_em_json(client):
    for metodo, url in (('get', '/api/v1/admin/armazenamento'),
                        ('post', '/api/v1/admin/armazenamento/prazo'),
                        ('post', '/api/v1/admin/armazenamento/arquivar')):
        r = getattr(client, metodo)(url, json={})
        assert r.status_code == 401 and r.is_json, url
    assert client.get('/novo/admin/armazenamento').status_code == 302      # login


@pytest.mark.parametrize('papel', ['gerente', 'pleno', 'supervisor', 'encarregado'])
def test_so_o_administrador(app_module, papel, monkeypatch):
    from facilities import telas
    monkeypatch.setattr(telas, '_manifesto', lambda: {'src/main.tsx': {'file': 'a.js'}})
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'arq.{papel}@trino.com', papel,
                       locais=[fabrica.CONTRATOS_SEMEADOS[0]])
    c = fabrica.entrar(app_module, f'arq.{papel}@trino.com')
    assert c.get('/api/v1/admin/armazenamento').status_code == 403
    assert c.post('/api/v1/admin/armazenamento/prazo', json={'dias': 1}).status_code == 403
    assert c.post('/api/v1/admin/armazenamento/arquivar',
                  json={'confirmar': True}).status_code == 403
    assert c.get('/novo/admin/armazenamento').status_code == 403
    from facilities.arquivo_fotos.models import ArquivoAjustes, LoteArquivo
    with app_module.app.app_context():
        assert ArquivoAjustes.query.count() == 0 and LoteArquivo.query.count() == 0


def test_administrador_abre_a_tela(auth_client, monkeypatch):
    from facilities import telas
    monkeypatch.setattr(telas, '_manifesto', lambda: {'src/main.tsx': {'file': 'a.js'}})
    assert auth_client.get('/novo/admin/armazenamento').status_code == 200
    d = auth_client.get('/api/v1/admin/armazenamento').get_json()
    assert d['dias'] == 60 and len(d['por_mes']) == 12 and d['lotes'] == []


# ── O painel e o prazo ────────────────────────────────────────────────────

def test_painel_conta_so_as_fotos_e_respeita_o_prazo(app_module, auth_client, chamado_antigo,
                                                     destino):
    d = auth_client.get('/api/v1/admin/armazenamento').get_json()
    assert d['destino']['disponivel'] and d['destino']['mesmo_disco']
    assert d['total'] == {'fotos': 1, 'bytes': chamado_antigo['tamanho'], 'sem_tamanho': 0}
    assert d['pendentes']['fotos'] == 1                       # o PDF não conta
    assert d['locais'][0] == {'local': fabrica.CONTRATOS_SEMEADOS[0],
                              'bytes': chamado_antigo['tamanho']}
    # Prazo de 120 dias: a foto de 90 dias ainda não passou.
    r = auth_client.post('/api/v1/admin/armazenamento/prazo', json={'dias': 120})
    assert r.status_code == 200 and r.get_json()['dias'] == 120
    assert r.get_json()['pendentes']['fotos'] == 0
    r = auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    assert r.status_code == 409 and 'Nenhuma foto com mais de 120 dias' in r.get_json()['erro']
    for ruim in ('abc', 0, 5000, None):
        r = auth_client.post('/api/v1/admin/armazenamento/prazo', json={'dias': ruim})
        assert r.status_code == 400, ruim
    assert auth_client.get('/api/v1/admin/armazenamento').get_json()['dias'] == 120


def test_sem_destino_nao_comeca(auth_client, chamado_antigo):
    r = auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    assert r.status_code == 409
    d = auth_client.get('/api/v1/admin/armazenamento').get_json()
    assert d['destino']['disponivel'] is False and d['lotes'] == []


def test_pede_confirmacao(auth_client, chamado_antigo, destino):
    r = auth_client.post('/api/v1/admin/armazenamento/arquivar', json={})
    assert r.status_code == 400


# ── O caminho de cada foto ────────────────────────────────────────────────

def test_arquiva_confere_e_so_depois_tira_do_principal(app_module, auth_client,
                                                       chamado_antigo, destino):
    from facilities.arquivo_fotos.models import FotoArquivada
    principal, arquivo = destino.principal, destino.arquivo
    chave = chamado_antigo['foto_key']
    original = principal.load(chave)
    r = auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    assert r.status_code == 200
    assert r.get_json()['em_andamento']['previstas'] == 1

    # 1ª rodada: copiada e conferida; o principal ainda tem a foto.
    assert _rodada(app_module)['arquivadas'] == 1
    assert arquivo.load(chave) == original and principal.exists(chave)
    import hashlib
    with app_module.app.app_context():
        fa = FotoArquivada.query.one()
        assert fa.sha256 == hashlib.sha256(original).hexdigest()
        assert (fa.origem, fa.origem_id, fa.tamanho) == ('chamado_anexos',
                                                         chamado_antigo['foto'], len(original))
    # 2ª rodada: agora que o registro está gravado, sai do principal.
    assert _rodada(app_module)['removidas'] == 1
    assert not principal.exists(chave) and arquivo.exists(chave)
    # 3ª rodada: nada mais a fazer, o lote termina.
    _rodada(app_module)
    lt = _lote(app_module)
    assert lt['situacao'] == 'concluido' and lt['arquivadas'] == 1
    assert lt['bytes_arquivados'] == len(original)

    # A tela de sempre continua mostrando a foto (vem do arquivo).
    r = auth_client.get(f"/chamados/anexos/{chamado_antigo['foto']}")
    assert r.status_code == 200 and r.data == original
    # O PDF nunca sai do principal; a linha do anexo nunca sai do banco.
    assert principal.exists(chamado_antigo['pdf_key'])
    assert not arquivo.exists(chamado_antigo['pdf_key'])
    from facilities.chamados.models import ChamadoAnexo
    with app_module.app.app_context():
        assert ChamadoAnexo.query.count() == 2

    # Painel depois: arquivada e fora do principal.
    d = auth_client.get('/api/v1/admin/armazenamento').get_json()
    assert d['arquivadas']['fotos'] == 1 and d['arquivadas']['fora_do_principal'] == 1
    assert d['pendentes']['fotos'] == 0 and d['no_principal_bytes'] == 0
    assert d['lotes'][0]['situacao_rotulo'] == 'Concluído'

    # Repetir não duplica: novas rodadas e um novo pedido não acham nada.
    assert _rodada(app_module) is None
    r = auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    assert r.status_code == 409
    assert _arquivadas(app_module) == [(chave, 'chamado_anexos', True)]


class _ArquivoQueEstraga(LocalStorage):
    """Grava outra coisa no lugar da foto: a conferência tem de pegar."""

    def save(self, key, data, content_type=None):
        super().save(key, data + b'estragou', content_type)


class _ArquivoFora(LocalStorage):
    def save(self, key, data, content_type=None):
        raise OSError('bucket fora do ar')


@pytest.mark.parametrize('defeito, erro', [(_ArquivoQueEstraga, 'não confere'),
                                           (_ArquivoFora, 'bucket fora do ar')])
def test_falha_deixa_a_foto_no_principal(app_module, auth_client, chamado_antigo, destino,
                                         tmp_path, defeito, erro):
    from facilities.arquivo_fotos.servico import TENTATIVAS_POR_LOTE
    destino.arquivo = defeito(str(tmp_path / 'defeito'))
    principal, chave = destino.principal, chamado_antigo['foto_key']
    original = principal.load(chave)
    assert auth_client.post('/api/v1/admin/armazenamento/arquivar',
                            json={'confirmar': True}).status_code == 200
    r = _rodada(app_module)
    assert r['arquivadas'] == 0 and r['falhas'] == 1
    assert principal.load(chave) == original and _arquivadas(app_module) == []
    lt = _lote(app_module)
    assert lt['situacao'] == 'em_andamento' and erro in lt['ultimo_erro']
    # Tenta de novo nas rodadas seguintes; esgotadas as tentativas, o lote
    # termina dizendo que ela não saiu — e ela continua no principal.
    for _ in range(TENTATIVAS_POR_LOTE):
        _rodada(app_module)
    lt = _lote(app_module)
    assert lt['situacao'] == 'concluido_com_falhas' and lt['nao_arquivadas'] == 1
    assert lt['tentativas_com_erro'] == TENTATIVAS_POR_LOTE
    assert principal.load(chave) == original
    assert auth_client.get(f"/chamados/anexos/{chamado_antigo['foto']}").data == original
    d = auth_client.get('/api/v1/admin/armazenamento').get_json()
    assert d['nao_sairam'] == 1 and d['pendentes']['fotos'] == 1

    # Destino consertado, novo lote: agora vai.
    destino.arquivo = LocalStorage(str(tmp_path / 'bom'))
    assert auth_client.post('/api/v1/admin/armazenamento/arquivar',
                            json={'confirmar': True}).status_code == 200
    _rodada(app_module)
    _rodada(app_module)
    _rodada(app_module)
    assert _lote(app_module)['situacao'] == 'concluido'
    assert auth_client.get('/api/v1/admin/armazenamento').get_json()['nao_sairam'] == 0
    assert destino.arquivo.load(chave) == original and not principal.exists(chave)


def test_copia_sumiu_do_arquivo_antes_de_sair_do_principal(app_module, auth_client,
                                                           chamado_antigo, destino):
    """O principal só apaga depois de conferir que a cópia ainda está lá."""
    chave = chamado_antigo['foto_key']
    auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    _rodada(app_module)
    destino.arquivo.delete(chave)                  # alguém apagou no bucket
    _rodada(app_module)
    assert destino.principal.exists(chave)
    assert 'vai ser copiada de novo' in _lote(app_module)['ultimo_erro']
    # A rodada seguinte copia de novo; depois sai do principal.
    _rodada(app_module)
    _rodada(app_module)
    _rodada(app_module)
    assert _lote(app_module)['situacao'] == 'concluido'
    assert destino.arquivo.exists(chave) and not destino.principal.exists(chave)


def test_anda_pela_rodada_do_agendador(app_module, auth_client, chamado_antigo, destino):
    from app import db
    from facilities.rotas.servico import rodar
    auth_client.post('/api/v1/admin/armazenamento/arquivar', json={'confirmar': True})
    for _ in range(3):
        with app_module.app.app_context():
            reg = rodar(origem='teste')
            db.session.commit()
            assert 'arquivo das fotos' not in (reg.erro or '')
    assert _lote(app_module)['situacao'] == 'concluido'
    assert not destino.principal.exists(chamado_antigo['foto_key'])


def test_lote_pequeno_por_rodada(app_module, auth_client, destino):
    """Muitas fotos: cada rodada leva no máximo ``por_rodada``. As fotos da
    passagem entram pela mesma regra (só imagem; o PDF fica)."""
    from facilities.arquivo_fotos.models import FotoArquivada
    from facilities.passagem.models import DiarioAnexo
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        _turno_com_fotos(app_module, admin.id, 5, destino.principal)
    assert auth_client.post('/api/v1/admin/armazenamento/arquivar',
                            json={'confirmar': True}).status_code == 200
    assert _rodada(app_module, por_rodada=2)['arquivadas'] == 2
    assert _rodada(app_module, por_rodada=2)['arquivadas'] == 2
    assert _rodada(app_module, por_rodada=2)['arquivadas'] == 1
    with app_module.app.app_context():
        assert FotoArquivada.query.count() == 5
        assert DiarioAnexo.query.count() == 6                   # nenhuma linha sai
        pdf = DiarioAnexo.query.filter_by(mime='application/pdf').one().storage_key
    assert destino.principal.exists(pdf) and not destino.arquivo.exists(pdf)


def _turno_com_fotos(app_module, autor_id, n, principal):
    from app import db
    from facilities.passagem.models import DiarioAnexo, DiarioArea, DiarioConfiguracao, DiarioTurno
    from facilities import tempo
    cid = fabrica.local().id
    area = DiarioArea(client_id=cid, nome='Área arquivo', ativo=True, created_by=autor_id)
    db.session.add(area)
    db.session.flush()
    cfg = DiarioConfiguracao(client_id=cid, area_id=area.id, nome='Modelo arquivo',
                             turnos_json='[{"nome": "Diurno"}]', campos_json='[]',
                             atividades_json='[]', tipos_ocorrencia_json='[]',
                             ativo=True, created_by=autor_id)
    db.session.add(cfg)
    db.session.flush()
    turno = DiarioTurno(client_id=cid, configuracao_id=cfg.id, data_turno=tempo.hoje(),
                        turno='Diurno', created_by=autor_id)
    db.session.add(turno)
    db.session.flush()
    velho = datetime.utcnow() - timedelta(days=200)
    for i in range(n):
        chave = f'diario/{turno.id}/foto{i}.png'
        principal.save(chave, _png() + bytes([i]), 'image/png')
        db.session.add(DiarioAnexo(turno_id=turno.id, storage_key=chave, nome=f'f{i}.png',
                                   mime='image/png', tamanho=len(_png()) + 1,
                                   uploaded_by=autor_id, created_at=velho))
    principal.save(f'diario/{turno.id}/doc.pdf', PDF, 'application/pdf')
    db.session.add(DiarioAnexo(turno_id=turno.id, storage_key=f'diario/{turno.id}/doc.pdf',
                               nome='doc.pdf', mime='application/pdf', tamanho=len(PDF),
                               uploaded_by=autor_id, created_at=velho))
    db.session.commit()


# ── O destino, lido do ambiente ───────────────────────────────────────────

def _limpar_ambiente(monkeypatch):
    for v in ('ARQUIVO_FOTOS_PASTA', 'ARQUIVO_FOTOS_PASTA_OUTRO_DISCO', 'ARQUIVO_R2_ENDPOINT',
              'ARQUIVO_R2_ACCESS_KEY_ID', 'ARQUIVO_R2_SECRET_ACCESS_KEY', 'ARQUIVO_R2_BUCKET',
              'R2_ENDPOINT'):
        monkeypatch.delenv(v, raising=False)


def test_destino_do_ambiente(monkeypatch, tmp_path):
    from facilities.object_storage import arquivo_do_ambiente
    _limpar_ambiente(monkeypatch)
    fotos = tmp_path / 'uploads'
    fotos.mkdir()
    principal = LocalStorage(str(fotos))

    st, info = arquivo_do_ambiente(principal)
    assert st is None and info['tipo'] is None and info['problema'] is None

    # A mesma pasta (ou uma dentro da outra): recusada.
    for perigosa in (fotos, fotos / 'arquivo', tmp_path):
        monkeypatch.setenv('ARQUIVO_FOTOS_PASTA', str(perigosa))
        st, info = arquivo_do_ambiente(principal)
        assert st is None and 'dentro da pasta das fotos' in info['problema'], perigosa

    monkeypatch.setenv('ARQUIVO_FOTOS_PASTA', str(tmp_path / 'arquivo-fotos'))
    st, info = arquivo_do_ambiente(principal)
    assert isinstance(st, LocalStorage) and info['mesmo_disco'] and not info['problema']

    # Os dois destinos ao mesmo tempo: recusado.
    monkeypatch.setenv('ARQUIVO_R2_BUCKET', 'arquivo')
    st, info = arquivo_do_ambiente(principal)
    assert st is None and 'Deixe só um' in info['problema']
    monkeypatch.delenv('ARQUIVO_FOTOS_PASTA')
    st, info = arquivo_do_ambiente(principal)
    assert st is None and 'ARQUIVO_R2_ENDPOINT' in info['problema']


def test_r2_do_arquivo_nao_pode_ser_o_bucket_principal(monkeypatch):
    from facilities import object_storage
    _limpar_ambiente(monkeypatch)

    class R2Falso(object_storage.R2Storage):
        def __init__(self, endpoint, access_key, secret_key, bucket, prefix=''):
            self.bucket, self.prefix = bucket, prefix

    monkeypatch.setattr(object_storage, 'R2Storage', R2Falso)
    monkeypatch.setenv('R2_ENDPOINT', 'https://r2.exemplo')
    for v, x in (('ARQUIVO_R2_ENDPOINT', 'https://r2.exemplo'), ('ARQUIVO_R2_ACCESS_KEY_ID', 'a'),
                 ('ARQUIVO_R2_SECRET_ACCESS_KEY', 's'), ('ARQUIVO_R2_BUCKET', 'fotos')):
        monkeypatch.setenv(v, x)
    principal = R2Falso('https://r2.exemplo', 'a', 's', 'fotos')
    st, info = object_storage.arquivo_do_ambiente(principal)
    assert st is None and 'bucket separado' in info['problema']
    monkeypatch.setenv('ARQUIVO_R2_BUCKET', 'fotos-arquivo')
    st, info = object_storage.arquivo_do_ambiente(principal)
    assert isinstance(st, R2Falso) and st.bucket == 'fotos-arquivo'
    assert info['rotulo'] == 'Cloudflare R2, bucket fotos-arquivo'


def test_leitura_procura_no_arquivo(tmp_path):
    from facilities.object_storage import ComArquivo
    principal, arquivo = LocalStorage(str(tmp_path / 'p')), LocalStorage(str(tmp_path / 'a'))
    st = ComArquivo(principal, arquivo)
    arquivo.save('x/foto.png', b'velha')
    st.save('x/nova.png', b'nova')
    assert st.load('x/foto.png') == b'velha' and st.load('x/nova.png') == b'nova'
    assert st.exists('x/foto.png') and not principal.exists('x/foto.png')
    assert not arquivo.exists('x/nova.png')
    with pytest.raises(NotFound):
        st.load('x/nada.png')
    st.delete('x/foto.png')
    assert not st.exists('x/foto.png')
    with pytest.raises(NotFound):
        ComArquivo(principal).load('x/foto.png')
