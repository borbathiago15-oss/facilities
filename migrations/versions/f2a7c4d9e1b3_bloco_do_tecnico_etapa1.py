"""Bloco do técnico, etapa 1 (decisões do dono, 22/10/2026): chegada no local,
tempo previsto, motivo de atraso e itens do QR público.

O que muda no schema (só acrescenta):

* 1 tabela nova: ``chegadas`` (pessoa, local, ponto de entrada lido, dia
  local, hora UTC, se foi pela câmera, quem liberou). Uma chegada por
  pessoa, local e dia (``uq_chegadas_pessoa_local_dia``); índice por local
  e dia.
* colunas novas, todas aditivas (nenhuma linha existente é reescrita):
  - ``pontos_inspecao.entrada_do_local`` (booleano, NOT NULL, padrão falso:
    os pontos de hoje seguem como pontos comuns);
  - ``rota_itens.tempo_previsto_min`` (inteiro, opcional: vazio = sem
    controle de tempo, como hoje);
  - ``rota_modelo_itens.tempo_previsto_min`` (inteiro, opcional: o tempo
    que a rota pronta copia para o item ao ser aplicada);
  - ``execucoes.motivo_atraso`` (texto 40, opcional) e
    ``execucoes.motivo_atraso_texto`` (texto 300, opcional);
  - ``ocorrencias_publicas.itens_json`` (texto, opcional: os itens do
    checklist marcados por quem abriu) e ``ocorrencias_publicas.autor_id``
    (FK users, opcional: quem abriu QUANDO estava logado).

A volta guarda em quarentena a tabela nova e os valores das colunas novas
(só das linhas que têm valor); a ida seguinte devolve.

Revision ID: f2a7c4d9e1b3
Revises: c45830310c26
Create Date: 2026-10-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela, restaurar_tabela


# revision identifiers, used by Alembic.
revision = 'f2a7c4d9e1b3'
down_revision = 'c45830310c26'
branch_labels = None
depends_on = None

TABELAS = ('chegadas',)
# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'pontos_inspecao': (('entrada_do_local',), 'entrada_do_local'),
    'rota_itens': (('tempo_previsto_min',), 'tempo_previsto_min IS NOT NULL'),
    'rota_modelo_itens': (('tempo_previsto_min',), 'tempo_previsto_min IS NOT NULL'),
    'execucoes': (('motivo_atraso', 'motivo_atraso_texto'), 'motivo_atraso IS NOT NULL'),
    'ocorrencias_publicas': (('itens_json', 'autor_id'),
                             'itens_json IS NOT NULL OR autor_id IS NOT NULL'),
}


def upgrade():
    op.create_table('chegadas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('ponto_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('chegou_em', sa.DateTime(), nullable=False),
    sa.Column('com_camera', sa.Boolean(), nullable=False),
    sa.Column('liberada_por', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['liberada_por'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['ponto_id'], ['pontos_inspecao.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'client_id', 'data', name='uq_chegadas_pessoa_local_dia')
    )
    with op.batch_alter_table('chegadas', schema=None) as batch_op:
        batch_op.create_index('ix_chegadas_local_data', ['client_id', 'data'], unique=False)
        batch_op.create_index(batch_op.f('ix_chegadas_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('pontos_inspecao', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entrada_do_local', sa.Boolean(),
                                      server_default=sa.text('false'), nullable=False))

    with op.batch_alter_table('rota_itens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tempo_previsto_min', sa.Integer(), nullable=True))

    with op.batch_alter_table('rota_modelo_itens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tempo_previsto_min', sa.Integer(), nullable=True))

    with op.batch_alter_table('execucoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('motivo_atraso', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('motivo_atraso_texto', sa.String(length=300),
                                      nullable=True))

    with op.batch_alter_table('ocorrencias_publicas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('itens_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('autor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_ocorrencias_publicas_autor_id_users', 'users',
                                    ['autor_id'], ['id'], ondelete='RESTRICT')

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
        batch_op.drop_constraint('fk_ocorrencias_publicas_autor_id_users', type_='foreignkey')
        batch_op.drop_column('autor_id')
        batch_op.drop_column('itens_json')

    with op.batch_alter_table('execucoes', schema=None) as batch_op:
        batch_op.drop_column('motivo_atraso_texto')
        batch_op.drop_column('motivo_atraso')

    with op.batch_alter_table('rota_modelo_itens', schema=None) as batch_op:
        batch_op.drop_column('tempo_previsto_min')

    with op.batch_alter_table('rota_itens', schema=None) as batch_op:
        batch_op.drop_column('tempo_previsto_min')

    with op.batch_alter_table('pontos_inspecao', schema=None) as batch_op:
        batch_op.drop_column('entrada_do_local')

    with op.batch_alter_table('chegadas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chegadas_user_id'))
        batch_op.drop_index('ix_chegadas_local_data')

    op.drop_table('chegadas')
