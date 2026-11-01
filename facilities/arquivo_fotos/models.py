"""O que o arquivo das fotos registra: o prazo, cada lote e cada foto que
saiu do armazenamento principal (e as que não conseguiram sair)."""
from datetime import datetime

from facilities.extensions import db

DIAS_PADRAO = 60

LOTE_EM_ANDAMENTO = 'em_andamento'
LOTE_CONCLUIDO = 'concluido'
LOTE_CONCLUIDO_COM_FALHAS = 'concluido_com_falhas'
SITUACOES_DO_LOTE = {
    LOTE_EM_ANDAMENTO: 'Em andamento',
    LOTE_CONCLUIDO: 'Concluído',
    LOTE_CONCLUIDO_COM_FALHAS: 'Concluído, com fotos que não saíram',
}


class ArquivoAjustes(db.Model):
    """Uma linha só (id 1): depois de quantos dias a foto vai para o arquivo."""
    __tablename__ = 'arquivo_fotos_ajustes'
    id = db.Column(db.Integer, primary_key=True)
    dias = db.Column(db.Integer, nullable=False, default=DIAS_PADRAO)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=True)


class LoteArquivo(db.Model):
    """Um pedido do administrador: arquivar as fotos de antes de ``corte_em``.
    O agendador anda com ele, um pouco por rodada, até não sobrar nada."""
    __tablename__ = 'arquivo_fotos_lotes'
    id = db.Column(db.Integer, primary_key=True)
    iniciado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                             nullable=False)
    iniciado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    concluido_em = db.Column(db.DateTime)
    dias = db.Column(db.Integer, nullable=False)
    corte_em = db.Column(db.DateTime, nullable=False)          # UTC: fotos de antes disto
    destino = db.Column(db.String(300), nullable=False)
    situacao = db.Column(db.String(30), nullable=False, default=LOTE_EM_ANDAMENTO, index=True)
    previstas = db.Column(db.Integer, nullable=False, default=0)
    arquivadas = db.Column(db.Integer, nullable=False, default=0)
    bytes_arquivados = db.Column(db.BigInteger, nullable=False, default=0)
    tentativas_com_erro = db.Column(db.Integer, nullable=False, default=0)
    nao_arquivadas = db.Column(db.Integer, nullable=False, default=0)
    ultimo_erro = db.Column(db.Text)
    ultima_rodada_em = db.Column(db.DateTime)

    pessoa = db.relationship('User')

    @property
    def situacao_rotulo(self):
        return SITUACOES_DO_LOTE.get(self.situacao, self.situacao)


class FotoArquivada(db.Model):
    """Uma foto que está no arquivo, conferida pelo SHA-256. Enquanto
    ``removida_do_principal_em`` estiver vazio, a cópia do principal ainda
    existe (a remoção vem na rodada seguinte, depois de este registro estar
    gravado)."""
    __tablename__ = 'fotos_arquivadas'
    __table_args__ = (db.Index('ix_fotos_arquivadas_origem', 'origem', 'origem_id'),)
    id = db.Column(db.Integer, primary_key=True)
    storage_key = db.Column(db.String(300), nullable=False, unique=True)
    origem = db.Column(db.String(40), nullable=False)          # a tabela da foto
    origem_id = db.Column(db.Integer, nullable=False)
    tamanho = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    arquivada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    lote_id = db.Column(db.Integer, db.ForeignKey('arquivo_fotos_lotes.id',
                                                  ondelete='RESTRICT'),
                        nullable=False, index=True)
    removida_do_principal_em = db.Column(db.DateTime)


class FalhaArquivo(db.Model):
    """Uma foto que não conseguiu ir para o arquivo (continua no principal).
    Sai daqui quando ela for arquivada numa tentativa seguinte."""
    __tablename__ = 'arquivo_fotos_falhas'
    id = db.Column(db.Integer, primary_key=True)
    storage_key = db.Column(db.String(300), nullable=False, unique=True)
    origem = db.Column(db.String(40), nullable=False)
    origem_id = db.Column(db.Integer, nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey('arquivo_fotos_lotes.id',
                                                  ondelete='RESTRICT'),
                        nullable=False, index=True)
    tentativas = db.Column(db.Integer, nullable=False, default=0)
    erro = db.Column(db.String(500))
    em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# Filhos antes dos pais (FK) — a limpeza entre testes usa esta ordem.
MODELOS_EM_ORDEM_DE_LIMPEZA = (FotoArquivada, FalhaArquivo, LoteArquivo, ArquivoAjustes)
