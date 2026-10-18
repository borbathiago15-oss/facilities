"""Painel único de demandas (D55, Fase 5): tudo que espera alguém, numa fila
só — chamados (inclusive os preventivos) e os avisos do público pelo QR.
Pedidos de insumo (Fase 7) e cobranças do cliente (Fase 9) entram aqui
quando chegarem.

A fila segue a carteira de quem olha e põe primeiro o que está atrasado.
"""
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.core.acesso import allowed_client_ids_or_none, clientes_visiveis

bp = Blueprint('demandas', __name__, url_prefix='/demandas')

TIPOS = {'chamado': 'Chamado', 'preventiva': 'Preventiva', 'publico': 'Aviso do público'}
SITUACOES = {'atrasada': 'Atrasada', 'hoje': 'Vence hoje', 'no_prazo': 'No prazo',
             'parada': 'Aguardando (prazo parado)', 'sem_prazo': 'Sem prazo'}
ORDEM = {'atrasada': 0, 'hoje': 1, 'no_prazo': 2, 'parada': 3, 'sem_prazo': 4}


def _situacao(prazo, agora, parada=False):
    if parada:
        return 'parada'
    if prazo is None:
        return 'sem_prazo'
    if agora > prazo:
        return 'atrasada'
    if tempo.local(prazo).date() == tempo.local(agora).date():
        return 'hoje'
    return 'no_prazo'


def demandas(client_ids, agora=None):
    from facilities.chamados.models import (AGUARDANDO, ORIGEM_PREVENTIVA, STATUS_EM_ABERTO,
                                            Chamado)
    from facilities.rotas.models import TIPOS_OCORRENCIA_PUBLICA, SITUACOES_OCORRENCIA
    from facilities.rotas.ocorrencias import abertas
    agora = agora or datetime.utcnow()
    q = Chamado.query.filter(Chamado.status.in_(STATUS_EM_ABERTO))
    if client_ids is not None:
        q = q.filter(Chamado.client_id.in_(client_ids or [-1]))
    itens = []
    for ch in q.all():
        itens.append({
            'tipo': 'preventiva' if ch.origem == ORIGEM_PREVENTIVA else 'chamado',
            'titulo': ch.titulo, 'numero': ch.numero, 'local': ch.contrato.name,
            'client_id': ch.client_id,
            'responsavel': ch.responsavel.name if ch.responsavel else '',
            'prazo': ch.prazo, 'estado': ch.status_rotulo,
            'situacao': _situacao(ch.prazo, agora, ch.status == AGUARDANDO),
            'link': f'/chamados/{ch.id}'})
    ids = client_ids if client_ids is not None else [c.id for c in clientes_visiveis()]
    for oc in abertas(ids):
        itens.append({
            'tipo': 'publico', 'titulo': f'{TIPOS_OCORRENCIA_PUBLICA[oc.tipo]} · '
                                         f'{oc.ponto.ambiente.nome} · {oc.ponto.nome}',
            'numero': '', 'local': oc.ponto.ambiente.setor.local.name,
            'client_id': oc.client_id,
            'responsavel': oc.quem_atendeu.name if oc.quem_atendeu else '',
            'prazo': oc.prazo, 'estado': SITUACOES_OCORRENCIA[oc.status],
            'situacao': _situacao(oc.prazo, agora),
            'link': f'/rotas/locais/{oc.client_id}/dia'})
    longe = agora + timedelta(days=3650)
    itens.sort(key=lambda i: (ORDEM[i['situacao']], i['prazo'] or longe))
    return itens


@bp.get('/')
@login_required
def painel():
    if not current_user.can_view('chamados'):
        raise Forbidden('Sem acesso às demandas.')
    locais = clientes_visiveis()
    ids = allowed_client_ids_or_none()
    cid = request.args.get('local', type=int)
    if cid and cid in {c.id for c in locais}:
        ids = [cid]
    itens = demandas(ids)
    contagem = {s: sum(1 for i in itens if i['situacao'] == s) for s in SITUACOES}
    tipo = request.args.get('tipo') or ''
    situacao = request.args.get('situacao') or ''
    if tipo in TIPOS:
        itens = [i for i in itens if i['tipo'] == tipo]
    if situacao in SITUACOES:
        itens = [i for i in itens if i['situacao'] == situacao]
    return render_template('demandas/painel.html', itens=itens, locais=locais, cid=cid,
                           tipo=tipo, situacao=situacao, tipos=TIPOS, situacoes=SITUACOES,
                           contagem=contagem)
