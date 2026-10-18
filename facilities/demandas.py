"""Painel único de demandas (D55, Fase 5): tudo que espera alguém, numa fila
só — chamados (inclusive os preventivos) e os avisos do público pelo QR.
Desde a Fase 6, também as visitas de supervisão em aberto; desde a Fase 7,
os pedidos de insumo; desde a Fase 9B, as cobranças do cliente que esperam a
coordenação (o prazo é a data que o cliente escolheu).

A fila segue a carteira de quem olha e põe primeiro o que está atrasado.
"""
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.core.acesso import allowed_client_ids_or_none, clientes_visiveis

bp = Blueprint('demandas', __name__, url_prefix='/demandas')

TIPOS = {'chamado': 'Chamado', 'preventiva': 'Preventiva', 'publico': 'Aviso do público',
         'visita': 'Visita de supervisão', 'insumo': 'Pedido de insumo',
         'cobranca': 'Cobrança do cliente'}
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


def demandas(client_ids, agora=None, com_visitas=True, com_pedidos=True):
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
    # Fase 6: as visitas de supervisão ainda não feitas.
    from facilities.visitas import servico as visitas
    for v in (visitas.abertas(ids) if com_visitas else []):
        p = visitas.prazo(v)
        itens.append({
            'tipo': 'visita', 'titulo': v.programada.nome, 'numero': '',
            'local': v.local.name, 'client_id': v.client_id,
            'responsavel': v.supervisor.name if v.supervisor else '',
            'prazo': p, 'estado': v.situacao_rotulo, 'situacao': _situacao(p, agora),
            'link': f'/app/visitas/{v.id}'})
    # Fase 7: os pedidos de insumo que o gestor ainda não viu.
    from facilities.materiais import servico as materiais
    for p in (materiais.pedidos_abertos(ids) if com_pedidos else []):
        itens.append({
            'tipo': 'insumo', 'titulo': p.resumo, 'numero': '', 'local': p.local.name,
            'client_id': p.client_id, 'responsavel': p.pessoa.name, 'prazo': p.prazo,
            'estado': p.situacao_rotulo, 'situacao': _situacao(p.prazo, agora),
            'link': '/materiais/pedidos'})
    # Fase 9B: as cobranças do cliente esperando a coordenação.
    from facilities.portal import servico as portal
    for cob in portal.em_aberto(ids):
        itens.append({
            'tipo': 'cobranca', 'titulo': cob.titulo, 'numero': cob.numero,
            'local': cob.local.name, 'client_id': cob.client_id, 'responsavel': '',
            'prazo': cob.prazo, 'estado': cob.status_rotulo,
            'situacao': _situacao(cob.prazo, agora), 'link': f'/cobrancas/{cob.id}'})
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
    from facilities.visitas.servico import PERFIS_QUE_VISITAM
    from facilities.materiais.servico import ve_custo
    itens = demandas(ids, com_visitas=current_user._effective_role() in PERFIS_QUE_VISITAM
                     + ('visualizador',), com_pedidos=ve_custo(current_user))
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
