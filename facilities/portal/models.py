"""A cobrança do cliente (Fase 9B, F9-2).

O cliente escolhe a data (no mínimo 24 h à frente), a coordenação do contrato
responde e SÓ o cliente encerra: confirma que ficou bom ou reabre, com uma
data nova. Toda mudança vira um evento na trilha, e o cliente vê a trilha
inteira (o nome de quem respondeu aparece como "Coordenação").

    aberta ──► respondida ──► fechada
       ▲            │
       └─(reaberta)─┘

Tabela própria, e não a ``DiarioTarefaTurno`` da Passagem: aquela exige área,
data e turno, e é código herdado do Intelligence que precisa continuar igual
ao de lá.
"""
from datetime import datetime

from facilities.extensions import db

ABERTA = 'aberta'
RESPONDIDA = 'respondida'
FECHADA = 'fechada'
STATUS = {ABERTA: 'Aguardando a coordenação', RESPONDIDA: 'Respondida — confirme ou reabra',
          FECHADA: 'Encerrada'}

EVENTO_ABERTA = 'aberta'
EVENTO_RESPOSTA = 'resposta'
EVENTO_CONFIRMADA = 'confirmada'
EVENTO_REABERTA = 'reaberta'
EVENTOS = {EVENTO_ABERTA: 'Cobrança aberta', EVENTO_RESPOSTA: 'Resposta da coordenação',
           EVENTO_CONFIRMADA: 'Confirmada pelo cliente', EVENTO_REABERTA: 'Reaberta pelo cliente'}


class Cobranca(db.Model):
    __tablename__ = 'cobrancas'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    titulo = db.Column(db.String(200), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    # O fim do dia escolhido pelo cliente, em UTC. Reabrir troca o prazo.
    prazo = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=ABERTA, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    respondida_em = db.Column(db.DateTime, nullable=True)
    fechada_em = db.Column(db.DateTime, nullable=True)
    reaberturas = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    local = db.relationship('Client')
    autor = db.relationship('User')
    eventos = db.relationship('CobrancaEvento', backref='cobranca', order_by='CobrancaEvento.id')

    @property
    def numero(self):
        return f'CB-{self.id:05d}' if self.id else 'CB-nova'

    @property
    def status_rotulo(self):
        return STATUS.get(self.status, self.status)

    def atrasada(self, agora=None):
        return self.status == ABERTA and (agora or datetime.utcnow()) > self.prazo


class CobrancaEvento(db.Model):
    """Um passo da trilha — o cliente vê todos."""
    __tablename__ = 'cobranca_eventos'
    id = db.Column(db.Integer, primary_key=True)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    texto = db.Column(db.Text)
    # O prazo que valia depois deste passo (abrir e reabrir mudam o prazo).
    prazo = db.Column(db.DateTime, nullable=True)
    autor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                         nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    autor = db.relationship('User')

    @property
    def tipo_rotulo(self):
        return EVENTOS.get(self.tipo, self.tipo)


# Filhos antes dos pais (FK) — a limpeza entre testes usa esta ordem.
MODELOS_EM_ORDEM_DE_LIMPEZA = (CobrancaEvento, Cobranca)
