"""Estrutura inicial do Trino Facilities.

O banco nasce VAZIO (decisão do projeto: começar do zero, sem migrar o
histórico do Trino Intelligence). Esta revisão cria as 16 tabelas de uma vez:

* núcleo — users, clients (contratos), user_clients, notifications;
* passagem de turno — as 9 tabelas diario_operacional_* (mesmos nomes do
  Trino, de onde o módulo veio), com os índices compostos que lá só
  existiam nas migrações;
* chamados — chamados, chamado_eventos, chamado_anexos.

Gerada contra um Postgres 16 e conferida com upgrade → downgrade → upgrade.
Como é a primeira revisão e o banco está vazio, o downgrade apaga tabelas
VAZIAS; daqui para a frente, migração que apaga ou reescreve dado precisa de
quarentena (regra herdada do Trino Intelligence).

Revision ID: c6b7dccc9cae
Revises: 
Create Date: 2026-10-17 11:28:03.818182

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6b7dccc9cae'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('permissions_json', sa.Text(), nullable=True),
    sa.Column('all_clients', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('lockout_until', sa.DateTime(), nullable=True),
    sa.Column('session_epoch', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_is_deleted'), ['is_deleted'], unique=False)

    op.create_table('clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('cost_center', sa.String(length=50), nullable=True),
    sa.Column('endereco', sa.String(length=255), nullable=True),
    sa.Column('responsible_user_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['responsible_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clients_is_deleted'), ['is_deleted'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('notification_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('link', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)

    op.create_table('diario_operacional_areas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_areas', schema=None) as batch_op:
        batch_op.create_index('ix_diario_area_cliente_nome', ['client_id', 'nome'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_areas_ativo'), ['ativo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_areas_client_id'), ['client_id'], unique=False)

    op.create_table('user_clients',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'client_id')
    )
    op.create_table('chamados',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=200), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('local', sa.String(length=200), nullable=True),
    sa.Column('categoria', sa.String(length=30), nullable=False),
    sa.Column('prioridade', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('solicitante_id', sa.Integer(), nullable=False),
    sa.Column('responsavel_id', sa.Integer(), nullable=True),
    sa.Column('prazo', sa.DateTime(), nullable=True),
    sa.Column('solucao', sa.Text(), nullable=True),
    sa.Column('motivo_espera', sa.String(length=300), nullable=True),
    sa.Column('origem', sa.String(length=20), nullable=False),
    sa.Column('origem_id', sa.Integer(), nullable=True),
    sa.Column('aberto_em', sa.DateTime(), nullable=False),
    sa.Column('iniciado_em', sa.DateTime(), nullable=True),
    sa.Column('resolvido_em', sa.DateTime(), nullable=True),
    sa.Column('fechado_em', sa.DateTime(), nullable=True),
    sa.Column('cancelado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['area_id'], ['diario_operacional_areas.id'], ),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['responsavel_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['solicitante_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chamados', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chamados_aberto_em'), ['aberto_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_chamados_area_id'), ['area_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chamados_client_id'), ['client_id'], unique=False)
        # Uma ocorrência vira UM chamado vivo, garantido pelo banco (dois
        # cliques simultâneos abriam duas OS). Parcial: o manual (origem_id
        # NULL) e o cancelado ficam fora. O texto é o mesmo de
        # ``chamados.models.CONDICAO_ORIGEM_VIVA``.
        batch_op.create_index(
            'uq_chamados_origem_viva', ['origem', 'origem_id'], unique=True,
            postgresql_where=sa.text("origem_id IS NOT NULL AND status <> 'cancelado'"),
            sqlite_where=sa.text("origem_id IS NOT NULL AND status <> 'cancelado'"))
        batch_op.create_index(batch_op.f('ix_chamados_responsavel_id'), ['responsavel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chamados_status'), ['status'], unique=False)

    op.create_table('diario_operacional_configuracoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=True),
    sa.Column('nome', sa.String(length=150), nullable=False),
    sa.Column('descricao', sa.String(length=500), nullable=True),
    sa.Column('turnos_json', sa.Text(), nullable=False),
    sa.Column('campos_json', sa.Text(), nullable=False),
    sa.Column('atividades_json', sa.Text(), nullable=False),
    sa.Column('tipos_ocorrencia_json', sa.Text(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['diario_operacional_areas.id'], ),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_configuracoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_configuracoes_area_id'), ['area_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_configuracoes_ativo'), ['ativo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_configuracoes_client_id'), ['client_id'], unique=False)

    op.create_table('chamado_anexos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chamado_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('mime', sa.String(length=100), nullable=True),
    sa.Column('tamanho', sa.Integer(), nullable=True),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('momento', sa.String(length=10), nullable=False),
    sa.Column('uploaded_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['chamado_id'], ['chamados.id'], ),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chamado_anexos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chamado_anexos_chamado_id'), ['chamado_id'], unique=False)

    op.create_table('chamado_eventos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chamado_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('texto', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['chamado_id'], ['chamados.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chamado_eventos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chamado_eventos_chamado_id'), ['chamado_id'], unique=False)

    op.create_table('diario_operacional_turnos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('configuracao_id', sa.Integer(), nullable=False),
    sa.Column('data_turno', sa.Date(), nullable=False),
    sa.Column('turno', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('dados_json', sa.Text(), nullable=False),
    sa.Column('observacao', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['configuracao_id'], ['diario_operacional_configuracoes.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_turnos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_turnos_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_turnos_configuracao_id'), ['configuracao_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_turnos_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_turnos_data_turno'), ['data_turno'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_turnos_status'), ['status'], unique=False)
        batch_op.create_index('ix_diario_turnos_cliente_data', ['client_id', 'data_turno'], unique=False)

    op.create_table('diario_operacional_anexos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=False),
    sa.Column('atividade_codigo', sa.String(length=120), nullable=True),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('mime', sa.String(length=120), nullable=True),
    sa.Column('tamanho', sa.Integer(), nullable=True),
    sa.Column('uploaded_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['turno_id'], ['diario_operacional_turnos.id'], ),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_anexos', schema=None) as batch_op:
        batch_op.create_index('ix_diario_anexo_turno_ativ', ['turno_id', 'atividade_codigo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_anexos_atividade_codigo'), ['atividade_codigo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_anexos_turno_id'), ['turno_id'], unique=False)

    op.create_table('diario_operacional_ocorrencias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=80), nullable=False),
    sa.Column('referencia', sa.String(length=120), nullable=True),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('gravidade', sa.String(length=20), server_default='normal', nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['turno_id'], ['diario_operacional_turnos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_ocorrencias', schema=None) as batch_op:
        batch_op.create_index('ix_diario_ocor_cliente_criacao', ['client_id', 'created_at'], unique=False)
        batch_op.create_index('ix_diario_ocorrencia_cliente_gravidade', ['client_id', 'gravidade'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_ocorrencias_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_ocorrencias_gravidade'), ['gravidade'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_ocorrencias_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_ocorrencias_tipo'), ['tipo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_ocorrencias_turno_id'), ['turno_id'], unique=False)

    op.create_table('diario_operacional_pendencias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=200), nullable=False),
    sa.Column('referencia', sa.String(length=120), nullable=True),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('prioridade', sa.String(length=20), nullable=False),
    sa.Column('assigned_to', sa.Integer(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.Column('resolucao', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['turno_id'], ['diario_operacional_turnos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_pendencias', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencias_assigned_to'), ['assigned_to'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencias_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencias_referencia'), ['referencia'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencias_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencias_turno_id'), ['turno_id'], unique=False)
        batch_op.create_index('ix_diario_pend_cliente_criacao', ['client_id', 'created_at'], unique=False)

    op.create_table('diario_operacional_turno_correcoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.Column('campos', sa.String(length=200), nullable=True),
    sa.Column('antes_json', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['turno_id'], ['diario_operacional_turnos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_turno_correcoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_turno_correcoes_turno_id'), ['turno_id'], unique=False)

    op.create_table('diario_operacional_pendencia_eventos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pendencia_id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('texto', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pendencia_id'], ['diario_operacional_pendencias.id'], ),
    sa.ForeignKeyConstraint(['turno_id'], ['diario_operacional_turnos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_pendencia_eventos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencia_eventos_pendencia_id'), ['pendencia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencia_eventos_tipo'), ['tipo'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_pendencia_eventos_turno_id'), ['turno_id'], unique=False)
        batch_op.create_index('ix_diario_pend_evento_pend_data', ['pendencia_id', 'created_at'], unique=False)

    op.create_table('diario_operacional_tarefas_turno',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('configuracao_id', sa.Integer(), nullable=False),
    sa.Column('data_turno', sa.Date(), nullable=False),
    sa.Column('turno', sa.String(length=50), nullable=False),
    sa.Column('titulo', sa.String(length=300), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('forma_resposta', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('resposta', sa.Text(), nullable=True),
    sa.Column('pendencia_id', sa.Integer(), nullable=True),
    sa.Column('criada_por', sa.Integer(), nullable=False),
    sa.Column('respondida_por', sa.Integer(), nullable=True),
    sa.Column('respondida_em', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['configuracao_id'], ['diario_operacional_configuracoes.id'], ),
    sa.ForeignKeyConstraint(['criada_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pendencia_id'], ['diario_operacional_pendencias.id'], ),
    sa.ForeignKeyConstraint(['respondida_por'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('diario_operacional_tarefas_turno', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diario_operacional_tarefas_turno_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_tarefas_turno_configuracao_id'), ['configuracao_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_tarefas_turno_data_turno'), ['data_turno'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_tarefas_turno_pendencia_id'), ['pendencia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diario_operacional_tarefas_turno_status'), ['status'], unique=False)
        batch_op.create_index('ix_diario_tarefa_turno_alvo', ['client_id', 'configuracao_id', 'data_turno', 'turno'], unique=False)



def downgrade():
    with op.batch_alter_table('diario_operacional_tarefas_turno', schema=None) as batch_op:
        batch_op.drop_index('ix_diario_tarefa_turno_alvo')
        batch_op.drop_index(batch_op.f('ix_diario_operacional_tarefas_turno_status'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_tarefas_turno_pendencia_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_tarefas_turno_data_turno'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_tarefas_turno_configuracao_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_tarefas_turno_client_id'))

    op.drop_table('diario_operacional_tarefas_turno')
    with op.batch_alter_table('diario_operacional_pendencia_eventos', schema=None) as batch_op:
        batch_op.drop_index('ix_diario_pend_evento_pend_data')
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencia_eventos_turno_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencia_eventos_tipo'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencia_eventos_pendencia_id'))

    op.drop_table('diario_operacional_pendencia_eventos')
    with op.batch_alter_table('diario_operacional_turno_correcoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turno_correcoes_turno_id'))

    op.drop_table('diario_operacional_turno_correcoes')
    with op.batch_alter_table('diario_operacional_pendencias', schema=None) as batch_op:
        batch_op.drop_index('ix_diario_pend_cliente_criacao')
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencias_turno_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencias_status'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencias_referencia'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencias_client_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_pendencias_assigned_to'))

    op.drop_table('diario_operacional_pendencias')
    with op.batch_alter_table('diario_operacional_ocorrencias', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_diario_operacional_ocorrencias_turno_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_ocorrencias_tipo'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_ocorrencias_status'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_ocorrencias_gravidade'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_ocorrencias_client_id'))
        batch_op.drop_index('ix_diario_ocorrencia_cliente_gravidade')
        batch_op.drop_index('ix_diario_ocor_cliente_criacao')

    op.drop_table('diario_operacional_ocorrencias')
    with op.batch_alter_table('diario_operacional_anexos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_diario_operacional_anexos_turno_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_anexos_atividade_codigo'))
        batch_op.drop_index('ix_diario_anexo_turno_ativ')

    op.drop_table('diario_operacional_anexos')
    with op.batch_alter_table('diario_operacional_turnos', schema=None) as batch_op:
        batch_op.drop_index('ix_diario_turnos_cliente_data')
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turnos_status'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turnos_data_turno'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turnos_created_by'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turnos_configuracao_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_turnos_client_id'))

    op.drop_table('diario_operacional_turnos')
    with op.batch_alter_table('chamado_eventos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chamado_eventos_chamado_id'))

    op.drop_table('chamado_eventos')
    with op.batch_alter_table('chamado_anexos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chamado_anexos_chamado_id'))

    op.drop_table('chamado_anexos')
    with op.batch_alter_table('diario_operacional_configuracoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_diario_operacional_configuracoes_client_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_configuracoes_ativo'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_configuracoes_area_id'))

    op.drop_table('diario_operacional_configuracoes')
    with op.batch_alter_table('chamados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chamados_status'))
        batch_op.drop_index(batch_op.f('ix_chamados_responsavel_id'))
        batch_op.drop_index('uq_chamados_origem_viva')
        batch_op.drop_index(batch_op.f('ix_chamados_client_id'))
        batch_op.drop_index(batch_op.f('ix_chamados_area_id'))
        batch_op.drop_index(batch_op.f('ix_chamados_aberto_em'))

    op.drop_table('chamados')
    op.drop_table('user_clients')
    with op.batch_alter_table('diario_operacional_areas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_diario_operacional_areas_client_id'))
        batch_op.drop_index(batch_op.f('ix_diario_operacional_areas_ativo'))
        batch_op.drop_index('ix_diario_area_cliente_nome')

    op.drop_table('diario_operacional_areas')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))
        batch_op.drop_index(batch_op.f('ix_notifications_created_at'))

    op.drop_table('notifications')
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clients_is_deleted'))

    op.drop_table('clients')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_is_deleted'))

    op.drop_table('users')
