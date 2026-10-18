"""As regras da equipe do posto (Fase 6). O commit é de quem chama.

* Funcionário: do local; login opcional (o usuário precisa atender o local e
  não pode estar ligado a outro funcionário).
* Escala: a mesma pessoa nunca fica em dois postos ao mesmo tempo — conta
  dia da semana, horário do posto (inclusive o que vira o dia) e período.
* Presença: o supervisor (ou a gestão) lança, no dia, quem veio, faltou ou
  atrasou. Só "veio / faltou / atrasou" (F6-2): nada de horário de entrada e
  saída, que é ponto eletrônico e é do RH (D36). Vale para hoje e os 7 dias
  anteriores (o lançamento esquecido).
* Cobertura: só para falta, sempre com motivo. Se o posto tem rota, as
  tarefas do dia de quem faltou passam para quem cobriu; os pedidos de
  presença aleatória (D48) de quem faltou ficam dispensados.
"""
import calendar
from datetime import date, datetime, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import PERFIS_DE_GESTAO, User
from facilities.equipes.models import (FALTOU, SITUACOES_PRESENCA, Cobertura, EscalaTrabalho,
                                       Funcionario, Posto, Presenca)

PERFIS_QUE_LANCAM = ('supervisor',) + tuple(PERFIS_DE_GESTAO) + ('master',)
DIAS_PARA_TRAS = 7
DISPENSADA = 'dispensada'     # pedido de presença de quem faltou (status da Fase 4B)


class RegraDaEquipe(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


def _texto(dados, campo, maximo):
    return (dados.get(campo) or '').strip()[:maximo] or None


def _data(bruto, rotulo, obrigatoria=True):
    if not bruto:
        if obrigatoria:
            raise RegraDaEquipe(f'Informe {rotulo}.')
        return None
    try:
        return datetime.strptime(str(bruto), '%Y-%m-%d').date()
    except ValueError:
        raise RegraDaEquipe(f'{rotulo[0].upper()}{rotulo[1:]}: data inválida.')


# ── Funcionários e postos ─────────────────────────────────────────────────

def logins_possiveis(local_id):
    """Quem pode ser ligado a um funcionário do local: as pessoas do campo
    que atendem o local."""
    from facilities.rotas.servico import pessoas_escalaveis
    return pessoas_escalaveis(local_id)


def salvar_funcionario(local, func, dados, autor):
    nome = _texto(dados, 'nome', 120)
    if not nome:
        raise RegraDaEquipe('Informe o nome do funcionário.')
    matricula = _texto(dados, 'matricula', 30)
    if matricula:
        outro = Funcionario.query.filter_by(client_id=local.id, matricula=matricula,
                                            is_active=True).first()
        if outro is not None and (func is None or outro.id != func.id):
            raise RegraDaEquipe(f'A matrícula {matricula} já é de {outro.nome} neste local.')
    uid = _id(dados, 'user_id') or None
    if uid:
        if uid not in {u.id for u in logins_possiveis(local.id)}:
            raise RegraDaEquipe('O login escolhido não atende este local.')
        outro = Funcionario.query.filter_by(user_id=uid).first()
        if outro is not None and (func is None or outro.id != func.id):
            raise RegraDaEquipe(f'Este login já está ligado a {outro.nome} '
                                f'({outro.local.name}).')
    func = func or Funcionario(client_id=local.id, criado_por=autor.id if autor else None)
    func.nome, func.funcao, func.matricula, func.user_id = (
        nome, _texto(dados, 'funcao', 80), matricula, uid)
    if func.id is None:
        db.session.add(func)
    db.session.flush()
    return func


def salvar_posto(local, posto, dados):
    from facilities.rotas.models import Rota
    from facilities.rotas.servico import RegraDaRota, _hora
    nome = _texto(dados, 'nome', 120)
    if not nome:
        raise RegraDaEquipe('Dê um nome ao posto (ex.: Limpeza 2º andar — manhã).')
    outro = Posto.query.filter(Posto.client_id == local.id,
                               db.func.lower(Posto.nome) == nome.lower()).first()
    if outro is not None and (posto is None or outro.id != posto.id):
        raise RegraDaEquipe('Já existe um posto com este nome neste local.')
    try:
        inicio = _hora(dados.get('hora_inicio'), 'Início')
        fim = _hora(dados.get('hora_fim'), 'Fim')
    except RegraDaRota as erro:
        raise RegraDaEquipe(erro.mensagem)
    if inicio == fim:
        raise RegraDaEquipe('O horário do posto precisa ter duração.')
    rota = None
    if _id(dados, 'rota_id'):
        rota = db.session.get(Rota, _id(dados, 'rota_id'))
        if rota is None or rota.client_id != local.id:
            raise RegraDaEquipe('Escolha uma rota deste local.')
    if posto is not None and (posto.hora_inicio, posto.hora_fim) != (inicio, fim):
        # O horário novo pode fazer escalas que já existem se sobreporem.
        for e in EscalaTrabalho.query.filter_by(posto_id=posto.id, is_active=True):
            _conferir_sobreposicao(e.funcionario_id, e.dias_semana, inicio, fim,
                                   e.data_inicio, e.data_fim, ignorar=e.id)
    posto = posto or Posto(client_id=local.id)
    posto.nome, posto.hora_inicio, posto.hora_fim = nome, inicio, fim
    posto.rota_id = rota.id if rota else None
    if posto.id is None:
        db.session.add(posto)
    db.session.flush()
    return posto


# ── Escala ────────────────────────────────────────────────────────────────

SEMANA_MIN = 7 * 24 * 60


def _minutos(h):
    return h.hour * 60 + h.minute


def intervalos_semanais(dias, inicio, fim):
    """Os trechos da semana (em minutos desde segunda 00:00) ocupados pelo
    posto nos ``dias``. Turno que vira o dia passa para o dia seguinte."""
    trechos = []
    dur = (_minutos(fim) - _minutos(inicio)) % (24 * 60)
    for d in dias:
        ini = (int(d) - 1) * 24 * 60 + _minutos(inicio)
        trechos.append((ini, ini + dur))
    return trechos


def _cruzam(a, b):
    """Dois trechos semanais se cruzam? (O domingo à noite encosta na segunda.)"""
    for desloc in (-SEMANA_MIN, 0, SEMANA_MIN):
        if a[0] < b[1] + desloc and b[0] + desloc < a[1]:
            return True
    return False


def se_sobrepoem(dias_a, ini_a, fim_a, dias_b, ini_b, fim_b):
    return any(_cruzam(x, y) for x in intervalos_semanais(dias_a, ini_a, fim_a)
               for y in intervalos_semanais(dias_b, ini_b, fim_b))


def _periodos_cruzam(ini_a, fim_a, ini_b, fim_b):
    # Um dia de folga nas pontas: o turno da noite do último dia invade o seguinte.
    ate_a = fim_a + timedelta(days=1) if fim_a else date.max
    ate_b = fim_b + timedelta(days=1) if fim_b else date.max
    return ini_a <= ate_b and ini_b <= ate_a


def _conferir_sobreposicao(funcionario_id, dias, inicio, fim, data_ini, data_fim, ignorar=None):
    for e in (EscalaTrabalho.query.filter_by(funcionario_id=funcionario_id, is_active=True)
              .all()):
        if e.id == ignorar or not e.posto.is_active:
            continue
        if not _periodos_cruzam(data_ini, data_fim, e.data_inicio, e.data_fim):
            continue
        if se_sobrepoem(dias, inicio, fim, e.dias_semana, e.posto.hora_inicio,
                        e.posto.hora_fim):
            raise RegraDaEquipe(
                f'{e.funcionario.nome} já está escalado(a) em "{e.posto.nome}" '
                f'({e.posto.hora_inicio.strftime("%H:%M")} às '
                f'{e.posto.hora_fim.strftime("%H:%M")}) nesses dias. Uma pessoa não fica '
                'em dois postos ao mesmo tempo.', 409)


def _dias(bruto):
    dias = ''.join(sorted({d for d in str(bruto or '') if d in '1234567'}))
    if not dias:
        raise RegraDaEquipe('Escolha pelo menos um dia da semana.')
    return dias


def salvar_escala(local, dados, autor):
    func = db.session.get(Funcionario, _id(dados, 'funcionario_id'))
    if func is None or func.client_id != local.id or not func.is_active:
        raise RegraDaEquipe('Escolha um funcionário ativo deste local.')
    posto = db.session.get(Posto, _id(dados, 'posto_id'))
    if posto is None or posto.client_id != local.id or not posto.is_active:
        raise RegraDaEquipe('Escolha um posto ativo deste local.')
    dias = _dias(dados.get('dias_semana') or ''.join(
        d for d in '1234567' if dados.get(f'dia_{d}')))
    inicio = _data(dados.get('data_inicio') or tempo.hoje().isoformat(), 'o começo da escala')
    fim = _data(dados.get('data_fim'), 'o fim da escala', obrigatoria=False)
    if fim is not None and fim < inicio:
        raise RegraDaEquipe('O fim da escala é antes do começo.')
    _conferir_sobreposicao(func.id, dias, posto.hora_inicio, posto.hora_fim, inicio, fim)
    e = EscalaTrabalho(client_id=local.id, funcionario_id=func.id, posto_id=posto.id,
                       dias_semana=dias, data_inicio=inicio, data_fim=fim,
                       criado_por=autor.id if autor else None)
    db.session.add(e)
    db.session.flush()
    return e


def encerrar_escala(escala, fim):
    """A escala termina em ``fim`` (o histórico de presença fica)."""
    if fim < escala.data_inicio:
        # Nunca valeu: some da lista, mas a linha fica (desligada).
        escala.is_active = False
        escala.data_fim = escala.data_inicio
    else:
        escala.data_fim = fim
    db.session.flush()
    return escala


def vale_no_dia(escala, dia):
    return (escala.is_active and str(dia.isoweekday()) in escala.dias_semana
            and escala.data_inicio <= dia and (escala.data_fim is None or dia <= escala.data_fim)
            and escala.funcionario.is_active and escala.posto.is_active)


def escalados_do_dia(client_ids, dia):
    """As escalas que valem em ``dia`` nos locais pedidos, com a presença já
    lançada (se houver)."""
    escalas = (EscalaTrabalho.query
               .filter(EscalaTrabalho.client_id.in_(list(client_ids) or [-1]),
                       EscalaTrabalho.is_active.is_(True))
               .all())
    validas = [e for e in escalas if vale_no_dia(e, dia)]
    presencas = {(p.funcionario_id, p.posto_id): p for p in Presenca.query.filter(
        Presenca.client_id.in_(list(client_ids) or [-1]), Presenca.data == dia)}
    linhas = [{'escala': e, 'presenca': presencas.get((e.funcionario_id, e.posto_id))}
              for e in validas]
    linhas.sort(key=lambda x: (x['escala'].posto.local.name, x['escala'].posto.hora_inicio,
                               x['escala'].posto.nome, x['escala'].funcionario.nome))
    return linhas


# ── Presença e cobertura ──────────────────────────────────────────────────

def _pode_lancar(user, client_id):
    from facilities.core.acesso import allowed_client_ids_or_none
    if user._effective_role() not in PERFIS_QUE_LANCAM:
        raise RegraDaEquipe('A presença é lançada pelo supervisor ou pela gestão.', 403)
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and client_id not in permitidos:
        raise RegraDaEquipe('Este local não está entre os seus.', 403)


def _dia_permitido(dia):
    hoje = tempo.hoje()
    if dia > hoje:
        raise RegraDaEquipe('Presença só se lança no dia (ou depois), não antes.')
    if dia < hoje - timedelta(days=DIAS_PARA_TRAS):
        raise RegraDaEquipe(f'Só dá para lançar presença dos últimos {DIAS_PARA_TRAS} dias.')


def registrar_presenca(user, escala, dia, situacao, observacao='', agora_utc=None):
    agora_utc = agora_utc or datetime.utcnow()
    _pode_lancar(user, escala.client_id)
    _dia_permitido(dia)
    if not vale_no_dia(escala, dia):
        raise RegraDaEquipe(f'{escala.funcionario.nome} não está escalado(a) neste posto '
                            f'em {dia.strftime("%d/%m")}.')
    if situacao not in SITUACOES_PRESENCA:
        raise RegraDaEquipe('Escolha: veio, faltou ou atrasou.')
    p = Presenca.query.filter_by(funcionario_id=escala.funcionario_id,
                                 posto_id=escala.posto_id, data=dia).first()
    if p is not None and p.cobertura is not None and situacao != FALTOU:
        raise RegraDaEquipe(f'A falta já tem cobertura ({p.cobertura.funcionario.nome}). '
                            'Peça à gestão para corrigir.', 409)
    if p is None:
        p = Presenca(client_id=escala.client_id, funcionario_id=escala.funcionario_id,
                     posto_id=escala.posto_id, data=dia, situacao=situacao,
                     registrada_por=user.id, registrada_em=agora_utc)
        db.session.add(p)
    p.situacao = situacao
    p.observacao = (observacao or '').strip()[:300] or None
    p.registrada_por, p.registrada_em = user.id, agora_utc
    db.session.flush()
    if situacao == FALTOU:
        _dispensar_pedidos_de_presenca(p)
    return p


def _dispensar_pedidos_de_presenca(presenca):
    """Quem faltou não recebe (nem "deixa sem resposta") o pedido de presença
    aleatória da rota do posto naquele dia."""
    from facilities.rotas.models import PRESENCA_PENDENTE, ConfirmacaoPresenca
    uid = presenca.funcionario.user_id
    if not uid or not presenca.posto.rota_id:
        return 0
    n = 0
    for c in ConfirmacaoPresenca.query.filter_by(rota_id=presenca.posto.rota_id, user_id=uid,
                                                 data=presenca.data,
                                                 status=PRESENCA_PENDENTE):
        c.status = DISPENSADA
        n += 1
    return n


def registrar_cobertura(user, presenca, dados, agora_utc=None):
    agora_utc = agora_utc or datetime.utcnow()
    _pode_lancar(user, presenca.client_id)
    _dia_permitido(presenca.data)
    if presenca.situacao != FALTOU:
        raise RegraDaEquipe('Cobertura só para falta.')
    if presenca.cobertura is not None:
        raise RegraDaEquipe(f'Esta falta já foi coberta por {presenca.cobertura.funcionario.nome}.',
                            409)
    motivo = (dados.get('motivo') or '').strip()[:300]
    if len(motivo) < 3:
        raise RegraDaEquipe('Diga o motivo da cobertura (ex.: atestado, folga trocada).')
    quem = db.session.get(Funcionario, _id(dados, 'funcionario_id'))
    if quem is None or quem.client_id != presenca.client_id or not quem.is_active:
        raise RegraDaEquipe('Escolha um funcionário ativo deste local para cobrir.')
    if quem.id == presenca.funcionario_id:
        raise RegraDaEquipe('Quem faltou não cobre a própria falta.')
    faltou_tambem = Presenca.query.filter_by(funcionario_id=quem.id, data=presenca.data,
                                             situacao=FALTOU).first()
    if faltou_tambem is not None:
        raise RegraDaEquipe(f'{quem.nome} também está com falta neste dia.')
    c = Cobertura(presenca_id=presenca.id, client_id=presenca.client_id,
                  funcionario_id=quem.id, motivo=motivo, registrada_por=user.id,
                  registrada_em=agora_utc)
    db.session.add(c)
    db.session.flush()
    passadas = reescalar_rota(presenca, quem)
    return c, passadas


def reescalar_rota(presenca, quem_cobre):
    """As tarefas ainda previstas do dia, de quem faltou, vão para quem cobre.
    Devolve quantas passaram. Sem login, quem cobre não recebe aviso no
    celular: as tarefas ficam sem escalado (qualquer um do local faz)."""
    from facilities.rotas import presenca as pedidos
    from facilities.rotas.models import PREVISTA, TarefaDia
    rota = presenca.posto.rota
    if rota is None:
        return 0
    de, para = presenca.funcionario.user_id, quem_cobre.user_id
    q = TarefaDia.query.filter(TarefaDia.rota_id == rota.id, TarefaDia.data == presenca.data,
                               TarefaDia.status == PREVISTA)
    q = q.filter(TarefaDia.user_id == de) if de else q.filter(TarefaDia.user_id.is_(None))
    n = 0
    for t in q.all():
        t.user_id = para
        t.avisada_em = None
        n += 1
    if para:
        pedidos.gerar(rota, presenca.data, para)
    return n


def substituto(rota, dia, user_id):
    """Para o agendador da rota: se ``user_id`` faltou e alguém cobriu, a
    tarefa nasce com quem cobriu."""
    if not user_id:
        return user_id
    c = (Cobertura.query.join(Presenca, Presenca.id == Cobertura.presenca_id)
         .join(Posto, Posto.id == Presenca.posto_id)
         .join(Funcionario, Funcionario.id == Presenca.funcionario_id)
         .filter(Posto.rota_id == rota.id, Presenca.data == dia,
                 Funcionario.user_id == user_id).first())
    return c.funcionario.user_id if c is not None else user_id


# ── Conferência do mês ────────────────────────────────────────────────────

def mes(local_id, ano, mes_):
    """A grade do mês: uma linha por escala, uma coluna por dia, com o que
    estava previsto e o que foi lançado."""
    dias = [date(ano, mes_, d) for d in range(1, calendar.monthrange(ano, mes_)[1] + 1)]
    escalas = (EscalaTrabalho.query.filter_by(client_id=local_id)
               .filter(EscalaTrabalho.data_inicio <= dias[-1])
               .filter(db.or_(EscalaTrabalho.data_fim.is_(None),
                              EscalaTrabalho.data_fim >= dias[0])).all())
    presencas = {(p.funcionario_id, p.posto_id, p.data): p for p in Presenca.query.filter(
        Presenca.client_id == local_id, Presenca.data >= dias[0], Presenca.data <= dias[-1])}
    linhas, totais = [], {'previstos': 0, 'lancados': 0, 'faltas': 0, 'cobertas': 0}
    hoje = tempo.hoje()
    for e in sorted(escalas, key=lambda x: (x.funcionario.nome, x.posto.nome)):
        celulas = []
        for d in dias:
            previsto = (str(d.isoweekday()) in e.dias_semana and e.data_inicio <= d
                        and (e.data_fim is None or d <= e.data_fim) and e.is_active)
            p = presencas.get((e.funcionario_id, e.posto_id, d))
            if previsto and d <= hoje:
                totais['previstos'] += 1
                if p is not None:
                    totais['lancados'] += 1
            if p is not None and p.situacao == FALTOU:
                totais['faltas'] += 1
                if p.cobertura is not None:
                    totais['cobertas'] += 1
            celulas.append({'dia': d, 'previsto': previsto, 'presenca': p,
                            'pendente': previsto and p is None and d <= hoje})
        linhas.append({'escala': e, 'celulas': celulas})
    return {'dias': dias, 'linhas': linhas, 'totais': totais}


def funcionarios_ativos(local_id):
    return (Funcionario.query.filter_by(client_id=local_id, is_active=True)
            .order_by(Funcionario.nome).all())


def usuario_de(uid):
    return db.session.get(User, uid) if uid else None
