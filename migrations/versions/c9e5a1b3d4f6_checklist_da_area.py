"""Cadastro simplificado: o checklist de cada área (decisões do dono, 27/10/2026).

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* ``pontos_inspecao.checklist_id`` (opcional, chave para ``checklist_modelos``):
  o checklist da área — o escopo do que fazer ali. A rota digitada em linhas
  ("06:00 · Banheiro 01") e a limpeza fora da rota usam este checklist.

A volta guarda em quarentena os valores da coluna nova (só das linhas que têm
checklist); a ida seguinte devolve.

Revision ID: c9e5a1b3d4f6
Revises: b8d4f0a2c3e5
Create Date: 2026-10-27 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela


# revision identifiers, used by Alembic.
revision = 'c9e5a1b3d4f6'
down_revision = 'b8d4f0a2c3e5'
branch_labels = None
depends_on = None

# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'pontos_inspecao': (('checklist_id',), 'checklist_id IS NOT NULL'),
}


def upgrade():
    with op.batch_alter_table('pontos_inspecao', schema=None) as batch_op:
        batch_op.add_column(sa.Column('checklist_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_pontos_inspecao_checklist_id'), ['checklist_id'],
                              unique=False)
        batch_op.create_foreign_key('fk_pontos_inspecao_checklist_id_checklist_modelos',
                                    'checklist_modelos', ['checklist_id'], ['id'],
                                    ondelete='RESTRICT')

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

    with op.batch_alter_table('pontos_inspecao', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pontos_inspecao_checklist_id_checklist_modelos',
                                 type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_pontos_inspecao_checklist_id'))
        batch_op.drop_column('checklist_id')
