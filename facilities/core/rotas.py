"""Início, avisos e saúde do serviço."""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from facilities.extensions import db
from facilities.core.auth import _destino_seguro
from facilities.core.models import MODULO_CHAMADOS, MODULO_PASSAGEM, Notification

bp = Blueprint('core', __name__)

AVISOS_POR_PAGINA = 50


def avisar(user_ids, titulo, mensagem='', link=None, tipo='geral', client_id=None):
    """Grava um aviso para cada pessoa e devolve quem foi avisado (o commit é
    de quem chama).

    Só recebe quem está ativo e — com ``client_id`` — ainda tem o local na
    carteira: quem saiu do local não continua recebendo título e local dele
    (a mesma conferência dos avisos de chamado). Quem chama manda o push só
    para os devolvidos."""
    from facilities.core.hierarquia import carteira
    from facilities.core.models import User
    ids = {u for u in (user_ids or []) if u}
    if not ids:
        return set()
    avisados = set()
    for u in User.query.filter(User.id.in_(ids), User.is_active.is_(True),
                               User.is_deleted.is_(False)):
        if client_id is not None:
            cart = carteira(u)
            if cart is not None and client_id not in cart:
                continue
        db.session.add(Notification(user_id=u.id, notification_type=tipo,
                                    title=(titulo or '')[:150], message=mensagem,
                                    link=link, status='unread'))
        avisados.add(u.id)
    return avisados


@bp.app_context_processor
def _avisos_no_topo():
    """O número do sino vai para toda tela."""
    if not current_user.is_authenticated:
        return {}
    n = Notification.query.filter_by(user_id=current_user.id, status='unread').count()
    return {'avisos_nao_lidos': n}


@bp.get('/healthz')
def healthz():
    """Liveness: público, sem banco, sempre 200 com o processo de pé."""
    return jsonify({'status': 'ok'}), 200


@bp.get('/')
@login_required
def inicio():
    """O Início: o que espera a pessoa hoje (números que levam à fila de
    Demandas já filtrada), o que resolver primeiro e os atalhos do perfil."""
    from facilities.paineis.telas import ve_painel
    from facilities.rotas.telas import _pode_acompanhar
    r = current_user._effective_role()
    atalhos = []
    if ve_painel(current_user):
        atalhos.append({'nome': 'Painel', 'icone': 'bi-speedometer2', 'url': url_for('paineis.painel'),
                        'texto': 'A nota de cada local e o que está atrasado agora.'})
    if current_user.can_view(MODULO_CHAMADOS):
        atalhos.append({'nome': 'Chamados', 'icone': 'bi-tools', 'url': url_for('chamados.index'),
                        'texto': 'Abrir, atribuir, acompanhar o prazo e fechar.'})
    if current_user.can_view(MODULO_PASSAGEM):
        atalhos.append({'nome': 'Passagem de turno', 'icone': 'bi-journal-text',
                        'url': url_for('diario_operacional.index'),
                        'texto': 'O que o turno fez, o que ficou pendente e o que aconteceu.'})
    if _pode_acompanhar():
        atalhos.append({'nome': 'Rotina dos locais', 'icone': 'bi-signpost-split',
                        'url': url_for('rotas.inicio'),
                        'texto': 'Rotas e checklists, preventivas, equipe e visitas de cada local.'})
    if ve_painel(current_user):
        atalhos.append({'nome': 'Materiais e estoque', 'icone': 'bi-box-seam',
                        'url': url_for('materiais.catalogo'),
                        'texto': 'Estoque por local, consumo, pedidos de insumo e custo.'})
    numeros, primeiro = [], []
    if current_user.can_view(MODULO_CHAMADOS):
        from facilities import demandas
        from facilities.core.acesso import allowed_client_ids_or_none
        from facilities.materiais.servico import ve_custo
        from facilities.visitas.servico import PERFIS_QUE_VISITAM
        com_visitas = r in PERFIS_QUE_VISITAM + ('visualizador',)
        com_pedidos = ve_custo(current_user)
        itens = demandas.demandas(allowed_client_ids_or_none(), com_visitas=com_visitas,
                                  com_pedidos=com_pedidos, acompanha_rotas=_pode_acompanhar())
        def conta(**f):
            return sum(1 for i in itens if all(i[k] == v for k, v in f.items()))
        numeros = [
            {'rotulo': 'Atrasadas', 'n': conta(situacao='atrasada'), 'tom': 'perigo',
             'icone': 'bi-alarm', 'url': url_for('demandas.painel', situacao='atrasada')},
            {'rotulo': 'Vencem hoje', 'n': conta(situacao='hoje'), 'tom': 'aviso',
             'icone': 'bi-hourglass-split', 'url': url_for('demandas.painel', situacao='hoje')},
            {'rotulo': 'Cobranças do cliente', 'n': conta(tipo='cobranca'), 'tom': 'marca',
             'icone': 'bi-megaphone', 'url': url_for('demandas.painel', tipo='cobranca')},
            {'rotulo': 'Chamados em aberto', 'n': conta(tipo='chamado') + conta(tipo='preventiva'),
             'tom': 'info', 'icone': 'bi-tools', 'url': url_for('chamados.index')},
        ]
        if com_visitas:
            numeros.append({'rotulo': 'Visitas a fazer', 'n': conta(tipo='visita'), 'tom': 'info',
                            'icone': 'bi-clipboard-check',
                            'url': url_for('demandas.painel', tipo='visita')})
        if com_pedidos:
            numeros.append({'rotulo': 'Pedidos de insumo', 'n': conta(tipo='insumo'), 'tom': 'info',
                            'icone': 'bi-box-seam', 'url': url_for('demandas.painel', tipo='insumo')})
        primeiro = itens[:6]
    return render_template('core/inicio.html', atalhos=atalhos, numeros=numeros,
                           primeiro=primeiro, tipos=_tipos_de_demanda(),
                           situacoes=_situacoes_de_demanda())


def _tipos_de_demanda():
    from facilities.demandas import TIPOS
    return TIPOS


def _situacoes_de_demanda():
    from facilities.demandas import SITUACOES
    return SITUACOES


@bp.get('/avisos')
@login_required
def avisos():
    lista = (Notification.query.filter_by(user_id=current_user.id)
             .order_by(Notification.created_at.desc()).limit(AVISOS_POR_PAGINA).all())
    return render_template('core/avisos.html', avisos=lista)


@bp.post('/avisos/<int:aviso_id>/abrir')
@login_required
def abrir_aviso(aviso_id):
    """Marca como lido e leva ao link do aviso — só se for caminho interno.

    A conferência é a mesma do ``next=`` do login: ``//host`` e ``/\\host``
    começam com "/" mas o navegador os lê como outro site. Hoje todo link de
    aviso é montado pelo servidor; a trava fica para o dia em que não for.
    """
    a = Notification.query.filter_by(id=aviso_id, user_id=current_user.id).first_or_404()
    a.status = 'read'
    db.session.commit()
    return redirect(_destino_seguro(a.link) or url_for('core.avisos'))


@bp.post('/avisos/ler-todos')
@login_required
def ler_todos():
    (Notification.query.filter_by(user_id=current_user.id, status='unread')
     .update({'status': 'read'}))
    db.session.commit()
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('core.avisos'))
