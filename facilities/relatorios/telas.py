"""Telas dos relatórios. Primeiro o do CLIENTE (decisão do dono): a gestão vê
o relatório do mês, troca as fotos se quiser, deixa um recado e LIBERA; o
cliente vê os liberados no portal (``portal.relatorios``). PDF e Excel nos
dois lados."""
import io
from datetime import timedelta

from flask import (Blueprint, abort, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import db
from facilities.core.acesso import clientes_visiveis, require_client
from facilities.core.models import Client
from facilities.relatorios import cliente as rel
from facilities.relatorios.cliente import RegraDoRelatorio

bp = Blueprint('relatorios', __name__, url_prefix='/relatorios')

PERFIS_QUE_LEEM = ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')


def le_relatorios(user):
    return user._effective_role() in PERFIS_QUE_LEEM


def _so_quem_le():
    if not le_relatorios(current_user):
        raise Forbidden('Os relatórios são da supervisão, da gestão e da diretoria.')


def _local(cid):
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


# ── Fotos: endereço (para a tela) e bytes (para o PDF) ────────────────────

def url_da_foto(f, portal=False):
    if f['tipo'] == 'execucao':
        return url_for('portal.foto_checklist' if portal else 'rotas.foto', fid=f['id'])
    if f['tipo'] == 'chamado':
        return url_for('portal.foto_chamado' if portal else 'chamados.baixar_anexo',
                       anexo_id=f['id'])
    return url_for('portal.foto_visita' if portal else 'visitas.foto', vfid=f['id'])


def carregar_foto(f):
    from facilities.chamados.models import ChamadoAnexo
    from facilities.core.anexos import storage
    from facilities.rotas.models import ExecucaoFoto
    from facilities.visitas.models import VisitaFoto
    modelo = {'execucao': ExecucaoFoto, 'chamado': ChamadoAnexo, 'visita': VisitaFoto}[f['tipo']]
    reg = db.session.get(modelo, f['id'])
    if reg is None:
        return None
    try:
        return storage().load(reg.storage_key)
    except Exception:
        return None


def montar(local, primeiro):
    """Os números, as fotos escolhidas (ou a amostra) e o registro do mês."""
    d = rel.dados(local, primeiro)
    registro = rel.relatorio_do_mes(local.id, primeiro)
    todas = rel.candidatas(local.id, primeiro)
    fotos, automatica = rel.fotos_do_relatorio(registro, todas)
    return d, registro, todas, fotos, automatica


def arquivo(local, primeiro, formato, so_liberado=False):
    from facilities.relatorios import arquivos
    d, registro, _todas, fotos, _auto = montar(local, primeiro)
    if so_liberado and (registro is None or registro.liberado_em is None):
        abort(404)
    nome = f'relatorio-{local.name}-{primeiro.strftime("%Y-%m")}'
    nome = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in nome).lower()
    if formato == 'pdf':
        corpo = arquivos.pdf(d, fotos, carregar_foto, registro.recado if registro else None)
        tipo, ext = 'application/pdf', 'pdf'
    elif formato == 'xlsx':
        corpo = arquivos.excel(d)
        tipo = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ext = 'xlsx'
    else:
        abort(404)
    # send_file monta o nome em ASCII + filename* (UTF-8): local com "ł" ou
    # "中" no nome não quebra o cabeçalho (auditoria SEC-025).
    return send_file(io.BytesIO(corpo), mimetype=tipo, as_attachment=True,
                     download_name=f'{nome}.{ext}')


# ── Gestão ────────────────────────────────────────────────────────────────

@bp.get('/')
@login_required
def inicio():
    _so_quem_le()
    primeiro = rel.mes_de(request.args.get('mes'))
    locais = clientes_visiveis()
    registros = {r.client_id: r for r in rel.RelatorioCliente.query.filter(
        rel.RelatorioCliente.client_id.in_([c.id for c in locais] or [-1]),
        rel.RelatorioCliente.mes == primeiro)}
    return render_template('relatorios/inicio.html', locais=locais, primeiro=primeiro,
                           registros=registros, nome_do_mes=rel.nome_do_mes(primeiro),
                           anterior=rel.mes_anterior(primeiro).strftime('%Y-%m'),
                           seguinte=(rel.fim_do_mes(primeiro) + timedelta(days=1))
                           .strftime('%Y-%m'))


@bp.get('/cliente/<int:cid>/<mes>')
@login_required
def cliente(cid, mes):
    _so_quem_le()
    loc = _local(cid)
    primeiro = rel.mes_de(mes)
    d, registro, todas, fotos, automatica = montar(loc, primeiro)
    escolhidas = {f['ref'] for f in fotos}
    return render_template('relatorios/cliente.html', d=d, registro=registro, todas=todas,
                           fotos=fotos, automatica=automatica, escolhidas=escolhidas,
                           url_da_foto=url_da_foto, portal=False, mes=primeiro.strftime('%Y-%m'),
                           pode_gerir=current_user.e_gestao(), fotos_max=rel.FOTOS_MAX,
                           mes_fechado=rel.fim_do_mes(primeiro) < tempo.hoje())


@bp.post('/cliente/<int:cid>/<mes>/<acao>')
@login_required
def agir(cid, mes, acao):
    _so_quem_le()
    loc = _local(cid)
    primeiro = rel.mes_de(mes)
    destino = url_for('relatorios.cliente', cid=loc.id, mes=primeiro.strftime('%Y-%m'))
    passos = {
        'fotos': (lambda: rel.escolher_fotos(loc.id, primeiro, request.form.getlist('foto'),
                                             current_user), 'Fotos do relatório salvas.'),
        'amostra': (lambda: rel.escolher_fotos(loc.id, primeiro, [], current_user),
                    'Voltou para a amostra automática de fotos.'),
        'recado': (lambda: rel.salvar_recado(loc.id, primeiro, request.form.get('recado'),
                                             current_user), 'Recado salvo.'),
        'liberar': (lambda: rel.liberar(loc.id, primeiro, current_user),
                    'Relatório liberado: o cliente já vê no portal.'),
        'recolher': (lambda: rel.recolher(loc.id, primeiro, current_user),
                     'Relatório recolhido: o cliente deixa de ver até liberar de novo.'),
    }
    if acao not in passos:
        abort(404)
    fazer, ok = passos[acao]
    try:
        fazer()
        db.session.commit()
    except RegraDoRelatorio as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(destino)
    flash(ok, 'success')
    return redirect(destino)


@bp.get('/cliente/<int:cid>/<mes>/arquivo.<formato>')
@login_required
def baixar(cid, mes, formato):
    _so_quem_le()
    return arquivo(_local(cid), rel.mes_de(mes), formato)
