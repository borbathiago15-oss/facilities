"""Reclamação e elogio pelo QR (decisões do dono, 27/10/2026).

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* Tabela nova ``elogios_publicos``: a avaliação de 1 a 5 estrelas (e um
  comentário opcional) de quem leu o QR do ponto.
* ``ocorrencias_publicas.responsavel_id`` (opcional): quem cuida do ponto no
  dia e recebe o aviso como tarefa "Checar aviso".
* ``ocorrencias_publicas.resumo`` (texto, opcional): os problemas marcados,
  em palavras, guardados no momento do aviso.

A volta guarda em quarentena os elogios e os valores das colunas novas (só
das linhas que têm valor); a ida seguinte devolve.

Revision ID: a7c3e9f1b2d4
Revises: e5f6a7b8c9d0
Create Date: 2026-10-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela, restaurar_tabela


# revision identifiers, used by Alembic.
revision = 'a7c3e9f1b2d4'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

TABELAS = ('elogios_publicos',)
# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'ocorrencias_publicas': (('responsavel_id', 'resumo'),
                             'responsavel_id IS NOT NULL OR resumo IS NOT NULL'),
}


def upgrade():
    op.create_table('elogios_publicos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ponto_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('nota', sa.SmallInteger(), nullable=False),
    sa.Column('texto', sa.String(length=300), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.Column('responsavel_id', sa.Integer(), nullable=True),
    sa.Column('autor_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('nota BETWEEN 1 AND 5', name='ck_elogios_nota'),
    sa.ForeignKeyConstraint(['ponto_id'], ['pontos_inspecao.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['responsavel_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['autor_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('elogios_publicos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_elogios_publicos_ponto_id'), ['ponto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_elogios_publicos_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_elogios_publicos_criado_em'), ['criado_em'], unique=False)

    with op.batch_alter_table('ocorrencias_publicas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('responsavel_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('resumo', sa.String(length=300), nullable=True))
        batch_op.create_index(batch_op.f('ix_ocorrencias_publicas_responsavel_id'),
                              ['responsavel_id'], unique=False)
        batch_op.create_foreign_key('fk_ocorrencias_publicas_responsavel_id_users', 'users',
                                    ['responsavel_id'], ['id'], ondelete='RESTRICT')

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

    with op.batch_alter_table('ocorrencias_publicas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ocorrencias_publicas_responsavel_id_users',
                                 type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_ocorrencias_publicas_responsavel_id'))
        batch_op.drop_column('resumo')
        batch_op.drop_column('responsavel_id')

    with op.batch_alter_table('elogios_publicos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_elogios_publicos_criado_em'))
        batch_op.drop_index(batch_op.f('ix_elogios_publicos_client_id'))
        batch_op.drop_index(batch_op.f('ix_elogios_publicos_ponto_id'))

    op.drop_table('elogios_publicos')
