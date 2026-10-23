"""Ajustes de fluxo (decisões do dono, 23/10/2026): feriados, rota que se
refaz ao ser editada e relatório do cliente congelado na liberação.

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* Tabela nova ``feriados``: feriado de um LOCAL (estadual, municipal, ponto
  facultativo do cliente). Os nacionais não ficam no banco: são calculados.
* ``rotas.funciona_em_feriado`` (bool, padrão verdadeiro): a rota funciona
  em feriado. Toda rota existente continua como era (gera em feriado).
* ``rotas.vale_a_partir`` (data e hora, opcional): quando a gestão mudou a
  rota pela última vez; o agendador não cria tarefa cujo horário já tinha
  passado nesse momento (a tarefa não nasce atrasada).
* ``relatorios_cliente.congelado_json`` (texto, opcional): a versão que o
  cliente recebeu ao liberar (números, fotos e recado).

A volta guarda em quarentena os feriados e os valores das colunas novas (só
das linhas que têm valor diferente do padrão); a ida seguinte devolve.

Revision ID: e5f6a7b8c9d0
Revises: d1e8a3c5b7f2
Create Date: 2026-10-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela, restaurar_tabela


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd1e8a3c5b7f2'
branch_labels = None
depends_on = None

TABELAS = ('feriados',)
# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'rotas': (('funciona_em_feriado', 'vale_a_partir'),
              'NOT funciona_em_feriado OR vale_a_partir IS NOT NULL'),
    'relatorios_cliente': (('congelado_json',), 'congelado_json IS NOT NULL'),
}


def upgrade():
    op.create_table('feriados',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('nome', sa.String(length=80), nullable=False),
    sa.Column('criado_por', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['criado_por'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id', 'data', name='uq_feriados_local_data')
    )
    with op.batch_alter_table('feriados', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feriados_client_id'), ['client_id'], unique=False)

    with op.batch_alter_table('rotas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('funciona_em_feriado', sa.Boolean(),
                                      server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('vale_a_partir', sa.DateTime(), nullable=True))

    with op.batch_alter_table('relatorios_cliente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('congelado_json', sa.Text(), nullable=True))

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

    with op.batch_alter_table('relatorios_cliente', schema=None) as batch_op:
        batch_op.drop_column('congelado_json')

    with op.batch_alter_table('rotas', schema=None) as batch_op:
        batch_op.drop_column('vale_a_partir')
        batch_op.drop_column('funciona_em_feriado')

    with op.batch_alter_table('feriados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feriados_client_id'))

    op.drop_table('feriados')
