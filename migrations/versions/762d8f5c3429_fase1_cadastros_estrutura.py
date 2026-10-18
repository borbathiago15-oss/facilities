"""Fase 1 — cadastros e estrutura: empresa, estado, cliente, setor, ambiente,
equipamento, ponto com QR e a trilha dos cadastros.

O que muda no schema (só acrescenta):

* 8 tabelas novas: ``empresas``, ``estados`` (já com as 27 UFs, desativadas),
  ``contratantes`` (o "Cliente" da tela), ``setores``, ``ambientes``,
  ``equipamentos``, ``pontos_inspecao`` e ``cadastro_eventos``;
* 2 colunas novas e OPCIONAIS em ``clients`` (o local): ``contratante_id`` e
  ``estado_id``. Nenhuma linha existente é reescrita; local sem cliente
  continua como antes.

A volta (``downgrade``) apagaria o que foi cadastrado nas tabelas novas e os
vínculos dos locais. Por isso ela põe tudo em quarentena antes
(``_quarentena_762d8f5c3429_<tabela>``), e a ida seguinte devolve: ida → volta
→ ida não perde cadastro nenhum. A quarentena fica no banco (limpeza é
decisão humana).

Revision ID: 762d8f5c3429
Revises: c6b7dccc9cae
Create Date: 2026-10-17 18:00:00

"""
from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import (nome_quarentena, quarentenar_tabela,
                                        restaurar_tabela)

revision = '762d8f5c3429'
down_revision = 'c6b7dccc9cae'
branch_labels = None
depends_on = None

# Pai antes do filho: é a ordem de criar e de devolver da quarentena.
TABELAS = ('empresas', 'estados', 'contratantes', 'setores', 'ambientes',
           'equipamentos', 'pontos_inspecao', 'cadastro_eventos')

UFS = (
    ('AC', 'Acre'), ('AL', 'Alagoas'), ('AP', 'Amapá'), ('AM', 'Amazonas'),
    ('BA', 'Bahia'), ('CE', 'Ceará'), ('DF', 'Distrito Federal'),
    ('ES', 'Espírito Santo'), ('GO', 'Goiás'), ('MA', 'Maranhão'),
    ('MT', 'Mato Grosso'), ('MS', 'Mato Grosso do Sul'), ('MG', 'Minas Gerais'),
    ('PA', 'Pará'), ('PB', 'Paraíba'), ('PR', 'Paraná'), ('PE', 'Pernambuco'),
    ('PI', 'Piauí'), ('RJ', 'Rio de Janeiro'), ('RN', 'Rio Grande do Norte'),
    ('RS', 'Rio Grande do Sul'), ('RO', 'Rondônia'), ('RR', 'Roraima'),
    ('SC', 'Santa Catarina'), ('SP', 'São Paulo'), ('SE', 'Sergipe'),
    ('TO', 'Tocantins'),
)


def _tem_tabela(nome):
    return nome in sa.inspect(op.get_bind()).get_table_names()


def _tem_coluna(tabela, coluna):
    return coluna in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def upgrade():
    op.create_table(
        'empresas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('cnpj', sa.String(length=18), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome'),
    )
    op.create_table(
        'estados',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sigla', sa.String(length=2), nullable=False),
        sa.Column('nome', sa.String(length=40), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sigla'),
    )
    op.create_table(
        'contratantes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('centro_custo', sa.String(length=50), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['gerente_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'nome', name='uq_contratantes_empresa_nome'),
    )
    with op.batch_alter_table('contratantes', schema=None) as b:
        b.create_index(b.f('ix_contratantes_empresa_id'), ['empresa_id'], unique=False)
        b.create_index(b.f('ix_contratantes_gerente_id'), ['gerente_id'], unique=False)

    op.create_table(
        'setores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', 'nome', name='uq_setores_local_nome'),
    )
    with op.batch_alter_table('setores', schema=None) as b:
        b.create_index(b.f('ix_setores_client_id'), ['client_id'], unique=False)

    op.create_table(
        'ambientes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setor_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('descricao', sa.String(length=300), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['setor_id'], ['setores.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('setor_id', 'nome', name='uq_ambientes_setor_nome'),
    )
    with op.batch_alter_table('ambientes', schema=None) as b:
        b.create_index(b.f('ix_ambientes_client_id'), ['client_id'], unique=False)
        b.create_index(b.f('ix_ambientes_setor_id'), ['setor_id'], unique=False)

    op.create_table(
        'equipamentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ambiente_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('patrimonio', sa.String(length=50), nullable=True),
        sa.Column('fabricante', sa.String(length=80), nullable=True),
        sa.Column('modelo', sa.String(length=80), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('equipamentos', schema=None) as b:
        b.create_index(b.f('ix_equipamentos_ambiente_id'), ['ambiente_id'], unique=False)
        b.create_index(b.f('ix_equipamentos_client_id'), ['client_id'], unique=False)

    op.create_table(
        'pontos_inspecao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ambiente_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('equipamento_id', sa.Integer(), nullable=True),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('descricao', sa.String(length=300), nullable=True),
        sa.Column('codigo_qr', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['equipamento_id'], ['equipamentos.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo_qr'),
    )
    with op.batch_alter_table('pontos_inspecao', schema=None) as b:
        b.create_index(b.f('ix_pontos_inspecao_ambiente_id'), ['ambiente_id'], unique=False)
        b.create_index(b.f('ix_pontos_inspecao_client_id'), ['client_id'], unique=False)
        b.create_index(b.f('ix_pontos_inspecao_equipamento_id'), ['equipamento_id'],
                       unique=False)

    op.create_table(
        'cadastro_eventos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entidade', sa.String(length=20), nullable=False),
        sa.Column('entidade_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('acao', sa.String(length=20), nullable=False),
        sa.Column('antes_json', sa.Text(), nullable=True),
        sa.Column('depois_json', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cadastro_eventos', schema=None) as b:
        b.create_index(b.f('ix_cadastro_eventos_client_id'), ['client_id'], unique=False)
        b.create_index(b.f('ix_cadastro_eventos_criado_em'), ['criado_em'], unique=False)
        b.create_index('ix_cadastro_eventos_entidade', ['entidade', 'entidade_id'],
                       unique=False)

    with op.batch_alter_table('clients', schema=None) as b:
        if not _tem_coluna('clients', 'contratante_id'):
            b.add_column(sa.Column('contratante_id', sa.Integer(), nullable=True))
            b.add_column(sa.Column('estado_id', sa.Integer(), nullable=True))
            b.create_index(b.f('ix_clients_contratante_id'), ['contratante_id'], unique=False)
            b.create_index(b.f('ix_clients_estado_id'), ['estado_id'], unique=False)
            b.create_foreign_key('fk_clients_contratante_id', 'contratantes',
                                 ['contratante_id'], ['id'], ondelete='RESTRICT')
            b.create_foreign_key('fk_clients_estado_id', 'estados',
                                 ['estado_id'], ['id'], ondelete='RESTRICT')

    # Uma volta anterior deixou cadastros na quarentena? Devolve, pai antes do filho.
    for tabela in TABELAS:
        restaurar_tabela(op, tabela, revision)
    bind = op.get_bind()
    q_clients = nome_quarentena('clients', revision)
    if _tem_tabela(q_clients):
        bind.execute(sa.text(
            f'UPDATE clients SET contratante_id = (SELECT q.contratante_id FROM {q_clients} q '
            f'WHERE q.id = clients.id), estado_id = (SELECT q.estado_id FROM {q_clients} q '
            f'WHERE q.id = clients.id) WHERE id IN (SELECT id FROM {q_clients})'))

    # As 27 UFs (as que ainda não voltaram da quarentena), desativadas.
    existentes = {r[0] for r in bind.execute(sa.text('SELECT sigla FROM estados'))}
    estados = sa.table('estados', sa.column('sigla', sa.String), sa.column('nome', sa.String),
                       sa.column('is_active', sa.Boolean))
    faltam = [{'sigla': s, 'nome': n, 'is_active': False} for s, n in UFS if s not in existentes]
    if faltam:
        op.bulk_insert(estados, faltam)


def downgrade():
    # Quarentena ANTES de apagar: o vínculo dos locais e cada tabela nova.
    quarentenar_tabela(op, 'clients', revision,
                       onde='contratante_id IS NOT NULL OR estado_id IS NOT NULL')
    for tabela in TABELAS:
        quarentenar_tabela(op, tabela, revision)

    with op.batch_alter_table('clients', schema=None) as b:
        b.drop_constraint('fk_clients_estado_id', type_='foreignkey')
        b.drop_constraint('fk_clients_contratante_id', type_='foreignkey')
        b.drop_index(b.f('ix_clients_estado_id'))
        b.drop_index(b.f('ix_clients_contratante_id'))
        b.drop_column('estado_id')
        b.drop_column('contratante_id')

    for tabela in reversed(TABELAS):
        op.drop_table(tabela)
