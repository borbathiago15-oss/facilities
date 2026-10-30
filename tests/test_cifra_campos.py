"""Campos sensíveis cifrados no banco (core/cifra.py, pedido do dono 30/10/2026).

* o valor GUARDADO de e-mail, telefone, endereço, segredo da segunda etapa e
  chaves do aviso no celular não contém o texto;
* o login acha a conta pelo índice cego, sem diferença de maiúsculas;
* e-mail repetido continua barrado (o índice é único);
* rodízio: chave nova + a antiga em FIELD_ENCRYPTION_OLD_KEYS lê tudo, o
  ``flask chaves girar`` recifra, e depois a antiga pode sair;
* a cifra é OPCIONAL: sem a chave o sistema sobe com os campos em texto
  aberto e o login funciona; pôr a chave e rodar ``chaves girar`` cifra o
  que já existe; tirar a chave com dado cifrado no banco é erro claro.
"""
import pytest
import sqlalchemy as sa

from facilities import create_app
from facilities.core import cifra
from tests import fabrica

CHAVE_SUITE = 'dGVzdGUtZGEtc3VpdGUtY2hhdmUtY2lmcmEtMzJieXQ='


def _bruto(tabela, coluna, linha_id):
    from app import db
    return db.session.execute(sa.text(f'SELECT {coluna} FROM {tabela} WHERE id = :i'),
                              {'i': linha_id}).scalar()


def test_o_banco_guarda_so_o_texto_cifrado(app_module):
    from app import Client, User, db
    from facilities.core.models import PushInscricao
    from facilities.cadastros.models import Convite
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'cifra.ana@trino.com')
        u = db.session.get(User, uid)
        u.totp_segredo = 'JBSWY3DPEHPK3PXP'
        local = Client.query.first()
        local.endereco = 'Rua das Flores, 123'
        p = PushInscricao(user_id=uid, endpoint='https://fcm.googleapis.com/fcm/send/cifra',
                          p256dh='chave-publica-do-aparelho', auth='segredo-auth')
        db.session.add(p)
        db.session.commit()
        brutos = [(_bruto('users', 'email', uid), 'cifra.ana'),
                  (_bruto('users', 'totp_segredo', uid), 'JBSWY3DPEHPK3PXP'),
                  (_bruto('clients', 'endereco', local.id), 'Flores'),
                  (_bruto('push_inscricoes', 'p256dh', p.id), 'chave-publica'),
                  (_bruto('push_inscricoes', 'auth', p.id), 'segredo-auth')]
        for valor, texto in brutos:
            assert valor.startswith('gAAAAA') and texto not in valor
        # Lido pelo modelo, volta o texto.
        db.session.expire_all()
        assert db.session.get(User, uid).totp_segredo == 'JBSWY3DPEHPK3PXP'
        assert db.session.get(Client, local.id).endereco == 'Rua das Flores, 123'
        # O índice cego não é o e-mail e não muda com a maiúscula.
        indice = _bruto('users', 'email_index', uid)
        assert 'cifra' not in indice and indice == cifra.indice('  CIFRA.Ana@Trino.com ')
        c = Convite(token_hash='x' * 64, nome='Bia', email='bia.convite@trino.com',
                    telefone='71999998888', role='tecnico', criado_por_id=uid,
                    expira_em=local.created_at)
        db.session.add(c)
        db.session.commit()
        assert '99999' not in _bruto('convites', 'telefone', c.id)
        assert 'bia' not in _bruto('convites', 'email', c.id)
        assert Convite.query.filter_by(email='BIA.convite@trino.com').one().id == c.id
        db.session.delete(c)
        db.session.delete(p)
        local.endereco = None
        db.session.commit()


def test_login_acha_a_conta_sem_diferenca_de_maiuscula(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'cifra.login@trino.com')
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': 'Cifra.Login@TRINO.com', 'password': fabrica.SENHA})
    assert r.status_code == 302 and '/login' not in r.headers['Location']


def test_email_repetido_continua_barrado(app_module):
    from app import User, db
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'cifra.unico@trino.com')
        db.session.add(User(name='Outra', email='CIFRA.unico@trino.com', password_hash='x'))
        with pytest.raises(sa.exc.IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_comparar_campo_cifrado_fora_do_igual_e_recusado(app_module):
    from app import User
    with app_module.app.app_context(), pytest.raises(TypeError):
        User.query.filter(User.email.like('%trino%')).all()


def test_rodizio_da_chave(app_module):
    from app import User, db
    from facilities.core.cifra_banco import em_claro
    nova = cifra.gerar_chave()
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'cifra.rodizio@trino.com')
        antes = _bruto('users', 'email', uid)
        try:
            # 1. A chave nova entra; a antiga fica só para ler.
            cifra.configurar(nova, CHAVE_SUITE)
            db.session.expire_all()
            assert User.por_email('cifra.rodizio@trino.com').id == uid
            # 2. O comando recifra tudo e refaz o índice.
            r = app_module.app.test_cli_runner().invoke(args=['chaves', 'girar'])
            assert r.exit_code == 0, r.output
            assert _bruto('users', 'email', uid) != antes
            # 3. Sem a antiga, tudo continua legível.
            cifra.configurar(nova)
            db.session.expire_all()
            assert User.por_email('cifra.rodizio@trino.com').id == uid
            assert not em_claro(db.session)
        finally:
            # De volta à chave da suíte (a nova fica só para ler e recifrar).
            cifra.configurar(CHAVE_SUITE, nova)
            app_module.app.test_cli_runner().invoke(args=['chaves', 'girar'])
            cifra.configurar(CHAVE_SUITE)
            db.session.expire_all()


def test_chave_errada_e_erro_nunca_lixo():
    token = cifra.cifrar('segredo')
    try:
        cifra.configurar(cifra.gerar_chave())
        with pytest.raises(cifra.ChaveAusente):
            cifra.decifrar(token)
    finally:
        cifra.configurar(CHAVE_SUITE)


def test_conferir_acusa_campo_sem_cifra(app_module):
    from app import db
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'cifra.conferir@trino.com')
        runner = app_module.app.test_cli_runner()
        assert runner.invoke(args=['chaves', 'conferir']).exit_code == 0
        db.session.execute(sa.text("UPDATE users SET totp_segredo = 'EMCLARO' WHERE id = :i"),
                           {'i': uid})
        db.session.commit()
        r = runner.invoke(args=['chaves', 'conferir'])
        assert r.exit_code == 1 and 'users.totp_segredo' in r.output
        db.session.execute(sa.text('UPDATE users SET totp_segredo = NULL WHERE id = :i'),
                           {'i': uid})
        db.session.commit()


def test_sem_chave_o_sistema_sobe_com_aviso(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv('FIELD_ENCRYPTION_KEY')
    monkeypatch.setenv('EXIGIR_DATABASE_URL', '1')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@127.0.0.1:1/facilities')
    monkeypatch.setenv('UPLOAD_FOLDER', str(tmp_path))
    try:
        create_app()
        assert not cifra.ligada()
        assert 'TEXTO ABERTO' in caplog.text
    finally:
        cifra.configurar(CHAVE_SUITE)


def test_cifra_desligada_grava_aberto_e_ligar_depois_cifra_tudo(app_module):
    """O caminho de qualquer servidor: começa sem chave, liga quando quiser."""
    from app import User, db
    from facilities.core.cifra_banco import em_claro
    with app_module.app.app_context():
        try:
            cifra.configurar('')
            uid = fabrica.pessoa(app_module, 'cifra.aberta@trino.com')
            db.session.get(User, uid).totp_segredo = 'JBSWY3DPEHPK3PXP'
            db.session.commit()
            assert _bruto('users', 'email', uid) == 'cifra.aberta@trino.com'
            assert _bruto('users', 'totp_segredo', uid) == 'JBSWY3DPEHPK3PXP'
            c = app_module.app.test_client()
            r = c.post('/login', data={'email': 'CIFRA.aberta@trino.com',
                                       'password': fabrica.SENHA})
            assert r.status_code == 302 and '/login' not in r.headers['Location']
            # Liga: chave no ambiente + o comando. O login continua.
            cifra.configurar(CHAVE_SUITE)
            r = app_module.app.test_cli_runner().invoke(args=['chaves', 'girar'])
            assert r.exit_code == 0, r.output
            assert 'cifra.aberta' not in _bruto('users', 'email', uid)
            assert not em_claro(db.session)
            db.session.expire_all()
            assert User.por_email('cifra.aberta@trino.com').id == uid
            assert db.session.get(User, uid).totp_segredo == 'JBSWY3DPEHPK3PXP'
            # Tirar a chave com dado cifrado no banco: erro claro, nunca lixo.
            cifra.configurar('')
            db.session.expire_all()
            with pytest.raises(cifra.ChaveAusente, match='ponha de volta a chave'):
                db.session.get(User, uid).totp_segredo
            db.session.rollback()
        finally:
            cifra.configurar(CHAVE_SUITE)
            db.session.expire_all()
            u = db.session.get(User, uid)
            u.totp_segredo = None
            db.session.commit()


def test_girar_sem_chave_avisa_e_nao_mexe(app_module):
    try:
        cifra.configurar('')
        r = app_module.app.test_cli_runner().invoke(args=['chaves', 'girar'])
        assert r.exit_code == 1 and 'não definida' in r.output
    finally:
        cifra.configurar(CHAVE_SUITE)


def test_chave_invalida_e_recusada():
    with pytest.raises(cifra.ChaveAusente, match='não é uma chave válida'):
        cifra.configurar('curta-demais')
    cifra.configurar(CHAVE_SUITE)


# ── Conexão com o banco ───────────────────────────────────────────────────

@pytest.mark.parametrize('url, esperado', [
    ('postgresql://u:p@banco.empresa.com.br:5432/fac', 'sslmode=require'),
    ('postgresql://u:p@postgres.railway.internal:5432/railway', None),
    ('postgresql://u:p@db:5432/fac', None),
    ('postgresql://u:p@127.0.0.1:5432/fac', None),
    ('postgresql://u:p@banco.empresa.com.br/fac?sslmode=verify-full', 'sslmode=verify-full'),
])
def test_banco_fora_da_rede_interna_so_com_tls(monkeypatch, url, esperado):
    from facilities import _com_tls
    monkeypatch.setenv('EXIGIR_DATABASE_URL', '1')
    monkeypatch.delenv('DATABASE_SSLMODE', raising=False)
    final = _com_tls(url)
    if esperado:
        assert esperado in final and final.startswith('postgresql://u:p@')
    else:
        assert final == url


def test_database_sslmode_manda(monkeypatch):
    from facilities import _com_tls
    monkeypatch.delenv('EXIGIR_DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_SSLMODE', 'verify-full')
    assert 'sslmode=verify-full' in _com_tls('postgresql://u:p@db/fac')


# ── Senha ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('senha', ['12345678', 'Senha123', 'aaaaaaaa', 'abababab',
                                   '23456789', 'joaosilva2026'])
def test_senha_obvia_e_recusada(senha):
    from facilities.core import senhas
    assert senhas.problema(senha, 'joaosilva@trino.com')


def test_senha_boa_passa():
    from facilities.core import senhas
    assert senhas.problema('Limpeza-turno-7', 'joaosilva@trino.com') is None


def test_hash_antigo_e_refeito_no_login(app_module):
    from werkzeug.security import generate_password_hash
    from app import User, db
    with app_module.app.app_context():
        uid = fabrica.pessoa(app_module, 'cifra.hash@trino.com')
        u = db.session.get(User, uid)
        u.password_hash = generate_password_hash(fabrica.SENHA, method='pbkdf2:sha256')
        db.session.commit()
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': 'cifra.hash@trino.com', 'password': fabrica.SENHA})
    assert r.status_code == 302
    with app_module.app.app_context():
        assert db.session.get(User, uid).password_hash.startswith('scrypt:')
