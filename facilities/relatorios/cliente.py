"""O relatório mensal do cliente: os números do mês, por local.

Pergunta que ele responde: "o serviço que eu pago foi feito, e com prova?".
Por isso: a nota e os indicadores do mês contra o anterior, as rotinas feitas
por ambiente, os chamados e o tempo de atendimento, o que não estava conforme
e o que foi corrigido, os avisos do público, as visitas de supervisão, as
cobranças e uma amostra de fotos.

Fica de fora (F9-1, R5): custo, material, comentário interno e o NOME de
qualquer pessoa da equipe.

Tudo aqui é só leitura e sai das mesmas regras do painel — o PDF, o Excel, a
tela da gestão e o portal mostram os mesmos números.
"""
import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.relatorios.models import RelatorioCliente

FOTOS_MAX = 12
FOTOS_NA_AMOSTRA = 9
CHAMADOS_NA_LISTA = 60
ELOGIOS_NA_LISTA = 8
MESES = ('janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
         'setembro', 'outubro', 'novembro', 'dezembro')


class RegraDoRelatorio(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


# ── O mês ─────────────────────────────────────────────────────────────────

def mes_de(bruto, hoje=None):
    """'AAAA-MM' → o primeiro dia; vazio ou inválido → o mês passado."""
    hoje = hoje or tempo.hoje()
    try:
        ano, m = (int(x) for x in str(bruto or '').split('-'))
        return date(ano, m, 1)
    except ValueError:
        return (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)


def fim_do_mes(primeiro):
    return (primeiro + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def mes_anterior(primeiro):
    return (primeiro - timedelta(days=1)).replace(day=1)


def nome_do_mes(primeiro):
    return f'{MESES[primeiro.month - 1]} de {primeiro.year}'


def _utc(dia, h=time(0, 0)):
    return tempo.para_utc(dia, h)


# ── Os números ────────────────────────────────────────────────────────────

def _rotinas_por_ambiente(local_id, de, ate, agora):
    from facilities.cadastros.models import Ambiente, PontoInspecao
    from facilities.rotas.models import (CONCLUIDA_COM_ATRASO, CONCLUIDA_NO_PRAZO, NAO_REALIZADA,
                                         PERDIDA, TarefaDia)
    from facilities.rotas.servico import aderencia
    linhas = (db.session.query(TarefaDia, Ambiente.nome)
              .join(PontoInspecao, PontoInspecao.id == TarefaDia.ponto_id)
              .join(Ambiente, Ambiente.id == PontoInspecao.ambiente_id)
              .filter(TarefaDia.client_id == local_id, TarefaDia.data >= de,
                      TarefaDia.data <= ate).all())
    grupos = defaultdict(list)
    for t, amb in linhas:
        grupos[amb].append(t)
    saida = []
    for amb in sorted(grupos):
        ts = grupos[amb]
        bom, base, pct = aderencia(ts, agora)
        saida.append({
            'ambiente': amb, 'previstas': len(ts),
            'no_prazo': sum(1 for t in ts if t.status == CONCLUIDA_NO_PRAZO),
            'com_atraso': sum(1 for t in ts if t.status == CONCLUIDA_COM_ATRASO),
            'nao_feitas': sum(1 for t in ts if t.status in (NAO_REALIZADA, PERDIDA)),
            'pct': pct})
    return saida


def _horas(segundos):
    return round(segundos / 3600, 1) if segundos is not None else None


def _chamados(local_id, de, ate):
    from facilities.chamados.models import CANCELADO, CATEGORIAS, STATUS, Chamado
    ini, fim = _utc(de), _utc(ate + timedelta(days=1))
    abertos = (Chamado.query.filter(Chamado.client_id == local_id, Chamado.aberto_em >= ini,
                                    Chamado.aberto_em < fim, Chamado.status != CANCELADO)
               .order_by(Chamado.aberto_em).all())
    resolvidos = Chamado.query.filter(Chamado.client_id == local_id,
                                      Chamado.resolvido_em.isnot(None),
                                      Chamado.resolvido_em >= ini,
                                      Chamado.resolvido_em < fim).all()
    no_prazo = [c for c in resolvidos if c.prazo is None or c.resolvido_em <= c.prazo]
    tempos = [max(0, (c.resolvido_em - c.aberto_em).total_seconds() - (c.pausa_total_seg or 0))
              for c in resolvidos]
    pendentes = Chamado.query.filter(
        Chamado.client_id == local_id, Chamado.aberto_em < fim, Chamado.status != CANCELADO,
        db.or_(Chamado.resolvido_em.is_(None), Chamado.resolvido_em >= fim)).count()
    categorias = Counter(CATEGORIAS.get(c.categoria, c.categoria) for c in abertos)
    return {
        'abertos': len(abertos), 'resolvidos': len(resolvidos), 'no_prazo': len(no_prazo),
        'pct_no_prazo': round(100 * len(no_prazo) / len(resolvidos), 1) if resolvidos else None,
        'tempo_medio_h': _horas(sum(tempos) / len(tempos)) if tempos else None,
        'pendentes_no_fim': pendentes,
        'categorias': categorias.most_common(6),
        'lista': [{'numero': c.numero, 'titulo': c.titulo,
                   'categoria': CATEGORIAS.get(c.categoria, c.categoria),
                   'aberto_em': c.aberto_em, 'prazo': c.prazo, 'resolvido_em': c.resolvido_em,
                   'situacao': STATUS.get(c.status, c.status),
                   'no_prazo': (None if c.resolvido_em is None or c.prazo is None
                                else c.resolvido_em <= c.prazo)}
                  for c in abertos[:CHAMADOS_NA_LISTA]],
        'lista_cortada': len(abertos) > CHAMADOS_NA_LISTA,
    }


def _nao_conformidades(local_id, de, ate):
    from facilities.chamados.models import FECHADO, RESOLVIDO, Chamado
    from facilities.rotas.models import Execucao, NaoConformidade
    ncs = (NaoConformidade.query.join(Execucao, Execucao.id == NaoConformidade.execucao_id)
           .filter(NaoConformidade.client_id == local_id,
                   Execucao.concluida_em >= _utc(de),
                   Execucao.concluida_em < _utc(ate + timedelta(days=1))).all())
    chamados = {c.id: c for c in Chamado.query.filter(
        Chamado.id.in_([n.chamado_id for n in ncs if n.chamado_id] or [-1]))}
    corrigidas = sum(1 for n in ncs if n.chamado_id and
                     chamados.get(n.chamado_id) is not None and
                     chamados[n.chamado_id].status in (RESOLVIDO, FECHADO))
    return {'total': len(ncs), 'corrigidas': corrigidas,
            'itens': Counter(n.item_texto for n in ncs).most_common(5)}


def _ocorrencias(local_id, de, ate):
    from facilities.rotas.models import OCORRENCIA_RESOLVIDA, OcorrenciaPublica
    lista = OcorrenciaPublica.query.filter(
        OcorrenciaPublica.client_id == local_id,
        OcorrenciaPublica.criada_em >= _utc(de),
        OcorrenciaPublica.criada_em < _utc(ate + timedelta(days=1))).all()
    resolvidas = [o for o in lista if o.status == OCORRENCIA_RESOLVIDA and o.resolvida_em]
    com_prazo = [o for o in resolvidas if o.prazo]
    tempos = [(o.resolvida_em - o.criada_em).total_seconds() for o in resolvidas]
    no_prazo = sum(1 for o in com_prazo if o.resolvida_em <= o.prazo)
    return {'total': len(lista), 'resolvidas': len(resolvidas),
            'pct_no_prazo': round(100 * no_prazo / len(com_prazo), 1) if com_prazo else None,
            'tempo_medio_min': (round(sum(tempos) / len(tempos) / 60) if tempos else None)}


def _elogios(local_id, de, ate):
    """Os elogios do público no mês: média de estrelas, quantos, e os
    comentários mais recentes (sem nome de ninguém)."""
    from facilities.rotas.models import ElogioPublico
    lista = (ElogioPublico.query.filter(
        ElogioPublico.client_id == local_id, ElogioPublico.criado_em >= _utc(de),
        ElogioPublico.criado_em < _utc(ate + timedelta(days=1)))
        .order_by(ElogioPublico.criado_em.desc()).all())
    return {'total': len(lista),
            'media': round(sum(e.nota for e in lista) / len(lista), 1) if lista else None,
            'comentarios': [{'quando': e.criado_em, 'nota': e.nota, 'texto': e.texto,
                             'onde': f'{e.ponto.ambiente.nome} · {e.ponto.nome}'}
                            for e in lista if e.texto][:ELOGIOS_NA_LISTA]}


def _visitas(local_id, de, ate):
    from facilities.visitas.models import FEITA, Visita
    lista = Visita.query.filter(Visita.client_id == local_id, Visita.vencimento >= de,
                                Visita.vencimento <= ate).all()
    feitas = [v for v in lista if v.status == FEITA]
    return {'programadas': len(lista), 'feitas': len(feitas),
            'conformes': sum(1 for v in feitas if not v.n_nao_conformes)}


def _cobrancas(local_id, de, ate):
    from facilities.portal.models import (EVENTO_RESPOSTA, FECHADA, Cobranca, CobrancaEvento)
    lista = Cobranca.query.filter(Cobranca.client_id == local_id,
                                  Cobranca.criada_em >= _utc(de),
                                  Cobranca.criada_em < _utc(ate + timedelta(days=1))).all()
    respondidas = no_prazo = 0
    for c in lista:
        r = (CobrancaEvento.query.filter_by(cobranca_id=c.id, tipo=EVENTO_RESPOSTA)
             .order_by(CobrancaEvento.id).first())
        if r is not None:
            respondidas += 1
            prazo = r.prazo or c.prazo
            no_prazo += 1 if prazo is None or r.created_at <= prazo else 0
    return {'abertas': len(lista), 'respondidas': respondidas, 'no_prazo': no_prazo,
            'encerradas': sum(1 for c in lista if c.status == FECHADA)}


def dados(local, primeiro, agora=None):
    """Tudo o que o relatório mostra, num dicionário (tela, PDF e Excel)."""
    from facilities.paineis.servico import FAIXAS, INDICADORES, nota_do_local
    agora = agora or datetime.utcnow()
    ate = fim_do_mes(primeiro)
    anterior = mes_anterior(primeiro)
    nota = nota_do_local(local, primeiro, ate, agora)
    nota_ant = nota_do_local(local, anterior, fim_do_mes(anterior), agora)
    variacao = (round(nota['nota'] - nota_ant['nota'], 1)
                if nota['nota'] is not None and nota_ant['nota'] is not None else None)
    return {
        'local': local, 'cliente': local.contratante.nome if local.contratante else None,
        'mes': primeiro, 'ate': ate, 'nome_do_mes': nome_do_mes(primeiro),
        'nota': nota, 'nota_anterior': nota_ant, 'variacao': variacao,
        'faixas': FAIXAS, 'indicadores': INDICADORES,
        'rotinas': _rotinas_por_ambiente(local.id, primeiro, ate, agora),
        'chamados': _chamados(local.id, primeiro, ate),
        'ncs': _nao_conformidades(local.id, primeiro, ate),
        'ocorrencias': _ocorrencias(local.id, primeiro, ate),
        'elogios': _elogios(local.id, primeiro, ate),
        'visitas': _visitas(local.id, primeiro, ate),
        'cobrancas': _cobrancas(local.id, primeiro, ate),
        'gerado_em': agora,
    }


# ── As fotos ──────────────────────────────────────────────────────────────

def candidatas(local_id, primeiro):
    """As fotos do mês que podem ir no relatório, com legenda sem nomes:
    checklists (as de depois primeiro), chamados resolvidos (antes e depois)
    e visitas de supervisão feitas."""
    from facilities.chamados.models import Chamado, ChamadoAnexo
    from facilities.rotas.models import Execucao, ExecucaoFoto
    from facilities.visitas.models import FEITA, Visita, VisitaFoto
    ini, fim = _utc(primeiro), _utc(fim_do_mes(primeiro) + timedelta(days=1))
    fotos = []
    for f, ex in (db.session.query(ExecucaoFoto, Execucao)
                  .join(Execucao, Execucao.id == ExecucaoFoto.execucao_id)
                  .filter(Execucao.client_id == local_id, Execucao.concluida_em >= ini,
                          Execucao.concluida_em < fim)
                  .order_by(Execucao.concluida_em).all()):
        fotos.append({'ref': f'execucao:{f.id}', 'tipo': 'execucao', 'id': f.id,
                      'momento': f.momento, 'grupo': ex.ponto.ambiente.nome,
                      'legenda': f'{ex.ponto.ambiente.nome} · {ex.ponto.nome} · '
                                 f'{ex.versao.modelo.nome} · {tempo.fmt(ex.concluida_em)}',
                      'quando': ex.concluida_em})
    for a, ch in (db.session.query(ChamadoAnexo, Chamado)
                  .join(Chamado, Chamado.id == ChamadoAnexo.chamado_id)
                  .filter(Chamado.client_id == local_id, Chamado.resolvido_em.isnot(None),
                          Chamado.resolvido_em >= ini, Chamado.resolvido_em < fim)
                  .order_by(Chamado.resolvido_em).all()):
        if not (a.mime or '').startswith('image/'):
            continue
        fotos.append({'ref': f'chamado:{a.id}', 'tipo': 'chamado', 'id': a.id,
                      'momento': a.momento, 'grupo': ch.numero,
                      'legenda': f'{ch.numero} · {ch.titulo} · '
                                 f'{"depois" if a.momento == "depois" else "antes"}',
                      'quando': ch.resolvido_em})
    for f, v in (db.session.query(VisitaFoto, Visita)
                 .join(Visita, Visita.id == VisitaFoto.visita_id)
                 .filter(Visita.client_id == local_id, Visita.status == FEITA,
                         Visita.feita_em >= ini, Visita.feita_em < fim)
                 .order_by(Visita.feita_em).all()):
        fotos.append({'ref': f'visita:{f.id}', 'tipo': 'visita', 'id': f.id,
                      'momento': f.momento, 'grupo': f'visita-{v.id}',
                      'legenda': f'Visita de supervisão · {v.programada.nome} · '
                                 f'{tempo.fmt(v.feita_em)}',
                      'quando': v.feita_em})
    return fotos


def amostra_automatica(fotos, n=FOTOS_NA_AMOSTRA):
    """Uma amostra que conta a história do mês: o antes e o depois de até 2
    chamados, uma foto de checklist por ambiente (a de depois, de preferência)
    e até 2 de visitas; depois completa com o resto, espalhado no mês."""
    escolha = []

    def por(tipo):
        return [f for f in fotos if f['tipo'] == tipo]
    chamados = defaultdict(list)
    for f in por('chamado'):
        chamados[f['grupo']].append(f)
    for grupo in list(chamados)[-2:]:
        par = sorted(chamados[grupo], key=lambda f: f['momento'] != 'antes')[:2]
        escolha += par
    vistos = set()
    execs = sorted(por('execucao'), key=lambda f: (f['momento'] != 'depois', f['quando']))
    for f in execs:
        if f['grupo'] not in vistos:
            vistos.add(f['grupo'])
            escolha.append(f)
    escolha += por('visita')[:2]
    resto = [f for f in fotos if f not in escolha]
    if resto and len(escolha) < n:
        passo = max(1, len(resto) // (n - len(escolha)))
        escolha += resto[::passo]
    return escolha[:n]


def relatorio_do_mes(local_id, primeiro, criar=False):
    r = RelatorioCliente.query.filter_by(client_id=local_id, mes=primeiro).first()
    if r is None and criar:
        r = RelatorioCliente(client_id=local_id, mes=primeiro)
        db.session.add(r)
        db.session.flush()
    return r


def fotos_do_relatorio(rel, fotos):
    """As escolhidas pela gestão (as que ainda existem), ou a amostra."""
    escolhidas = json.loads(rel.fotos_json) if rel is not None and rel.fotos_json else None
    if not escolhidas:
        return amostra_automatica(fotos), True
    por_ref = {f['ref']: f for f in fotos}
    return [por_ref[r] for r in escolhidas if r in por_ref], False


def escolher_fotos(local_id, primeiro, refs, user):
    if not user.e_gestao():
        raise RegraDoRelatorio('Quem escolhe as fotos é a gestão do contrato.', 403)
    validas = {f['ref'] for f in candidatas(local_id, primeiro)}
    refs = [r for r in dict.fromkeys(refs) if r in validas]
    if len(refs) > FOTOS_MAX:
        raise RegraDoRelatorio(f'No máximo {FOTOS_MAX} fotos no relatório.')
    rel = relatorio_do_mes(local_id, primeiro, criar=True)
    rel.fotos_json = json.dumps(refs) if refs else None
    return rel


def salvar_recado(local_id, primeiro, texto, user):
    if not user.e_gestao():
        raise RegraDoRelatorio('O recado ao cliente é da gestão do contrato.', 403)
    rel = relatorio_do_mes(local_id, primeiro, criar=True)
    rel.recado = (texto or '').strip()[:1500] or None
    return rel


def liberar(local_id, primeiro, user, agora=None):
    """O cliente passa a ver o relatório deste mês no portal. Só mês fechado.

    Os números, as fotos e o recado ficam CONGELADOS no que o cliente recebe
    (decisão do dono, 23/10/2026). Liberar de novo troca pela versão de agora."""
    from facilities.core.models import Client
    if not user.e_gestao():
        raise RegraDoRelatorio('Quem libera o relatório para o cliente é a gestão.', 403)
    if fim_do_mes(primeiro) >= tempo.hoje():
        raise RegraDoRelatorio('O mês ainda não acabou: libere a partir do dia 1º do mês '
                               'seguinte.')
    agora = agora or datetime.utcnow()
    rel = relatorio_do_mes(local_id, primeiro, criar=True)
    local = db.session.get(Client, local_id)
    d = dados(local, primeiro, agora)
    fotos, _auto = fotos_do_relatorio(rel, candidatas(local_id, primeiro))
    rel.congelado_json = json.dumps({'dados': _para_json(d),
                                     'fotos': [f['ref'] for f in fotos],
                                     'recado': rel.recado}, ensure_ascii=False)
    rel.liberado_em = agora
    rel.liberado_por = user.id
    return rel


def recolher(local_id, primeiro, user):
    if not user.e_gestao():
        raise RegraDoRelatorio('Só a gestão recolhe um relatório liberado.', 403)
    rel = relatorio_do_mes(local_id, primeiro)
    if rel is not None:
        rel.liberado_em = None
        rel.liberado_por = None
        rel.congelado_json = None
    return rel


# ── A versão congelada ────────────────────────────────────────────────────

def _para_json(v):
    """Os dados do relatório num formato que volta igual (datas marcadas; o
    local vira id e nome; tuplas viram listas)."""
    from facilities.core.models import Client
    if isinstance(v, Client):
        return {'__local': True, 'id': v.id, 'name': v.name}
    if isinstance(v, datetime):
        return {'__dt': v.isoformat()}
    if isinstance(v, date):
        return {'__d': v.isoformat()}
    if isinstance(v, dict):
        return {str(k): _para_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_para_json(x) for x in v]
    return v


class _LocalCongelado(dict):
    """O local da versão congelada: ``.id`` e ``.name`` como no objeto."""
    __getattr__ = dict.get


def _de_json(v):
    if isinstance(v, dict):
        if '__dt' in v:
            return datetime.fromisoformat(v['__dt'])
        if '__d' in v:
            return date.fromisoformat(v['__d'])
        if v.get('__local'):
            return _LocalCongelado(id=v['id'], name=v['name'])
        return {k: _de_json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_de_json(x) for x in v]
    return v


def congelado(rel):
    """``(dados, refs das fotos, recado)`` do que o cliente recebeu, ou None
    (relatório liberado antes do congelamento: o portal recalcula)."""
    if rel is None or not rel.congelado_json:
        return None
    bruto = json.loads(rel.congelado_json)
    return _de_json(bruto['dados']), bruto.get('fotos') or [], bruto.get('recado')


def mudancas(rel, atual):
    """O que mudou nos números desde a liberação: [(o quê, antes, agora)].
    Vazio = o cliente vê o mesmo que a tela da gestão."""
    from facilities.paineis.servico import INDICADORES
    versao = congelado(rel)
    if versao is None:
        return []
    antes = versao[0]
    linhas = [('Nota do mês', antes['nota']['nota'], atual['nota']['nota'])]
    for chave, rotulo in INDICADORES.items():
        linhas.append((rotulo, antes['nota']['indicadores'][chave]['pct'],
                       atual['nota']['indicadores'][chave]['pct']))
    linhas += [
        ('Tarefas previstas', sum(r['previstas'] for r in antes['rotinas']),
         sum(r['previstas'] for r in atual['rotinas'])),
        ('Chamados abertos', antes['chamados']['abertos'], atual['chamados']['abertos']),
        ('Chamados resolvidos', antes['chamados']['resolvidos'],
         atual['chamados']['resolvidos']),
        ('Não conformidades', antes['ncs']['total'], atual['ncs']['total']),
        ('Avisos do público', antes['ocorrencias']['total'], atual['ocorrencias']['total']),
        # Relatório liberado antes dos elogios existirem: sem a chave.
        ('Elogios do público', (antes.get('elogios') or {}).get('total'),
         (atual.get('elogios') or {}).get('total')),
        ('Visitas feitas', antes['visitas']['feitas'], atual['visitas']['feitas']),
    ]
    return [(o, a, b) for o, a, b in linhas if a != b]


def liberados(local_ids):
    return (RelatorioCliente.query
            .filter(RelatorioCliente.client_id.in_(list(local_ids) or [-1]),
                    RelatorioCliente.liberado_em.isnot(None))
            .order_by(RelatorioCliente.mes.desc(), RelatorioCliente.client_id).all())
