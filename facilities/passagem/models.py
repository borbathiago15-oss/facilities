"""Modelos da Passagem de Turno (vindos do Diário Operacional do Trino Intelligence).

O módulo é configurável por cliente: a configuração guarda os campos e
atividades que cada operação precisa registrar. Os lançamentos preservam o
payload original para manter histórico mesmo quando a configuração evolui.
"""
from datetime import datetime
from facilities.extensions import db

# Gravidade da ocorrência. Duas, e não uma escala de cinco: o encarregado
# marca isso no fim do turno, com pressa, e uma escala longa vira ruído —
# todo mundo escolhe o meio, e o meio não informa nada.
OCORRENCIA_NORMAL = 'normal'
OCORRENCIA_CRITICA = 'critica'
OCORRENCIA_GRAVIDADES = (
    (OCORRENCIA_NORMAL, 'Normal'),
    (OCORRENCIA_CRITICA, 'Ponto de atenção'),
)


class DiarioArea(db.Model):
    """Uma área do contrato — o lugar onde a passagem de turno acontece.

    Um contrato não é um lugar só. A PepsiCo Fábrica Recife tem Expedição e
    Almoxarifado passando o mesmo 1º Turno, com responsáveis diferentes e
    perguntas diferentes. O Novo Atacarejo Moreno tem cerca de dez áreas e
    vinte encarregados.

    É CADASTRO e não texto digitado no modelo, e a razão é a escala: com dez
    áreas e vinte pessoas lançando, "Expedição", "expedicao" e "EXPEDIÇÃO"
    apareceriam na mesma base em uma semana, e o filtro do painel passaria a
    mostrar três áreas onde existe uma. Aqui o nome é escrito uma vez, por
    quem administra, e todo o resto aponta para ele.

    Também é o que evita o contorno que o usuário descreveu: dividir a
    operação em áreas sem precisar cadastrar um cliente novo para cada uma —
    o que duplicaria contrato, centro de custo e carteira.
    """
    __tablename__ = 'diario_operacional_areas'
    __table_args__ = (db.Index('ix_diario_area_cliente_nome', 'client_id', 'nome'),)
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'),
                          nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)


class DiarioConfiguracao(db.Model):
    """O modelo de passagem de UMA ÁREA de um contrato.

    Cada área passa o turno do seu jeito. Na PepsiCo Fábrica Recife, no mesmo
    1º Turno, a Expedição registra veículos em doca, expedições concluídas e
    reprovas, enquanto o Almoxarifado registra pendências, efetivo,
    equipamentos e estoque. São duas passagens, com responsáveis diferentes,
    no mesmo dia e turno.

    ``area_id`` é NULO nos modelos criados antes de a área existir, e em
    contrato que não se divide. Inventar uma área para eles seria escrever no
    histórico o que ninguém disse. A tela só mostra o seletor de área quando
    o contrato tem área cadastrada.
    """
    __tablename__ = 'diario_operacional_configuracoes'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_areas.id'),
                        nullable=True, index=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.String(500))
    turnos_json = db.Column(db.Text, nullable=False, default='[]')
    campos_json = db.Column(db.Text, nullable=False, default='[]')
    atividades_json = db.Column(db.Text, nullable=False, default='[]')
    tipos_ocorrencia_json = db.Column(db.Text, nullable=False, default='[]')
    ativo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DiarioTurno(db.Model):
    __tablename__ = 'diario_operacional_turnos'
    __table_args__ = (db.Index('ix_diario_turnos_cliente_data', 'client_id', 'data_turno'),)
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    configuracao_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_configuracoes.id'), nullable=False, index=True)
    data_turno = db.Column(db.Date, nullable=False, index=True)
    turno = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='aberto', index=True)
    dados_json = db.Column(db.Text, nullable=False, default='{}')
    observacao = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DiarioAnexo(db.Model):
    """A foto (ou o PDF) que o encarregado prende à observação de uma atividade.

    Nasceu de um pedido de uma frase: "ao fazer passagem de turno, ele poderá
    anexar imagens ou PDF no campo de observação". No armazém isso é o normal
    — o 5S que não foi feito se PROVA com a foto da rua bagunçada, e a avaria
    do pallet descrita em texto vira discussão na reunião seguinte.

    ``atividade_codigo`` amarra o anexo à linha do checklist (o mesmo código
    que ``dados_json`` usa em ``atividade:<codigo>``). Nulo = anexo da
    observação GERAL do turno, não de uma atividade específica: as duas
    coisas cabem na mesma tabela porque a pergunta de quem lê é uma só —
    "que prova acompanha este turno?" — e separar faria a tela procurar em
    dois lugares.

    Guarda-se o código e não o id de uma linha de configuração porque a
    atividade não é linha de tabela: ela mora dentro do JSON da configuração
    do contrato. O código sobrevive à edição do checklist; o índice na lista,
    não.

    O arquivo vai para o object storage (R2 em produção, o mesmo dos anexos
    de ação e de SLA); aqui ficam só o caminho, o nome original, o tipo, o
    tamanho e quem subiu.
    """
    __tablename__ = 'diario_operacional_anexos'
    __table_args__ = (db.Index('ix_diario_anexo_turno_ativ', 'turno_id', 'atividade_codigo'),)
    id = db.Column(db.Integer, primary_key=True)
    turno_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_turnos.id'),
                         nullable=False, index=True)
    # Nulo = anexo da observação geral do turno.
    atividade_codigo = db.Column(db.String(120), index=True)
    storage_key = db.Column(db.String(300), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    mime = db.Column(db.String(120))
    tamanho = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    turno = db.relationship('DiarioTurno', backref=db.backref(
        'anexos', cascade='all, delete-orphan', lazy='selectin'))

    def to_dict(self):
        return {'id': self.id, 'turno_id': self.turno_id,
                'atividade': self.atividade_codigo or '',
                'nome': self.nome, 'mime': self.mime or '',
                'tamanho': self.tamanho or 0,
                # Imagem a tela mostra; PDF ela oferece para abrir.
                'e_imagem': (self.mime or '').startswith('image/')}


class DiarioPendencia(db.Model):
    """O que um turno não terminou e entrega ao próximo.

    Ela não morre com o turno nem com o dia: enquanto o status for ``aberta``
    ela reaparece na passagem seguinte, de qualquer turno, indefinidamente.
    A devolução que chegou na Tarde e cujo processo ninguém achou continua na
    tela da Manhã de depois de amanhã.

    ``referencia`` existe porque, na maior parte dos casos, o número É a
    coisa: a devolução 445.221, a NF, o pedido. Antes dele o encarregado
    enfiava o número dentro do título, e então não havia como procurar.

    ``resolucao`` e ``resolved_by`` respondem à pergunta que o status sozinho
    não responde — resolvida COMO, e por quem. Sem elas, "resolver" é um
    botão de limpar a tela.
    """
    __tablename__ = 'diario_operacional_pendencias'
    __table_args__ = (db.Index('ix_diario_pend_cliente_criacao', 'client_id', 'created_at'),)
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    # O turno que ABRIU a pendência. Os que a carregaram depois estão em
    # ``eventos`` — este campo não muda de dono ao longo da vida dela.
    turno_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_turnos.id'), nullable=True, index=True)
    titulo = db.Column(db.String(200), nullable=False)
    referencia = db.Column(db.String(120), index=True)
    descricao = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='aberta', index=True)
    prioridade = db.Column(db.String(20), nullable=False, default='media')
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    due_date = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolucao = db.Column(db.Text)


class DiarioPendenciaEvento(db.Model):
    """A trilha da pendência — o filme, não a foto.

    Sem ela o registro só sabia dizer QUE a pendência está aberta, nunca o
    que já se tentou. O encarregado que passou o turno atrás do processo da
    devolução não deixava rastro nenhum, e o do turno seguinte começava do
    zero, ligando de novo para o mesmo lugar.

    Três tipos, e a diferença entre eles é quanto se cobrou do piso:

    ``recebida``   o turno herdou a pendência e a encerrou sem resolver. É
                   gravada SOZINHA no fechamento, sem pedir nada a ninguém —
                   é o que faz "passou por N turnos" ser verdade mesmo para
                   quem não escreveu uma linha.
    ``tentativa``  o encarregado disse o que tentou e por que não deu.
    ``resolvida``  o fim da linha, com o que foi feito.

    ``turno_id`` é nulo quando o evento não nasce de uma passagem (o gestor
    resolvendo pelo dashboard, por exemplo).
    """
    __tablename__ = 'diario_operacional_pendencia_eventos'
    __table_args__ = (db.Index('ix_diario_pend_evento_pend_data', 'pendencia_id', 'created_at'),)
    id = db.Column(db.Integer, primary_key=True)
    pendencia_id = db.Column(db.Integer,
                             db.ForeignKey('diario_operacional_pendencias.id'),
                             nullable=False, index=True)
    turno_id = db.Column(db.Integer,
                         db.ForeignKey('diario_operacional_turnos.id'),
                         nullable=True, index=True)
    tipo = db.Column(db.String(20), nullable=False, default='recebida', index=True)
    texto = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pendencia = db.relationship('DiarioPendencia', backref=db.backref(
        'eventos', cascade='all, delete-orphan', lazy='selectin',
        order_by='DiarioPendenciaEvento.created_at'))


# Como a gestão quer a resposta. Não é enfeite: é o que separa "confere a
# temperatura da câmara" respondido com "ok" de respondido com "-18,4" — e só
# o segundo serve para alguma coisa depois.
RESPOSTA_SIM_NAO = 'sim_nao'
RESPOSTA_NUMERO = 'numero'
RESPOSTA_TEXTO = 'texto'

FORMAS_DE_RESPOSTA = {
    RESPOSTA_SIM_NAO: 'Sim ou não',
    RESPOSTA_NUMERO: 'Um número',
    RESPOSTA_TEXTO: 'Uma descrição',
}

TAREFA_TURNO_PENDENTE = 'pendente'
TAREFA_TURNO_FEITA = 'feita'
TAREFA_TURNO_VIROU_PENDENCIA = 'virou_pendencia'


class DiarioTarefaTurno(db.Model):
    """A tarefa que a GESTÃO manda para um turno específico.

    **Não é o checklist.** O checklist (``DiarioConfiguracao``) é a rotina
    permanente daquela área: vale todo dia, em todo turno, e mudá-lo muda a
    régua de aderência do contrato. Isto aqui é o contrário — é pontual:
    "no 2º turno de quinta, confira a temperatura da câmara fria depois da
    manutenção". Misturar as duas coisas obrigaria o gestor a cadastrar e
    descadastrar item de régua para pedir uma coisa só, e cada ida e volta
    dessas mexe na nota histórica do contrato.

    **A forma de resposta é do PEDIDO, não da resposta.** Quem pede é quem
    sabe o que vai fazer com o dado: "confira a temperatura" respondido com
    "ok" não serve para nada; respondido com "-18,4" entra em série. Por isso
    ela é escolhida na hora de atribuir, e a tela do turno monta o campo
    certo a partir dela.

    **Dois desfechos, e o segundo é o que dá valor.** O encarregado diz que
    FEZ (com a resposta) ou que aquilo VIROU PENDÊNCIA — e nesse caso nasce
    uma ``DiarioPendencia`` de verdade, ligada em ``pendencia_id``, que
    atravessa turnos e sobe para a Torre de Comando como qualquer outra. Sem
    essa segunda saída, o encarregado que não conseguiu fazer só teria a
    opção de mentir ou de deixar em branco.
    """
    __tablename__ = 'diario_operacional_tarefas_turno'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'),
                          nullable=False, index=True)
    # A ÁREA (modelo) é obrigatória: é ela que, junto de data e turno,
    # identifica a passagem em que a tarefa tem de aparecer. Sem ela a
    # tarefa cairia em todas as áreas do contrato ao mesmo tempo.
    configuracao_id = db.Column(
        db.Integer, db.ForeignKey('diario_operacional_configuracoes.id'),
        nullable=False, index=True)
    data_turno = db.Column(db.Date, nullable=False, index=True)
    turno = db.Column(db.String(50), nullable=False)

    titulo = db.Column(db.String(300), nullable=False)
    descricao = db.Column(db.Text)
    forma_resposta = db.Column(db.String(20), nullable=False,
                               default=RESPOSTA_SIM_NAO)

    status = db.Column(db.String(20), nullable=False,
                       default=TAREFA_TURNO_PENDENTE, index=True)
    # A resposta em texto, sempre — inclusive o número. Guardar "-18,4" como
    # Float obrigaria uma coluna por forma, e o que a operação escreve nem
    # sempre é número limpo ("-18,4 na sonda 2").
    resposta = db.Column(db.Text)
    pendencia_id = db.Column(
        db.Integer, db.ForeignKey('diario_operacional_pendencias.id'),
        nullable=True, index=True)

    criada_por = db.Column(db.Integer, db.ForeignKey('users.id'),
                           nullable=False)
    respondida_por = db.Column(db.Integer, db.ForeignKey('users.id'),
                               nullable=True)
    respondida_em = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # A leitura quente é sempre "o que a gestão mandou para ESTE turno",
        # feita a cada abertura da passagem.
        db.Index('ix_diario_tarefa_turno_alvo',
                 'client_id', 'configuracao_id', 'data_turno', 'turno'),
    )


class DiarioTurnoCorrecao(db.Model):
    """A correção de uma passagem já encerrada — o que mudou, e por quê.

    **Por que não se sobrescreve e pronto.** A passagem encerrada é a prova
    do que foi informado ao turno seguinte: é ela que responde, quando a
    devolução estoura na quinta, se a Tarde foi avisada. Deixar reescrever
    ontem em silêncio destrói exatamente esse valor — a passagem deixaria de
    provar qualquer coisa. Mas travar tudo também não serve: quem lançou no
    turno errado às 6h da manhã fica com o erro para sempre, e um sistema que
    não deixa consertar engano honesto ensina a operação a não registrar.

    A saída é a mesma do resto da casa: CORRIGE-SE COM RASTRO. O valor novo
    vale, o antigo fica guardado aqui, e a tela diz que houve correção. O
    ``motivo`` é obrigatório pela razão de sempre — correção que não custa
    uma frase vira, em duas semanas, um botão de reescrever o passado.

    ``antes_json`` guarda o estado anterior dos campos tocados. Não é
    histórico completo da passagem: é o que basta para alguém entender o que
    foi trocado sem precisar de backup do banco.
    """
    __tablename__ = 'diario_operacional_turno_correcoes'
    id = db.Column(db.Integer, primary_key=True)
    turno_id = db.Column(db.Integer,
                         db.ForeignKey('diario_operacional_turnos.id'),
                         nullable=False, index=True)
    motivo = db.Column(db.Text, nullable=False)
    # Os nomes dos campos trocados, separados por vírgula — para a tela
    # resumir "corrigiu turno e observação" sem abrir o JSON.
    campos = db.Column(db.String(200))
    antes_json = db.Column(db.Text, nullable=False, default='{}')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # `lazy='select'` e NÃO 'selectin', ao contrário da trilha da pendência.
    # A diferença é o padrão de acesso: a correção só é lida na tela de UMA
    # passagem, enquanto o painel lista vinte turnos por vez. Com 'selectin'
    # cada listagem pagava uma consulta a esta tabela para, quase sempre, não
    # mostrar nada — visto no navegador, no dashboard.
    turno = db.relationship('DiarioTurno', backref=db.backref(
        'correcoes', cascade='all, delete-orphan', lazy='select',
        order_by='DiarioTurnoCorrecao.created_at'))


class DiarioOcorrencia(db.Model):
    """O que aconteceu no turno — e não o que ficou pendente dele.

    A diferença com a pendência não é de grau, é de natureza: a pendência
    pede AÇÃO do próximo turno, a ocorrência é fato consumado. "Suspendi o
    colaborador X por indisciplina" não é tarefa de ninguém amanhã.

    ``gravidade`` existe porque parte desses fatos o gestor precisa LER, e
    hoje eles morrem dentro da passagem: o encarregado registra a suspensão
    e nada sobe. Marcada como crítica, a ocorrência vira ponto de atenção na
    Torre de Comando — de leitura, não de execução. Ela não entra na mesa P1/
    P2/P3 de propósito: a mesa é o que se faz hoje, e transformar um fato
    consumado em item de fazer criaria uma tarefa que ninguém pode fechar.
    """
    __tablename__ = 'diario_operacional_ocorrencias'
    __table_args__ = (
        db.Index('ix_diario_ocor_cliente_criacao', 'client_id', 'created_at'),
        db.Index('ix_diario_ocorrencia_cliente_gravidade', 'client_id', 'gravidade'),
    )
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    turno_id = db.Column(db.Integer, db.ForeignKey('diario_operacional_turnos.id'), nullable=True, index=True)
    tipo = db.Column(db.String(80), nullable=False, index=True)
    referencia = db.Column(db.String(120))
    descricao = db.Column(db.Text, nullable=False)
    # 'normal' | 'critica'. String, e não booleano, porque um terceiro nível
    # (o "grave" que não é crítico) é pedido plausível, e ele não deve custar
    # outra migração.
    gravidade = db.Column(db.String(20), nullable=False,
                          default=OCORRENCIA_NORMAL,
                          server_default=OCORRENCIA_NORMAL, index=True)
    status = db.Column(db.String(20), nullable=False, default='aberta', index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)
