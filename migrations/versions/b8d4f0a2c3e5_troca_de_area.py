"""Troca de área no aplicativo (decisões do dono, 27/10/2026).

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* ``execucoes.motivo_troca`` (texto curto, opcional): por que o técnico foi a
  esta área fora da ordem da rota — tarefa adiantada ou área fora da rota
  (pedido da gestão, pedido do cliente, área mais suja, outro).
* ``execucoes.motivo_troca_texto`` (texto, opcional): o que ele escreveu em
  "outro".

A volta guarda em quarentena os valores das colunas novas (só das linhas que
têm motivo); a ida seguinte devolve.

Revision ID: b8d4f0a2c3e5
Revises: a7c3e9f1b2d4
Create Date: 2026-10-27 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela


# revision identifiers, used by Alembic.
revision = 'b8d4f0a2c3e5'
down_revision = 'a7c3e9f1b2d4'
branch_labels = None
depends_on = None

# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'execucoes': (('motivo_troca', 'motivo_troca_texto'), 'motivo_troca IS NOT NULL'),
}


def upgrade():
    with op.batch_alter_table('execucoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('motivo_troca', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('motivo_troca_texto', sa.String(length=300),
                                      nullable=True))

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

    with op.batch_alter_table('execucoes', schema=None) as batch_op:
        batch_op.drop_column('motivo_troca_texto')
        batch_op.drop_column('motivo_troca')
