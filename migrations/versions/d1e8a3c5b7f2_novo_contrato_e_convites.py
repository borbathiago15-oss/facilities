"""Assistente "Novo contrato" (decisões do dono, 22/10/2026): gerente e
coordenador montam cliente, local, estrutura e equipe, e convidam as pessoas
por e-mail ou WhatsApp.

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* Tabela nova ``convites``: o convite para entrar no sistema, com o perfil, o
  superior, os locais e quem convidou. Guarda só o HASH do link (o link em
  si nunca vai para o banco). Vale 7 dias e uma vez só.
* ``contratantes.logo_key`` (texto 200, opcional): onde está a logo do
  cliente no armazenamento; vai na etiqueta do QR.

A volta guarda em quarentena os convites e as logos já cadastradas; a ida
seguinte devolve.

Revision ID: d1e8a3c5b7f2
Revises: b7d4e9f1a2c3
Create Date: 2026-10-22 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela, restaurar_tabela


# revision identifiers, used by Alembic.
revision = 'd1e8a3c5b7f2'
down_revision = 'b7d4e9f1a2c3'
branch_labels = None
depends_on = None

TABELAS = ('convites',)
# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'contratantes': (('logo_key',), 'logo_key IS NOT NULL'),
}


def upgrade():
    op.create_table('convites',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('telefone', sa.String(length=20), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('superior_id', sa.Integer(), nullable=True),
    sa.Column('cliente_id', sa.Integer(), nullable=True),
    sa.Column('locais_json', sa.Text(), nullable=False),
    sa.Column('criado_por_id', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.Column('expira_em', sa.DateTime(), nullable=False),
    sa.Column('aceito_em', sa.DateTime(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('cancelado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['contratantes.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['criado_por_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['superior_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('convites', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_convites_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_convites_criado_por_id'), ['criado_por_id'],
                              unique=False)

    with op.batch_alter_table('contratantes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo_key', sa.String(length=200), nullable=True))

    for tabela in TABELAS:
        restaurar_tabela(op, tabela, revision)
    bind = op.get_bind()
    nomes = sa.inspect(bind).get_table_names()
    for tabela, (cols, _f) in COLUNAS.items():
        q = nome_quarentena(tabela, revision)
        if q in nomes:
            sets = ', '.join(f'{c} = (SELECT x.{c} FROM {q} x WHERE x.id = {tabela}.id)'
                             for c in cols)
            bind.execute(sa.text(f'UPDATE {tabela} SET {sets} WHERE id IN (SELECT id FROM {q})'))


def downgrade():
    for tabela, (_cols, filtro) in COLUNAS.items():
        quarentenar_tabela(op, tabela, revision, onde=filtro)
    for tabela in TABELAS:
        quarentenar_tabela(op, tabela, revision)

    with op.batch_alter_table('contratantes', schema=None) as batch_op:
        batch_op.drop_column('logo_key')

    with op.batch_alter_table('convites', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_convites_criado_por_id'))
        batch_op.drop_index(batch_op.f('ix_convites_email'))

    op.drop_table('convites')
