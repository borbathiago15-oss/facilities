"""O analítico da Passagem de Turno — de contador a indicador.

A Fase 1 entregou o motor: configuração por contrato, passagem de turno,
pendência e ocorrência. O que ela mostrava na tela eram três contadores
(``turnos|length``, ``pendencias|length``, ``ocorrencias|length``) — números
que dizem quanto foi digitado, não como a operação está indo.

Este módulo é a camada que responde às perguntas do Encarregado, do
Supervisor e da Diretoria:

* a rotina obrigatória do contrato está sendo cumprida? (aderência)
* o que um turno deixa para o outro volta resolvido? (resolução)
* o que está apodrecendo na fila agora? (crítico e vencido)
* a operação gera quantos desvios por turno, e em qual turno?

Fica separado de ``trino.web.diario_operacional`` de propósito: aqui não há
Flask, sessão nem request — só funções que recebem ``client_id`` e uma janela
de datas e devolvem números. É o que permite testar cada fórmula sem subir
uma tela, e é onde o custo de consulta fica visível num lugar só.

**A régua das contas** (as decisões que uma tela não consegue explicar):

* **Só turno ENCERRADO conta — e o que ele lançou também não.** Um turno
  aberto é rascunho: o encarregado ainda vai marcar o resto do checklist,
  apagar a pendência que resolveu antes de sair, reescrever a ocorrência.
  Contá-lo como reprovado puniria a operação pelo relógio, não pelo
  trabalho; e contar a pendência e a ocorrência dele faria o indicador
  mudar a cada "Salvar rascunho". Ver ``_fora_do_rascunho``.
* **Ocorrência é do DIA DO TURNO, não do dia em que foi digitada.** O 3º
  Turno de terça lança à 01h de quarta; datar pelo ``created_at`` jogava a
  ocorrência no dia (e às vezes no mês) seguinte, longe do turno que ela
  descreve. Ver ``_ocorrencias_com_turno``.
* **A exigência vem da configuração DAQUELE turno**, via ``configuracao_id``,
  não da configuração ativa hoje. Renegociar o checklist em setembro não
  reescreve o que março cobrava — a mesma regra que o SLA Contratual já
  aplica às medições congeladas.
* **Pendência é medida por safra (coorte).** O denominador é o que foi ABERTO
  na janela; o numerador, quantas dessas já foram baixadas. É o único
  recorte que não passa de 100% e que casa com o subtítulo "X abertas | Y
  resolvidas". Pelo recorte de fluxo (baixadas na janela ÷ abertas na janela)
  um mutirão de backlog daria 300% e ninguém saberia ler.
* **O cartão de crítico/vencido ignora a janela.** Pendência velha em aberto
  é problema de hoje, não do recorte que se está olhando: escondê-la porque
  nasceu fora dos últimos 7 dias seria exatamente o erro que o cartão existe
  para evitar.
"""
import json
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from facilities import tempo
from facilities.passagem.models import (
    DiarioConfiguracao, DiarioTurno, DiarioPendencia, DiarioOcorrencia,
    DiarioTarefaTurno, OCORRENCIA_CRITICA,
)

# Meta padrão da casa para o cumprimento do checklist do turno.
META_ADERENCIA = 95.0
FAIXA_ATENCAO = 85.0
# Prefixo com que a tela de turno grava cada atividade dentro de ``dados_json``
# (ver ``static/js/diario_operacional.js``): ``atividade:<codigo>``.
PREFIXO_ATIVIDADE = 'atividade:'
# Onde o turno guarda a régua que valia no dia em que foi encerrado. Chave
# reservada em ``dados_json``: começa com ``_`` justamente para não colidir
# com o código de nenhum campo configurado (os códigos nascem de
# ``nome.toLowerCase().replace(/[^a-z0-9]+/g,'_')``, que nunca começa com
# ``_`` a menos que o nome comece com pontuação — e ainda assim não seria
# ``_exigidas``).
CHAVE_EXIGIDAS = '_exigidas'
# A marca do envio que gravou o turno por último (o app sem internet manda a
# mesma marca quando reenvia). É o que faz o servidor reconhecer "esse
# encerramento já chegou" em vez de responder "já foi encerrada" ao próprio
# autor. Reservada pelo mesmo motivo da de cima.
CHAVE_ENVIO = '_envio'
# A partir de quantas horas uma pendência aberta passa a ser cobrada.
HORAS_PARA_VENCER = 24

# O banco guarda a prioridade sem acento ('media'); a tela e o PDF escrevem
# em português. ``|title`` não resolve — devolveria "Media".
ROTULO_PRIORIDADE = {'baixa': 'Baixa', 'media': 'Média', 'alta': 'Alta'}


def rotulo_prioridade(valor):
    bruto = (valor or '').strip().lower()
    return ROTULO_PRIORIDADE.get(bruto, bruto.title() or '—')


PERIODOS = OrderedDict([
    ('hoje', 'Hoje'),
    ('7d', 'Últimos 7 dias'),
    ('30d', 'Últimos 30 dias'),
    ('mes', 'Mês atual'),
    ('custom', 'Personalizado'),
])


def _carrega(texto, padrao):
    """JSON gravado em coluna Text → objeto. Texto corrompido não derruba a tela."""
    try:
        valor = json.loads(texto or '')
    except (ValueError, TypeError):
        return padrao
    return valor if isinstance(valor, type(padrao)) else padrao


def janela(periodo, de=None, ate=None, hoje=None):
    """O recorte de datas escolhido no topo da tela → (inicio, fim, rótulo).

    Sempre devolve um par de ``date`` inclusivo nas duas pontas. Data inicial
    depois da final é invertida em silêncio: é erro de digitação, não motivo
    para negar a tela.
    """
    hoje = hoje or tempo.hoje()
    if periodo == 'hoje':
        return hoje, hoje, 'Hoje'
    if periodo == '30d':
        return hoje - timedelta(days=29), hoje, 'Últimos 30 dias'
    if periodo == 'mes':
        return hoje.replace(day=1), hoje, 'Mês atual'
    if periodo == 'custom':
        inicio = de if isinstance(de, date) else hoje - timedelta(days=6)
        fim = ate if isinstance(ate, date) else hoje
        if inicio > fim:
            inicio, fim = fim, inicio
        rotulo = f'{inicio.strftime("%d/%m/%Y")} a {fim.strftime("%d/%m/%Y")}'
        return inicio, fim, rotulo
    return hoje - timedelta(days=6), hoje, 'Últimos 7 dias'


def _limites_do_dia(inicio, fim):
    """Janela de dias LOCAIS → par de ``datetime`` UTC ingênuo.

    ``created_at`` é gravado com ``datetime.utcnow`` (UTC, sem fuso), mas o
    dia que a pessoa escolhe na tela é o dia de Brasília. Comparar um com o
    outro sem converter custa três horas — e três horas, num diário de TURNO,
    é exatamente o T3: uma ocorrência lançada às 23h de terça é 02h de
    quarta em UTC e sumiria do recorte "Hoje" de terça.

    Por isso a borda é convertida: meia-noite local do primeiro dia e o
    último instante local do último dia, ambos trazidos para UTC.
    """
    def _para_utc(momento):
        return (momento.replace(tzinfo=tempo.FUSO)
                .astimezone(timezone.utc).replace(tzinfo=None))

    return (_para_utc(datetime.combine(inicio, datetime.min.time())),
            _para_utc(datetime.combine(fim, datetime.max.time())))


def nasceu_em(pendencia, origem=None):
    """Desde quando o problema existe — que não é o mesmo que "desde quando
    foi digitado".

    ``created_at`` é o carimbo do banco: a hora em que alguém abriu a tela e
    lançou. Quase sempre é o fim do próprio turno, e aí os dois coincidem.
    Mas lançar atrasado é rotina no armazém — esqueceu de fechar a Tarde de
    ontem e fecha hoje de manhã — e nesse caso a idade da pendência sairia
    um dia menor do que o problema realmente tem.

    Quando o turno de origem é de um dia ANTERIOR ao do lançamento, a âncora
    passa a ser o último instante daquele dia. É o mais conservador de
    propósito: a pendência nasceu em algum momento daquele turno, e escolher
    o fim do dia SUBESTIMA a idade em vez de superestimar — o cartão de
    vencidas nunca acusa a operação de mais tempo do que ela deve.
    """
    carimbo = pendencia.created_at
    if origem is None or not getattr(origem, 'data_turno', None) or not carimbo:
        return carimbo
    dia_do_lancamento = tempo.local(carimbo).date()
    if origem.data_turno >= dia_do_lancamento:
        return carimbo
    _de, fim_do_dia = _limites_do_dia(origem.data_turno, origem.data_turno)
    return fim_do_dia


TODAS_AS_AREAS = 0


def areas_do_contrato(client_id, apenas_ativas=True):
    """As áreas cadastradas do contrato, em ordem de nome.

    Um contrato tem mais de uma área e cada uma passa o turno do seu jeito
    (na PepsiCo Fábrica Recife, Expedição e Almoxarifado; no Novo Atacarejo
    Moreno, cerca de dez). Contrato sem área cadastrada devolve lista vazia,
    e a tela então não mostra seletor nenhum.
    """
    from facilities.passagem.models import (
        DiarioArea)
    q = DiarioArea.query.filter(DiarioArea.client_id == client_id)
    if apenas_ativas:
        q = q.filter(DiarioArea.ativo.is_(True))
    return q.order_by(DiarioArea.nome.asc()).all()


def _configs_da_area(client_id, area_id):
    """Ids dos modelos daquela área. ``None`` = não filtrar por área.

    Devolve lista VAZIA quando a área não tem modelo nenhum — e quem chama
    tem de tratar isso como "nenhum turno", não como "todos". Confundir os
    dois faria um filtro de área recém-criada mostrar o contrato inteiro.
    """
    if not area_id or area_id == TODAS_AS_AREAS:
        return None
    return [c.id for c in DiarioConfiguracao.query
            .with_entities(DiarioConfiguracao.id)
            .filter(DiarioConfiguracao.client_id == client_id,
                    DiarioConfiguracao.area_id == int(area_id)).all()]


def turnos_da_janela(client_id, inicio, fim, turno=None, apenas_encerrados=True,
                     area_id=None):
    """Os turnos do contrato na janela, opcionalmente de um turno/área só."""
    q = (DiarioTurno.query
         .filter(DiarioTurno.client_id == client_id,
                 DiarioTurno.data_turno >= inicio,
                 DiarioTurno.data_turno <= fim))
    if apenas_encerrados:
        q = q.filter(DiarioTurno.status == 'encerrado')
    if turno and turno != 'todos':
        q = q.filter(DiarioTurno.turno == turno)
    ids = _configs_da_area(client_id, area_id)
    if ids is not None:
        if not ids:
            return []
        q = q.filter(DiarioTurno.configuracao_id.in_(ids))
    return q.order_by(DiarioTurno.data_turno.asc(), DiarioTurno.id.asc()).all()


# O status que libera a passagem — e tudo o que ela lançou — para os
# indicadores.
TURNO_ENCERRADO = 'encerrado'


def _fora_do_rascunho(modelo, client_id):
    """Critério SQL: esta pendência/ocorrência já pode entrar num indicador?

    Entra o que nasceu de passagem ENCERRADA e o que não nasceu de passagem
    nenhuma (``turno_id`` nulo: a pendência que a gestão abriu pelo painel,
    a tarefa do turno que virou pendência). Fica de fora o que está dentro
    de um RASCUNHO.

    O porquê é a mesma régua da aderência: rascunho é trabalho em andamento.
    A pendência lançada no "Salvar rascunho" ainda pode ser resolvida pelo
    próprio turno antes de sair, a ocorrência ainda pode ser reescrita — e o
    painel dizia "turno em aberto não entra nos indicadores" enquanto a taxa
    de resolução, o cartão de vencidas, o Pareto e a Torre contavam tudo o
    que o rascunho tinha. Quando o turno encerra, o que ele lançou passa a
    contar sozinho, sem ninguém regravar nada.

    É uma subconsulta, não uma lista de ids em Python: o número de turnos
    encerrados de um contrato cresce todo dia, e trazê-los para a memória a
    cada tela custaria mais do que a própria conta.
    """
    encerrados = (select(DiarioTurno.id)
                  .where(DiarioTurno.client_id == client_id,
                         DiarioTurno.status == TURNO_ENCERRADO))
    criterio = or_(modelo.turno_id.is_(None), modelo.turno_id.in_(encerrados))
    if modelo is DiarioPendencia:
        # A pendência do "Não deu" respondido ANTES de a passagem ser salva
        # nasce sem turno — e, sem esta linha, entrava na hora no painel e
        # como P1 na Torre, enquanto a do mesmo "Não deu" respondido depois
        # do primeiro rascunho ficava escondida. As duas são a mesma coisa:
        # trabalho de uma passagem que ainda não saiu — e as duas esperam o
        # mesmo prazo: passado ele, contam mesmo que a passagem nunca tenha
        # saído (a do rascunho abandonado não pode sumir para sempre).
        criterio = or_(
            and_(criterio,
                 modelo.id.notin_(pendencias_aguardando_passagem(client_id))),
            modelo.id.in_(pendencias_de_tarefa_vencidas(client_id)))
    return criterio


# Quanto tempo a pendência do "Não deu" espera pela passagem do turno dela.
# Se ninguém encerrar aquela passagem, ela não pode sumir para sempre: depois
# disso vale como pendência do contrato, igual à aberta pela gestão.
DIAS_DE_ESPERA_DA_TAREFA = 2


def pendencias_de_tarefa_vencidas(client_id, hoje=None):
    """Subconsulta: pendências do "Não deu" que já esperaram demais.

    A tarefa é de um dia que passou há mais de ``DIAS_DE_ESPERA_DA_TAREFA``
    dias. A pendência dela conta e é carregada esteja onde estiver: sem
    turno (vale como do contrato) ou presa a um RASCUNHO que ninguém
    encerrou (vale como da área daquele rascunho). Sem isto, o "Não deu"
    respondido depois de "Salvar rascunho" num turno que nunca encerrou
    ficava fora de todo indicador para sempre — e o mesmo "Não deu"
    respondido antes do rascunho voltava a contar em dois dias. A ordem de
    dois cliques decidia se o pedido da gestão sumia.
    """
    hoje = hoje or tempo.hoje()
    return (select(DiarioTarefaTurno.pendencia_id)
            .where(DiarioTarefaTurno.client_id == client_id,
                   DiarioTarefaTurno.pendencia_id.isnot(None),
                   DiarioTarefaTurno.data_turno
                   < hoje - timedelta(days=DIAS_DE_ESPERA_DA_TAREFA)))


def pendencias_aguardando_passagem(client_id, hoje=None):
    """Subconsulta: pendências do "Não deu" cuja passagem ainda não chegou.

    São as que a tarefa da gestão gerou (``DiarioTarefaTurno.pendencia_id``)
    e que ainda não têm turno de origem — no encerramento da passagem
    daquela chave elas ganham o turno (``_tarefas_no_encerramento``) e daí
    em diante seguem a régua de sempre. Enquanto esperam, ficam fora dos
    indicadores e ninguém as "recebe": outra área encerrando não carrega o
    que a Expedição ainda nem entregou, e o aviso de pendência parada não
    dispara minutos depois de ela nascer.

    ``pendencia_id IS NOT NULL`` não é enfeite: é o que permite usar esta
    subconsulta num NOT IN sem que um NULO anule a comparação inteira.
    """
    hoje = hoje or tempo.hoje()
    return (select(DiarioTarefaTurno.pendencia_id)
            .join(DiarioPendencia, DiarioPendencia.id == DiarioTarefaTurno.pendencia_id)
            .where(DiarioTarefaTurno.client_id == client_id,
                   DiarioTarefaTurno.pendencia_id.isnot(None),
                   DiarioPendencia.turno_id.is_(None),
                   DiarioTarefaTurno.data_turno
                   >= hoje - timedelta(days=DIAS_DE_ESPERA_DA_TAREFA)))


def _dia_da_ocorrencia(ocorrencia, turno):
    """O dia a que a ocorrência pertence: o DIA DO TURNO que a lançou.

    O ``created_at`` é a hora da digitação, e o 3º Turno digita depois da
    meia-noite: a ocorrência do 3º Turno de 15/10 nasce às 01h de 16/10 e,
    datada assim, aparecia como "16/10 · 3º Turno" — um turno que naquele
    dia ainda nem tinha começado. Ocorrência avulsa (sem turno) não tem
    outro relógio; para ela vale o dia LOCAL da digitação.
    """
    if turno is not None and getattr(turno, 'data_turno', None):
        return turno.data_turno
    if ocorrencia.created_at is None:
        return None
    return tempo.local(ocorrencia.created_at).date()


def _ocorrencias_com_turno(client_id, inicio, fim, turno=None, area_id=None):
    """``[(ocorrência, turno de origem ou None)]`` da janela, mais recente antes.

    A janela é a do DIA DO TURNO (ver ``_dia_da_ocorrencia``). Antes ela era
    a do ``created_at``, e cada tela recortava de um jeito: o cartão do
    índice selecionava pelo ``created_at`` e o gráfico entre turnos casava
    essas ocorrências com os turnos da janela pelo ``data_turno`` — a do 3º
    Turno de 30/09 digitada em 01/10 entrava no cartão de outubro e sumia do
    gráfico (22 contra 21), e o relatório do mês somava 49 no contrato e
    33 + 15 nas áreas. Uma régua só, aqui, e todos leem dela.

    O turno de origem vem na MESMA consulta (junção), porque quem lista
    precisa do dia e do nome dele — uma consulta por linha seria N+1 no
    relatório do mês inteiro.

    Filtrar por turno ou por área exige o vínculo ``turno_id`` — ocorrência
    avulsa (sem turno) fica de fora nesse caso, porque não há como afirmar de
    qual turno nem de qual área ela é. Ocorrência de turno em rascunho fica
    de fora sempre (ver ``_fora_do_rascunho``).
    """
    do_turno = [DiarioTurno.client_id == client_id,
                DiarioTurno.status == TURNO_ENCERRADO,
                DiarioTurno.data_turno >= inicio,
                DiarioTurno.data_turno <= fim]
    if turno and turno != 'todos':
        do_turno.append(DiarioTurno.turno == turno)
    ids = _configs_da_area(client_id, area_id)
    if ids is not None:
        if not ids:
            return []
        do_turno.append(DiarioTurno.configuracao_id.in_(ids))
    criterio = and_(*do_turno)
    recorta = (turno and turno != 'todos') or ids is not None
    if not recorta:
        de, ate = _limites_do_dia(inicio, fim)
        criterio = or_(criterio, and_(DiarioOcorrencia.turno_id.is_(None),
                                      DiarioOcorrencia.created_at >= de,
                                      DiarioOcorrencia.created_at <= ate))
    pares = (DiarioOcorrencia.query
             .outerjoin(DiarioTurno, DiarioTurno.id == DiarioOcorrencia.turno_id)
             .add_entity(DiarioTurno)
             .filter(DiarioOcorrencia.client_id == client_id, criterio)
             .all())
    # A ordem é feita aqui e não no SQL: a avulsa não tem ``data_turno``, e
    # onde o NULL cai num ORDER BY muda do SQLite dos testes para o Postgres.
    pares.sort(key=lambda par: (_dia_da_ocorrencia(*par) or date.min,
                                par[0].created_at or datetime.min,
                                par[0].id or 0),
               reverse=True)
    return [(o, t) for o, t in pares]


def _exigencias_por_configuracao(config_ids):
    """``{configuracao_id: [atividade obrigatória, ...]}`` — uma consulta só.

    Sem isto a aderência faria um SELECT de configuração por turno: 90 turnos
    no fechamento do mês eram 90 idas ao banco para ler quatro linhas de JSON.
    """
    if not config_ids:
        return {}
    cfgs = (DiarioConfiguracao.query
            .filter(DiarioConfiguracao.id.in_(list(config_ids))).all())
    mapa = {}
    for cfg in cfgs:
        obrig = [a for a in _carrega(cfg.atividades_json, [])
                 if isinstance(a, dict) and a.get('obrigatorio') is not False]
        mapa[cfg.id] = obrig
    return mapa


def exigidas_do_turno(turno, exigencias, dados=None):
    """O que ESTE turno tinha de cumprir — a régua congelada, não a de hoje.

    Mesma regra do SLA Contratual: a medição congela meta, tolerância e peso
    do momento em que foi lançada, e renegociar em setembro não reescreve
    março. Aqui o que se congela é a lista de atividades obrigatórias.

    Sem isto o histórico era reescrito em silêncio: acrescentar duas rotinas
    ao checklist derrubava um turno passado, que tinha cumprido tudo o que
    lhe foi pedido, de 100% para 50% — sem ninguém tocar naquele turno. O
    encarregado fazia tudo certo e o relatório do mês dizia que não.

    Turno lançado ANTES deste congelamento existir não tem a chave; para ele
    ainda se lê a configuração atual, que é a melhor informação disponível.
    Não dá para inventar retroativamente o que o checklist pedia num dia em
    que ninguém anotou.
    """
    dados = _carrega(turno.dados_json, {}) if dados is None else dados
    congelado = dados.get(CHAVE_EXIGIDAS)
    if isinstance(congelado, list):
        return [a for a in congelado if isinstance(a, dict)]
    return exigencias.get(turno.configuracao_id) or []


def _chave(atividade):
    """A chave com que o turno grava a atividade em ``dados_json``."""
    if isinstance(atividade, dict):
        return atividade.get('codigo') or atividade.get('nome') or ''
    return str(atividade or '')


def _rotulo(atividade):
    if isinstance(atividade, dict):
        return atividade.get('nome') or atividade.get('codigo') or '—'
    return str(atividade or '—')


def _concluida(dados, chave):
    """A atividade foi marcada como concluída neste turno?

    Aceita as duas formas que já existem em banco: o dicionário
    ``{'concluido': true}`` que a tela grava hoje e o booleano solto que um
    lançamento antigo (ou uma integração futura) pode ter deixado.
    """
    valor = dados.get(PREFIXO_ATIVIDADE + chave)
    if valor is None:
        return False
    if isinstance(valor, dict):
        return bool(valor.get('concluido'))
    return bool(valor)


def aderencia(turnos, exigencias):
    """Cumprimento do checklist obrigatório → (pct, cumpridas, exigidas).

    ``pct`` é ``None`` quando nada era exigido: zero de zero não é 0%, é
    "não se aplica", e mostrar 0% acenderia um alarme falso em contrato que
    ainda não tem rotina cadastrada.
    """
    exigidas = cumpridas = 0
    for t in turnos:
        dados = _carrega(t.dados_json, {})
        obrigatorias = exigidas_do_turno(t, exigencias, dados)
        if not obrigatorias:
            continue
        exigidas += len(obrigatorias)
        cumpridas += sum(1 for a in obrigatorias
                         if _concluida(dados, _chave(a)))
    pct = round(cumpridas * 100.0 / exigidas, 1) if exigidas else None
    return pct, cumpridas, exigidas


def faixa_aderencia(pct):
    """Cor do semáforo da aderência: verde ≥95, amarelo 85–94,9, vermelho <85."""
    if pct is None:
        return 'neutro'
    if pct >= META_ADERENCIA:
        return 'ok'
    if pct >= FAIXA_ATENCAO:
        return 'alerta'
    return 'critico'


def raio_x_das_rotinas(turnos, exigencias, configs_por_id=None):
    """Uma linha por atividade: quanto foi exigido, quanto foi cumprido, e a %.

    É o detalhe que o cartão de aderência esconde — 91% de aderência pode ser
    tudo quase perfeito com uma rotina abandonada, e é a rotina abandonada que
    vira ocorrência no mês seguinte.
    """
    acumulado = OrderedDict()
    for t in turnos:
        dados = _carrega(t.dados_json, {})
        obrigatorias = exigidas_do_turno(t, exigencias, dados)
        if not obrigatorias:
            continue
        for a in obrigatorias:
            chave = _chave(a)
            linha = acumulado.setdefault(
                chave, {'codigo': chave, 'nome': _rotulo(a),
                        'exigida': 0, 'cumprida': 0})
            linha['exigida'] += 1
            if _concluida(dados, chave):
                linha['cumprida'] += 1
    linhas = []
    for linha in acumulado.values():
        pct = round(linha['cumprida'] * 100.0 / linha['exigida'], 1) if linha['exigida'] else None
        linhas.append({**linha, 'pct': pct, 'faixa': faixa_aderencia(pct)})
    # Pior primeiro: o painel existe para achar o gargalo, não para elogiar.
    linhas.sort(key=lambda x: (x['pct'] if x['pct'] is not None else 999,
                               x['nome']))
    return linhas


def pendencias_da_janela(client_id, inicio, fim):
    """Pendências ABERTAS na janela (a safra), já com o desfecho de cada uma.

    A do turno em rascunho fica fora até o turno encerrar (ver
    ``_fora_do_rascunho``); a da gestão, que não tem turno, conta sempre.
    """
    de, ate = _limites_do_dia(inicio, fim)
    return (DiarioPendencia.query
            .filter(DiarioPendencia.client_id == client_id,
                    DiarioPendencia.created_at >= de,
                    DiarioPendencia.created_at <= ate,
                    _fora_do_rascunho(DiarioPendencia, client_id))
            .order_by(DiarioPendencia.created_at.asc()).all())


def resolucao_de_pendencias(client_id, inicio, fim):
    """Eficácia da safra: das que nasceram na janela, quantas foram baixadas."""
    safra = pendencias_da_janela(client_id, inicio, fim)
    abertas = len(safra)
    resolvidas = sum(1 for p in safra if p.status == 'resolvida')
    pct = round(resolvidas * 100.0 / abertas, 1) if abertas else None
    return {'pct': pct, 'abertas': abertas, 'resolvidas': resolvidas,
            'faixa': faixa_aderencia(pct)}


def criticas_e_vencidas(client_id, agora=None):
    """Pendências abertas de prioridade alta OU paradas há mais de 24h.

    Deliberadamente fora da janela de datas — ver a régua no topo do módulo.
    Mas não fora da régua do rascunho: a pendência que o turno ainda não
    entregou não acende o cartão nem o P1 da Torre (ver
    ``_fora_do_rascunho``). Ela passa a contar no encerramento, com a idade
    desde a criação — o tempo de rascunho não é perdoado, só não é cobrado
    antes de a passagem existir.
    """
    agora = agora or datetime.utcnow()
    corte = agora - timedelta(hours=HORAS_PARA_VENCER)
    abertas = (DiarioPendencia.query
               .filter(DiarioPendencia.client_id == client_id,
                       DiarioPendencia.status == 'aberta',
                       _fora_do_rascunho(DiarioPendencia, client_id))
               .order_by(DiarioPendencia.created_at.asc()).all())
    # A idade sai da mesma âncora que a fila da tela do piso usa (ver
    # ``nasceu_em``); os dois números precisam ser o mesmo número.
    ids_turno = {p.turno_id for p in abertas if p.turno_id}
    origens = {t.id: t for t in DiarioTurno.query
               .filter(DiarioTurno.id.in_(list(ids_turno))).all()} if ids_turno else {}
    fila = []
    for p in abertas:
        alta = (p.prioridade or '').lower() == 'alta'
        nascimento = nasceu_em(p, origens.get(p.turno_id))
        vencida = bool(nascimento and nascimento <= corte)
        if alta or vencida:
            horas = ((agora - nascimento).total_seconds() / 3600.0
                     if nascimento else 0.0)
            fila.append({'pendencia': p, 'alta': alta, 'vencida': vencida,
                         'horas': int(horas), 'dias': int(horas // 24)})
    # Mais velha primeiro: é a que já custou mais turno.
    fila.sort(key=lambda x: -x['horas'])
    return fila


def fila_de_pendencias(client_id, agora=None):
    """As pendências abertas do contrato, prontas para a tela do piso.

    A consulta não tem corte de data de propósito: pendência aberta é
    pendência aberta, tenha nascido ontem ou há três semanas. É o que faz a
    devolução cujo processo ninguém achou reaparecer na passagem seguinte até
    alguém baixá-la.

    O que a tela não conseguia dizer antes, e agora diz em cada linha:

    * **de onde veio** — o turno e o dia que a abriram. Sem isso o rótulo
      "recebida do turno anterior" mentia para tudo que tivesse mais de um
      dia.
    * **há quanto tempo está aberta** — uma de cinco dias tinha exatamente a
      mesma cara de uma de duas horas.
    * **por quantos turnos já passou** — o tamanho da trilha. É o número que
      transforma "está demorando" em "seis turnos tentaram e não resolveram".
      Conta POR ÁREA: ver ``passagens_das_pendencias``.
    * **o que já se tentou** — a última tentativa registrada, para que o
      turno seguinte não refaça o caminho que o anterior já fez.

    São cinco consultas fixas (pendências, turnos de origem, eventos da
    trilha, áreas dos turnos e as tentativas): nenhuma cresce com o tamanho
    da fila.
    """
    from facilities.passagem.models import (
        DiarioPendenciaEvento)

    agora = agora or datetime.utcnow()
    abertas = (DiarioPendencia.query
               .filter(DiarioPendencia.client_id == client_id,
                       DiarioPendencia.status == 'aberta')
               .order_by(DiarioPendencia.created_at.asc()).all())
    if not abertas:
        return []

    ids_turno = {p.turno_id for p in abertas if p.turno_id}
    origens = {t.id: t for t in DiarioTurno.query
               .filter(DiarioTurno.id.in_(list(ids_turno))).all()} if ids_turno else {}
    # TURNOS distintos, não eventos: um mesmo turno que anota o que tentou e
    # depois encerra deixa dois registros, e contá-los como dois faria a tela
    # dizer "passou por 2 turnos" quando passou por um. Evento sem turno
    # (quem agiu antes de a passagem existir no banco) não conta passagem
    # nenhuma — ele conta como o que é, uma anotação. E só contam os turnos
    # da ÁREA de onde a pendência veio (a mesma conta do aviso de pendência
    # parada — por isso ela mora numa função só).
    passagens = passagens_das_pendencias(abertas)

    # A última tentativa vai NO CARTÃO, não escondida num relatório. É a
    # razão de a trilha existir: sem ela na tela de entrada, o encarregado do
    # turno seguinte liga de novo para o mesmo CD de origem que o anterior já
    # ligou, e a trilha vira arquivo morto em vez de ferramenta de trabalho.
    tentativas = (DiarioPendenciaEvento.query
                  .filter(DiarioPendenciaEvento.pendencia_id.in_(
                      [p.id for p in abertas]),
                      DiarioPendenciaEvento.tipo == 'tentativa')
                  .order_by(DiarioPendenciaEvento.created_at.asc(),
                            DiarioPendenciaEvento.id.asc()).all())
    nomes = _nomes_de_usuario({e.created_by for e in tentativas})
    ultima = {}
    for e in tentativas:                      # a mais recente sobrescreve
        if (e.texto or '').strip():
            ultima[e.pendencia_id] = {'texto': e.texto.strip(),
                                      'quem': nomes.get(e.created_by, '—'),
                                      'quando': e.created_at}

    fila = []
    for p in abertas:
        origem = origens.get(p.turno_id)
        nascimento = nasceu_em(p, origem)
        horas = ((agora - nascimento).total_seconds() / 3600.0
                 if nascimento else 0.0)
        fila.append({
            'pendencia': p, 'id': p.id, 'titulo': p.titulo,
            'referencia': p.referencia or '', 'descricao': p.descricao or '',
            'prioridade': (p.prioridade or 'media').lower(),
            'origem_turno': origem.turno if origem else '',
            'origem_data': origem.data_turno if origem else None,
            'horas': int(horas), 'dias': int(horas // 24),
            'vencida': horas >= HORAS_PARA_VENCER,
            'alta': (p.prioridade or '').lower() == 'alta',
            'passagens': int(passagens.get(p.id, 0)),
            'ultima_tentativa': ultima.get(p.id),
        })
    # Mais velha no topo: é a que já custou mais turno.
    fila.sort(key=lambda x: -x['horas'])
    return fila


# ── A área do turno e a contagem de passagens por área ──────────────────
#
# Um contrato tem mais de uma área passando turno (Expedição e Almoxarifado
# no mesmo 1º Turno). Antes, toda passagem encerrada, de QUALQUER área,
# gravava "recebida" em todas as pendências abertas do contrato — e a conta
# "passou por N turnos" somava as passagens de todas as áreas. Na demo isso
# virou "aberta há 5 dias · passou por 25 turnos": o Almoxarifado nunca
# recebeu a devolução da Expedição, mas a trilha dizia que sim, e o aviso de
# pendência parada disparava pela soma das áreas, não pelo descaso de uma.
#
# A regra agora: a pendência é carregada pela ÁREA de onde veio. Quem a
# abriu foi um turno da Expedição; quem a recebe é o turno seguinte da
# Expedição. A pendência sem área de origem é do contrato, e qualquer área a
# carrega: a aberta pela gestão no dashboard (sem turno) e a aberta por um
# modelo sem área (``AREA_DO_CONTRATO``).
#
# "Tentativa" e "resolvida" valem de qualquer área: alguém do Almoxarifado
# que ligou para o CD atrás da devolução da Expedição TRABALHOU nela, e isso
# não pode sumir da trilha só porque ele estava em outro setor.


# A área "do contrato": a de todo modelo sem área ATIVA — o contrato que
# nunca dividiu a operação, o modelo antigo de antes da área existir, o
# modelo cuja área foi desativada.
AREA_DO_CONTRATO = ('contrato', 0)


def chave_da_area(area_id, configuracao_id):
    """A área de um turno, como chave comparável.

    É o ``area_id`` do modelo — o EFETIVO: quem chama passa ``None`` quando
    a área do modelo está desativada (``areas_dos_turnos`` e
    ``chaves_dos_modelos`` já fazem isso). Modelo sem área efetiva é da área
    "do contrato" (``AREA_DO_CONTRATO``) — todos juntos. É assim que a tela
    os trata: sem área ativa, a nova passagem oferece esses modelos juntos e
    escolhe o modelo pelo turno (o CD com um modelo para o T1, outro para o
    T2...). Separá-los fazia o T2 nunca "receber" a pendência do T1: o
    "passou por N" subia uma vez por dia e o aviso de parada atrasava três
    dias. Contrato com operações de fato separadas cadastra as áreas.

    O prefixo na tupla impede que uma área cadastrada colida com a área do
    contrato por coincidência de numeração. ``configuracao_id`` fica na
    assinatura porque quem chama sempre tem os dois à mão.
    """
    if area_id:
        return ('area', area_id)
    return AREA_DO_CONTRATO


def chaves_dos_modelos(client_id):
    """``{configuracao_id: chave da área}`` de TODOS os modelos do contrato.

    Inclui os modelos inativos — a passagem antiga continua sendo da área do
    modelo que a lançou — e lê a área efetiva: área desativada vira a área
    do contrato, como na tela.
    """
    from facilities.passagem.models import (
        DiarioArea)
    linhas = (DiarioConfiguracao.query
              .outerjoin(DiarioArea, DiarioArea.id == DiarioConfiguracao.area_id)
              .with_entities(DiarioConfiguracao.id, DiarioConfiguracao.area_id,
                             DiarioArea.ativo)
              .filter(DiarioConfiguracao.client_id == client_id).all())
    return {cid: chave_da_area(aid if ativa else None, cid)
            for cid, aid, ativa in linhas}


def areas_dos_turnos(turno_ids):
    """``{turno_id: chave da área}`` em UMA consulta (turno + modelo + área).

    A área desativada conta como área do contrato (ver ``chave_da_area``).
    """
    from facilities.passagem.models import (
        DiarioArea)
    ids = {i for i in (turno_ids or ()) if i}
    if not ids:
        return {}
    linhas = (DiarioTurno.query
              .outerjoin(DiarioConfiguracao,
                         DiarioConfiguracao.id == DiarioTurno.configuracao_id)
              .outerjoin(DiarioArea, DiarioArea.id == DiarioConfiguracao.area_id)
              .with_entities(DiarioTurno.id, DiarioTurno.configuracao_id,
                             DiarioConfiguracao.area_id, DiarioArea.ativo)
              .filter(DiarioTurno.id.in_(list(ids))).all())
    return {tid: chave_da_area(area_id if ativa else None, cfg_id)
            for tid, cfg_id, area_id, ativa in linhas}


def area_do_turno(turno):
    """A área de UM turno já carregado — ver ``chave_da_area``."""
    from facilities.passagem.models import (
        DiarioArea)
    if turno is None:
        return None
    cfg = (DiarioConfiguracao.query.get(turno.configuracao_id)
           if turno.configuracao_id else None)
    area_id = cfg.area_id if cfg is not None else None
    if area_id:
        area = DiarioArea.query.get(area_id)
        if area is None or not area.ativo:
            area_id = None
    return chave_da_area(area_id, turno.configuracao_id)


def area_de_origem(turno_origem_id, areas):
    """A área de onde a pendência veio; ``None`` = do contrato inteiro.

    ``None`` quando a pendência não tem turno de origem (a gestão a abriu
    pelo dashboard) — e também quando o turno de origem não aparece no mapa:
    sem saber a área, restringir faria a pendência nunca mais atravessar
    turno nenhum, parada para sempre sem que o aviso de parada disparasse.
    """
    if not turno_origem_id:
        return None
    return areas.get(turno_origem_id)


def area_carrega(area_origem, area):
    """A passagem desta ``area`` carrega a pendência vinda de ``area_origem``?

    Carrega a da própria área e a que é do contrato inteiro: sem área de
    origem (``None``, a da gestão) ou aberta por modelo sem área
    (``AREA_DO_CONTRATO``). Esta última não pode ficar presa à "área do
    contrato": no contrato que já se dividiu em áreas, nenhuma passagem da
    tela é dessa área, e a pendência do modelo antigo ficaria "passou por 0"
    para sempre, sem aviso de parada. No contrato sem área nada muda — todos
    os turnos são da área do contrato e carregam tudo.

    A regra num lugar só: o registro no encerramento
    (``diario_operacional._registrar_passagem_das_abertas``) e a contagem da
    trilha perguntam a mesma coisa, e duas respostas diferentes dariam uma
    trilha que conta o que o encerramento já não grava (ou o contrário).
    """
    return (area_origem is None or area_origem == AREA_DO_CONTRATO
            or area_origem == area)


def _evento_conta(tipo, turno_id, area_origem, areas, turno_origem=None):
    """O evento entra na trilha (e na conta de turnos) desta pendência?

    Só a "recebida" depende da área: é ela que o defeito antigo gravou em
    massa, de todas as áreas, e o banco ainda guarda essas linhas. Elas não
    são apagadas (seria reescrever histórico sem quarentena); são lidas pela
    regra nova. Evento sem turno não tem área a comparar e fica como está.

    E a "recebida" do próprio turno que abriu a pendência não conta: quem
    abre está entregando, não carregando. O encerramento já não a grava,
    mas a correção de dia/turno pode dar a origem DEPOIS — o "Não deu" sem
    turno que a passagem recebeu e, corrigida para a chave da tarefa, passou
    a ter aberto (``corrigir_turno``). A linha fica no banco; só não conta.
    """
    if tipo != 'recebida' or not turno_id:
        return True
    if turno_origem and turno_id == turno_origem:
        return False
    return area_carrega(area_origem, areas.get(turno_id))


def _turnos_atravessados(eventos, area_origem, areas, turno_origem=None):
    """``{pendencia_id: {turno_id, ...}}`` — os turnos que contam na trilha.

    ``eventos`` precisa ter ``pendencia_id``, ``turno_id`` e ``tipo``;
    ``area_origem`` é ``{pendencia_id: área de origem}`` e ``turno_origem``,
    ``{pendencia_id: turno que a abriu}``.
    """
    turno_origem = turno_origem or {}
    saida = {}
    for e in eventos:
        if e.turno_id and _evento_conta(e.tipo, e.turno_id,
                                        area_origem.get(e.pendencia_id), areas,
                                        turno_origem.get(e.pendencia_id)):
            saida.setdefault(e.pendencia_id, set()).add(e.turno_id)
    return saida


def passagens_das_pendencias(pendencias):
    """``{pendencia_id: N}`` — "passou por N turnos", contado POR ÁREA.

    A fonte única da frase: a fila da tela do piso e o aviso de pendência
    parada leem daqui. Duas contas diferentes para a mesma frase dariam aviso
    de "3 turnos" com a tela dizendo 2.

    Duas consultas fixas (os eventos com turno e as áreas dos turnos
    envolvidos), qualquer que seja o tamanho da fila.
    """
    from facilities.passagem.models import (
        DiarioPendenciaEvento)
    pendencias = [p for p in (pendencias or []) if p is not None and p.id]
    if not pendencias:
        return {}
    eventos = (DiarioPendenciaEvento.query
               .with_entities(DiarioPendenciaEvento.pendencia_id,
                              DiarioPendenciaEvento.turno_id,
                              DiarioPendenciaEvento.tipo)
               .filter(DiarioPendenciaEvento.pendencia_id.in_(
                           [p.id for p in pendencias]),
                       DiarioPendenciaEvento.turno_id.isnot(None))
               .all())
    areas = areas_dos_turnos({p.turno_id for p in pendencias if p.turno_id}
                             | {e.turno_id for e in eventos})
    origem = {p.id: area_de_origem(p.turno_id, areas) for p in pendencias}
    return {pid: len(turnos) for pid, turnos
            in _turnos_atravessados(eventos, origem, areas,
                                    {p.id: p.turno_id for p in pendencias}).items()}


def trilha_da_pendencia(pendencia_id):
    """Os eventos de uma pendência, do mais antigo ao mais novo, com nomes.

    A "recebida" gravada por turno de OUTRA área (o defeito antigo — ver o
    bloco acima) não aparece: a trilha diria que o Almoxarifado recebeu a
    devolução da Expedição, e ele nunca a viu.
    """
    from facilities.passagem.models import (
        DiarioPendenciaEvento)
    eventos = (DiarioPendenciaEvento.query
               .filter_by(pendencia_id=pendencia_id)
               .order_by(DiarioPendenciaEvento.created_at.asc()).all())
    if not eventos:
        return []
    pendencia = DiarioPendencia.query.get(pendencia_id)
    origem_id = pendencia.turno_id if pendencia is not None else None
    areas = areas_dos_turnos({e.turno_id for e in eventos if e.turno_id}
                             | {origem_id})
    origem = area_de_origem(origem_id, areas)
    eventos = [e for e in eventos
               if _evento_conta(e.tipo, e.turno_id, origem, areas, origem_id)]
    if not eventos:
        return []
    turnos = {t.id: t for t in DiarioTurno.query.filter(
        DiarioTurno.id.in_([e.turno_id for e in eventos if e.turno_id])).all()} \
        if any(e.turno_id for e in eventos) else {}
    nomes = _nomes_de_usuario({e.created_by for e in eventos})
    saida = []
    for e in eventos:
        t = turnos.get(e.turno_id)
        saida.append({'tipo': e.tipo, 'texto': e.texto or '',
                      'quem': nomes.get(e.created_by, '—'),
                      'quando': e.created_at,
                      'turno': t.turno if t else '',
                      'data_turno': t.data_turno if t else None})
    return saida


def ocorrencias_da_janela(client_id, inicio, fim, turno=None, area_id=None):
    """Ocorrências do contrato na janela, pelo DIA DO TURNO, mais recente antes.

    A régua (dia do turno, rascunho fora, avulsa só sem recorte de turno ou
    área) está em ``_ocorrencias_com_turno``; esta é a forma para quem só
    precisa da lista.
    """
    return [o for o, _t in _ocorrencias_com_turno(client_id, inicio, fim,
                                                  turno, area_id)]


def pontos_de_atencao(client_id, desde=None, limite=None):
    """As ocorrências que o encarregado marcou como ponto de atenção.

    Sem janela de data por padrão, pela mesma razão que ``criticas_e_vencidas``
    ignora o filtro do painel: um ponto de atenção de anteontem não deixa de
    ser um ponto de atenção porque o gestor escolheu ver a semana.

    ``desde`` existe para a Torre de Comando, que quer a abertura da manhã e não
    o arquivo do contrato. O que ela recorta é a TELA, não o dado.

    O ponto de atenção de turno em rascunho não sobe: o encarregado ainda
    pode reescrevê-lo ou desmarcá-lo, e a gestão leria uma versão que talvez
    nunca seja entregue (ver ``_fora_do_rascunho``).
    """
    q = (DiarioOcorrencia.query
         .outerjoin(DiarioTurno, DiarioTurno.id == DiarioOcorrencia.turno_id)
         .filter(DiarioOcorrencia.client_id == client_id,
                 DiarioOcorrencia.gravidade == OCORRENCIA_CRITICA,
                 or_(DiarioOcorrencia.turno_id.is_(None),
                     DiarioTurno.status == TURNO_ENCERRADO)))
    if desde is not None:
        # O corte é pelo DIA DO TURNO, a mesma régua do painel e do
        # relatório (ver ``_ocorrencias_com_turno``): o ponto de atenção do
        # 3º Turno de domingo, digitado à 01h de segunda, é da semana que
        # acabou. Para a avulsa, sem turno, vale a meia-noite LOCAL do dia de
        # corte trazida para UTC — comparar com a data crua custaria três
        # horas e faria a ocorrência das 23h sumir do recorte do próprio dia.
        q = q.filter(or_(
            and_(DiarioOcorrencia.turno_id.isnot(None),
                 DiarioTurno.data_turno >= desde),
            and_(DiarioOcorrencia.turno_id.is_(None),
                 DiarioOcorrencia.created_at >= _limites_do_dia(desde, desde)[0])))
    q = q.order_by(DiarioOcorrencia.created_at.desc())
    if limite:
        q = q.limit(limite)
    return q.all()


def pareto(ocorrencias):
    """Ocorrências por tipo, da maior para a menor, com o acumulado em %.

    ``vital`` marca as categorias que, somadas, chegam a 80% do volume — o
    corte de Pareto. A categoria que CRUZA os 80% entra: parar antes dela
    deixaria de fora justamente a que fecha a conta.

    Empate com a última vital também é vital. Sem isto, quem decidia entre
    duas categorias de 4 ocorrências cada era a ORDEM ALFABÉTICA: "Avaria"
    ficava vermelha e "Divergência", com o mesmo volume, cinza — e a reunião
    atacava uma e ignorava a outra por causa da letra inicial.
    """
    contagem = OrderedDict()
    for o in ocorrencias:
        tipo = (o.tipo or 'Outros').strip() or 'Outros'
        contagem[tipo] = contagem.get(tipo, 0) + 1
    ordenado = sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(contagem.values())
    linhas, acumulado = [], 0
    for tipo, qtd in ordenado:
        antes = acumulado
        acumulado += qtd
        linhas.append({
            'tipo': tipo, 'qtd': qtd,
            'pct': round(qtd * 100.0 / total, 1) if total else 0.0,
            'acumulado': round(acumulado * 100.0 / total, 1) if total else 0.0,
            # Vital enquanto o acumulado ANTES desta categoria ainda não
            # tinha alcançado os 80%.
            'vital': bool(total) and (antes * 100.0 / total) < 80.0,
        })
    # O volume da última vital é a linha de corte; quem empata com ela entra.
    # A lista vem da maior para a menor, então os empatados são vizinhos.
    corte = min((linha['qtd'] for linha in linhas if linha['vital']), default=None)
    if corte is not None:
        for linha in linhas:
            if linha['qtd'] == corte:
                linha['vital'] = True
    return linhas


def comparativo_de_turnos(client_id, inicio, fim, turnos_da_config=None,
                          area_id=None):
    """Aderência × volume de ocorrências, turno a turno.

    É a tela que responde "o problema é a noite?" — e responde com número, não
    com impressão. Só turnos com trabalho encerrado aparecem, mais os turnos
    previstos na configuração ativa (com traço) para que a ausência de
    lançamento de um turno inteiro fique visível em vez de sumir.

    ``area_id`` é o mesmo recorte do resto do painel. Sem ele, com a
    Expedição escolhida no topo, o cartão do índice contava só a Expedição e
    este gráfico, logo ao lado, somava o Almoxarifado junto.
    """
    todos = turnos_da_janela(client_id, inicio, fim, area_id=area_id)
    exigencias = _exigencias_por_configuracao({t.configuracao_id for t in todos})
    por_nome = OrderedDict()
    for nome in (turnos_da_config or []):
        por_nome.setdefault(nome, [])
    for t in todos:
        por_nome.setdefault(t.turno, []).append(t)

    # Cada ocorrência vem com o turno que a lançou (a mesma consulta e a
    # mesma régua do cartão do índice), e é agrupada pelo nome dele. Antes o
    # nome saía de um segundo mapa de turnos, recortado por ``data_turno``,
    # enquanto as ocorrências eram recortadas por ``created_at`` — e a do 3º
    # Turno digitada depois da meia-noite caía no vão entre os dois.
    volume = {}
    for _o, t in _ocorrencias_com_turno(client_id, inicio, fim,
                                        area_id=area_id):
        if t is not None:
            volume[t.turno] = volume.get(t.turno, 0) + 1

    linhas = []
    for nome, lista in por_nome.items():
        pct, cumpridas, exigidas = aderencia(lista, exigencias)
        linhas.append({'turno': nome, 'turnos': len(lista), 'pct': pct,
                       'cumpridas': cumpridas, 'exigidas': exigidas,
                       'ocorrencias': volume.get(nome, 0),
                       'faixa': faixa_aderencia(pct)})
    linhas.sort(key=lambda x: x['turno'])
    return linhas


def burndown(client_id, fim, dias=14):
    """Criadas × baixadas, dia a dia — a curva que mostra se a fila anda.

    Duas consultas, cada uma trazendo só a coluna de data da janela: o
    agrupamento é feito em Python de propósito, porque o balde é o dia
    LOCAL e a coluna é UTC. ``GROUP BY date(created_at)`` jogaria a
    pendência das 23h no dia seguinte — e no SQLite dos testes e no Postgres
    de produção a aritmética de fuso em SQL nem sequer se escreve igual.
    O volume é pequeno e limitado pela janela (pendências de um contrato em
    até 30 dias), então não há varredura de tabela aqui.

    Pendência de turno em rascunho fica fora das duas curvas, como fica da
    taxa de resolução (ver ``_fora_do_rascunho``): a curva e o cartão ao
    lado precisam contar a mesma fila.
    """
    inicio = fim - timedelta(days=dias - 1)
    de, ate = _limites_do_dia(inicio, fim)
    dias_lista = [inicio + timedelta(days=i) for i in range(dias)]

    def _por_dia(coluna):
        linhas = (DiarioPendencia.query
                  .with_entities(coluna)
                  .filter(DiarioPendencia.client_id == client_id,
                          coluna >= de, coluna <= ate,
                          _fora_do_rascunho(DiarioPendencia, client_id)).all())
        mapa = {}
        for (momento,) in linhas:
            if momento is None:
                continue
            dia = tempo.local(momento).date()
            mapa[dia] = mapa.get(dia, 0) + 1
        return mapa

    criadas = _por_dia(DiarioPendencia.created_at)
    baixadas = _por_dia(DiarioPendencia.resolved_at)
    return {
        'labels': [d.strftime('%d/%m') for d in dias_lista],
        'criadas': [criadas.get(d, 0) for d in dias_lista],
        'resolvidas': [baixadas.get(d, 0) for d in dias_lista],
    }


def indice_de_ocorrencias(n_ocorrencias, n_turnos):
    """Ocorrências por turno realizado. Sem turno encerrado, não há índice."""
    if not n_turnos:
        return None
    return round(n_ocorrencias / float(n_turnos), 2)


def _janela_anterior(inicio, fim):
    """A janela imediatamente anterior, do mesmo tamanho — base da tendência."""
    tamanho = (fim - inicio).days + 1
    return inicio - timedelta(days=tamanho), inicio - timedelta(days=1)


def painel(client_id, periodo='7d', de=None, ate=None, turno=None, hoje=None,
           area_id=None):
    """Tudo o que o dashboard precisa, numa chamada.

    Devolve um dicionário fechado (sem objeto ORM solto além das listas que a
    tela lista) para que o template não faça consulta nenhuma — o custo de
    banco desta tela é o que está escrito aqui, e mais nada.

    ``area_id`` recorta por ÁREA do contrato. Sem ele, a aderência da Expedição
    e a do Almoxarifado viram uma média só — e média de coisas incomparáveis
    não diz nada a ninguém.
    """
    hoje = hoje or tempo.hoje()
    inicio, fim, rotulo = janela(periodo, de, ate, hoje)

    turnos = turnos_da_janela(client_id, inicio, fim, turno, area_id=area_id)
    exigencias = _exigencias_por_configuracao({t.configuracao_id for t in turnos})
    pct_ader, cumpridas, exigidas = aderencia(turnos, exigencias)

    pares = _ocorrencias_com_turno(client_id, inicio, fim, turno, area_id)
    ocorr = [o for o, _t in pares]
    # A coluna "Quando" da lista mostra o DIA E O NOME DO TURNO — a mesma
    # régua que selecionou a ocorrência. Mostrar a hora da digitação punha o
    # 3º Turno de ontem com a data de hoje, ao lado de um cartão que o conta
    # em ontem.
    quando_ocorr = {o.id: {'dia': _dia_da_ocorrencia(o, t),
                           'turno': getattr(t, 'turno', None)} for o, t in pares}
    resolucao = resolucao_de_pendencias(client_id, inicio, fim)
    criticas = criticas_e_vencidas(client_id)

    indice = indice_de_ocorrencias(len(ocorr), len(turnos))
    # Tendência: mesma conta na janela anterior de igual tamanho.
    ant_ini, ant_fim = _janela_anterior(inicio, fim)
    turnos_ant = turnos_da_janela(client_id, ant_ini, ant_fim, turno, area_id=area_id)
    ocorr_ant = ocorrencias_da_janela(client_id, ant_ini, ant_fim, turno,
                                      area_id=area_id)
    indice_ant = indice_de_ocorrencias(len(ocorr_ant), len(turnos_ant))
    delta = (round(indice - indice_ant, 2)
             if indice is not None and indice_ant is not None else None)

    # Os turnos oferecidos no filtro são os da ÁREA escolhida: a Expedição
    # trabalha em 1º e 2º Turno e o Almoxarifado pode ter outro nome para a
    # mesma hora. Oferecer a união dos dois faria o filtro prometer recortes
    # que não existem.
    q_cfg = DiarioConfiguracao.query.filter_by(client_id=client_id, ativo=True)
    if area_id and area_id != TODAS_AS_AREAS:
        q_cfg = q_cfg.filter(DiarioConfiguracao.area_id == int(area_id))
    nomes_de_turno, vistos = [], set()
    for cfg in q_cfg.order_by(DiarioConfiguracao.id.asc()).all():
        for t in _carrega(cfg.turnos_json, []):
            nome = (t.get('nome') if isinstance(t, dict) else str(t)) or ''
            if nome and nome not in vistos:
                vistos.add(nome)
                nomes_de_turno.append(nome)

    # Burn-down: no máximo 14 dias. Com 30 pontos os rótulos se encavalam e a
    # curva vira ruído; com menos de 7 não há curva, só dois pontos. A janela
    # menor manda quando é menor que 14 — só o piso de 7 dias é imposto, para
    # que o recorte "Hoje" ainda mostre uma tendência.
    dias_curva = max(7, min(14, (fim - inicio).days + 1))

    return {
        'inicio': inicio, 'fim': fim, 'periodo': periodo,
        'periodo_label': rotulo, 'turno': turno or 'todos',
        'turnos_disponiveis': nomes_de_turno,
        'area_id': int(area_id or TODAS_AS_AREAS),
        'areas_disponiveis': areas_do_contrato(client_id),
        'aderencia': {'pct': pct_ader, 'cumpridas': cumpridas,
                      'exigidas': exigidas, 'faixa': faixa_aderencia(pct_ader),
                      'meta': META_ADERENCIA},
        'resolucao': resolucao,
        'criticas': criticas,
        'n_criticas': len(criticas),
        'indice_ocorrencias': {'valor': indice, 'anterior': indice_ant,
                               'delta': delta,
                               'turnos': len(turnos),
                               'ocorrencias': len(ocorr)},
        'rotinas': raio_x_das_rotinas(turnos, exigencias),
        'pareto': pareto(ocorr),
        'turnos_comparativo': comparativo_de_turnos(client_id, inicio, fim,
                                                    nomes_de_turno,
                                                    area_id=area_id),
        'burndown': burndown(client_id, fim, dias_curva),
        'ocorrencias': ocorr,
        'quando_ocorrencias': quando_ocorr,
        'n_turnos': len(turnos),
    }


# ─────────────────────────────────────────────────────────────────────────
# Fechamento mensal — o documento que vai para a Diretoria e para o cliente
# ─────────────────────────────────────────────────────────────────────────

# Observação de turno que não diz nada. O Bloco 5 existe para o FATO
# relevante; encher a linha do tempo de "sem observações" é o que faria a
# diretoria parar de ler a linha do tempo.
_SEM_FATO = {
    '', '-', '--', '---', 'n/a', 'na', 'nada', 'nada a relatar',
    'nada a declarar', 'nada consta', 'sem observacao', 'sem observação',
    'sem observacoes', 'sem observações', 'sem ocorrencia', 'sem ocorrência',
    'sem ocorrencias', 'sem ocorrências', 'sem alteracao', 'sem alteração',
    'sem alteracoes', 'sem alterações', 'ok', 'tudo ok', 'tudo certo',
    'normal', 'operacao normal', 'operação normal', 'sem novidades',
}


def _tem_fato(texto):
    """A observação do turno merece entrar no Diário de Bordo?"""
    limpo = ' '.join((texto or '').split())
    if not limpo:
        return False
    chave = limpo.lower().strip(' .!;:')
    if chave in _SEM_FATO:
        return False
    # Frase curta demais não é fato; é carimbo.
    return len(limpo) >= 8


def _nomes_de_usuario(ids):
    """``{user_id: nome}`` numa consulta — evita o N+1 do relatório mensal."""
    ids = {i for i in (ids or set()) if i}
    if not ids:
        return {}
    from facilities.core.models import User
    return {u.id: u.name for u in
            User.query.with_entities(User.id, User.name)
            .filter(User.id.in_(list(ids))).all()}


def _resumo_das_trilhas(ids):
    """``{pendencia_id: {passagens, ultima}}`` em consultas fixas.

    ``passagens`` conta TURNOS distintos da MESMA ÁREA de origem (a regra de
    ``passagens_das_pendencias`` — o relatório não pode dizer "passou por 25
    turnos" com a tela dizendo 5) e ``ultima`` é o texto da tentativa mais
    recente — o que o relatório precisa mostrar ao lado de uma pendência
    parada há dias. Três consultas (eventos, turno de origem de cada
    pendência, áreas dos turnos), nenhuma por pendência, porque isto roda
    sobre o mês inteiro.
    """
    ids = [i for i in (ids or []) if i]
    if not ids:
        return {}
    from facilities.passagem.models import (
        DiarioPendenciaEvento)
    eventos = (DiarioPendenciaEvento.query
               .filter(DiarioPendenciaEvento.pendencia_id.in_(ids))
               .order_by(DiarioPendenciaEvento.created_at.asc(),
                         DiarioPendenciaEvento.id.asc()).all())
    if not eventos:
        return {}
    origens = dict(DiarioPendencia.query
                   .with_entities(DiarioPendencia.id, DiarioPendencia.turno_id)
                   .filter(DiarioPendencia.id.in_(
                       list({e.pendencia_id for e in eventos}))).all())
    areas = areas_dos_turnos({t for t in origens.values() if t}
                             | {e.turno_id for e in eventos if e.turno_id})
    turnos = _turnos_atravessados(
        eventos, {pid: area_de_origem(tid, areas) for pid, tid in origens.items()},
        areas, origens)
    saida = {}
    for e in eventos:
        alvo = saida.setdefault(e.pendencia_id, {'ultima': ''})
        if e.tipo == 'tentativa' and (e.texto or '').strip():
            alvo['ultima'] = e.texto.strip()
    return {k: {'passagens': len(turnos.get(k, ())), 'ultima': v['ultima']}
            for k, v in saida.items()}


def ultimo_dia(ano, mes):
    return (date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1))


def fechamento_mensal(client_id, ano, mes, hoje=None, area_id=None):
    """A competência fechada, em um dicionário — a fonte única do relatório.

    A TELA e o PDF leem daqui. Foi o que evitou, no SLA Contratual, o defeito
    clássico do relatório: a tela dizer 93% e o anexo do e-mail dizer 91%
    porque cada um refez a conta do seu jeito.

    ``area_id`` recorta por ÁREA: o relatório da Expedição e o do Almoxarifado
    são documentos diferentes, com responsáveis diferentes. Sem o recorte,
    sairia um só, com a média dos dois.
    """
    hoje = hoje or tempo.hoje()
    inicio = date(ano, mes, 1)
    fim = ultimo_dia(ano, mes)
    # O que o cabeçalho pode afirmar que foi apurado. No mês em curso, o
    # período vai até HOJE: escrever "01/10 a 31/10" no dia 16 dizia que a
    # segunda quinzena estava no relatório — e o número que a diretoria lia
    # como o do mês era o de meio mês. ``fim`` continua sendo o último dia,
    # porque é a competência (e a janela das consultas) que ele nomeia.
    em_andamento = inicio <= hoje <= fim
    # Competência que ainda não começou não tem período apurado: dizer
    # "01/11 a 30/11" num relatório sem dado nenhum leria como mês fechado.
    fim_apurado = hoje if em_andamento else (fim if hoje > fim else None)

    turnos = turnos_da_janela(client_id, inicio, fim, area_id=area_id)
    exigencias = _exigencias_por_configuracao({t.configuracao_id for t in turnos})
    pct_ader, cumpridas, exigidas = aderencia(turnos, exigencias)

    # Turnos concluídos por nome: "90 turnos (T1: 30 | T2: 30 | T3: 30)".
    por_turno = OrderedDict()
    for t in turnos:
        por_turno[t.turno] = por_turno.get(t.turno, 0) + 1

    safra = pendencias_da_janela(client_id, inicio, fim)
    resolvidas = [p for p in safra if p.status == 'resolvida']
    # Em aberto: as da safra que não foram baixadas, mais o que vinha de
    # antes e continua aberto — o relatório do mês não pode esconder um
    # arrasto que já dura dois meses só porque ele nasceu em agosto.
    abertas_antigas = (DiarioPendencia.query
                       .filter(DiarioPendencia.client_id == client_id,
                               DiarioPendencia.status == 'aberta',
                               DiarioPendencia.created_at < _limites_do_dia(inicio, fim)[0],
                               _fora_do_rascunho(DiarioPendencia, client_id))
                       .order_by(DiarioPendencia.created_at.asc()).all())
    em_aberto = [p for p in safra if p.status != 'resolvida'] + list(abertas_antigas)
    em_aberto.sort(key=lambda p: p.created_at or datetime.min)

    referencia = datetime.combine(min(fim, hoje), datetime.max.time())
    # Mesma âncora da tela do piso: sem isto, a mesma pendência lançada com
    # atraso dizia "aberta há 3 dias" no celular e "0 dia(s)" no relatório —
    # o defeito clássico de dois lugares refazendo a conta cada um do seu
    # jeito, que o SLA Contratual já custou caro para aprender.
    origens_pend = {t.id: t for t in DiarioTurno.query.filter(
        DiarioTurno.id.in_([p.turno_id for p in safra + list(abertas_antigas)
                            if p.turno_id])).all()}

    def _dias_parada(p):
        nascimento = nasceu_em(p, origens_pend.get(p.turno_id))
        if not nascimento:
            return 0
        return max(0, (referencia - nascimento).days)

    # Ocorrências pelo DIA DO TURNO, com o turno junto (ver
    # ``_ocorrencias_com_turno``): é o que faz o total deste bloco bater com
    # a soma dos relatórios por área e com o painel, e o que tira do mês a
    # ocorrência do 3º Turno do último dia do mês anterior.
    pares = _ocorrencias_com_turno(client_id, inicio, fim, area_id=area_id)
    ocorr = [o for o, _t in pares]
    # A matriz do bloco 4 em ordem de calendário: dia do turno, e dentro do
    # dia a ordem em que foram lançadas.
    cronologia = [{'o': o, 'turno': t.turno if t is not None else '—',
                   'data': _dia_da_ocorrencia(o, t)}
                  for o, t in sorted(pares, key=lambda par: (
                      _dia_da_ocorrencia(*par) or date.min,
                      par[0].created_at or datetime.min, par[0].id or 0))]
    # O nome do turno que abriu cada pendência sai do mesmo mapa que dá a
    # idade dela. Antes saía dos turnos da janela, e a pendência do 3º Turno
    # de 30/09, digitada em 01/10, aparecia em outubro com turno "—".
    nome_do_turno = {tid: t.turno for tid, t in origens_pend.items()}

    # Bloco 5: só os turnos que registraram fato.
    bordo = [{'data': t.data_turno, 'turno': t.turno,
              'texto': ' '.join((t.observacao or '').split())}
             for t in turnos if _tem_fato(t.observacao)]
    bordo.sort(key=lambda x: (x['data'], x['turno']))

    resol_pct = (round(len(resolvidas) * 100.0 / len(safra), 1)
                 if safra else None)
    # Quem responde por cada pendência, resolvido numa consulta só: a coluna
    # ``assigned_to`` é FK solta (sem relationship no modelo da Fase 1), e um
    # ``User.query.get`` por linha seria N+1 no relatório do mês inteiro.
    nomes = _nomes_de_usuario({p.assigned_to for p in safra + list(abertas_antigas)}
                              | {p.resolved_by for p in resolvidas})
    # A trilha entra no relatório porque é ela que responde à única pergunta
    # que a diretoria faz sobre uma pendência velha: "o que já se tentou?".
    # Sem ela o relatório sabia dizer que algo está parado há nove dias e
    # nada sobre o que foi feito nesses nove dias.
    trilhas = _resumo_das_trilhas([p.id for p in resolvidas + em_aberto])

    return {
        'client_id': client_id, 'ano': ano, 'mes': mes,
        'mes_nome': MESES[mes - 1], 'inicio': inicio, 'fim': fim,
        'fim_apurado': fim_apurado, 'em_andamento': em_andamento,
        'competencia': f'{MESES[mes - 1]}/{ano}',
        'turnos': {'total': len(turnos), 'por_turno': list(por_turno.items())},
        'aderencia': {'pct': pct_ader, 'cumpridas': cumpridas,
                      'exigidas': exigidas, 'faixa': faixa_aderencia(pct_ader),
                      'meta': META_ADERENCIA},
        'pendencias': {
            'abertas': len(safra), 'resolvidas': len(resolvidas),
            'pct': resol_pct, 'faixa': faixa_aderencia(resol_pct),
            'lista_resolvidas': [
                {'p': p, 'turno': nome_do_turno.get(p.turno_id) or '—',
                 'responsavel': nomes.get(p.assigned_to) or '—',
                 'resolucao': (p.resolucao or '').strip(),
                 'resolvida_por': nomes.get(p.resolved_by) or '—',
                 'passagens': trilhas.get(p.id, {}).get('passagens', 0)}
                for p in resolvidas],
            'lista_em_aberto': [
                {'p': p, 'turno': nome_do_turno.get(p.turno_id) or '—',
                 'responsavel': nomes.get(p.assigned_to) or '—',
                 'dias': _dias_parada(p),
                 'passagens': trilhas.get(p.id, {}).get('passagens', 0),
                 'ultima_tentativa': trilhas.get(p.id, {}).get('ultima', ''),
                 'anterior': bool(p.created_at
                                  and p.created_at < _limites_do_dia(inicio, fim)[0])}
                for p in em_aberto],
        },
        'ocorrencias': {
            'total': len(ocorr),
            'pareto': pareto(ocorr),
            # ``data`` é o DIA DO TURNO — o que a tela e o PDF escrevem ao
            # lado do nome dele, no lugar da data de digitação.
            'lista': cronologia,
            # Recorte do que já está em `lista`, não consulta nova: o mês do
            # relatório é o mesmo mês. Separado porque é o que a reunião lê
            # primeiro — e porque um Pareto de tipos não distingue a avaria de
            # palete da suspensão de colaborador.
            'atencao': [linha for linha in cronologia
                        if linha['o'].gravidade == OCORRENCIA_CRITICA],
        },
        'rotinas': raio_x_das_rotinas(turnos, exigencias),
        'bordo': bordo,
    }


MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
         'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
