"""Fase 4B — o QR público, os avisos no celular e a presença.

* ``/q/<código>`` sem login: o formulário de ocorrência do público
  (``cadastros.rotas.qr`` decide quem vê o quê).
* ``/q/<código>/ocorrencia`` (POST, sem login): limitado por endereço e por
  QR, com campo-isca contra robô. Só tipo, texto curto e foto opcional.
* ``/q/<código>/acompanhar/<token>``: a situação, sem dado de ninguém.
* ``/app/api/ocorrencias/<id>/<atender|resolver>`` e a versão do site.
* ``/app/api/push`` (inscrever/sair) e ``/app/api/push/chave``.
* ``/app/api/presenca`` e ``/app/api/presenca/<id>`` (confirmar).
* Bloco do técnico (22/10/2026): o POST da ocorrência aceita ``itens`` (os
  problemas marcados do checklist do ponto) e registra o autor logado.
"""
import io

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db, limiter
from facilities.core.acesso import allowed_client_ids_or_none, require_client
from facilities.cadastros.models import PontoInspecao
from facilities.rotas import ocorrencias, presenca
from facilities.rotas.models import (SITUACOES_OCORRENCIA, TIPO_ITENS_DO_CHECKLIST,
                                     TIPOS_OCORRENCIA_PUBLICA, ConfirmacaoPresenca,
                                     OcorrenciaPublica)
from facilities.rotas.servico import PERFIS_QUE_EXECUTAM, RegraDaRota

bp = Blueprint('publico', __name__)


def _ponto_ativo(codigo):
    p = PontoInspecao.query.filter_by(codigo_qr=(codigo or '')[:32]).first()
    if p is None:
        abort(404)
    return p


def pagina_publica(ponto, erro=None, status=200):
    """A página do QR (etapa 2): "É aqui?" → os itens do checklist do ponto
    para marcar → foto → enviar. Sem checklist no ponto, a lista de tipos de
    antes continua valendo (o tipo "itens" é só do caminho com checklist)."""
    tipos = {k: v for k, v in TIPOS_OCORRENCIA_PUBLICA.items() if k != TIPO_ITENS_DO_CHECKLIST}
    return render_template('publico/ocorrencia.html', ponto=ponto, tipos=tipos, erro=erro,
                           local=ponto.ambiente.setor.local.name if ponto.ambiente else '',
                           itens_reportaveis=ocorrencias.itens_reportaveis(ponto)), status


def _chave_do_qr():
    return f'qr:{request.view_args.get("codigo", "")}'


@bp.post('/q/<codigo>/ocorrencia')
@limiter.limit('5 per hour')                          # por endereço de quem envia
@limiter.limit('30 per hour', key_func=_chave_do_qr)  # por QR (um banheiro, muitos visitantes)
@limiter.limit('100 per day', key_func=_chave_do_qr)  # teto do dia por QR (auditoria N-06)
def abrir_ocorrencia(codigo):
    ponto = _ponto_ativo(codigo)
    # Campo-isca: invisível para gente, preenchido por robô.
    if (request.form.get('site') or '').strip():
        return pagina_publica(ponto, 'Não foi possível enviar.', 400)
    try:
        oc = ocorrencias.abrir(ponto, request.form.get('tipo'), request.form.get('texto'),
                               request.files.get('foto'), itens=request.form.getlist('itens'),
                               autor=current_user)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        return pagina_publica(ponto, erro.mensagem, erro.codigo)
    return redirect(url_for('publico.acompanhar', codigo=ponto.codigo_qr, token=oc.token))


@bp.route('/q/<codigo>/elogio', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
@limiter.limit('30 per hour', key_func=_chave_do_qr, methods=['POST'])
@limiter.limit('100 per day', key_func=_chave_do_qr, methods=['POST'])
def elogio(codigo):
    """O elogio de quem passou pelo ponto: 1 a 5 estrelas e um comentário
    opcional. Sem login, sem dado de quem avaliou."""
    ponto = _ponto_ativo(codigo)
    local = ponto.ambiente.setor.local.name if ponto.ambiente else ''
    if request.method == 'GET':
        return render_template('publico/elogio.html', ponto=ponto, local=local)
    if (request.form.get('site') or '').strip():
        return render_template('publico/elogio.html', ponto=ponto, local=local,
                               erro='Não foi possível enviar.'), 400
    try:
        ocorrencias.elogiar(ponto, request.form.get('nota'), request.form.get('texto'),
                            autor=current_user)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        return render_template('publico/elogio.html', ponto=ponto, local=local,
                               erro=erro.mensagem), erro.codigo
    return render_template('publico/elogio_obrigado.html', ponto=ponto)


@bp.get('/q/<codigo>/acompanhar/<token>')
def acompanhar(codigo, token):
    oc = OcorrenciaPublica.query.filter_by(token=(token or '')[:40]).first()
    if oc is None or oc.ponto.codigo_qr != codigo:
        abort(404)
    return render_template('publico/acompanhar.html', oc=oc, tipos=TIPOS_OCORRENCIA_PUBLICA,
                           situacoes=SITUACOES_OCORRENCIA,
                           atrasada=ocorrencias.atrasada(oc))


# ── A equipe e a gestão atendem ───────────────────────────────────────────

def _ocorrencia_da_carteira(oid):
    oc = db.get_or_404(OcorrenciaPublica, oid)
    permitidos = allowed_client_ids_or_none()
    if permitidos is not None and oc.client_id not in permitidos:
        raise Forbidden('Esta ocorrência é de um local que não está entre os seus.')
    if current_user._effective_role() not in PERFIS_QUE_EXECUTAM:
        raise Forbidden('Seu perfil não atende ocorrências.')
    return oc


def _agir(oc, acao):
    if acao == 'atender':
        ocorrencias.atender(oc, current_user)
    elif acao == 'resolver':
        ocorrencias.resolver(oc, current_user, request.values.get('resolucao') or
                             (request.get_json(silent=True) or {}).get('resolucao'))
    else:
        abort(404)


@bp.post('/app/api/ocorrencias/<int:oid>/<acao>')
@login_required
def api_ocorrencia(oid, acao):
    oc = _ocorrencia_da_carteira(oid)
    try:
        _agir(oc, acao)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        return jsonify({'error': erro.mensagem}), erro.codigo
    return jsonify({'ok': True, 'status': oc.status,
                    'situacao': SITUACOES_OCORRENCIA[oc.status]})


@bp.post('/rotas/ocorrencias/<int:oid>/<acao>')
@login_required
def ocorrencia_no_site(oid, acao):
    oc = _ocorrencia_da_carteira(oid)
    try:
        _agir(oc, acao)
        db.session.commit()
        flash('Ocorrência resolvida.' if acao == 'resolver' else 'Ocorrência em atendimento.',
              'success')
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
    return redirect(url_for('rotas.dia', cid=oc.client_id))


@bp.get('/rotas/ocorrencias/<int:oid>/foto')
@login_required
def foto_da_ocorrencia(oid):
    from facilities.core.anexos import storage
    oc = db.get_or_404(OcorrenciaPublica, oid)
    require_client(oc.client_id)
    if not oc.foto_key:
        abort(404)
    try:
        dados = storage().load(oc.foto_key)
    except Exception:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype=oc.foto_mime or 'image/jpeg')


# ── Avisos no celular (Web Push) ──────────────────────────────────────────

@bp.get('/app/api/push/chave')
@login_required
def push_chave():
    from facilities.core import push
    return jsonify({'chave': push.chave_publica() if push.ligado() else None})


@bp.post('/app/api/push')
@login_required
def push_inscrever():
    from facilities.core import push
    try:
        push.inscrever(current_user, request.get_json(silent=True) or {},
                       request.headers.get('User-Agent', ''))
        db.session.commit()
    except ValueError as erro:
        db.session.rollback()
        return jsonify({'error': str(erro)}), 400
    return jsonify({'ok': True})


@bp.delete('/app/api/push')
@login_required
def push_sair():
    from facilities.core.models import PushInscricao
    endpoint = str((request.get_json(silent=True) or {}).get('endpoint') or '')
    PushInscricao.query.filter_by(endpoint=endpoint, user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'ok': True})


# ── Presença ──────────────────────────────────────────────────────────────

@bp.get('/app/api/presenca')
@login_required
def presenca_agora():
    c = presenca.pendente_de(current_user)
    if c is None:
        return jsonify({'pedido': None})
    return jsonify({'pedido': {'id': c.id, 'rota': c.rota.nome,
                               'ate': tempo.fmt(c.prazo_ate, '%H:%M')}})


@bp.post('/app/api/presenca/<int:pid>')
@login_required
def presenca_confirmar(pid):
    c = db.get_or_404(ConfirmacaoPresenca, pid)
    try:
        presenca.confirmar(c, current_user)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        return jsonify({'error': erro.mensagem}), erro.codigo
    return jsonify({'ok': True, 'status': c.status,
                    'mensagem': 'Presença confirmada.' if c.status == 'confirmada' else
                    'O prazo já tinha passado: a resposta ficou registrada como tardia.'})
