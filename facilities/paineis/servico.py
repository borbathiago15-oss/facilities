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


def _aderencia(client_id, de, ate, agora):
    from facilities.rotas.models import TarefaDia
    from facilities.rotas.servico import aderencia
    tarefas = TarefaDia.query.filter(TarefaDia.client_id == client_id, TarefaDia.data >= de,
                                     TarefaDia.data <= ate).all()
    bom, base, _ = aderencia(tarefas, agora)
    return bom, base


def _ocorrencias(client_id, de, ate, agora):
    from facilities.rotas.models import OCORRENCIA_RESOLVIDA, OcorrenciaPublica
    lista = OcorrenciaPublica.query.filter(
        OcorrenciaPublica.client_id == client_id, OcorrenciaPublica.prazo.isnot(None),
        OcorrenciaPublica.criada_em >= _utc(de),
        OcorrenciaPublica.criada_em < _utc(ate + timedelta(days=1))).all()
    base = [o for o in lista if o.status == OCORRENCIA_RESOLVIDA or agora > o.prazo]
    bom = sum(1 for o in base if o.status == OCORRENCIA_RESOLVIDA and o.resolvida_em
              and o.resolvida_em <= o.prazo)
    return bom, len(base)


def _visitas(client_id, de, ate, agora):
    from facilities.visitas.models import FEITA, Visita
    from facilities.visitas.servico import prazo
    lista = Visita.query.filter(Visita.client_id == client_id, Visita.vencimento >= de,
                                Visita.vencimento <= ate).all()
    base = [v for v in lista if v.status == FEITA or agora > prazo(v)]
    bom = sum(1 for v in base if v.status == FEITA and not v.n_nao_conformes)
    return bom, len(base)


def _chamados(client_id, de, ate, agora):
    from facilities.chamados.models import Chamado
    lista = Chamado.query.filter(Chamado.client_id == client_id,
                                 Chamado.resolvido_em.isnot(None),
                                 Chamado.resolvido_em >= _utc(de),
                                 Chamado.resolvido_em < _utc(ate + timedelta(days=1))).all()
    bom = sum(1 for c in lista if c.prazo is None or c.resolvido_em <= c.prazo)
    return bom, len(lista)


CALCULO = {'aderencia': _aderencia, 'ocorrencias': _ocorrencias, 'visitas': _visitas,
           'chamados': _chamados}


def nota_do_local(local, de, ate, agora=None):
    agora = agora or datetime.utcnow()
    indicadores = {}
    for chave, conta in CALCULO.items():
        bom, base = conta(local.id, de, ate, agora)
        indicadores[chave] = {'bom': bom, 'base': base, 'pct': _pct(bom, base)}
    validos = [i['pct'] for i in indicadores.values() if i['pct'] is not None]
    nota = round(sum(validos) / len(validos), 1) if validos else None
    return {'local': local, 'indicadores': indicadores, 'nota': nota, 'faixa': faixa(nota)}


def notas(locais, de, ate, agora=None):
    agora = agora or datetime.utcnow()
    linhas = [nota_do_local(loc, de, ate, agora) for loc in locais]
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


