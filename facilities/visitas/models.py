"""Visitas de supervisão programadas (Fase 6, D56).

    Programação (local + checklist + a cada N dias) ──► Visita (uma por vencimento)

O agendador abre a visita na data e avisa o supervisor. Ele faz o checklist
no aplicativo; o que vier não conforme abre UM chamado (F6-3), que cai no
painel de demandas com prazo e avisa a gestão do local.
"""
from datetime import datetime

from facilities.extensions import db

PREVISTA = 'prevista'
FEITA = 'feita'
SITUACOES_VISITA = {PREVISTA: 'A fazer', FEITA: 'Feita'}


class VisitaProgramada(db.Model):
    __tablename__ = 'visitas_programadas'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id',
                                                    ondelete='RESTRICT'), nullable=False)
    # Quem faz; vazio = qualquer supervisor ou gestor do local.
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=True)
    intervalo_dias = db.Column(db.Integer, nullable=False)
    proxima_em = db.Column(db.Date, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    modelo = db.relationship('ChecklistModelo')
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    visitas = db.relationship('Visita', back_populates='programada',
                              order_by='Visita.vencimento.desc()')


class Visita(db.Model):
    __tablename__ = 'visitas'
    id = db.Column(db.Integer, primary_key=True)
    programada_id = db.Column(db.Integer, db.ForeignKey('visitas_programadas.id',
                                                        ondelete='RESTRICT'),
                              nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    vencimento = db.Column(db.Date, nullable=False, index=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=True)
    status = db.Column(db.String(10), nullable=False, default=PREVISTA, index=True)
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    feita_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                          nullable=True)
    feita_em = db.Column(db.DateTime)
    versao_id = db.Column(db.Integer, db.ForeignKey('checklist_versoes.id',
                                                    ondelete='RESTRICT'), nullable=True)
    respostas_json = db.Column(db.Text)
    observacao = db.Column(db.String(2000))
    n_nao_conformes = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True)

    programada = db.relationship('VisitaProgramada', back_populates='visitas')
    local = db.relationship('Client')
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    quem_fez = db.relationship('User', foreign_keys=[feita_por])
    versao = db.relationship('ChecklistVersao')
    chamado = db.relationship('Chamado')

    __table_args__ = (db.UniqueConstraint('programada_id', 'vencimento',
                                          name='uq_visitas_programada_venc'),)

    @property
    def situacao_rotulo(self):
        return SITUACOES_VISITA.get(self.status, self.status)


MODELOS_EM_ORDEM_DE_LIMPEZA = (Visita, VisitaProgramada)
