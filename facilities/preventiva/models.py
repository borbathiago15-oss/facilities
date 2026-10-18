"""Plano preventivo: o que se faz de tempos em tempos num equipamento ou
ambiente, sem esperar quebrar (Fase 5).

    Plano (ponto + checklist + a cada N dias) ──► Ciclo (um por vencimento)
                                                     └─► Chamado de origem "preventiva"

O agendador abre a ordem de serviço do ciclo (``antecedencia_dias`` antes do
vencimento) e empurra o próximo vencimento. Um ciclo vira UMA ordem: rodar
de novo não duplica (``uq_preventiva_ordens_plano_venc``). O técnico faz o
checklist do plano no aplicativo, lendo o QR do ponto, e a ordem fica
resolvida para a gestão conferir.
"""
from datetime import datetime

from facilities.extensions import db


class PlanoPreventivo(db.Model):
    __tablename__ = 'planos_preventivos'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False)
    # Onde o técnico lê o QR e faz o checklist; o equipamento é opcional.
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id', ondelete='RESTRICT'),
                               nullable=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id', ondelete='RESTRICT'),
                          nullable=False)
    intervalo_dias = db.Column(db.Integer, nullable=False)
    proxima_em = db.Column(db.Date, nullable=False, index=True)
    antecedencia_dias = db.Column(db.Integer, nullable=False, default=0)
    prioridade = db.Column(db.String(10), nullable=False, default='media')
    responsavel_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=True)
    # Quem cadastrou: aparece como quem "pediu" a ordem de serviço.
    criado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    ponto = db.relationship('PontoInspecao')
    equipamento = db.relationship('Equipamento')
    modelo = db.relationship('ChecklistModelo')
    responsavel = db.relationship('User', foreign_keys=[responsavel_id])
    ciclos = db.relationship('PreventivaOrdem', backref='plano',
                             order_by='PreventivaOrdem.vencimento.desc()')


class PreventivaOrdem(db.Model):
    """Um ciclo do plano: o vencimento e a ordem de serviço aberta para ele."""
    __tablename__ = 'preventiva_ordens'
    id = db.Column(db.Integer, primary_key=True)
    plano_id = db.Column(db.Integer, db.ForeignKey('planos_preventivos.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    vencimento = db.Column(db.Date, nullable=False)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True, index=True)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    chamado = db.relationship('Chamado')

    __table_args__ = (db.UniqueConstraint('plano_id', 'vencimento',
                                          name='uq_preventiva_ordens_plano_venc'),)


MODELOS_EM_ORDEM_DE_LIMPEZA = (PreventivaOrdem, PlanoPreventivo)
