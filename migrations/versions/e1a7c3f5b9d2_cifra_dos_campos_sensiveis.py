"""Cifra dos campos sensíveis (pedido do dono, 30/10/2026).

O que muda no schema:

* ``users.email`` e ``users.totp_segredo``, ``convites.email`` e
  ``convites.telefone``, ``clients.endereco``, ``push_inscricoes.p256dh`` e
  ``push_inscricoes.auth`` passam a TEXT e guardam o valor cifrado
  (``facilities/core/cifra.py``, chave em ``FIELD_ENCRYPTION_KEY``).
* ``users.email_index`` (único) e ``convites.email_index``: o índice cego
  (HMAC) do e-mail, por onde o login e os convites procuram.
* Sai a restrição única de ``users.email`` e o índice ``ix_convites_email``
  (sobre texto cifrado eles não servem; a unicidade passa para o índice cego,
  sem diferença de maiúsculas).

As linhas existentes são REESCRITAS (texto → cifrado). Antes disso:

* e-mails iguais sem diferença de maiúsculas em ``users`` param a migração
  (o índice único não aceitaria) — a mensagem diz quais ids conferir;
* o valor original de cada campo vai para ``_quarentena_<rev>_campos``,
  CIFRADO (uma cópia em texto aberto manteria no banco o vazamento que esta
  migração fecha), e cada valor é conferido: cifrar e decifrar devolve o
  mesmo texto, senão nada é gravado.

A volta decifra tudo, devolve tipos, restrição e índice; a quarentena fica.
Precisa da ``FIELD_ENCRYPTION_KEY`` no ambiente (o app não sobe sem ela).

Revision ID: e1a7c3f5b9d2
Revises: d0f6b2c4e5a7
Create Date: 2026-10-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core import cifra
from facilities.core.cifra_banco import cifrar_tabela, decifrar_tabela
from facilities.core.quarentena import nome_quarentena


# revision identifiers, used by Alembic.
revision = 'e1a7c3f5b9d2'
down_revision = 'd0f6b2c4e5a7'
branch_labels = None
depends_on = None

# Congelado aqui (a lista do código pode crescer depois): tabela → (colunas,
# tamanho antigo de cada uma, coluna do índice cego).
CAMPOS = {
    'users': ({'email': 150, 'totp_segredo': 64}, 'email'),
    'convites': ({'email': 150, 'telefone': 20}, 'email'),
    'clients': ({'endereco': 255}, None),
    'push_inscricoes': ({'p256dh': 200, 'auth': 100}, None),
}
NULO = {('users', 'email'): False, ('convites', 'email'): False,
        ('push_inscricoes', 'p256dh'): False, ('push_inscricoes', 'auth'): False}
QUARENTENA = nome_quarentena('campos', revision)
# Para o SQLite (batch recria a tabela): dá nome à restrição única sem nome.
CONVENCAO = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}


def _unica_do_email(bind):
    for uc in sa.inspect(bind).get_unique_constraints('users'):
        if uc['column_names'] == ['email']:
            return uc['name'] or 'uq_users_email'
    return None


def _conferir_duplicados(bind):
    vistos = {}
    for uid, email in bind.execute(sa.text('SELECT id, email FROM users ORDER BY id')):
        chave = cifra.normalizar_email(cifra.decifrar(email))
        vistos.setdefault(chave, []).append(uid)
    repetidos = {k: v for k, v in vistos.items() if len(v) > 1}
    if repetidos:
        ids = '; '.join(', '.join(map(str, v)) for v in repetidos.values())
        raise RuntimeError(
            'Há contas com o mesmo e-mail (só muda maiúscula/minúscula ou espaço): ids '
            f'{ids}. Junte ou corrija essas contas antes de rodar esta migração.')


def _quarentenar(bind):
    """O original de cada campo, cifrado, antes de reescrever. Conferido."""
    if QUARENTENA not in sa.inspect(bind).get_table_names():
        op.create_table(
            QUARENTENA,
            sa.Column('tabela', sa.String(40), nullable=False),
            sa.Column('linha_id', sa.Integer, nullable=False),
            sa.Column('coluna', sa.String(40), nullable=False),
            sa.Column('valor', sa.Text, nullable=True),
            sa.Column('_quarentena_em', sa.DateTime, server_default=sa.func.now()))
    for tabela, (colunas, _ix) in CAMPOS.items():
        nomes = tuple(colunas)
        for linha in bind.execute(sa.text(
                f'SELECT id, {", ".join(nomes)} FROM {tabela} ORDER BY id')):
            for coluna, valor in zip(nomes, linha[1:]):
                if valor is None:
                    continue
                aberto = cifra.decifrar(valor)
                guardado = cifra.cifrar(aberto)
                if cifra.decifrar(guardado) != aberto:
                    raise RuntimeError(f'{tabela}.{coluna} id {linha[0]}: a cifra não '
                                       'devolveu o mesmo texto; nada foi gravado.')
                params = {'t': tabela, 'i': linha[0], 'c': coluna, 'v': guardado}
                # A volta e a ida: a linha da quarentena é trocada pela atual.
                bind.execute(sa.text(f'DELETE FROM {QUARENTENA} WHERE tabela = :t '
                                     'AND linha_id = :i AND coluna = :c'), params)
                bind.execute(sa.text(f'INSERT INTO {QUARENTENA} (tabela, linha_id, coluna, '
                                     'valor) VALUES (:t, :i, :c, :v)'), params)


def upgrade():
    bind = op.get_bind()
    _conferir_duplicados(bind)
    _quarentenar(bind)

    unica = _unica_do_email(bind)
    with op.batch_alter_table('users', schema=None, naming_convention=CONVENCAO) as batch_op:
        if unica:
            batch_op.drop_constraint(unica, type_='unique')
        batch_op.add_column(sa.Column('email_index', sa.String(length=64), nullable=True))
        for coluna, tamanho in CAMPOS['users'][0].items():
            batch_op.alter_column(coluna, existing_type=sa.String(length=tamanho),
                                  type_=sa.Text(),
                                  existing_nullable=NULO.get(('users', coluna), True))
    with op.batch_alter_table('convites', schema=None) as batch_op:
        batch_op.drop_index('ix_convites_email')
        batch_op.add_column(sa.Column('email_index', sa.String(length=64), nullable=True))
        for coluna, tamanho in CAMPOS['convites'][0].items():
            batch_op.alter_column(coluna, existing_type=sa.String(length=tamanho),
                                  type_=sa.Text(),
                                  existing_nullable=NULO.get(('convites', coluna), True))
    for tabela in ('clients', 'push_inscricoes'):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            for coluna, tamanho in CAMPOS[tabela][0].items():
                batch_op.alter_column(coluna, existing_type=sa.String(length=tamanho),
                                      type_=sa.Text(),
                                      existing_nullable=NULO.get((tabela, coluna), True))

    for tabela, (colunas, indice_de) in CAMPOS.items():
        cifrar_tabela(bind, tabela, tuple(colunas), indice_de)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email_index', existing_type=sa.String(length=64),
                              nullable=False)
        batch_op.create_index('ix_users_email_index', ['email_index'], unique=True)
    with op.batch_alter_table('convites', schema=None) as batch_op:
        batch_op.alter_column('email_index', existing_type=sa.String(length=64),
                              nullable=False)
        batch_op.create_index('ix_convites_email_index', ['email_index'], unique=False)


def downgrade():
    bind = op.get_bind()
    for tabela, (colunas, _ix) in CAMPOS.items():
        decifrar_tabela(bind, tabela, tuple(colunas))

    with op.batch_alter_table('convites', schema=None) as batch_op:
        batch_op.drop_index('ix_convites_email_index')
        batch_op.drop_column('email_index')
        for coluna, tamanho in CAMPOS['convites'][0].items():
            batch_op.alter_column(coluna, existing_type=sa.Text(),
                                  type_=sa.String(length=tamanho),
                                  existing_nullable=NULO.get(('convites', coluna), True))
        batch_op.create_index('ix_convites_email', ['email'], unique=False)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_email_index')
        batch_op.drop_column('email_index')
        for coluna, tamanho in CAMPOS['users'][0].items():
            batch_op.alter_column(coluna, existing_type=sa.Text(),
                                  type_=sa.String(length=tamanho),
                                  existing_nullable=NULO.get(('users', coluna), True))
        batch_op.create_unique_constraint('users_email_key', ['email'])
    for tabela in ('clients', 'push_inscricoes'):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            for coluna, tamanho in CAMPOS[tabela][0].items():
                batch_op.alter_column(coluna, existing_type=sa.Text(),
                                      type_=sa.String(length=tamanho),
                                      existing_nullable=NULO.get((tabela, coluna), True))
