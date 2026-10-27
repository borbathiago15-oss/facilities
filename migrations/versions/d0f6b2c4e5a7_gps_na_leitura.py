"""GPS na leitura do QR (decisões do dono, 27/10/2026).

O que muda no schema (só acrescenta; nenhuma linha existente é reescrita):

* ``clients``: ``latitude`` e ``longitude`` (NUMERIC 9,6), ``raio_gps_m``,
  ``posicao_marcada_em`` e ``posicao_marcada_por`` — a posição do local,
  marcada pela gestão no próprio local.
* ``execucoes`` e ``chegadas``: ``gps_situacao`` (no local / fora do local /
  sem GPS / local sem posição), ``gps_distancia_m`` e ``gps_precisao_m``. A
  coordenada da pessoa NÃO é guardada.

Todas opcionais. A volta guarda em quarentena os valores das colunas novas
(só das linhas que têm valor); a ida seguinte devolve.

Revision ID: d0f6b2c4e5a7
Revises: c9e5a1b3d4f6
Create Date: 2026-10-27 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import nome_quarentena, quarentenar_tabela


# revision identifiers, used by Alembic.
revision = 'd0f6b2c4e5a7'
down_revision = 'c9e5a1b3d4f6'
branch_labels = None
depends_on = None

GPS = ('gps_situacao', 'gps_distancia_m', 'gps_precisao_m')
# tabela → (colunas novas, filtro do que vale guardar na volta)
COLUNAS = {
    'clients': (('latitude', 'longitude', 'raio_gps_m', 'posicao_marcada_em',
                 'posicao_marcada_por'), 'latitude IS NOT NULL OR raio_gps_m IS NOT NULL'),
    'execucoes': (GPS, 'gps_situacao IS NOT NULL'),
    'chegadas': (GPS, 'gps_situacao IS NOT NULL'),
}


def _colunas_gps(batch_op):
    batch_op.add_column(sa.Column('gps_situacao', sa.String(length=20), nullable=True))
    batch_op.add_column(sa.Column('gps_distancia_m', sa.Integer(), nullable=True))
    batch_op.add_column(sa.Column('gps_precisao_m', sa.Integer(), nullable=True))


def upgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latitude', sa.Numeric(9, 6), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Numeric(9, 6), nullable=True))
        batch_op.add_column(sa.Column('raio_gps_m', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('posicao_marcada_em', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('posicao_marcada_por', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_clients_posicao_marcada_por_users', 'users',
                                    ['posicao_marcada_por'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('execucoes', schema=None) as batch_op:
        _colunas_gps(batch_op)
    with op.batch_alter_table('chegadas', schema=None) as batch_op:
        _colunas_gps(batch_op)

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

    for tabela in ('chegadas', 'execucoes'):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            for c in reversed(GPS):
                batch_op.drop_column(c)
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_constraint('fk_clients_posicao_marcada_por_users', type_='foreignkey')
        for c in ('posicao_marcada_por', 'posicao_marcada_em', 'raio_gps_m', 'longitude',
                  'latitude'):
            batch_op.drop_column(c)
