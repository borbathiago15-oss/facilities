"""Auditoria, Fase 4 — o que acontece quando um serviço de fora falha.

Os serviços de fora do Facilities: o aviso no celular (Web Push), o
armazenamento das fotos (R2 ou disco), o e-mail (SMTP) e o Redis do
limitador de tentativas. Nenhum teste fala com serviço de verdade: os
"serviços" aqui são falsos (funções no lugar do envio) ou servidores locais
que aceitam a conexão e não respondem (o serviço pendurado).

A regra que estes testes cobram:

* o trabalho da pessoa fica gravado mesmo se o serviço de fora falhar;
* nenhum aviso sai sobre algo que não foi gravado;
* nenhuma linha aponta para um arquivo que não existe, e nenhum arquivo
  fica sobrando de uma gravação desfeita;
* a chamada de fora não segura a trava de linha nem a transação aberta — os
  outros pedidos não esperam por ela;
* todo serviço de fora tem tempo limite curto.

Os testes marcados ``xfail(strict=True)`` são defeitos que ficaram para
outra leva (o motivo diz qual).
"""
import os
import socket
import threading
import time

import pytest
from sqlalchemy import event

from facilities.chamados.models import Chamado, ChamadoAnexo
from tests.test_chamados import _abrir, _entrar, _png, cena  # noqa: F401

SO_POSTGRES = pytest.mark.skipif(
    'postgres' not in os.environ.get('TEST_DATABASE_URL', ''),
    reason='trava de linha de verdade só no Postgres (TEST_DATABASE_URL)')


# ── Ferramentas ──────────────────────────────────────────────────────────

class Pendurado:
    """Servidor TCP local que aceita a conexão e nunca responde: o serviço
    de push, o R2 ou o SMTP "pendurado"."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(16)
        self.porta = self.sock.getsockname()[1]
        self.conexoes = []
        self.parar = False
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while not self.parar:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conexoes.append(c)

    def fechar(self):
        self.parar = True
        for c in self.conexoes:
            c.close()
        self.sock.close()


@pytest.fixture()
def pendurado():
    s = Pendurado()
    yield s
    s.fechar()


class ArmazenamentoDeTeste:
    """Por cima do armazenamento do teste: anota o que foi gravado e
    apagado, e pode falhar ou esperar."""

    def __init__(self, real, falhar=False, esperar=None, entrou=None):
        self.real, self.falhar, self.esperar, self.entrou = real, falhar, esperar, entrou
        self.gravadas, self.apagadas = [], []

    def save(self, key, data, content_type=None):
        if self.entrou is not None:
            self.entrou.set()
        if self.esperar is not None:
            self.esperar.wait(10)
        if self.falhar:
            from facilities.object_storage import StorageError
            raise StorageError('armazenamento fora do ar (teste)')
        self.real.save(key, data, content_type)
        self.gravadas.append(key)

    def delete(self, key):
        self.apagadas.append(key)
        self.real.delete(key)

    def load(self, key):
        return self.real.load(key)

    def exists(self, key):
        return self.real.exists(key)


def _trocar_armazenamento(app_module, monkeypatch, **kw):
    falso = ArmazenamentoDeTeste(app_module.app.extensions['facilities_storage'], **kw)
    monkeypatch.setitem(app_module.app.extensions, 'facilities_storage', falso)
    return falso


def _celulares(app_module, user_id, n=1):
    from app import User, db
    from facilities.core import push
    from tests.test_push import _celular
    with app_module.app.app_context():
        u = db.session.get(User, user_id)
        for i in range(n):
            _r, d, _a = _celular()
            d['endpoint'] = f"{d['endpoint']}-{user_id}-{i}"
            push.inscrever(u, d)
        db.session.commit()


def _foto():
    import io
    return (io.BytesIO(_png()), 'foto.png')


# ── Push ─────────────────────────────────────────────────────────────────

def test_chamado_urgente_fica_gravado_mesmo_se_o_envio_do_push_explodir(app_module, cena):  # noqa: F811
    """Antes: uma exceção no envio (chave VAPID estragada, biblioteca de
    cifra, um bug) subia pela requisição — 500 e o chamado DESFEITO."""
    _celulares(app_module, cena['gestora'])

    def explode(insc, carga):
        raise RuntimeError('serviço de push quebrado (teste)')
    app_module.app.extensions['facilities_push'] = explode
    enc = _entrar(app_module, 'enc.ch@trino.com')
    r = _abrir(enc, cena, titulo='Fio desencapado na copa', prioridade='urgente')
    assert r.status_code == 302
    with app_module.app.app_context():
        assert Chamado.query.filter_by(titulo='Fio desencapado na copa').count() == 1


def test_push_nao_sai_se_a_gravacao_for_desfeita(app_module, cena):  # noqa: F811
    """Antes: o aviso "Urgente: OS-…" saía no meio da transação; se ela era
    desfeita depois, o gestor recebia o aviso de um chamado que não existe."""
    from app import User, db
    from facilities.chamados import servico as chs
    _celulares(app_module, cena['gestora'])
    enviados = []
    app_module.app.extensions['facilities_push'] = \
        lambda insc, carga: enviados.append(carga['titulo']) or 201
    with app_module.app.app_context():
        chs.abrir(db.session.get(User, cena['enc']), cena['c1'], 'Curto na portaria',
                  prioridade='urgente')
        db.session.rollback()
        assert Chamado.query.filter_by(titulo='Curto na portaria').count() == 0
    assert enviados == []


def test_push_so_sai_depois_que_o_chamado_foi_gravado(app_module, cena):  # noqa: F811
    """Na hora do envio, o chamado já tem de estar gravado (visto por OUTRA
    conexão): é o que tira a trava do local e a transação aberta do caminho
    do serviço de push."""
    from app import db
    _celulares(app_module, cena['gestora'])
    visto = []

    def confere(insc, carga):
        from sqlalchemy import text
        with db.engine.connect() as outra:
            visto.append(outra.execute(text(
                "SELECT count(*) FROM chamados WHERE titulo = 'Porta corta-fogo travada'"))
                .scalar())
        return 201
    app_module.app.extensions['facilities_push'] = confere
    enc = _entrar(app_module, 'enc.ch@trino.com')
    assert _abrir(enc, cena, titulo='Porta corta-fogo travada',
                  prioridade='urgente').status_code == 302
    assert visto == [1]


def test_varios_aparelhos_recebem_ao_mesmo_tempo(app_module, cena):  # noqa: F811
    """Antes: um aparelho por vez — 3 gestores × 3 aparelhos com o serviço a
    5 s = 45 s para abrir UM chamado urgente."""
    _celulares(app_module, cena['gestora'], n=6)

    def lento(insc, carga):
        time.sleep(0.5)
        return 201
    app_module.app.extensions['facilities_push'] = lento
    enc = _entrar(app_module, 'enc.ch@trino.com')
    t0 = time.monotonic()
    assert _abrir(enc, cena, titulo='Elevador parado', prioridade='urgente').status_code == 302
    assert time.monotonic() - t0 < 2.0       # 6 × 0,5 s em fila seriam 3 s


def test_servico_de_push_pendurado_desiste_em_poucos_segundos(app_module, pendurado,
                                                              monkeypatch):
    """Antes: 10 s de espera por aparelho (``urlopen(timeout=10)``)."""
    from types import SimpleNamespace

    from facilities.core import push
    from tests.test_push import _celular
    privada, publica = push.gerar_chaves()
    monkeypatch.setenv('VAPID_PRIVATE_KEY', privada)
    monkeypatch.setenv('VAPID_PUBLIC_KEY', publica)
    monkeypatch.setenv('PUSH_TIMEOUT', '1')
    _r, d, _a = _celular()
    insc = SimpleNamespace(id=1, user_id=1, endpoint=f'http://127.0.0.1:{pendurado.porta}/x',
                           p256dh=d['keys']['p256dh'], auth=d['keys']['auth'])
    t0 = time.monotonic()
    assert push._enviar_de_verdade(insc, {'titulo': 't'}) == 0
    assert time.monotonic() - t0 < 3.0


@pytest.mark.xfail(strict=True, reason='BUG (L5, fila): o envio do push ainda acontece '
                   'dentro da requisição de quem abriu o chamado. Com o serviço de push '
                   'pendurado, quem abre um urgente espera o tempo limite do push (PUSH_TIMEOUT, '
                   '3 s) antes de ver a tela. Sem fila (RQ), não há como responder antes.')
def test_quem_abre_urgente_nao_espera_o_servico_de_push(app_module, cena):  # noqa: F811
    _celulares(app_module, cena['gestora'])

    def pendura(insc, carga):
        time.sleep(3)
        return 0
    app_module.app.extensions['facilities_push'] = pendura
    enc = _entrar(app_module, 'enc.ch@trino.com')
    t0 = time.monotonic()
    assert _abrir(enc, cena, titulo='Gás vazando', prioridade='urgente').status_code == 302
    assert time.monotonic() - t0 < 1.0


@SO_POSTGRES
def test_outro_chamado_no_mesmo_local_nao_espera_o_push_lento(app_module, cena):  # noqa: F811
    """Antes: o push saía com a trava do local segura (``_travar_contrato``):
    todo chamado aberto no mesmo local esperava o serviço de push."""
    _celulares(app_module, cena['gestora'])
    entrou, soltar = threading.Event(), threading.Event()

    def preso(insc, carga):
        entrou.set()
        soltar.wait(8)
        return 201
    app_module.app.extensions['facilities_push'] = preso
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    respostas = {}
    a = threading.Thread(target=lambda: respostas.update(
        a=_abrir(enc, cena, titulo='Incêndio no depósito', prioridade='urgente')))
    a.start()
    try:
        assert entrou.wait(10), 'o push do urgente não começou'
        t0 = time.monotonic()
        respostas['b'] = _abrir(gestora, cena, titulo='Lâmpada queimada', prioridade='baixa')
        espera = time.monotonic() - t0
    finally:
        soltar.set()
        a.join(20)
    assert respostas['a'].status_code == 302 and respostas['b'].status_code == 302
    assert espera < 2.0, f'o segundo chamado esperou {espera:.1f} s pelo push do primeiro'


def test_aviso_do_agendador_que_falha_nao_desfaz_a_rodada(app_module, cena):  # noqa: F811
    """O prazo vencido é marcado (``aviso_vencido_em``) mesmo se o envio do
    push explodir: senão cada rodada tentaria (e falharia) de novo."""
    from datetime import datetime, timedelta

    from app import db
    from facilities.chamados import servico as chs
    _celulares(app_module, cena['gestora'])

    def explode(insc, carga):
        raise RuntimeError('push quebrado (teste)')
    app_module.app.extensions['facilities_push'] = explode
    with app_module.app.app_context():
        agora = datetime.utcnow()
        ch = Chamado(client_id=cena['c1'], titulo='Vencido', status='aberto',
                     prioridade='urgente', solicitante_id=cena['enc'],
                     aberto_em=agora - timedelta(hours=6), prazo=agora - timedelta(hours=1))
        db.session.add(ch)
        db.session.commit()
        chs.avisar_prazos(agora)
        db.session.commit()
        assert db.session.get(Chamado, ch.id).aviso_vencido_em is not None


# ── Armazenamento das fotos ──────────────────────────────────────────────

def test_r2_tem_tempo_limite_curto_e_poucas_tentativas():
    """Antes: o padrão do botocore — 60 s para conectar, 60 s para ler e
    novas tentativas: um R2 engasgado segurava a requisição por minutos."""
    from facilities.object_storage import R2Storage
    r2 = R2Storage('http://127.0.0.1:9', 'id-falso', 'segredo-falso', 'balde')
    cfg = r2._client.meta.config
    assert cfg.connect_timeout <= 3
    assert cfg.read_timeout <= 10
    assert cfg.retries['total_max_attempts'] <= 3     # 1 + 2 novas tentativas


def test_chamado_fica_gravado_sem_a_foto_quando_o_armazenamento_cai(app_module, cena,  # noqa: F811
                                                                    monkeypatch):
    """Antes: a falha do armazenamento virava 500 e o chamado — o texto que a
    pessoa escreveu — era desfeito."""
    _trocar_armazenamento(app_module, monkeypatch, falhar=True)
    enc = _entrar(app_module, 'enc.ch@trino.com')
    r = enc.post('/chamados/', data={'client_id': cena['c1'], 'titulo': 'Infiltração na sala 3',
                                     'prioridade': 'media', 'arquivo': _foto()},
                 content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        ch = Chamado.query.filter_by(titulo='Infiltração na sala 3').one()
        assert ChamadoAnexo.query.filter_by(chamado_id=ch.id).count() == 0
    pagina = enc.get(r.headers['Location']).get_data(as_text=True)
    assert 'não foi guardad' in pagina


def test_foto_enviada_e_apagada_se_a_gravacao_do_chamado_falhar(app_module, cena,  # noqa: F811
                                                                monkeypatch):
    """A foto foi para o armazenamento e a linha não entrou no banco: o
    arquivo não pode ficar sobrando (nem a linha apontar para o nada)."""
    from app import db
    falso = _trocar_armazenamento(app_module, monkeypatch)

    def recusa_o_anexo(session, *_):
        if any(isinstance(o, ChamadoAnexo) for o in session.new):
            raise RuntimeError('banco recusou a linha do anexo (teste)')
    event.listen(db.session, 'before_flush', recusa_o_anexo)
    app_module.app.config['PROPAGATE_EXCEPTIONS'] = False
    try:
        enc = _entrar(app_module, 'enc.ch@trino.com')
        r = enc.post('/chamados/', data={'client_id': cena['c1'], 'titulo': 'Vidro trincado',
                                         'prioridade': 'media', 'arquivo': _foto()},
                     content_type='multipart/form-data')
    finally:
        event.remove(db.session, 'before_flush', recusa_o_anexo)
        app_module.app.config['PROPAGATE_EXCEPTIONS'] = None
    assert r.status_code == 500
    assert falso.gravadas, 'a foto nem chegou a ser enviada'
    assert sorted(falso.apagadas) == sorted(falso.gravadas)
    with app_module.app.app_context():
        assert all(not app_module.app.extensions['facilities_storage'].exists(k)
                   for k in falso.gravadas)


@SO_POSTGRES
def test_outro_chamado_no_mesmo_local_nao_espera_o_armazenamento_lento(app_module, cena,  # noqa: F811
                                                                       monkeypatch):
    """Antes: a foto subia com o chamado já inserido e a trava do local segura."""
    entrou, soltar = threading.Event(), threading.Event()
    _trocar_armazenamento(app_module, monkeypatch, esperar=soltar, entrou=entrou)
    enc = _entrar(app_module, 'enc.ch@trino.com')
    gestora = _entrar(app_module, 'gestora.ch@trino.com')
    respostas = {}
    a = threading.Thread(target=lambda: respostas.update(a=enc.post(
        '/chamados/', data={'client_id': cena['c1'], 'titulo': 'Teto caindo',
                            'prioridade': 'alta', 'arquivo': _foto()},
        content_type='multipart/form-data')))
    a.start()
    try:
        assert entrou.wait(10), 'a foto não começou a subir'
        t0 = time.monotonic()
        respostas['b'] = _abrir(gestora, cena, titulo='Tomada solta', prioridade='baixa')
        espera = time.monotonic() - t0
    finally:
        soltar.set()
        a.join(20)
    assert respostas['a'].status_code == 302 and respostas['b'].status_code == 302
    assert espera < 2.0, f'o segundo chamado esperou {espera:.1f} s pela foto do primeiro'


def test_checklist_com_armazenamento_fora_pede_para_tentar_de_novo(app_module, monkeypatch):
    """O checklist pode EXIGIR a foto: sem armazenamento, nada é gravado e a
    resposta é 503 com o recado — a fila do aparelho guarda o envio e tenta
    de novo sozinha. Antes: 500 genérico ("Algo deu errado")."""
    from tests.test_rotas_servico import SEGUNDA, _executar, _tarefas, montar_cena, utc
    from facilities.rotas import servico as s
    from facilities.rotas.models import Execucao, ExecucaoFoto
    with app_module.app.app_context():
        ids = montar_cena(app_module)
        s.gerar(SEGUNDA)
        falso = _trocar_armazenamento(app_module, monkeypatch, falhar=True)
        with pytest.raises(s.RegraDaRota) as erro:
            _executar(ids['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'))
        assert erro.value.codigo == 503
        assert 'tente' in erro.value.mensagem.lower() or 'sozinh' in erro.value.mensagem.lower()
        from app import db
        db.session.rollback()
        assert Execucao.query.count() == 0 and ExecucaoFoto.query.count() == 0
        assert falso.gravadas == []


# ── E-mail ───────────────────────────────────────────────────────────────

def test_servidor_de_email_calado_desiste_no_tempo_configurado(app_module, pendurado,
                                                               monkeypatch):
    """Antes: 15 s fixos por etapa da conversa SMTP (conectar, saudação…)."""
    from facilities.core import correio
    monkeypatch.setenv('SMTP_HOST', '127.0.0.1')
    monkeypatch.setenv('SMTP_PORT', str(pendurado.porta))
    monkeypatch.setenv('SMTP_TIMEOUT', '1')
    with app_module.app.app_context():
        app_module.app.extensions.pop('facilities_correio', None)
        t0 = time.monotonic()
        assert correio.enviar('pessoa@exemplo.com', 'Assunto', 'Texto') is False
        assert time.monotonic() - t0 < 3.0


# ── Redis do limitador ───────────────────────────────────────────────────

def test_redis_do_limitador_fora_do_ar_nao_impede_o_login(tmp_path):
    """Num processo à parte (o limitador é um só por processo): o app com o
    Redis do limitador numa porta onde nada escuta (conexão recusada)."""
    pytest.importorskip('redis')
    import subprocess
    import sys
    roteiro = (
        "from facilities import create_app\n"
        "from facilities.extensions import db\n"
        "app = create_app()\n"
        "with app.app_context():\n"
        "    db.create_all()\n"
        "    from facilities.core.models import User\n"
        "    u = User(name='A', email='redis.fora@trino.com', role='encarregado')\n"
        "    u.set_password('senha12345'); u.must_change_password = False\n"
        "    db.session.add(u); db.session.commit()\n"
        "app.config['WTF_CSRF_ENABLED'] = False\n"
        "r = app.test_client().post('/login', data={'email': 'redis.fora@trino.com',\n"
        "                                         'password': 'senha12345'})\n"
        "print('STATUS', r.status_code)\n")
    amb = dict(os.environ, DATABASE_URL=f'sqlite:///{tmp_path}/r.db', STORAGE_BACKEND='local',
               UPLOAD_FOLDER=str(tmp_path / 'up'), RATELIMIT_ENABLED='1',
               RATELIMIT_STORAGE_URI='redis://127.0.0.1:1/0')
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    saida = subprocess.run([sys.executable, '-c', roteiro], cwd=raiz, env=amb,
                           capture_output=True, text=True, timeout=120).stdout
    assert 'STATUS 302' in saida, saida[-300:]


def test_logo_antiga_so_e_apagada_depois_que_a_troca_foi_gravada(app_module):
    """Antes: a logo antiga era apagada do armazenamento ANTES do commit; com
    a gravação desfeita, o cadastro continuava apontando para ela — apagada."""
    import io

    from app import db
    from facilities.cadastros import montagem, servico as cad
    from facilities.core.anexos import storage

    class Arq(io.BytesIO):
        filename = 'logo.png'
    with app_module.app.app_context():
        emp = cad.salvar_empresa(None, {'nome': 'Trino Logos'}, None)
        cli = cad.salvar_contratante(None, {'nome': 'Cliente da Logo', 'empresa_id': emp.id,
                                            'centro_custo': 'CL'}, None)
        antiga = montagem.salvar_logo(cli, Arq(_png()), None)
        db.session.commit()
        nova = montagem.salvar_logo(cli, Arq(_png()), None)
        db.session.rollback()                    # a troca não vingou
        assert storage().exists(antiga), 'a logo que continua no cadastro foi apagada'
        assert not storage().exists(nova), 'a logo da troca desfeita ficou sobrando'
        assert cli.logo_key == antiga
        nova = montagem.salvar_logo(cli, Arq(_png()), None)
        db.session.commit()                      # agora vingou: a antiga sai
        assert storage().exists(nova) and not storage().exists(antiga)


def test_aviso_de_ponto_de_salvamento_desfeito_nao_sai(app_module, cena):  # noqa: F811
    """O agendador roda cada etapa num ponto de salvamento: a etapa desfeita
    não pode mandar os avisos dela; a que vingou manda depois do commit."""
    from app import db
    from facilities.core import push
    _celulares(app_module, cena['gestora'])
    enviados = []
    app_module.app.extensions['facilities_push'] = \
        lambda insc, carga: enviados.append(carga['titulo']) or 201
    with app_module.app.app_context():
        try:
            with db.session.begin_nested():
                push.avisar_ao_gravar([cena['gestora']], 'etapa que falhou', '')
                raise RuntimeError('etapa falhou (teste)')
        except RuntimeError:
            pass
        with db.session.begin_nested():
            push.avisar_ao_gravar([cena['gestora']], 'etapa que vingou', '')
        assert enviados == []
        db.session.commit()
    assert enviados == ['etapa que vingou']
