"""Arquivo das fotos antigas (decisão do dono, 01/11/2026).

O que muda no schema (só acrescenta 4 tabelas; nenhuma linha existente é
alterada, nenhuma tabela de foto muda):

* ``arquivo_fotos_ajustes``: uma linha só, o prazo em dias (padrão 60) que o
  administrador muda na tela, e quem mudou;
* ``arquivo_fotos_lotes``: cada arquivamento pedido pelo administrador (quem,
  quando começou e terminou, data de corte, destino, situação, contagens,
  bytes, último erro);
* ``fotos_arquivadas``: cada foto que foi para o arquivo (``storage_key``
  única, tabela e linha de origem, tamanho, SHA-256, quando, lote, quando
  saiu do armazenamento principal);
* ``arquivo_fotos_falhas``: a foto que não conseguiu ir (continua no
  principal), com o número de tentativas e o erro.

A volta guarda as linhas em quarentena; a ida seguinte devolve. Atenção: sem
estas tabelas, as fotos já arquivadas continuam abrindo (a leitura procura no
destino do arquivo), mas a tela perde o registro de onde cada uma está.

Revision ID: f3b8d1a6c2e4
Revises: e1a7c3f5b9d2
Create Date: 2026-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import quarentenar_tabela, restaurar_tabela


# revision identifiers, used by Alembic.
revision = 'f3b8d1a6c2e4'
down_revision = 'e1a7c3f5b9d2'
branch_labels = None
depends_on = None

# Na ordem de criação (pais antes dos filhos).
TABELAS = ('arquivo_fotos_ajustes', 'arquivo_fotos_lotes', 'fotos_arquivadas',
           'arquivo_fotos_falhas')


def upgrade():
    op.create_table('arquivo_fotos_ajustes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dias', sa.Integer(), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), nullable=False),
    sa.Column('atualizado_por', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['atualizado_por'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('arquivo_fotos_lotes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('iniciado_por', sa.Integer(), nullable=False),
    sa.Column('iniciado_em', sa.DateTime(), nullable=False),
    sa.Column('concluido_em', sa.DateTime(), nullable=True),
    sa.Column('dias', sa.Integer(), nullable=False),
    sa.Column('corte_em', sa.DateTime(), nullable=False),
    sa.Column('destino', sa.String(length=300), nullable=False),
    sa.Column('situacao', sa.String(length=30), nullable=False),
    sa.Column('previstas', sa.Integer(), nullable=False),
    sa.Column('arquivadas', sa.Integer(), nullable=False),
    sa.Column('bytes_arquivados', sa.BigInteger(), nullable=False),
    sa.Column('tentativas_com_erro', sa.Integer(), nullable=False),
    sa.Column('nao_arquivadas', sa.Integer(), nullable=False),
    sa.Column('ultimo_erro', sa.Text(), nullable=True),
    sa.Column('ultima_rodada_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['iniciado_por'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('arquivo_fotos_lotes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_arquivo_fotos_lotes_situacao'), ['situacao'],
                              unique=False)
    op.create_table('fotos_arquivadas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('origem', sa.String(length=40), nullable=False),
    sa.Column('origem_id', sa.Integer(), nullable=False),
    sa.Column('tamanho', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('arquivada_em', sa.DateTime(), nullable=False),
    sa.Column('lote_id', sa.Integer(), nullable=False),
    sa.Column('removida_do_principal_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['lote_id'], ['arquivo_fotos_lotes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    with op.batch_alter_table('fotos_arquivadas', schema=None) as batch_op:
        batch_op.create_index('ix_fotos_arquivadas_origem', ['origem', 'origem_id'],
                              unique=False)
        batch_op.create_index(batch_op.f('ix_fotos_arquivadas_lote_id'), ['lote_id'],
                              unique=False)
    op.create_table('arquivo_fotos_falhas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('origem', sa.String(length=40), nullable=False),
    sa.Column('origem_id', sa.Integer(), nullable=False),
    sa.Column('lote_id', sa.Integer(), nullable=False),
    sa.Column('tentativas', sa.Integer(), nullable=False),
    sa.Column('erro', sa.String(length=500), nullable=True),
    sa.Column('em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['lote_id'], ['arquivo_fotos_lotes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    with op.batch_alter_table('arquivo_fotos_falhas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_arquivo_fotos_falhas_lote_id'), ['lote_id'],
                              unique=False)

    for tabela in TABELAS:
        restaurar_tabela(op, tabela, revision)


def downgrade():
    for tabela in reversed(TABELAS):
        quarentenar_tabela(op, tabela, revision)
    with op.batch_alter_table('arquivo_fotos_falhas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_arquivo_fotos_falhas_lote_id'))
    op.drop_table('arquivo_fotos_falhas')
    with op.batch_alter_table('fotos_arquivadas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fotos_arquivadas_lote_id'))
        batch_op.drop_index('ix_fotos_arquivadas_origem')
    op.drop_table('fotos_arquivadas')
    with op.batch_alter_table('arquivo_fotos_lotes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_arquivo_fotos_lotes_situacao'))
    op.drop_table('arquivo_fotos_lotes')
    op.drop_table('arquivo_fotos_ajustes')
