"""Plano de limpeza do cliente (decisões do dono, 22/10/2026): o sistema lê a
planilha "PLANO DE LIMPEZA E CONSERVAÇÃO" e monta blocos, checklists e rotas.
Para a rota caber no plano, o modelo ganha três coisas.

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* ``rota_itens.dias_semana`` (texto 7, opcional): vazio = todos os dias da
  rota, como hoje; preenchido = o item só gera tarefa nesses dias (ex.: a
  atividade da tarde que não existe no sábado).
* ``rota_itens.horarios_por_dia`` (texto, opcional): JSON
  ``{"6": "07:00, 09:30"}`` com os horários de um dia específico (o sábado
  da planilha começa mais cedo); nos outros dias vale ``horarios``.
* ``checklist_versoes.materiais`` e ``checklist_versoes.epi`` (texto,
  opcionais): o material usado e o EPI da atividade, congelados na versão
  publicada — a execução mostra o que valia no dia.
* ``rotas.intervalo_inicio`` e ``rotas.intervalo_fim`` (hora, opcionais): o
  intervalo dentro do turno; o agendador não cria tarefa nele.
* ``rotas.observacoes`` (texto, opcional): as observações do plano,
  mostradas na tela da rota.

A volta guarda em quarentena os valores das colunas novas (só das linhas
que têm valor); a ida seguinte devolve.

Revision ID: b7d4e9f1a2c3
Revises: f2a7c4d9e1b3
Create Date: 2026-10-22 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela


# revision identifiers, used by Alembic.
revision = 'b7d4e9f1a2c3'
down_revision = 'f2a7c4d9e1b3'
branch_labels = None
depends_on = None

# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'rota_itens': (('dias_semana', 'horarios_por_dia'),
                   'dias_semana IS NOT NULL OR horarios_por_dia IS NOT NULL'),
    'checklist_versoes': (('materiais', 'epi'), 'materiais IS NOT NULL OR epi IS NOT NULL'),
    'rotas': (('intervalo_inicio', 'intervalo_fim', 'observacoes'),
              'intervalo_inicio IS NOT NULL OR intervalo_fim IS NOT NULL '
              'OR observacoes IS NOT NULL'),
}


def upgrade():
    with op.batch_alter_table('rota_itens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dias_semana', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('horarios_por_dia', sa.Text(), nullable=True))

    with op.batch_alter_table('checklist_versoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('materiais', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('epi', sa.Text(), nullable=True))

    with op.batch_alter_table('rotas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intervalo_inicio', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('intervalo_fim', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('observacoes', sa.Text(), nullable=True))

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

    with op.batch_alter_table('rotas', schema=None) as batch_op:
        batch_op.drop_column('observacoes')
        batch_op.drop_column('intervalo_fim')
        batch_op.drop_column('intervalo_inicio')

    with op.batch_alter_table('checklist_versoes', schema=None) as batch_op:
        batch_op.drop_column('epi')
        batch_op.drop_column('materiais')

    with op.batch_alter_table('rota_itens', schema=None) as batch_op:
        batch_op.drop_column('horarios_por_dia')
        batch_op.drop_column('dias_semana')
