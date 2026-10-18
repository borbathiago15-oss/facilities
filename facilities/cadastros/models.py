"""A estrutura de um cliente, do grupo até o ponto com QR.

    Empresa (do Grupo Trino)
    └─ Contratante — na tela, "Cliente" (com gerente e centro de custo pai)
       └─ Local — a tabela ``clients`` de sempre (com estado e subcentro)
          └─ Setor
             └─ Ambiente
                ├─ Equipamento
                └─ Ponto (com QR)

Por que ``Contratante`` e não ``Cliente``: a tabela ``clients`` (o LOCAL) já
se chama "cliente" em inglês e o nome não muda (regra do projeto: nomes
herdados do Trino). Dois "clientes" no código seriam um erro esperando para
acontecer. Na tela, só existe "Cliente".

Nada aqui se apaga: o que tem histórico é DESATIVADO. As chaves estrangeiras
são ``RESTRICT``: o banco recusa apagar um setor que ainda tem ambiente.

O QR do ponto é um código ALEATÓRIO (``secrets.token_urlsafe``), não o id:
o QR vai estar colado na parede e, na Fase 4B, abre o formulário público de
ocorrência sem login — com o id em sequência, quem lê um QR adivinha todos os
outros. Depois de criado, o código não muda (``_qr_imutavel``): a etiqueta
impressa continua valendo para sempre.
"""
import secrets
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.orm.base import NEVER_SET, NO_VALUE

from facilities.extensions import db

# ── Os níveis, para a trilha e as telas ───────────────────────────────────
ENTIDADES = {
    'empresa': 'Empresa',
    'estado': 'Estado',
    'contratante': 'Cliente',
    'local': 'Local',
    'setor': 'Setor',
    'ambiente': 'Ambiente',
    'equipamento': 'Equipamento',
    'ponto': 'Ponto',
}

ACOES = {
    'criado': 'Cadastrado',
    'alterado': 'Alterado',
    'desativado': 'Desativado',
    'reativado': 'Reativado',
    'movido': 'Movido',
}

# As 27 unidades da federação. Lista fixa, carregada pela migração: o gestor
# só ativa as que usa (decisão de 17/10/2026).
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

TAMANHO_CODIGO_QR = 16   # bytes de aleatoriedade → 22 caracteres na URL


def novo_codigo_qr():
    return secrets.token_urlsafe(TAMANHO_CODIGO_QR)


class Empresa(db.Model):
    """Uma empresa do Grupo Trino (a que tem o contrato com o cliente)."""
    __tablename__ = 'empresas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    cnpj = db.Column(db.String(18))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Estado(db.Model):
    __tablename__ = 'estados'
    id = db.Column(db.Integer, primary_key=True)
    sigla = db.Column(db.String(2), nullable=False, unique=True)
    nome = db.Column(db.String(40), nullable=False)
    # Só os ativos aparecem na escolha do local.
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def rotulo(self):
        return f'{self.nome} ({self.sigla})'


class Contratante(db.Model):
    """Na tela, o CLIENTE: quem contrata (ex.: Grupo GL), com vários locais."""
    __tablename__ = 'contratantes'
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id', ondelete='RESTRICT'),
                           nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    # Centro de custo PAI; cada local guarda o seu subcentro (clients.cost_center).
    centro_custo = db.Column(db.String(50))
    # O gerente responsável pelo cliente (D43: o gerente é do cliente, não do estado).
    gerente_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Prazo de atendimento da ocorrência do QR público, em minutos, por tipo
    # (Q2: configurável por cliente; sem valor, a ocorrência fica sem prazo).
    prazos_ocorrencia_json = db.Column(db.Text)
    # Régua de prazo dos chamados deste cliente, em horas por prioridade (D9).
    # Vazio = a régua padrão (urgente 4 h, alta 24 h, média 72 h, baixa 7 dias).
    prazos_chamado_json = db.Column(db.Text)

    empresa = db.relationship('Empresa')
    gerente = db.relationship('User', foreign_keys=[gerente_id])

    __table_args__ = (
        db.UniqueConstraint('empresa_id', 'nome', name='uq_contratantes_empresa_nome'),
    )


class Setor(db.Model):
    __tablename__ = 'setores'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')

    __table_args__ = (db.UniqueConstraint('client_id', 'nome', name='uq_setores_local_nome'),)


class Ambiente(db.Model):
    """Um espaço do setor: "Banheiro masculino 2º andar", "Copa", "Doca 3"."""
    __tablename__ = 'ambientes'
    id = db.Column(db.Integer, primary_key=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    # Repetido do setor de propósito: a carteira (``require_client``) filtra
    # por local sem precisar subir a árvore. ``servico`` mantém os dois iguais.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.String(300))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    setor = db.relationship('Setor', backref=db.backref('ambientes', order_by='Ambiente.nome'))

    __table_args__ = (db.UniqueConstraint('setor_id', 'nome', name='uq_ambientes_setor_nome'),)


class Equipamento(db.Model):
    __tablename__ = 'equipamentos'
    id = db.Column(db.Integer, primary_key=True)
    ambiente_id = db.Column(db.Integer, db.ForeignKey('ambientes.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    patrimonio = db.Column(db.String(50))
    fabricante = db.Column(db.String(80))
    modelo = db.Column(db.String(80))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ambiente = db.relationship('Ambiente', backref=db.backref(
        'equipamentos', order_by='Equipamento.nome'))


class PontoInspecao(db.Model):
    """O lugar com QR: onde a pessoa lê o código e faz o checklist."""
    __tablename__ = 'pontos_inspecao'
    id = db.Column(db.Integer, primary_key=True)
    ambiente_id = db.Column(db.Integer, db.ForeignKey('ambientes.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    # Opcional: o ponto pode ser um equipamento (o QR colado no ar-condicionado).
    equipamento_id = db.Column(db.Integer,
                               db.ForeignKey('equipamentos.id', ondelete='RESTRICT'),
                               nullable=True, index=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.String(300))
    codigo_qr = db.Column(db.String(32), nullable=False, unique=True, default=novo_codigo_qr)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ambiente = db.relationship('Ambiente', backref=db.backref(
        'pontos', order_by='PontoInspecao.nome'))
    equipamento = db.relationship('Equipamento')


@event.listens_for(PontoInspecao.codigo_qr, 'set')
def _qr_imutavel(alvo, valor, antigo, _iniciador):
    """O código do QR não muda depois de gravado: a etiqueta já está na parede."""
    if antigo in (NO_VALUE, NEVER_SET, None) or antigo == valor:
        return valor
    if alvo.id is not None:
        raise ValueError('O código do QR de um ponto não pode ser alterado.')
    return valor


class CadastroEvento(db.Model):
    """A trilha dos cadastros: quem mudou o quê, quando, de que para quê.

    Só se ACRESCENTA linha: nenhuma rota edita nem apaga evento.
    """
    __tablename__ = 'cadastro_eventos'
    id = db.Column(db.Integer, primary_key=True)
    entidade = db.Column(db.String(20), nullable=False)
    entidade_id = db.Column(db.Integer, nullable=False)
    # O local do registro (quando houver): a trilha de um local sai num filtro só.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=True, index=True)
    acao = db.Column(db.String(20), nullable=False)
    antes_json = db.Column(db.Text)
    depois_json = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    autor = db.relationship('User')

    __table_args__ = (
        db.Index('ix_cadastro_eventos_entidade', 'entidade', 'entidade_id'),
    )


# Ordem segura para limpar nos testes (filho antes do pai).
MODELOS_EM_ORDEM_DE_LIMPEZA = (CadastroEvento, PontoInspecao, Equipamento, Ambiente,
                               Setor, Contratante, Empresa)
