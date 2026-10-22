"""Rotas e checklists — o dia da Ana, da Mariana e de cada posto (Fase 4A).

    Ponto (QR, Fase 1)
      │
    Modelo de checklist ── Versão publicada (não muda depois de publicada)
      │
    Rota (do LOCAL + turno) ── Itens: ponto + modelo + horários ou frequência
      │                        Escala: quem executa, em que dias
      ▼  agendador
    Tarefa do dia (uma por horário previsto) ──► Execução (QR + respostas + fotos)

Decisões que este arquivo segue (MODELO_ROTAS, R1 a R7; D49, D51 a D53):

* A rota pertence ao local e ao turno; a pessoa é ESCALADA nela. Trocar a
  pessoa não refaz a rota.
* O modelo de checklist vem de uma biblioteca da Trino (``client_id`` nulo)
  e é COPIADO para o local, que ajusta sem afetar os outros.
* Mudar o checklist publica a versão seguinte; a tarefa guarda a versão do
  dia em que foi gerada, e a execução mostra as perguntas da época.
* A execução não se edita. Correção é um registro à parte, com motivo.
* Sem sinal vale o horário do aparelho, marcado "feito sem sinal" (R4).
"""
import json
from datetime import datetime

from facilities.extensions import db

# ── Tipos de pergunta do checklist ────────────────────────────────────────
TIPOS_DE_ITEM = {
    'sim_nao': 'Sim ou não',
    'conforme': 'Conforme ou não conforme',
    'numero': 'Número (com faixa aceitável, se quiser)',
    'texto': 'Texto curto',
    'escolha': 'Escolha de uma lista',
    'data_hora': 'Data e hora',
}

# ── Situações da tarefa do dia ────────────────────────────────────────────
PREVISTA = 'prevista'
CONCLUIDA_NO_PRAZO = 'concluida_no_prazo'
CONCLUIDA_COM_ATRASO = 'concluida_com_atraso'
NAO_REALIZADA = 'nao_realizada'
PERDIDA = 'perdida'
SITUACOES = {
    PREVISTA: 'Prevista',
    'no_horario': 'No horário',
    'atrasada': 'Atrasada',
    CONCLUIDA_NO_PRAZO: 'Concluída no prazo',
    CONCLUIDA_COM_ATRASO: 'Concluída com atraso',
    NAO_REALIZADA: 'Não realizada',
    PERDIDA: 'Perdida',
}
ENCERRADAS = (CONCLUIDA_NO_PRAZO, CONCLUIDA_COM_ATRASO, NAO_REALIZADA, PERDIDA)

TOLERANCIA_PADRAO_MIN = 15   # R3: 15 min, ajustável por rota

# Motivos de "não realizada" (R6: motivo obrigatório).
MOTIVOS_NAO_REALIZADA = {
    'interditado': 'Local interditado ou fechado',
    'falta_material': 'Falta de material',
    'equipamento': 'Equipamento quebrado',
    'acesso': 'Sem acesso ao local',
    'outro': 'Outro motivo',
}

# ── Bloco do técnico (decisões do dono, 22/10/2026) ───────────────────────
# A limpeza levou mais que o previsto (``rota_itens.tempo_previsto_min`` +
# TOLERANCIA_ATRASO_MIN): a pessoa diz o que aconteceu. 'outro' exige texto.
TOLERANCIA_ATRASO_MIN = 10
MOTIVOS_ATRASO = {
    'sujo_acima_do_normal': 'Local muito sujo / uso acima do normal',
    'faltou_material': 'Faltou material e fui buscar',
    'chamado_no_meio': 'Fui chamado para outra coisa no meio',
    'equipamento': 'Equipamento com problema',
    'tempo_curto': 'O tempo previsto está curto',
    'outro': 'Outro',
}
# Um item do checklist que NÃO foi feito (resposta 'nao_feito'): vira não
# conformidade com o motivo; 'faltou_material' com material abre pedido de
# insumo; 'equipamento' entra no chamado da execução. 'outro' exige texto.
RESPOSTA_NAO_FEITO = 'nao_feito'
MOTIVOS_NAO_FEITO = {
    'faltou_material': 'Faltou material',
    'equipamento': 'Equipamento com problema',
    'sem_acesso': 'Sem acesso (fechado, ocupado)',
    'outro': 'Outro',
}


class ChecklistModelo(db.Model):
    __tablename__ = 'checklist_modelos'
    id = db.Column(db.Integer, primary_key=True)
    # Nulo = biblioteca da Trino (só o administrador mexe); preenchido = do local.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=True, index=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text)            # o procedimento (POP), mostrado no QR
    exige_foto_antes = db.Column(db.Boolean, default=False, nullable=False)
    exige_foto_depois = db.Column(db.Boolean, default=False, nullable=False)
    # De qual modelo da biblioteca este foi copiado (só para a tela dizer).
    # (Sem RESTRICT de propósito: chave para a própria tabela; o padrão do
    # banco já recusa apagar a origem de uma cópia.)
    origem_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    versoes = db.relationship('ChecklistVersao', backref='modelo',
                              order_by='ChecklistVersao.numero')

    @property
    def versao_atual(self):
        return self.versoes[-1] if self.versoes else None


class ChecklistDocumento(db.Model):
    """O POP ou a FIT do checklist (PDF, Excel, Word ou imagem), guardado
    para consulta. O RESUMO que o ASG lê no celular é o procedimento do
    checklist (``ChecklistModelo.descricao``), escrito pela gestão (decisão do
    dono, 18/10/2026). Trocar o documento não apaga o antigo: ele sai de uso
    (``is_active``) e fica no histórico."""
    __tablename__ = 'checklist_documentos'
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(200), nullable=False)
    mime = db.Column(db.String(100))
    tamanho = db.Column(db.Integer)
    storage_key = db.Column(db.String(300), nullable=False)
    # O cliente só vê o documento que a gestão marcar (é know-how da Trino).
    visivel_cliente = db.Column(db.Boolean, default=False, nullable=False,
                                server_default=db.false())
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    enviado_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'))
    enviado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    modelo = db.relationship('ChecklistModelo', backref=db.backref(
        'documentos', order_by='ChecklistDocumento.id'))


class ChecklistVersao(db.Model):
    """Uma versão PUBLICADA: as perguntas daquele momento. Não se edita."""
    __tablename__ = 'checklist_versoes'
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id',
                                                    ondelete='RESTRICT'),
                          nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    itens_json = db.Column(db.Text, nullable=False, default='[]')
    exige_foto_antes = db.Column(db.Boolean, default=False, nullable=False)
    exige_foto_depois = db.Column(db.Boolean, default=False, nullable=False)
    # Plano de limpeza (22/10/2026): o material usado e o EPI da atividade,
    # como a planilha do cliente lista. Ficam na VERSÃO, congelados com a
    # execução: a tela do técnico mostra o que valia no dia.
    materiais = db.Column(db.Text)
    epi = db.Column(db.Text)
    publicada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    publicada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=True)

    __table_args__ = (db.UniqueConstraint('modelo_id', 'numero',
                                          name='uq_checklist_versoes_modelo_numero'),)


class Rota(db.Model):
    __tablename__ = 'rotas'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False)
    turno = db.Column(db.String(50), nullable=False)       # "1º Turno", "Noturno"...
    hora_inicio = db.Column(db.Time, nullable=False)        # hora de Brasília
    hora_fim = db.Column(db.Time, nullable=False)           # menor que o início = vira o dia
    tolerancia_min = db.Column(db.Integer, nullable=False, default=TOLERANCIA_PADRAO_MIN)
    # Dias da semana em que a rota roda: "1234567" (1 = segunda ... 7 = domingo).
    dias_semana = db.Column(db.String(7), nullable=False, default='1234567')
    # Confirmação de presença em horário aleatório (D48, Q4): quantas por
    # turno (0 desliga) e quantos minutos a pessoa tem para responder.
    # Padrão DESLIGADO: só liga depois da validação de RH e jurídico (D48;
    # decisão do dono em 21/10/2026). O server_default fica em '2' para não
    # exigir migração; linhas novas sempre passam pelo default do modelo.
    presencas_por_turno = db.Column(db.Integer, nullable=False, default=0,
                                    server_default='2')
    presenca_prazo_min = db.Column(db.Integer, nullable=False, default=10,
                                   server_default='10')
    # Plano de limpeza (22/10/2026): o intervalo (almoço, ceia) dentro do
    # turno — o agendador não põe tarefa nele — e as observações do plano
    # (ex.: a regra das gaiolas), mostradas na tela da rota.
    intervalo_inicio = db.Column(db.Time)
    intervalo_fim = db.Column(db.Time)
    observacoes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship('Client')
    itens = db.relationship('RotaItem', backref='rota', order_by='RotaItem.ordem')
    escalas = db.relationship('RotaEscala', backref='rota', order_by='RotaEscala.id')

    __table_args__ = (db.UniqueConstraint('client_id', 'nome', name='uq_rotas_local_nome'),)


class RotaItem(db.Model):
    """Uma atividade da rota: um modelo de checklist num ponto, com horário."""
    __tablename__ = 'rota_itens'
    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id',
                                                    ondelete='RESTRICT'), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    # Horários fixos ("07:00,09:00,11:00") e/ou frequência (a cada N minutos,
    # do início ao fim do turno). Os dois podem conviver (R3).
    horarios = db.Column(db.String(300))
    frequencia_min = db.Column(db.Integer)
    # Minutos para executar o checklist neste ponto (1 a 480; vazio = sem
    # controle de tempo). Acima disto + TOLERANCIA_ATRASO_MIN, a execução
    # pede o motivo do atraso.
    tempo_previsto_min = db.Column(db.Integer)
    # Plano de limpeza (22/10/2026): vazio = todos os dias da rota; preenchido
    # ("12345") = só nesses dias (subconjunto dos dias da rota). E os horários
    # diferentes de um dia específico, em JSON {"6": "07:00, 09:30"}: nesse
    # dia valem SÓ estes; nos outros vale ``horarios``.
    dias_semana = db.Column(db.String(7))
    horarios_por_dia = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    ponto = db.relationship('PontoInspecao')
    modelo = db.relationship('ChecklistModelo')

    @property
    def horarios_por_dia_dict(self):
        try:
            d = json.loads(self.horarios_por_dia or '{}')
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}


class RotaModelo(db.Model):
    """Rota pronta da biblioteca da Trino (pedido do dono, 19/10/2026): um
    pacote por tipo de local — ambientes, checklist e horários — que a gestão
    APLICA num local (``rotas/rotas_prontas.py``). O administrador edita na
    tela; aplicar cria uma rota comum no local, que não muda se o modelo
    mudar depois."""
    __tablename__ = 'rota_modelos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, unique=True)
    segmento = db.Column(db.String(60), nullable=False, default='Outro')
    descricao = db.Column(db.Text)
    turno = db.Column(db.String(50), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)
    tolerancia_min = db.Column(db.Integer, nullable=False, default=TOLERANCIA_PADRAO_MIN)
    dias_semana = db.Column(db.String(7), nullable=False, default='12345')
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    itens = db.relationship('RotaModeloItem', backref='rota_modelo',
                            order_by='RotaModeloItem.ordem', cascade='all, delete-orphan')


class RotaModeloItem(db.Model):
    """Uma linha da rota pronta: em que setor e ambiente, com qual checklist
    da biblioteca, em que horários e quantos ambientes iguais (ex.: 2
    banheiros masculinos)."""
    __tablename__ = 'rota_modelo_itens'
    id = db.Column(db.Integer, primary_key=True)
    rota_modelo_id = db.Column(db.Integer, db.ForeignKey('rota_modelos.id', ondelete='CASCADE'),
                               nullable=False, index=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    setor = db.Column(db.String(120), nullable=False)
    ambiente = db.Column(db.String(120), nullable=False)
    checklist_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id',
                                                       ondelete='RESTRICT'), nullable=False)
    horarios = db.Column(db.String(300), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    # Tempo previsto (minutos) que ``aplicar`` copia para cada item da rota.
    tempo_previsto_min = db.Column(db.Integer)

    checklist = db.relationship('ChecklistModelo')


class RotaEscala(db.Model):
    """Quem executa a rota, em que dias, de quando a quando."""
    __tablename__ = 'rota_escalas'
    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    dias_semana = db.Column(db.String(7), nullable=False, default='12345')
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pessoa = db.relationship('User')


class TarefaDia(db.Model):
    """Uma tarefa prevista: gerada pelo agendador, uma por horário."""
    __tablename__ = 'tarefas_dia'
    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    rota_item_id = db.Column(db.Integer, db.ForeignKey('rota_itens.id', ondelete='RESTRICT'),
                             nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    versao_id = db.Column(db.Integer, db.ForeignKey('checklist_versoes.id',
                                                    ondelete='RESTRICT'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=True, index=True)       # a pessoa escalada (se houver)
    data = db.Column(db.Date, nullable=False, index=True)   # o dia do TURNO, em Brasília
    previsto_para = db.Column(db.DateTime, nullable=False, index=True)   # UTC
    fim_do_turno = db.Column(db.DateTime, nullable=False)                # UTC
    tolerancia_min = db.Column(db.Integer, nullable=False, default=TOLERANCIA_PADRAO_MIN)
    status = db.Column(db.String(25), nullable=False, default=PREVISTA, index=True)
    motivo = db.Column(db.String(30))
    motivo_texto = db.Column(db.String(300))
    encerrada_em = db.Column(db.DateTime)
    encerrada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True)
    # Quando o aviso "chegou a hora" foi mandado ao celular (Fase 4B).
    avisada_em = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rota = db.relationship('Rota')
    item = db.relationship('RotaItem')
    ponto = db.relationship('PontoInspecao')
    versao = db.relationship('ChecklistVersao')
    pessoa = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        # O agendador pode rodar quantas vezes quiser: um horário, uma tarefa.
        db.UniqueConstraint('rota_item_id', 'previsto_para', name='uq_tarefas_dia_item_hora'),
        db.Index('ix_tarefas_dia_local_data', 'client_id', 'data'),
    )


class Execucao(db.Model):
    """O que a pessoa fez num ponto: QR, respostas, fotos. Não se edita."""
    __tablename__ = 'execucoes'
    id = db.Column(db.Integer, primary_key=True)
    tarefa_id = db.Column(db.Integer, db.ForeignKey('tarefas_dia.id', ondelete='RESTRICT'),
                          nullable=True, index=True)     # nulo = atividade extra (D53)
    # Fase 5: o checklist de uma ordem de serviço preventiva.
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    versao_id = db.Column(db.Integer, db.ForeignKey('checklist_versoes.id',
                                                    ondelete='RESTRICT'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    extra = db.Column(db.Boolean, default=False, nullable=False)
    # Os horários: o QR lido, o começo e o fim (D52). Com sinal, os do
    # SERVIDOR; sem sinal, os do aparelho, com ``sem_sinal`` ligado (R4).
    lido_em = db.Column(db.DateTime, nullable=False)
    iniciada_em = db.Column(db.DateTime, nullable=False)
    concluida_em = db.Column(db.DateTime, nullable=False)
    sem_sinal = db.Column(db.Boolean, default=False, nullable=False)
    recebida_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    respostas_json = db.Column(db.Text, nullable=False, default='{}')
    observacao = db.Column(db.Text)
    # A marca do envio: o mesmo envio repetido (fila sem internet, clique
    # duplo, resposta perdida) devolve a mesma execução em vez de duplicar.
    envio_id = db.Column(db.String(64), nullable=False, unique=True)
    n_nao_conformes = db.Column(db.Integer, default=0, nullable=False)
    # Levou mais que o previsto: o motivo (MOTIVOS_ATRASO) e o texto de 'outro'.
    motivo_atraso = db.Column(db.String(40))
    motivo_atraso_texto = db.Column(db.String(300))

    tarefa = db.relationship('TarefaDia', backref='execucoes')

    @property
    def duracao_min(self):
        """Minutos entre ler o QR e concluir (inteiro, nunca negativo)."""
        return max(0, int((self.concluida_em - self.lido_em).total_seconds() // 60))
    ponto = db.relationship('PontoInspecao')
    versao = db.relationship('ChecklistVersao')
    pessoa = db.relationship('User')
    fotos = db.relationship('ExecucaoFoto', backref='execucao', order_by='ExecucaoFoto.id')
    correcoes = db.relationship('ExecucaoCorrecao', backref='execucao',
                                order_by='ExecucaoCorrecao.id')


class ExecucaoFoto(db.Model):
    __tablename__ = 'execucao_fotos'
    id = db.Column(db.Integer, primary_key=True)
    execucao_id = db.Column(db.Integer, db.ForeignKey('execucoes.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    momento = db.Column(db.String(10), nullable=False)      # antes | depois | item
    item_codigo = db.Column(db.String(60))
    mime = db.Column(db.String(100))
    tamanho = db.Column(db.Integer)
    storage_key = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class NaoConformidade(db.Model):
    """Um item do checklist que não ficou bom. Pode virar chamado (sem plano
    de ação: isso é do Intelligence, D35)."""
    __tablename__ = 'nao_conformidades'
    id = db.Column(db.Integer, primary_key=True)
    execucao_id = db.Column(db.Integer, db.ForeignKey('execucoes.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    item_codigo = db.Column(db.String(60), nullable=False)
    item_texto = db.Column(db.String(300), nullable=False)
    resposta = db.Column(db.String(300))
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='RESTRICT'),
                           nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    execucao = db.relationship('Execucao', backref='nao_conformidades')


class ExecucaoCorrecao(db.Model):
    """Correção de uma execução: o que mudou, por quem, por quê. A execução
    original continua como estava."""
    __tablename__ = 'execucao_correcoes'
    id = db.Column(db.Integer, primary_key=True)
    execucao_id = db.Column(db.Integer, db.ForeignKey('execucoes.id', ondelete='RESTRICT'),
                            nullable=False, index=True)
    motivo = db.Column(db.String(500), nullable=False)
    respostas_antes_json = db.Column(db.Text, nullable=False)
    respostas_depois_json = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    autor = db.relationship('User')


class AgendadorExecucao(db.Model):
    """Cada rodada do agendador: quando, quanto gerou, se deu certo."""
    __tablename__ = 'agendador_execucoes'
    id = db.Column(db.Integer, primary_key=True)
    iniciada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    concluida_em = db.Column(db.DateTime)
    origem = db.Column(db.String(20), nullable=False, default='comando')
    tarefas_geradas = db.Column(db.Integer, default=0, nullable=False)
    tarefas_perdidas = db.Column(db.Integer, default=0, nullable=False)
    ok = db.Column(db.Boolean, default=False, nullable=False)
    erro = db.Column(db.Text)


# ── Ocorrência do QR público (D47, Q1 a Q3) ───────────────────────────────
# Bloco do técnico (etapa 2): a pessoa só MARCA os itens do checklist do
# ponto ("Falta papel") sem escolher um tipo da lista — a ocorrência fica
# com este tipo e os itens marcados (``OcorrenciaPublica.itens``).
TIPO_ITENS_DO_CHECKLIST = 'itens'
TIPOS_OCORRENCIA_PUBLICA = {
    'itens': 'Itens do checklist',
    'falta_papel': 'Falta papel',
    'falta_sabonete': 'Falta sabonete ou álcool',
    'sujo': 'Local sujo',
    'lixo': 'Lixeira cheia',
    'vazamento': 'Vazamento ou entupimento',
    'quebrado': 'Algo quebrado',
    'outro': 'Outro problema',
}
OCORRENCIA_ABERTA = 'aberta'
OCORRENCIA_EM_ATENDIMENTO = 'em_atendimento'
OCORRENCIA_RESOLVIDA = 'resolvida'
SITUACOES_OCORRENCIA = {
    OCORRENCIA_ABERTA: 'Recebida',
    OCORRENCIA_EM_ATENDIMENTO: 'Em atendimento',
    OCORRENCIA_RESOLVIDA: 'Resolvida',
}


class OcorrenciaPublica(db.Model):
    """O que qualquer pessoa no local abriu pelo QR, sem login.

    Não guarda dado de quem abriu: nem nome, nem contato. O acompanhamento é
    pelo link com o ``token`` (Q3), que só mostra a situação.
    """
    __tablename__ = 'ocorrencias_publicas'
    id = db.Column(db.Integer, primary_key=True)
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    texto = db.Column(db.String(300))
    foto_key = db.Column(db.String(300))
    foto_mime = db.Column(db.String(100))
    token = db.Column(db.String(40), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default=OCORRENCIA_ABERTA, index=True)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    prazo = db.Column(db.DateTime)                 # UTC; nulo = cliente sem prazo definido
    atendida_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                             nullable=True)
    atendida_em = db.Column(db.DateTime)
    resolvida_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=True)
    resolvida_em = db.Column(db.DateTime)
    resolucao = db.Column(db.String(300))
    # Bloco do técnico (22/10/2026): os itens do checklist do ponto que quem
    # abriu marcou ("Falta papel", "Lixeira cheia"), como lista JSON de
    # códigos; e quem abriu, QUANDO estava logado (o cliente do portal). Sem
    # login continua anônimo: ``autor_id`` fica vazio.
    itens_json = db.Column(db.Text)
    autor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                         nullable=True)

    ponto = db.relationship('PontoInspecao')
    quem_atendeu = db.relationship('User', foreign_keys=[atendida_por])
    quem_resolveu = db.relationship('User', foreign_keys=[resolvida_por])
    autor = db.relationship('User', foreign_keys=[autor_id])

    @property
    def itens(self):
        return json.loads(self.itens_json or '[]')


# ── Confirmação de presença (D48, Q4) ─────────────────────────────────────
PRESENCA_PENDENTE = 'pendente'
PRESENCA_CONFIRMADA = 'confirmada'
PRESENCA_SEM_RESPOSTA = 'sem_resposta'
# O pedido venceu sem nunca ter sido enviado (o agendador atrasou): não é
# culpa de ninguém no posto — não vira "sem resposta" nem alerta o superior.
PRESENCA_NAO_ENVIADA = 'nao_enviada'


class ConfirmacaoPresenca(db.Model):
    """Um pedido de "confirme que você está no posto", num horário sorteado
    do turno, para quem está escalado na rota."""
    __tablename__ = 'confirmacoes_presenca'
    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('rotas.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)
    pedido_em = db.Column(db.DateTime, nullable=False, index=True)    # UTC
    prazo_ate = db.Column(db.DateTime, nullable=False)                # UTC
    avisado_em = db.Column(db.DateTime)
    respondida_em = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default=PRESENCA_PENDENTE, index=True)
    supervisor_avisado = db.Column(db.Boolean, default=False, nullable=False)

    rota = db.relationship('Rota')
    pessoa = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('rota_id', 'user_id', 'pedido_em',
                                          name='uq_confirmacoes_presenca_pedido'),)


# ── Chegada no local (bloco do técnico, 22/10/2026) ───────────────────────
class Chegada(db.Model):
    """A pessoa chegou ao local: leu o QR da ENTRADA (``PontoInspecao.
    entrada_do_local``). Uma por pessoa, local e dia: ler de novo no mesmo
    dia devolve a mesma. A gestão pode LIBERAR a chegada (``com_camera``
    falso) quando o QR da entrada não pôde ser lido."""
    __tablename__ = 'chegadas'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='RESTRICT'),
                          nullable=False)
    ponto_id = db.Column(db.Integer, db.ForeignKey('pontos_inspecao.id', ondelete='RESTRICT'),
                         nullable=False)
    data = db.Column(db.Date, nullable=False)                 # o dia LOCAL (Brasília)
    chegou_em = db.Column(db.DateTime, nullable=False)        # UTC
    com_camera = db.Column(db.Boolean, default=True, nullable=False)
    # Quem liberou, quando não foi pela câmera (a gestão).
    liberada_por = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                             nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pessoa = db.relationship('User', foreign_keys=[user_id])
    ponto = db.relationship('PontoInspecao')
    local = db.relationship('Client')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'client_id', 'data', name='uq_chegadas_pessoa_local_dia'),
        db.Index('ix_chegadas_local_data', 'client_id', 'data'),
    )


MODELOS_EM_ORDEM_DE_LIMPEZA = (Chegada, ConfirmacaoPresenca, OcorrenciaPublica, ExecucaoCorrecao,
                               NaoConformidade, ExecucaoFoto, Execucao, TarefaDia, RotaEscala,
                               RotaItem, Rota, RotaModeloItem, RotaModelo,
                               ChecklistDocumento, ChecklistVersao,
                               ChecklistModelo,
                               AgendadorExecucao)
