"""Chaves e dados da integração com o Trino Intelligence (Fase 8).

O Facilities só ENTREGA dados (D13, D42): o Intelligence lê com uma chave de
servidor e nunca escreve aqui. O custo de material fica de fora (D37, F8-3).

Formato da chave: ``fac_<prefixo>_<segredo>``. O banco guarda o SHA-256 da
chave inteira; a conferência é em tempo constante.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import Client
from facilities.integracao.models import IntegracaoAcesso, IntegracaoChave

MAX_DIAS = 92
MAX_ITENS = 5000


class RegraDaIntegracao(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def _hash(chave):
    return hashlib.sha256(chave.encode()).hexdigest()


def criar_chave(nome, client_ids, todos, autor):
    """Cria a chave e devolve ``(registro, chave_em_texto)`` — o texto só
    existe neste momento."""
    nome = (nome or '').strip()[:120]
    if not nome:
        raise RegraDaIntegracao('Dê um nome à chave (ex.: Trino Intelligence — produção).')
    locais = []
    if not todos:
        ids = sorted({int(i) for i in client_ids if str(i).isdigit()})
        locais = Client.query.filter(Client.id.in_(ids or [-1]),
                                     Client.is_deleted.is_(False)).all()
        if not locais:
            raise RegraDaIntegracao('Escolha os locais que a chave pode ler (ou "todos").')
    prefixo = secrets.token_hex(4)
    texto = f'fac_{prefixo}_{secrets.token_urlsafe(32)}'
    ch = IntegracaoChave(nome=nome, prefixo=prefixo, hash_chave=_hash(texto),
                         todos_os_locais=bool(todos), criada_por=autor.id)
    ch.locais = locais
    db.session.add(ch)
    db.session.flush()
    return ch, texto


def revogar(chave, agora=None):
    chave.is_active = False
    chave.revogada_em = agora or datetime.utcnow()


def chave_do_cabecalho(cabecalho):
    """``Authorization: Bearer fac_...`` → a chave ativa, ou ``None``."""
    if not cabecalho or not cabecalho.startswith('Bearer '):
        return None
    texto = cabecalho[7:].strip()
    partes = texto.split('_')
    if len(partes) < 3 or partes[0] != 'fac':
        return None
    ch = IntegracaoChave.query.filter_by(prefixo=partes[1]).first()
    if ch is None or not ch.is_active or not hmac.compare_digest(ch.hash_chave, _hash(texto)):
        return None
    return ch


def registrar_acesso(chave, rota, parametros, status, itens=None, ip=None, agora=None):
    """O registro de cada acesso — sem a chave (só qual era, pelo id)."""
    agora = agora or datetime.utcnow()
    limpos = '&'.join(f'{k}={v}' for k, v in sorted(parametros.items())
                      if k in ('de', 'ate', 'local'))[:300]
    db.session.add(IntegracaoAcesso(chave_id=chave.id if chave else None, em=agora,
                                    rota=rota[:80], parametros=limpos or None, status=status,
                                    itens=itens, ip=(ip or '')[:45] or None))
    if chave is not None and status == 200:
        chave.ultimo_uso_em = agora


# ── Escopo e período ──────────────────────────────────────────────────────

def locais_da_chave(chave, local=None):
    q = Client.query.filter(Client.is_deleted.is_(False))
    ids = chave.client_ids()
    if ids is not None:
        q = q.filter(Client.id.in_(ids or [-1]))
    if local not in (None, ''):
        if not str(local).isdigit():
            raise RegraDaIntegracao('O parâmetro "local" é o id numérico do local.')
        alvo = q.filter(Client.id == int(local)).first()
        if alvo is None:
            raise RegraDaIntegracao('Esta chave não lê este local.', 403)
        return [alvo]
    return q.order_by(Client.id).all()


def periodo(args):
    hoje = tempo.hoje()
    try:
        de = datetime.strptime(args.get('de') or '', '%Y-%m-%d').date()
        ate = datetime.strptime(args.get('ate') or '', '%Y-%m-%d').date()
    except ValueError:
        raise RegraDaIntegracao('Informe "de" e "ate" no formato AAAA-MM-DD.')
    if de > ate:
        raise RegraDaIntegracao('"de" é depois de "ate".')
    if (ate - de).days + 1 > MAX_DIAS:
        raise RegraDaIntegracao(f'Período máximo: {MAX_DIAS} dias por consulta.')
    if de > hoje:
        raise RegraDaIntegracao('O período começa no futuro.')
    return de, ate


def _iso(dt):
    return dt.isoformat() + 'Z' if dt else None


def _utc_do_dia(dia):
    from datetime import time
    return tempo.para_utc(dia, time(0, 0))


# ── Os dados ──────────────────────────────────────────────────────────────

def dados_locais(locais):
    return [{'id': c.id, 'nome': c.name, 'cost_center': c.cost_center,
             'cliente': c.contratante.nome if c.contratante else None,
             'centro_custo_cliente': c.contratante.centro_custo if c.contratante else None,
             'estado': c.estado.sigla if c.estado else None, 'ativo': bool(c.is_active)}
            for c in locais]


def dados_chamados(locais, de, ate):
    from facilities.chamados.models import Chamado
    q = (Chamado.query.filter(Chamado.client_id.in_([c.id for c in locais] or [-1]),
                              Chamado.aberto_em >= _utc_do_dia(de),
                              Chamado.aberto_em < _utc_do_dia(ate + timedelta(days=1)))
         .order_by(Chamado.id).limit(MAX_ITENS + 1).all())
    return [{'id': ch.id, 'numero': ch.numero, 'local_id': ch.client_id, 'titulo': ch.titulo,
             'categoria': ch.categoria, 'prioridade': ch.prioridade, 'status': ch.status,
             'origem': ch.origem, 'aberto_em': _iso(ch.aberto_em), 'prazo': _iso(ch.prazo),
             'resolvido_em': _iso(ch.resolvido_em), 'fechado_em': _iso(ch.fechado_em),
             'tempo_parado_seg': ch.pausa_total_seg or 0,
             'no_prazo': (None if ch.resolvido_em is None or ch.prazo is None
                          else ch.resolvido_em <= ch.prazo)} for ch in q]


def dados_aderencia(locais, de, ate, agora=None):
    from facilities.rotas.models import (CONCLUIDA_COM_ATRASO, CONCLUIDA_NO_PRAZO,
                                         NAO_REALIZADA, PERDIDA, TarefaDia)
    from facilities.rotas.servico import aderencia
    agora = agora or datetime.utcnow()
    saida = []
    tarefas = (TarefaDia.query.filter(TarefaDia.client_id.in_([c.id for c in locais] or [-1]),
                                      TarefaDia.data >= de, TarefaDia.data <= ate)
               .order_by(TarefaDia.client_id, TarefaDia.data, TarefaDia.id).all())
    grupos = {}
    for t in tarefas:
        grupos.setdefault((t.client_id, t.data), []).append(t)
    for (cid, dia), lista in sorted(grupos.items()):
        bom, base, pct = aderencia(lista, agora)
        saida.append({'local_id': cid, 'data': dia.isoformat(), 'previstas': len(lista),
                      'vencidas_ou_encerradas': base, 'no_prazo': bom,
                      'com_atraso': sum(1 for t in lista if t.status == CONCLUIDA_COM_ATRASO),
                      'nao_realizadas': sum(1 for t in lista if t.status == NAO_REALIZADA),
                      'perdidas': sum(1 for t in lista if t.status == PERDIDA),
                      'concluidas_no_prazo': sum(1 for t in lista
                                                 if t.status == CONCLUIDA_NO_PRAZO),
                      'aderencia_pct': pct})
    return saida


def referencia_nc(nc):
    """O número que o plano de ação do Intelligence guarda (D42, por referência)."""
    return f'NC-{nc.id}'


def dados_nao_conformidades(locais, de, ate):
    from facilities.rotas.models import Execucao, NaoConformidade
    q = (NaoConformidade.query.join(Execucao, Execucao.id == NaoConformidade.execucao_id)
         .filter(NaoConformidade.client_id.in_([c.id for c in locais] or [-1]),
                 Execucao.concluida_em >= _utc_do_dia(de),
                 Execucao.concluida_em < _utc_do_dia(ate + timedelta(days=1)))
         .order_by(NaoConformidade.id).limit(MAX_ITENS + 1).all())
    saida = []
    for nc in q:
        ex = nc.execucao
        saida.append({'referencia': referencia_nc(nc), 'id': nc.id, 'local_id': nc.client_id,
                      'item': nc.item_texto, 'resposta': nc.resposta,
                      'ponto': ex.ponto.nome, 'ambiente': ex.ponto.ambiente.nome,
                      'checklist': ex.versao.modelo.nome,
                      'registrada_em': _iso(ex.concluida_em),
                      'chamado': _numero(nc.chamado_id)})
    return saida


def _numero(chamado_id):
    from facilities.chamados.models import Chamado
    ch = db.session.get(Chamado, chamado_id) if chamado_id else None
    return ch.numero if ch else None


def dados_visitas(locais, de, ate):
    from facilities.visitas.models import Visita
    q = (Visita.query.filter(Visita.client_id.in_([c.id for c in locais] or [-1]),
                             Visita.vencimento >= de, Visita.vencimento <= ate)
         .order_by(Visita.id).limit(MAX_ITENS + 1).all())
    return [{'id': v.id, 'local_id': v.client_id, 'programacao': v.programada.nome,
             'vencimento': v.vencimento.isoformat(), 'status': v.status,
             'feita_em': _iso(v.feita_em), 'nao_conformes': v.n_nao_conformes,
             'chamado': v.chamado.numero if v.chamado else None} for v in q]


def dados_nota(locais, de, ate, agora=None):
    from facilities.paineis.servico import notas
    return [{'local_id': x['local'].id, 'nota': x['nota'], 'faixa': x['faixa'],
             'indicadores': x['indicadores']}
            for x in sorted(notas(locais, de, ate, agora), key=lambda x: x['local'].id)]
