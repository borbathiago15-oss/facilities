"""Leva L2 da auditoria (Fase 3): perda de dado e duplicação.

* a migração ``c85ddc846b35`` (uma passagem por contrato, modelo, dia e
  turno): as repetidas que já existem saem para a quarentena, as linhas
  filhas passam para a que fica, e a volta devolve tudo como estava — no
  SQLite (banco temporário à parte) e no Postgres (dentro de uma transação
  desfeita no fim, sem tocar no banco da suíte);
* a chave única no modelo;
* o cadastro da mesma pessoa duas vezes: o segundo recebe o recado "Já existe
  uma pessoa com este e-mail" (tela antiga) e 400 com a frase (tela nova),
  nunca 500.

As corridas de verdade (dois pedidos juntos) estão em
``test_auditoria_concorrencia.py`` (só no Postgres).
"""
import importlib.util
import json
import os
import tempfile
from datetime import date, datetime

import pytest
import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'mig_c85ddc846b35',
    os.path.join(RAIZ, 'migrations', 'versions', 'c85ddc846b35_passagem_unica_por_turno.py'))
MIG = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIG)

TABELAS = ('diario_operacional_turnos', 'diario_operacional_pendencias',
           'diario_operacional_ocorrencias', 'diario_operacional_anexos',
           'diario_operacional_turno_correcoes', 'diario_operacional_pendencia_eventos')
B = 900000          # ids altos: nunca colidem com o que a suíte cria


def _rodar(conn, passo):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with Operations.context(MigrationContext.configure(conn)):
        getattr(MIG, passo)()


def _digital(conn):
    return {t: [tuple(str(v) for v in r) for r in
                conn.execute(sa.text(f'SELECT * FROM {t} ORDER BY id')).fetchall()]
            for t in TABELAS}


def _semear(conn, cid, cfg, uid):
    """Grupo A (1º Turno): rascunho velho + duas encerradas (a das 09:00 fica).
    Grupo B (2º Turno): dois rascunhos (o de maior id fica). Uma passagem
    única que não pode ser tocada. Filhos em todas as passagens que saem."""
    agora = '2026-10-01 12:00:00'
    turnos = [
        (B + 101, '1º Turno', 'aberto', None, '{"banheiros": "rascunho"}'),
        (B + 102, '1º Turno', 'encerrado', '2026-10-01 10:00:00', '{"banheiros": "segundo"}'),
        (B + 103, '1º Turno', 'encerrado', '2026-10-01 09:00:00', '{"banheiros": "primeiro"}'),
        (B + 201, '2º Turno', 'aberto', None, '{"a": 1}'),
        (B + 202, '2º Turno', 'aberto', None, '{"a": 2}'),
        (B + 301, '3º Turno', 'encerrado', '2026-10-01 23:00:00', '{}'),
    ]
    for tid, turno, status, enviado, dados in turnos:
        conn.execute(sa.text(
            'INSERT INTO diario_operacional_turnos (id, client_id, configuracao_id, '
            'data_turno, turno, status, dados_json, observacao, created_by, created_at, '
            'submitted_at, updated_at) VALUES (:id, :c, :g, :d, :t, :s, :j, :o, :u, :a, '
            ':e, :a)'),
            {'id': tid, 'c': cid, 'g': cfg, 'd': date(2026, 10, 1), 't': turno, 's': status,
             'j': dados, 'o': f'obs {tid}', 'u': uid, 'a': agora, 'e': enviado})
    for pid, tid in ((1001, 101), (1002, 102), (1003, 103), (1004, None), (1005, 201)):
        conn.execute(sa.text(
            'INSERT INTO diario_operacional_pendencias (id, client_id, turno_id, titulo, '
            'status, prioridade, created_by, created_at) VALUES (:id, :c, :t, :ti, '
            "'aberta', 'media', :u, :a)"),
            {'id': B + pid, 'c': cid, 't': B + tid if tid else None, 'ti': f'Pend {pid}',
             'u': uid, 'a': agora})
    conn.execute(sa.text(
        'INSERT INTO diario_operacional_ocorrencias (id, client_id, turno_id, tipo, descricao, '
        "gravidade, status, created_by, created_at) VALUES (:id, :c, :t, 'Outros', 'Lâmpada', "
        "'normal', 'aberta', :u, :a)"), {'id': B + 2001, 'c': cid, 't': B + 102, 'u': uid,
                                         'a': agora})
    conn.execute(sa.text(
        'INSERT INTO diario_operacional_anexos (id, turno_id, storage_key, nome, uploaded_by, '
        "created_at) VALUES (:id, :t, 'passagem/x.jpg', 'x.jpg', :u, :a)"),
        {'id': B + 3001, 't': B + 101, 'u': uid, 'a': agora})
    conn.execute(sa.text(
        'INSERT INTO diario_operacional_turno_correcoes (id, turno_id, motivo, antes_json, '
        "created_by, created_at) VALUES (:id, :t, 'erro', '{}', :u, :a)"),
        {'id': B + 4001, 't': B + 102, 'u': uid, 'a': agora})
    conn.execute(sa.text(
        'INSERT INTO diario_operacional_pendencia_eventos (id, pendencia_id, turno_id, tipo, '
        "created_by, created_at) VALUES (:id, :p, :t, 'recebida', :u, :a)"),
        {'id': B + 5001, 'p': B + 1003, 't': B + 102, 'u': uid, 'a': agora})


def _turno_de(conn, tabela, linha):
    return conn.execute(sa.text(f'SELECT turno_id FROM {tabela} WHERE id = :i'),
                        {'i': B + linha}).scalar()


def _conferir_depois_da_ida(conn):
    vivos = [r[0] for r in conn.execute(sa.text(
        'SELECT id FROM diario_operacional_turnos WHERE id >= :b ORDER BY id'), {'b': B})]
    assert vivos == [B + 103, B + 202, B + 301]
    assert conn.execute(sa.text('SELECT dados_json FROM diario_operacional_turnos '
                                'WHERE id = :i'), {'i': B + 103}).scalar() == \
        '{"banheiros": "primeiro"}'
    for tabela, linha, esperado in (
            ('diario_operacional_pendencias', 1001, 103),
            ('diario_operacional_pendencias', 1002, 103),
            ('diario_operacional_pendencias', 1003, 103),
            ('diario_operacional_pendencias', 1005, 202),
            ('diario_operacional_ocorrencias', 2001, 103),
            ('diario_operacional_anexos', 3001, 103),
            ('diario_operacional_turno_correcoes', 4001, 103),
            ('diario_operacional_pendencia_eventos', 5001, 103)):
        assert _turno_de(conn, tabela, linha) == B + esperado, (tabela, linha)
    assert _turno_de(conn, 'diario_operacional_pendencias', 1004) is None
    q = '_quarentena_c85ddc846b35_diario_operacional_turnos'
    guardados = {r[0]: r[1] for r in conn.execute(sa.text(f'SELECT id, dados_json FROM {q}'))}
    assert guardados == {B + 101: '{"banheiros": "rascunho"}',
                         B + 102: '{"banheiros": "segundo"}', B + 201: '{"a": 1}'}
    qp = '_quarentena_c85ddc846b35_diario_operacional_pendencias'
    assert {r[0]: r[1] for r in conn.execute(sa.text(f'SELECT id, turno_id FROM {qp}'))} == \
        {B + 1001: B + 101, B + 1002: B + 102, B + 1005: B + 201}
    nomes = {i['name']: i['unique'] for i in
             sa.inspect(conn).get_indexes('diario_operacional_turnos')}
    assert nomes.get('uq_diario_turnos_chave') in (True, 1)


def _ida_volta_ida(conn, cid, cfg, uid):
    _semear(conn, cid, cfg, uid)
    antes = _digital(conn)
    _rodar(conn, 'upgrade')
    _conferir_depois_da_ida(conn)
    depois = _digital(conn)
    _rodar(conn, 'downgrade')
    assert _digital(conn) == antes, 'a volta não devolveu tudo como estava'
    assert all(i['name'] != 'uq_diario_turnos_chave'
               for i in sa.inspect(conn).get_indexes('diario_operacional_turnos'))
    _rodar(conn, 'upgrade')
    _conferir_depois_da_ida(conn)
    assert _digital(conn) == depois
    # E a chave segura daqui em diante.
    with pytest.raises(sa.exc.IntegrityError):
        with conn.begin_nested():
            conn.execute(sa.text(
                'INSERT INTO diario_operacional_turnos (id, client_id, configuracao_id, '
                'data_turno, turno, status, dados_json, created_by, created_at, updated_at) '
                "VALUES (:id, :c, :g, :d, '1º Turno', 'aberto', '{}', :u, :a, :a)"),
                {'id': B + 999, 'c': cid, 'g': cfg, 'd': date(2026, 10, 1), 'u': uid,
                 'a': '2026-10-02 00:00:00'})


def test_migracao_resolve_duplicatas_com_quarentena_e_volta_igual(app_module):
    from app import db
    url = os.environ.get('TEST_DATABASE_URL', '').strip()
    if 'postgres' in url:
        # Postgres: o banco da suíte, numa transação que é desfeita no fim
        # (DDL é transacional lá). Pais de verdade, porque a FK vale.
        from tests import fabrica
        from facilities.passagem.models import DiarioArea, DiarioConfiguracao
        with app_module.app.app_context():
            loc = fabrica.local()
            uid = fabrica.pessoa(app_module, 'mig.l2@trino.com', 'encarregado',
                                 locais=[loc.name])
            area = DiarioArea(client_id=loc.id, nome='Área L2', ativo=True, created_by=uid)
            db.session.add(area)
            db.session.flush()
            cfg = DiarioConfiguracao(client_id=loc.id, area_id=area.id, nome='Modelo L2',
                                     turnos_json='[]', campos_json='[]',
                                     atividades_json='[]', tipos_ocorrencia_json='[]',
                                     ativo=True, created_by=uid)
            db.session.add(cfg)
            db.session.commit()
            cid, cfg_id = loc.id, cfg.id
            db.session.remove()
            conn = db.engine.connect()
            trans = conn.begin()
            try:
                _rodar(conn, 'downgrade')     # o schema de antes: sem a chave
                _ida_volta_ida(conn, cid, cfg_id, uid)
            finally:
                trans.rollback()
                conn.close()
        return
    # SQLite: um banco temporário só deste teste, com o schema dos modelos
    # menos a chave (o estado de antes da migração).
    fd, caminho = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    motor = sa.create_engine(f'sqlite:///{caminho}')
    try:
        db.metadata.create_all(motor)
        with motor.begin() as conn:
            conn.execute(sa.text('DROP INDEX uq_diario_turnos_chave'))
        with motor.connect() as conn:
            trans = conn.begin()
            _ida_volta_ida(conn, 1, 1, 1)
            trans.commit()
    finally:
        motor.dispose()
        os.remove(caminho)


def test_sobrevivente_e_a_encerrada_mais_antiga_senao_o_rascunho_mais_novo():
    d = datetime
    assert MIG.sobrevivente([(1, 'aberto', None), (2, 'encerrado', d(2026, 1, 1, 10)),
                             (3, 'encerrado', d(2026, 1, 1, 9))]) == 3
    # Encerrada sem carimbo (passagem antiga) perde para a carimbada; entre
    # as sem carimbo, a de menor id.
    assert MIG.sobrevivente([(5, 'encerrado', None), (6, 'encerrado', '2026-01-01 09:00:00'),
                             (4, 'encerrado', None)]) == 6
    assert MIG.sobrevivente([(7, 'encerrado', None), (4, 'encerrado', None)]) == 4
    assert MIG.sobrevivente([(8, 'aberto', None), (9, 'aberto', None)]) == 9


def test_o_modelo_tem_a_chave_unica_da_passagem(app_module):
    from app import db
    from facilities.passagem.models import DiarioTurno
    idx = {i.name: i for i in DiarioTurno.__table__.indexes}['uq_diario_turnos_chave']
    assert idx.unique
    assert [c.name for c in idx.columns] == ['client_id', 'configuracao_id', 'data_turno',
                                             'turno']
    assert db is not None


# ── Cadastro da mesma pessoa duas vezes ───────────────────────────────────

@pytest.fixture()
def corrida_do_email(app_module):
    """A pessoa que o primeiro envio da corrida já gravou."""
    from app import User, db
    email = 'repetida.l2@trino.com'
    with app_module.app.app_context():
        if User.por_email(email) is None:
            u = User(name='Repetida L2', email=email, role='encarregado')
            u.set_password('senha12345')
            db.session.add(u)
            db.session.commit()
    yield email
    with app_module.app.app_context():
        u = User.por_email(email)
        if u is not None:
            db.session.delete(u)
            db.session.commit()


def _conferencia_cega(monkeypatch):
    """O segundo envio da corrida: a conferência de ``_validar`` não vê a
    pessoa (o primeiro ainda não tinha gravado quando ela olhou), e o commit
    bate no índice único do e-mail. Depois do login, que também usa
    ``por_email``."""
    from facilities.core import admin
    monkeypatch.setattr(admin.User, 'por_email', classmethod(lambda cls, e: None))


def test_cadastro_repetido_na_tela_antiga_mostra_o_recado_e_nao_da_500(app_module,
                                                                       corrida_do_email,
                                                                       monkeypatch):
    from app import User
    from tests.test_chamados import _entrar_admin
    adm = _entrar_admin(app_module)
    _conferencia_cega(monkeypatch)
    r = adm.post('/admin/usuarios', data={'name': 'Outra', 'email': corrida_do_email,
                                          'role': 'encarregado'})
    monkeypatch.undo()
    assert r.status_code == 302
    pagina = adm.get(r.headers['Location']).get_data(as_text=True)
    assert 'Já existe uma pessoa com este e-mail.' in pagina
    with app_module.app.app_context():
        assert User.query.filter_by(name='Outra').count() == 0


def test_cadastro_repetido_na_tela_nova_responde_400_com_a_frase(app_module, corrida_do_email,
                                                                 monkeypatch):
    from app import User
    from tests.test_chamados import _entrar_admin
    adm = _entrar_admin(app_module)
    _conferencia_cega(monkeypatch)
    r = adm.post('/api/v1/admin/usuarios', json={'name': 'Outra', 'email': corrida_do_email,
                                                 'role': 'encarregado'})
    monkeypatch.undo()
    assert r.status_code == 400
    corpo = r.get_json()
    assert corpo['error'] == 'Já existe uma pessoa com este e-mail.'
    assert 'senha' not in corpo
    assert r.headers['Cache-Control'] == 'no-store'
    with app_module.app.app_context():
        assert User.query.filter_by(name='Outra').count() == 0


def test_cadastro_normal_continua_criando(app_module):
    from app import User, db
    from tests.test_chamados import _entrar_admin
    adm = _entrar_admin(app_module)
    r = adm.post('/api/v1/admin/usuarios', json={'name': 'Nova L2',
                                                 'email': 'nova.l2@trino.com',
                                                 'role': 'encarregado'})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['senha']['senha']
    with app_module.app.app_context():
        u = User.por_email('nova.l2@trino.com')
        assert u is not None
        db.session.delete(u)
        db.session.commit()


def test_passagem_repetida_responde_409_e_nao_500(app_module):
    """Se a trava não segurasse (o caso não deveria acontecer), a chave única
    recusa a segunda passagem: 409 com o recado, nada gravado, nunca 500."""
    from app import db
    from tests import fabrica
    from facilities.passagem import rotas
    from facilities.passagem.models import DiarioArea, DiarioConfiguracao, DiarioTurno
    with app_module.app.app_context():
        loc = fabrica.local()
        uid = fabrica.pessoa(app_module, 'enc.l2@trino.com', 'encarregado', locais=[loc.name])
        area = DiarioArea(client_id=loc.id, nome='Área L2', ativo=True, created_by=uid)
        db.session.add(area)
        db.session.flush()
        cfg = DiarioConfiguracao(client_id=loc.id, area_id=area.id, nome='Modelo L2',
                                 turnos_json=json.dumps([{'nome': '1º Turno'}]),
                                 campos_json='[]', atividades_json='[]',
                                 tipos_ocorrencia_json='[]', ativo=True, created_by=uid)
        db.session.add(cfg)
        db.session.commit()
        cid, cfg_id = loc.id, cfg.id
    enc = fabrica.entrar(app_module, 'enc.l2@trino.com')
    corpo = {'client_id': cid, 'configuracao_id': cfg_id, 'data_turno': '2026-11-02',
             'turno': '1º Turno', 'dados': {}, 'pendencias': [], 'ocorrencias': [],
             'finalizar': True}
    assert enc.post('/passagem-de-turno/api/turnos', json=corpo).status_code == 201
    # A busca "não acha" a que já existe — como o segundo pedido da corrida
    # sem a trava.
    class _Cega:
        def __get__(self, obj, tipo):
            return db.session.query(DiarioTurno).filter(DiarioTurno.id < 0)
    DiarioTurno.query = _Cega()          # (o monkeypatch leria a propriedade fora do app)
    try:
        r = enc.post('/passagem-de-turno/api/turnos', json=corpo)
    finally:
        del DiarioTurno.query
    assert r.status_code == 409, r.get_data(as_text=True)
    assert r.get_json()['error'] == rotas.MSG_PASSAGEM_JA_GRAVADA
    with app_module.app.app_context():
        assert DiarioTurno.query.filter_by(client_id=cid, configuracao_id=cfg_id).count() == 1
