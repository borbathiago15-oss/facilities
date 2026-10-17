"""Chamados / ordens de serviço — a manutenção do dia a dia.

Um chamado nasce de quem viu o problema (o encarregado da limpeza que achou a
torneira vazando, o porteiro que viu a lâmpada queimada) e termina com quem o
pediu confirmando que ficou bom. No meio, o gestor atribui a um técnico, o
técnico atende, pode ficar aguardando peça ou terceiro, e resolve.

    aberto ──► em_atendimento ──► resolvido ──► fechado
       │            │   ▲             │
       │            ▼   │             └─(não ficou bom)─► em_atendimento
       │        aguardando
       └──────────────────────► cancelado (só gestor/administrador)

O PRAZO sai da prioridade no momento da abertura (``PRAZO_POR_PRIORIDADE``) e
fica gravado: mudar a régua amanhã não reescreve o prazo de quem já abriu.
"Atrasado" é ``agora > prazo`` com o chamado ainda nas mãos da operação —
resolvido aguardando confirmação já não conta, porque o técnico já entregou.

Toda mudança vira um EVENTO na trilha (quem, quando, o quê). A trilha é o
histórico que encerra discussão: "abriu às 8h, o técnico pegou às 9h, ficou
aguardando a peça até as 14h, resolveu às 15h".
"""
from datetime import datetime, timedelta

from facilities.extensions import db

# ── A régua ─────────────────────────────────────────────────────────────

PRIORIDADES = {
    'urgente': 'Urgente',
    'alta': 'Alta',
    'media': 'Média',
    'baixa': 'Baixa',
}
# Do mais urgente para o menos: é a ordem das listas.
ORDEM_DA_PRIORIDADE = {'urgente': 0, 'alta': 1, 'media': 2, 'baixa': 3}
PRAZO_POR_PRIORIDADE = {
    'urgente': timedelta(hours=4),
    'alta': timedelta(hours=24),
    'media': timedelta(hours=72),
    'baixa': timedelta(days=7),
}

CATEGORIAS = {
    'eletrica': 'Elétrica',
    'hidraulica': 'Hidráulica',
    'ar_condicionado': 'Ar-condicionado',
    'civil': 'Civil / alvenaria',
    'marcenaria': 'Marcenaria / serralheria',
    'limpeza': 'Limpeza',
    'seguranca': 'Segurança / acesso',
    'equipamento': 'Equipamento',
    'outro': 'Outro',
}

ABERTO = 'aberto'
EM_ATENDIMENTO = 'em_atendimento'
AGUARDANDO = 'aguardando'
RESOLVIDO = 'resolvido'
FECHADO = 'fechado'
CANCELADO = 'cancelado'
STATUS = {
    ABERTO: 'Aberto',
    EM_ATENDIMENTO: 'Em atendimento',
    AGUARDANDO: 'Aguardando',
    RESOLVIDO: 'Resolvido — aguardando confirmação',
    FECHADO: 'Fechado',
    CANCELADO: 'Cancelado',
}
# Ainda nas mãos da operação: conta para prazo e para "em aberto".
STATUS_EM_ABERTO = (ABERTO, EM_ATENDIMENTO, AGUARDANDO)
STATUS_ENCERRADOS = (FECHADO, CANCELADO)

ORIGEM_MANUAL = 'manual'
ORIGEM_OCORRENCIA = 'ocorrencia'
ORIGEM_PENDENCIA = 'pendencia'


class Chamado(db.Model):
    __tablename__ = 'chamados'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    # A área/serviço do contrato (limpeza, portaria, manutenção…): as mesmas
    # áreas da Passagem de Turno.
    area_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_areas.id'),
                        nullable=True, index=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    local = db.Column(db.String(200))
    categoria = db.Column(db.String(30), nullable=False, default='outro')
    prioridade = db.Column(db.String(10), nullable=False, default='media')
    status = db.Column(db.String(20), nullable=False, default=ABERTO, index=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    responsavel_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    prazo = db.Column(db.DateTime, nullable=True)          # UTC
    solucao = db.Column(db.Text)
    motivo_espera = db.Column(db.String(300))
    origem = db.Column(db.String(20), nullable=False, default=ORIGEM_MANUAL)
    origem_id = db.Column(db.Integer, nullable=True)
    aberto_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    iniciado_em = db.Column(db.DateTime, nullable=True)
    resolvido_em = db.Column(db.DateTime, nullable=True)
    fechado_em = db.Column(db.DateTime, nullable=True)
    cancelado_em = db.Column(db.DateTime, nullable=True)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # A busca por origem: o botão "abrir chamado" fica numa lista relida
        # todo dia, e o segundo clique tem de achar o chamado do primeiro.
        db.Index('ix_chamados_origem', 'origem', 'origem_id'),
    )

    contrato = db.relationship('Client')
    area = db.relationship('DiarioArea')
    solicitante = db.relationship('User', foreign_keys=[solicitante_id])
    responsavel = db.relationship('User', foreign_keys=[responsavel_id])
    eventos = db.relationship('ChamadoEvento', backref='chamado', lazy='select',
                              order_by='ChamadoEvento.id', cascade='all, delete-orphan')
    anexos = db.relationship('ChamadoAnexo', backref='chamado', lazy='select',
                             order_by='ChamadoAnexo.id', cascade='all, delete-orphan')

    @property
    def numero(self):
        return f'OS-{self.id:05d}' if self.id else 'OS-novo'

    @property
    def em_aberto(self):
        return self.status in STATUS_EM_ABERTO

    def atrasado(self, agora=None):
        agora = agora or datetime.utcnow()
        return bool(self.em_aberto and self.prazo and agora > self.prazo)

    @property
    def status_rotulo(self):
        return STATUS.get(self.status, self.status)

    @property
    def prioridade_rotulo(self):
        return PRIORIDADES.get(self.prioridade, self.prioridade)

    @property
    def categoria_rotulo(self):
        return CATEGORIAS.get(self.categoria, self.categoria)


class ChamadoEvento(db.Model):
    """Um passo da trilha do chamado."""
    __tablename__ = 'chamado_eventos'
    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    tipo = db.Column(db.String(30), nullable=False)
    texto = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    autor = db.relationship('User')


class ChamadoAnexo(db.Model):
    """Foto do problema (antes) e do serviço feito (depois), ou um PDF."""
    __tablename__ = 'chamado_anexos'
    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    nome = db.Column(db.String(200), nullable=False)
    mime = db.Column(db.String(100))
    tamanho = db.Column(db.Integer)
    storage_key = db.Column(db.String(300), nullable=False)
    momento = db.Column(db.String(10), nullable=False, default='antes')   # antes | depois
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Filhos antes dos pais (FK) — a limpeza entre testes usa esta ordem.
MODELOS_EM_ORDEM_DE_LIMPEZA = (ChamadoAnexo, ChamadoEvento, Chamado)
