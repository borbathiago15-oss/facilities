"""O relatório mensal do cliente (decisão do dono, 18/10/2026).

Enquanto o relatório não é liberado, os números saem sempre das mesmas
funções que alimentam o painel. Guarda-se o que é decisão de gente: quais
fotos vão no relatório, um recado da gestão ao cliente e QUANDO ele foi
liberado — e, desde 23/10/2026, a versão liberada congelada: o cliente nunca
vê o relatório mudar sozinho depois de recebido.
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
    # O que o cliente recebeu (decisão do dono, 23/10/2026): ao liberar, os
    # números e as fotos ficam CONGELADOS aqui, em JSON. O portal mostra esta
    # versão; se algo do mês for corrigido depois, a tela da gestão mostra a
    # diferença e quem decide liberar de novo é a gestão. Vazio = liberado
    # antes do congelamento (o portal recalcula, como antes).
    congelado_json = db.Column(db.Text)
    liberado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'))
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                              nullable=False)

    local = db.relationship('Client')
    quem_liberou = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('client_id', 'mes', name='uq_relatorio_cliente_mes'),)


MODELOS_EM_ORDEM_DE_LIMPEZA = (RelatorioCliente,)
