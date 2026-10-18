"""O relatório mensal do cliente (decisão do dono, 18/10/2026).

Os NÚMEROS não ficam guardados: saem sempre das mesmas funções que alimentam
o painel (o relatório nunca discorda da tela). Guarda-se só o que é decisão
de gente: quais fotos vão no relatório (a amostra automática, trocada pela
gestão se quiser), um recado da gestão ao cliente e QUANDO ele foi liberado —
o cliente só vê o relatório liberado.
"""
from datetime import datetime

from facilities.extensions import db


class RelatorioCliente(db.Model):
    __tablename__ = 'relatorios_cliente'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    # O primeiro dia do mês do relatório.
    mes = db.Column(db.Date, nullable=False)
    # Lista de referências ("execucao:12", "chamado:7", "visita:3"); vazio =
    # a amostra automática.
    fotos_json = db.Column(db.Text)
    recado = db.Column(db.Text)
    liberado_em = db.Column(db.DateTime)
    liberado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'))
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                              nullable=False)

    local = db.relationship('Client')
    quem_liberou = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('client_id', 'mes', name='uq_relatorio_cliente_mes'),)


MODELOS_EM_ORDEM_DE_LIMPEZA = (RelatorioCliente,)
