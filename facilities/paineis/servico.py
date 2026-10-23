"""A nota por local (D50, Q5) e os números do painel. Só leitura.

A nota é a média, com PESOS IGUAIS, dos indicadores do período que têm dado
(Q5, até haver dado real para calibrar):

* **Aderência à rota** — tarefas concluídas no prazo ÷ tarefas que já
  venceram ou foram encerradas (a mesma conta da tela "Hoje" das rotas).
* **Ocorrências no prazo** — avisos do QR público com prazo, abertos no
  período: resolvidos dentro do prazo ÷ (resolvidos + os que já venceram).
* **Visitas conformes** — visitas de supervisão com vencimento no período:
  feitas sem não conformidade ÷ (feitas + as que venceram sem ser feitas).
* **Chamados no prazo** — chamados resolvidos no período dentro do prazo ÷
  resolvidos no período (a mesma conta do topo da tela de Chamados).

Indicador sem dado no período sai da média (F8-1) — não conta como zero.
Faixas (F8-1): abaixo de 70 crítica; de 70 a menos de 85 atenção; 85 ou
mais, boa.

Estas MESMAS funções alimentam a tela e a API: o número é um só.
"""
from datetime import datetime, time, timedelta

from facilities import tempo


FAIXA_CRITICA = 70
FAIXA_BOA = 85
FAIXAS = {'critica': 'Crítica', 'atencao': 'Atenção', 'boa': 'Boa'}
INDICADORES = {'aderencia': 'Aderência à rota', 'ocorrencias': 'Ocorrências no prazo',
               'visitas': 'Visitas conformes', 'chamados': 'Chamados no prazo'}


def faixa(nota):
    if nota is None:
        return None
    if nota < FAIXA_CRITICA:
        return 'critica'
    if nota < FAIXA_BOA:
        return 'atencao'
    return 'boa'


def _pct(bom, base):
    return round(100.0 * bom / base, 1) if base else None


def _utc(dia, h=time(0, 0)):
    return tempo.para_utc(dia, h)


# Cada indicador é calculado para TODOS os locais de uma vez, lendo só as
# colunas da conta (sem montar objetos): o painel de 50 locais com um mês de
# rotas eram 48 mil tarefas carregadas uma a uma. Devolve {local: (bom, base)}.

def _aderencia(ids, de, ate, agora):
    from facilities.extensions import db
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, ENCERRADAS, TarefaDia
    contas = {}
    for cid, status, previsto, tol in db.session.query(
            TarefaDia.client_id, TarefaDia.status, TarefaDia.previsto_para,
            TarefaDia.tolerancia_min).filter(TarefaDia.client_id.in_(ids), TarefaDia.data >= de,
                                             TarefaDia.data <= ate):
        # A mesma conta de ``rotas.servico.aderencia``.
        if status in ENCERRADAS or agora > previsto + timedelta(minutes=tol):
            bom, base = contas.get(cid, (0, 0))
            contas[cid] = (bom + (status == CONCLUIDA_NO_PRAZO), base + 1)
    return contas


def _ocorrencias(ids, de, ate, agora):
    from facilities.extensions import db
    from facilities.rotas.models import OCORRENCIA_RESOLVIDA, OcorrenciaPublica as O
    contas = {}
    for cid, status, prazo, resolvida in db.session.query(
            O.client_id, O.status, O.prazo, O.resolvida_em).filter(
            O.client_id.in_(ids), O.prazo.isnot(None), O.criada_em >= _utc(de),
            O.criada_em < _utc(ate + timedelta(days=1))):
        if status == OCORRENCIA_RESOLVIDA or agora > prazo:
            bom, base = contas.get(cid, (0, 0))
            ok = status == OCORRENCIA_RESOLVIDA and resolvida and resolvida <= prazo
            contas[cid] = (bom + bool(ok), base + 1)
    return contas


def _visitas(ids, de, ate, agora):
    from facilities.extensions import db
    from facilities.visitas.models import FEITA, Visita
    contas = {}
    for cid, status, vencimento, nc in db.session.query(
            Visita.client_id, Visita.status, Visita.vencimento, Visita.n_nao_conformes).filter(
            Visita.client_id.in_(ids), Visita.vencimento >= de, Visita.vencimento <= ate):
        # O prazo da visita é o fim do dia do vencimento (``visitas.servico.prazo``).
        if status == FEITA or agora > _utc(vencimento, time(23, 59)):
            bom, base = contas.get(cid, (0, 0))
            contas[cid] = (bom + (status == FEITA and not nc), base + 1)
    return contas


def _chamados(ids, de, ate, agora):
    from facilities.chamados.models import Chamado
    from facilities.extensions import db
    contas = {}
    for cid, prazo, resolvido in db.session.query(
            Chamado.client_id, Chamado.prazo, Chamado.resolvido_em).filter(
            Chamado.client_id.in_(ids), Chamado.resolvido_em.isnot(None),
            Chamado.resolvido_em >= _utc(de),
            Chamado.resolvido_em < _utc(ate + timedelta(days=1))):
        bom, base = contas.get(cid, (0, 0))
        contas[cid] = (bom + (prazo is None or resolvido <= prazo), base + 1)
    return contas


CALCULO = {'aderencia': _aderencia, 'ocorrencias': _ocorrencias, 'visitas': _visitas,
           'chamados': _chamados}


def _linha(local, contas):
    indicadores = {}
    for chave in CALCULO:
        bom, base = contas[chave].get(local.id, (0, 0))
        indicadores[chave] = {'bom': bom, 'base': base, 'pct': _pct(bom, base)}
    validos = [i['pct'] for i in indicadores.values() if i['pct'] is not None]
    nota = round(sum(validos) / len(validos), 1) if validos else None
    return {'local': local, 'indicadores': indicadores, 'nota': nota, 'faixa': faixa(nota)}


def nota_do_local(local, de, ate, agora=None):
    return notas([local], de, ate, agora)[0]


def notas(locais, de, ate, agora=None):
    agora = agora or datetime.utcnow()
    if not locais:
        return []
    ids = [loc.id for loc in locais]
    contas = {chave: conta(ids, de, ate, agora) for chave, conta in CALCULO.items()}
    linhas = [_linha(loc, contas) for loc in locais]
    return sorted(linhas, key=lambda x: (x['nota'] is None, x['nota'] if x['nota'] is not None
                                         else 0, x['local'].name))


def resumo(linhas):
    com_nota = [x['nota'] for x in linhas if x['nota'] is not None]
    return {'media': round(sum(com_nota) / len(com_nota), 1) if com_nota else None,
            'faixas': {k: sum(1 for x in linhas if x['faixa'] == k) for k in FAIXAS},
            'sem_dado': sum(1 for x in linhas if x['nota'] is None)}


def por_cliente(linhas):
    """Agrupa as linhas por cliente (contratante) — a vista do gerente e da diretoria."""
    grupos = {}
    for x in linhas:
        c = x['local'].contratante
        nome = c.nome if c is not None else 'Sem cliente'
        grupos.setdefault(nome, []).append(x)
    return [{'cliente': k, 'linhas': v, 'resumo': resumo(v)}
            for k, v in sorted(grupos.items())]


def periodo_padrao(hoje=None):
    """Os últimos 30 dias, até hoje."""
    hoje = hoje or tempo.hoje()
    return hoje - timedelta(days=29), hoje


def ler_periodo(args, maximo_dias=None):
    de_p, ate_p = periodo_padrao()
    try:
        de = datetime.strptime(args.get('de') or '', '%Y-%m-%d').date()
    except ValueError:
        de = de_p
    try:
        ate = datetime.strptime(args.get('ate') or '', '%Y-%m-%d').date()
    except ValueError:
        ate = ate_p
    if de > ate:
        de, ate = ate, de
    if maximo_dias and (ate - de).days + 1 > maximo_dias:
        de = ate - timedelta(days=maximo_dias - 1)
    return de, ate


