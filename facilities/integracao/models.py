"""Chaves de servidor da integração e o registro de cada acesso (Fase 8).

* A chave aparece UMA vez, na criação. O banco guarda só o SHA-256 dela e
  um prefixo curto para reconhecê-la na lista e no registro.
* Cada chave vê só os locais escolhidos (ou todos, se marcada assim).
* O registro de acesso guarda quando, qual chave, qual rota e quais
  parâmetros — nunca a chave.
"""
from datetime import datetime

from facilities.extensions import db

# Com ``id`` próprio: a quarentena das migrações copia e devolve pelo id.
chave_locais = db.Table(
    'integracao_chave_locais',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('chave_id', db.Integer, db.ForeignKey('integracao_chaves.id', ondelete='CASCADE'),
              nullable=False, index=True),
    db.Column('client_id', db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
              nullable=False),
    db.UniqueConstraint('chave_id', 'client_id', name='uq_integracao_chave_local'),
)


class IntegracaoChave(db.Model):
    __tablename__ = 'integracao_chaves'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    prefixo = db.Column(db.String(12), nullable=False, unique=True)
    hash_chave = db.Column(db.String(64), nullable=False, unique=True)
    todos_os_locais = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    criada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=False)
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revogada_em = db.Column(db.DateTime)
    ultimo_uso_em = db.Column(db.DateTime)

    locais = db.relationship('Client', secondary=chave_locais, order_by='Client.name')
    autor = db.relationship('User')

    def client_ids(self):
        """``None`` = todos os locais."""
        return None if self.todos_os_locais else [c.id for c in self.locais]


class IntegracaoAcesso(db.Model):
    __tablename__ = 'integracao_acessos'
    id = db.Column(db.Integer, primary_key=True)
    chave_id = db.Column(db.Integer, db.ForeignKey('integracao_chaves.id', ondelete='RESTRICT'),
                         nullable=True, index=True)       # nulo = chave inválida
    em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    rota = db.Column(db.String(80), nullable=False)
    parametros = db.Column(db.String(300))
    status = db.Column(db.Integer, nullable=False)
    itens = db.Column(db.Integer)
    ip = db.Column(db.String(45))

    chave = db.relationship('IntegracaoChave')


MODELOS_EM_ORDEM_DE_LIMPEZA = (IntegracaoAcesso, IntegracaoChave)
