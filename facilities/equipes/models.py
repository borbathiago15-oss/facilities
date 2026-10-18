"""Equipe do posto (Fase 6).

    Funcionário (do local; com ou sem login) ──► Escala (posto + dias + período)
                                                     └─► Presença do dia (veio / faltou / atrasou)
                                                             └─► Cobertura (quem cobriu + motivo)

* O funcionário pode ter login (é o MESMO usuário do sistema, F6-1) ou não
  (a ASG que não usa o aplicativo também entra na escala).
* A presença é da ROTINA do posto: só "veio / faltou / atrasou" por turno,
  sem horário de entrada e saída (F6-2). Jornada e absenteísmo são do RH e
  do Trino Intelligence (D36).
* O posto pode apontar para uma rota (Fase 4): a cobertura passa as tarefas
  do dia de quem faltou para quem cobriu.
"""
from datetime import datetime

from facilities.extensions import db

VEIO = 'veio'
FALTOU = 'faltou'
ATRASOU = 'atrasou'
SITUACOES_PRESENCA = {VEIO: 'Veio', FALTOU: 'Faltou', ATRASOU: 'Atrasou'}


class Funcionario(db.Model):
    __tablename__ = 'funcionarios'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    funcao = db.Column(db.String(80))
    matricula = db.Column(db.String(30))
    # Login no sistema (opcional): um usuário é, no máximo, um funcionário.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=True, unique=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    usuario = db.relationship('User', foreign_keys=[user_id])


class Posto(db.Model):
    """Um posto de trabalho do local, num horário (ex.: "Limpeza 2º andar — manhã")."""
    __tablename__ = 'postos'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)        # hora de Brasília
    hora_fim = db.Column(db.Time, nullable=False)           # menor que o início = vira o dia
    # A rota que quem está no posto executa (opcional).
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    rota = db.relationship('Rota')

    __table_args__ = (db.UniqueConstraint('client_id', 'nome', name='uq_postos_local_nome'),)


class EscalaTrabalho(db.Model):
    """Quem trabalha no posto, em que dias da semana, de quando a quando."""
    __tablename__ = 'escalas'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id',
                                                         ondelete='RESTRICT'),
                               nullable=False, index=True)
    posto_id = db.Column(db.Integer, db.ForeignKey('postos.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    # "1234567" (1 = segunda ... 7 = domingo), como nas rotas.
    dias_semana = db.Column(db.String(7), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    funcionario = db.relationship('Funcionario')
    posto = db.relationship('Posto')


class Presenca(db.Model):
    """A presença de um dia no posto, lançada pelo supervisor."""
    __tablename__ = 'presencas'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id',
                                                         ondelete='RESTRICT'),
                               nullable=False, index=True)
    posto_id = db.Column(db.Integer, db.ForeignKey('postos.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)    # o dia do turno, em Brasília
    situacao = db.Column(db.String(10), nullable=False)
    observacao = db.Column(db.String(300))
    registrada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=False)
    registrada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    funcionario = db.relationship('Funcionario')
    posto = db.relationship('Posto')
    quem_registrou = db.relationship('User', foreign_keys=[registrada_por])
    cobertura = db.relationship('Cobertura', uselist=False, back_populates='presenca')

    __table_args__ = (db.UniqueConstraint('funcionario_id', 'posto_id', 'data',
                                          name='uq_presencas_func_posto_data'),)

    @property
    def situacao_rotulo(self):
        return SITUACOES_PRESENCA.get(self.situacao, self.situacao)


class Cobertura(db.Model):
    """Quem cobriu uma falta, e por quê (o motivo é obrigatório)."""
    __tablename__ = 'coberturas'
    id = db.Column(db.Integer, primary_key=True)
    presenca_id = db.Column(db.Integer, db.ForeignKey('presencas.id', ondelete='RESTRICT'),
                            nullable=False, unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id',
                                                         ondelete='RESTRICT'),
                               nullable=False, index=True)
    motivo = db.Column(db.String(300), nullable=False)
    registrada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=False)
    registrada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    presenca = db.relationship('Presenca', back_populates='cobertura')
    funcionario = db.relationship('Funcionario')


MODELOS_EM_ORDEM_DE_LIMPEZA = (Cobertura, Presenca, EscalaTrabalho, Posto, Funcionario)
