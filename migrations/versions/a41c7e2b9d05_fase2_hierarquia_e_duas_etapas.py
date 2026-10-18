"""Fase 2 — hierarquia de pessoas e segunda etapa do login.

O que muda no schema (só acrescenta, tudo opcional), na tabela ``users``:

* ``superior_id`` — o superior direto na cadeia (gerente › coordenador ›
  supervisor › encarregado/técnico);
* ``cliente_id`` — de qual cliente é a pessoa com o perfil Cliente;
* ``totp_segredo``, ``totp_ativo``, ``totp_ultimo_passo`` — a segunda etapa
  do login (código do aplicativo autenticador).

Os perfis novos (gerente, supervisor, cliente) são só valores novos da
coluna ``role``, que já existe: nenhuma linha é reescrita.

A volta guarda em quarentena as pessoas com cadeia, cliente ou segunda
etapa preenchidos, e a ida seguinte devolve esses valores.

Revision ID: a41c7e2b9d05
Revises: 762d8f5c3429
Create Date: 2026-10-17 21:00:00

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela

revision = 'a41c7e2b9d05'
down_revision = '762d8f5c3429'
branch_labels = None
depends_on = None

COLUNAS = ('superior_id', 'cliente_id', 'totp_segredo', 'totp_ativo', 'totp_ultimo_passo')


def upgrade():
    with op.batch_alter_table('users', schema=None) as b:
        b.add_column(sa.Column('superior_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('cliente_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('totp_segredo', sa.String(length=64), nullable=True))
        b.add_column(sa.Column('totp_ativo', sa.Boolean(), nullable=False,
                               server_default=sa.false()))
        b.add_column(sa.Column('totp_ultimo_passo', sa.BigInteger(), nullable=True))
        b.create_index(b.f('ix_users_superior_id'), ['superior_id'], unique=False)
        b.create_index(b.f('ix_users_cliente_id'), ['cliente_id'], unique=False)
        b.create_foreign_key('fk_users_superior_id', 'users', ['superior_id'], ['id'],
                             ondelete='RESTRICT')
        b.create_foreign_key('fk_users_cliente_id', 'contratantes', ['cliente_id'], ['id'],
                             ondelete='RESTRICT')

    bind = op.get_bind()
    q = nome_quarentena('users', revision)
    if q in sa.inspect(bind).get_table_names():
        sets = ', '.join(f'{c} = (SELECT x.{c} FROM {q} x WHERE x.id = users.id)'
                         for c in COLUNAS)
        bind.execute(sa.text(f'UPDATE users SET {sets} WHERE id IN (SELECT id FROM {q})'))


def downgrade():
    quarentenar_tabela(op, 'users', revision,
                       onde='superior_id IS NOT NULL OR cliente_id IS NOT NULL '
                            'OR totp_segredo IS NOT NULL OR totp_ativo')
    with op.batch_alter_table('users', schema=None) as b:
        b.drop_constraint('fk_users_cliente_id', type_='foreignkey')
        b.drop_constraint('fk_users_superior_id', type_='foreignkey')
        b.drop_index(b.f('ix_users_cliente_id'))
        b.drop_index(b.f('ix_users_superior_id'))
        for c in reversed(COLUNAS):
            b.drop_column(c)
