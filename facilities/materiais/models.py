"""Materiais e custo operacional (Fase 7).

    Material (catálogo do grupo; preço opcional, F7-1)
       └─► Movimento de estoque (por local): entrada, consumo, saída, ajuste
              └─► Consumo (o mesmo movimento, ligado à OS ou à rotina)
    Pedido de insumo (aviso do posto ao gestor; a compra é em outro sistema, F7-3)

* Quantidade em ``NUMERIC(12,3)`` (litro, quilo); dinheiro em
  ``NUMERIC(12,2)``. Nada de ``float``.
* O saldo é a soma dos movimentos do local: não há número guardado à parte
  para sair do compasso.
* Cada movimento guarda o preço do dia: mudar o preço do material não
  reescreve o passado. Material sem preço entra no estoque, mas fica fora
  do custo (e a tela diz isso).
* O custo é só operacional e NUNCA alimenta o DRE (D37).
"""
from datetime import datetime

from facilities.extensions import db

ENTRADA = 'entrada'
CONSUMO = 'consumo'
SAIDA = 'saida'
AJUSTE = 'ajuste'
TIPOS_MOVIMENTO = {ENTRADA: 'Entrada', CONSUMO: 'Consumo', SAIDA: 'Saída (perda, devolução)',
                   AJUSTE: 'Ajuste de inventário'}

PEDIDO_ABERTO = 'aberto'
PEDIDO_VISTO = 'visto'
SITUACOES_PEDIDO = {PEDIDO_ABERTO: 'Aguardando o gestor', PEDIDO_VISTO: 'Visto pelo gestor'}


class Material(db.Model):
    __tablename__ = 'materiais'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    unidade = db.Column(db.String(20), nullable=False)          # un, L, kg, cx...
    preco_unitario = db.Column(db.Numeric(12, 2), nullable=True)  # opcional (F7-1)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MovimentoEstoque(db.Model):
    __tablename__ = 'movimentos_estoque'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)
    # Com sinal: entrada soma, consumo e saída subtraem; ajuste, os dois.
    quantidade = db.Column(db.Numeric(12, 3), nullable=False)
    preco_unitario = db.Column(db.Numeric(12, 2), nullable=True)    # o preço do dia
    valor = db.Column(db.Numeric(12, 2), nullable=True)             # |qtd| × preço
    data = db.Column(db.Date, nullable=False, index=True)           # dia em Brasília
    motivo = db.Column(db.String(300))
    # Quem autorizou o saldo ficar negativo (o gestor do contrato, F7-2).
    autorizado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    material = db.relationship('Material')
    local = db.relationship('Client')
    pessoa = db.relationship('User', foreign_keys=[user_id])
    autorizou = db.relationship('User', foreign_keys=[autorizado_por])

    @property
    def tipo_rotulo(self):
        return TIPOS_MOVIMENTO.get(self.tipo, self.tipo)


class Consumo(db.Model):
    """Material gasto numa ordem de serviço ou na rotina (uma rota)."""
    __tablename__ = 'consumos'
    id = db.Column(db.Integer, primary_key=True)
    movimento_id = db.Column(db.Integer, db.ForeignKey('movimentos_estoque.id',
                                                       ondelete='RESTRICT'),
                             nullable=False, unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True, index=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=True, index=True)

    movimento = db.relationship('MovimentoEstoque')
    chamado = db.relationship('Chamado')
    rota = db.relationship('Rota')


class PedidoInsumo(db.Model):
    """O posto avisa o gestor que precisa de material; a compra é feita em
    outro sistema, e aqui o gestor só marca que viu (F7-3)."""
    __tablename__ = 'pedidos_insumo'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id', ondelete='RESTRICT'),
                            nullable=True)
    quantidade = db.Column(db.Numeric(12, 3), nullable=True)
    texto = db.Column(db.String(300))
    foto_key = db.Column(db.String(300))
    foto_mime = db.Column(db.String(100))
    prazo = db.Column(db.DateTime)                                  # UTC
    status = db.Column(db.String(10), nullable=False, default=PEDIDO_ABERTO, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    visto_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                          nullable=True)
    visto_em = db.Column(db.DateTime)

    local = db.relationship('Client')
    material = db.relationship('Material')
    pessoa = db.relationship('User', foreign_keys=[user_id])
    quem_viu = db.relationship('User', foreign_keys=[visto_por])

    @property
    def situacao_rotulo(self):
        return SITUACOES_PEDIDO.get(self.status, self.status)

    @property
    def resumo(self):
        partes = []
        if self.material is not None:
            q = f'{fmt_qtd(self.quantidade)} {self.material.unidade} de ' if self.quantidade else ''
            partes.append(q + self.material.nome)
        if self.texto:
            partes.append(self.texto)
        return ' · '.join(partes) or 'Pedido de insumo'


def fmt_qtd(q):
    """Decimal('1.500') → "1,5"; Decimal('2.000') → "2"."""
    if q is None:
        return ''
    texto = f'{q:f}'
    if '.' in texto:
        texto = texto.rstrip('0').rstrip('.')
    return texto.replace('.', ',')


MODELOS_EM_ORDEM_DE_LIMPEZA = (Consumo, PedidoInsumo, MovimentoEstoque, Material)
