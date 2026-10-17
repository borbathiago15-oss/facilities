"""Telas das rotas: a gestão monta e acompanha no SITE; o posto executa no
APLICATIVO (``/app/turno``).

Quem faz o quê:

* Biblioteca de checklists da Trino: o administrador cria e publica; a
  gestão consulta e copia para o local.
* Checklists, rotas e escalas do local: a gestão (gerente, coordenador,
  administrador), nos locais da carteira.
* Acompanhamento do dia e execuções: a gestão, o supervisor e a diretoria.
* Executar: o pessoal do posto (e o supervisor), pelo aplicativo.
"""
import io
import json
from datetime import datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities import tempo
from facilities.extensions import csrf, db
from facilities.core.acesso import allowed_client_ids_or_none, clientes_visiveis, require_client
from facilities.core.models import Client
from facilities.cadastros.models import PontoInspecao
from facilities.rotas import servico
from facilities.rotas.models import (MOTIVOS_NAO_REALIZADA, SITUACOES, TIPOS_DE_ITEM,
                                     ChecklistModelo, Execucao, ExecucaoFoto, NaoConformidade,
                                     Rota, RotaEscala, RotaItem, TarefaDia)
from facilities.rotas.servico import RegraDaRota

bp = Blueprint('rotas', __name__)

LINHAS_EM_BRANCO = 4


def _perfil():
    return current_user._effective_role()


def _pode_montar():
    return current_user.e_gestao()


def _pode_acompanhar():
    return current_user.e_gestao() or _perfil() in ('supervisor', 'visualizador')


def _local(cid, montar=False):
    if not (_pode_montar() if montar else _pode_acompanhar()):
        raise Forbidden('As rotas são montadas e acompanhadas pela gestão.')
    loc = db.get_or_404(Client, cid)
    if loc.is_deleted:
        abort(404)
    require_client(loc.id)
    return loc


def _modelo(mid, montar=False):
    m = db.get_or_404(ChecklistModelo, mid)
    if m.client_id is None:
        if montar and _perfil() != 'master':
            raise Forbidden('A biblioteca da Trino é mantida pelo administrador.')
        if not _pode_acompanhar():
            raise Forbidden('Sem acesso aos checklists.')
        return m
    _local(m.client_id, montar=montar)
    return m


def _rota(rid, montar=False):
    r = db.get_or_404(Rota, rid)
    _local(r.client_id, montar=montar)
    return r


def _gravar(funcao, *args, sucesso=None, destino):
    try:
        obj = funcao(*args)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(destino)
    if sucesso:
        flash(sucesso(obj) if callable(sucesso) else sucesso, 'success')
    return redirect(destino)


# ── Início e local ────────────────────────────────────────────────────────

@bp.get('/rotas/')
@login_required
def inicio():
    if not _pode_acompanhar():
        raise Forbidden('As rotas são acompanhadas pela gestão.')
    return render_template('rotas/inicio.html', locais=clientes_visiveis(),
                           pode_montar=_pode_montar())


@bp.get('/rotas/locais/<int:cid>')
@login_required
def local(cid):
    loc = _local(cid)
    modelos = (ChecklistModelo.query.filter_by(client_id=loc.id)
               .order_by(ChecklistModelo.is_active.desc(), ChecklistModelo.nome).all())
    biblioteca = (ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                               ChecklistModelo.is_active.is_(True))
                  .order_by(ChecklistModelo.nome).all())
    rotas = Rota.query.filter_by(client_id=loc.id).order_by(Rota.is_active.desc(),
                                                            Rota.hora_inicio).all()
    return render_template('rotas/local.html', local=loc, modelos=modelos,
                           biblioteca=[b for b in biblioteca if b.versao_atual],
                           rotas=rotas, pode_montar=_pode_montar(),
                           dias=servico.DIAS_DA_SEMANA)


# ── Checklists ────────────────────────────────────────────────────────────

@bp.get('/rotas/biblioteca')
@login_required
def biblioteca():
    if not _pode_acompanhar():
        raise Forbidden('Sem acesso aos checklists.')
    modelos = (ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None))
               .order_by(ChecklistModelo.is_active.desc(), ChecklistModelo.nome).all())
    return render_template('rotas/biblioteca.html', modelos=modelos,
                           pode_montar=_perfil() == 'master')


@bp.post('/rotas/biblioteca')
@login_required
def criar_na_biblioteca():
    if _perfil() != 'master':
        raise Forbidden('A biblioteca da Trino é mantida pelo administrador.')
    try:
        m = servico.criar_modelo(None, request.form, current_user)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('rotas.biblioteca'))
    return redirect(url_for('rotas.modelo', mid=m.id))


@bp.post('/rotas/locais/<int:cid>/modelos')
@login_required
def criar_modelo(cid):
    loc = _local(cid, montar=True)
    try:
        m = servico.criar_modelo(loc.id, request.form, current_user)
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('rotas.local', cid=loc.id))
    return redirect(url_for('rotas.modelo', mid=m.id))


@bp.post('/rotas/locais/<int:cid>/copiar')
@login_required
def copiar(cid):
    loc = _local(cid, montar=True)
    origem = db.get_or_404(ChecklistModelo, int(request.form.get('modelo_id') or 0))
    return _gravar(servico.copiar_da_biblioteca, origem, loc.id, current_user,
                   sucesso=lambda m: f'"{m.nome}" copiado para este local. Ajuste o que '
                                     'precisar e publique.',
                   destino=url_for('rotas.local', cid=loc.id))


@bp.get('/rotas/modelos/<int:mid>')
@login_required
def modelo(mid):
    m = _modelo(mid)
    v = m.versao_atual
    itens = servico.itens_da_versao(v) if v else []
    pode = (_perfil() == 'master') if m.client_id is None else _pode_montar()
    return render_template('rotas/modelo.html', modelo=m, itens=itens,
                           linhas=itens + [{}] * LINHAS_EM_BRANCO, tipos=TIPOS_DE_ITEM,
                           pode_montar=pode)


def _itens_do_formulario(form):
    campos = ('texto', 'tipo', 'opcoes', 'minimo', 'maximo', 'problema_se', 'mostrar_se',
              'codigo', 'ordem')
    linhas = []
    n = len(form.getlist('texto'))
    for i in range(n):
        linha = {c: (form.getlist(c)[i] if i < len(form.getlist(c)) else '') for c in campos}
        linha['obrigatorio'] = str(i) in form.getlist('obrigatorio')
        linha['exige_foto'] = str(i) in form.getlist('exige_foto')
        linhas.append(linha)

    def ordem(par):
        i, linha = par
        bruto = str(linha.get('ordem') or '').strip()
        return (int(bruto) if bruto.isdigit() else 1000 + i, i)
    return [linha for _i, linha in sorted(enumerate(linhas), key=ordem)]


@bp.post('/rotas/modelos/<int:mid>')
@login_required
def publicar(mid):
    m = _modelo(mid, montar=True)
    try:
        itens = servico.normalizar_itens(_itens_do_formulario(request.form))
        v, publicou = servico.publicar(m, itens, request.form, current_user)
        m.is_active = True
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('rotas.modelo', mid=m.id))
    flash(f'Versão {v.numero} publicada. As tarefas geradas daqui em diante usam esta '
          'versão; o que já foi feito continua com as perguntas da época.' if publicou
          else 'Nada mudou: a versão publicada continua a mesma.', 'success')
    return redirect(url_for('rotas.modelo', mid=m.id))


# ── Rotas, itens e escala ─────────────────────────────────────────────────

@bp.post('/rotas/locais/<int:cid>/rotas')
@login_required
def criar_rota(cid):
    loc = _local(cid, montar=True)
    try:
        r = servico.salvar_rota(loc, None, _com_dias(request.form))
        db.session.commit()
    except RegraDaRota as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('rotas.local', cid=loc.id))
    flash('Rota criada. Agora inclua as atividades (ponto, checklist e horários) e escale '
          'quem executa.', 'success')
    return redirect(url_for('rotas.rota', rid=r.id))


def _com_dias(form):
    dados = form.to_dict()
    dados['dias_semana'] = ''.join(form.getlist('dias_semana'))
    return dados


@bp.get('/rotas/<int:rid>')
@login_required
def rota(rid):
    r = _rota(rid)
    pontos = (PontoInspecao.query.filter_by(client_id=r.client_id, is_active=True)
              .order_by(PontoInspecao.nome).all())
    modelos = (ChecklistModelo.query.filter_by(client_id=r.client_id, is_active=True)
               .order_by(ChecklistModelo.nome).all())
    return render_template('rotas/rota.html', rota=r, pontos=pontos,
                           modelos=[m for m in modelos if m.versao_atual],
                           pessoas=servico.pessoas_escalaveis(r.client_id),
                           pode_montar=_pode_montar(), dias=servico.DIAS_DA_SEMANA,
                           hoje=tempo.hoje().isoformat(),
                           horarios=lambda it: servico.horarios_do_item(r, it, tempo.hoje()))


@bp.post('/rotas/<int:rid>')
@login_required
def editar_rota(rid):
    r = _rota(rid, montar=True)
    return _gravar(servico.salvar_rota, r.local, r, _com_dias(request.form),
                   sucesso='Rota atualizada. Vale para as tarefas geradas daqui em diante.',
                   destino=url_for('rotas.rota', rid=r.id))


@bp.post('/rotas/<int:rid>/ativo')
@login_required
def ativo_rota(rid):
    r = _rota(rid, montar=True)
    r.is_active = request.form.get('ativo') == '1'
    db.session.commit()
    flash('Rota reativada.' if r.is_active else
          'Rota desativada: não gera mais tarefas (o histórico fica).', 'success')
    return redirect(url_for('rotas.rota', rid=r.id))


@bp.post('/rotas/<int:rid>/itens')
@login_required
def criar_item(rid):
    r = _rota(rid, montar=True)
    return _gravar(servico.salvar_item, r, None, request.form,
                   sucesso='Atividade incluída na rota.', destino=url_for('rotas.rota', rid=r.id))


@bp.post('/rotas/<int:rid>/itens/<int:iid>')
@login_required
def editar_item(rid, iid):
    r = _rota(rid, montar=True)
    it = db.get_or_404(RotaItem, iid)
    if it.rota_id != r.id:
        abort(404)
    if request.form.get('ativo') in ('0', '1'):
        it.is_active = request.form.get('ativo') == '1'
        db.session.commit()
        flash('Atividade reativada.' if it.is_active else 'Atividade tirada da rota.', 'success')
        return redirect(url_for('rotas.rota', rid=r.id))
    return _gravar(servico.salvar_item, r, it, request.form,
                   sucesso='Atividade atualizada.', destino=url_for('rotas.rota', rid=r.id))


@bp.post('/rotas/<int:rid>/escalas')
@login_required
def criar_escala(rid):
    r = _rota(rid, montar=True)
    return _gravar(servico.salvar_escala, r, _com_dias(request.form),
                   sucesso=lambda e: f'{e.pessoa.name} escalado(a) nesta rota.',
                   destino=url_for('rotas.rota', rid=r.id))


@bp.post('/rotas/<int:rid>/escalas/<int:eid>/encerrar')
@login_required
def encerrar_escala(rid, eid):
    r = _rota(rid, montar=True)
    e = db.get_or_404(RotaEscala, eid)
    if e.rota_id != r.id:
        abort(404)
    e.is_active = False
    db.session.commit()
    flash(f'Escala de {e.pessoa.name} encerrada. As tarefas já geradas continuam com o nome '
          'dela; as próximas seguem a escala atual.', 'success')
    return redirect(url_for('rotas.rota', rid=r.id))


# ── Acompanhamento ────────────────────────────────────────────────────────

@bp.get('/rotas/locais/<int:cid>/dia')
@login_required
def dia(cid):
    loc = _local(cid)
    try:
        d = datetime.strptime(request.args.get('data') or '', '%Y-%m-%d').date()
    except ValueError:
        d = tempo.hoje()
    if d == tempo.hoje():
        servico.garantir_hoje([loc.id])
        db.session.commit()
    tarefas = servico.tarefas_do_dia([loc.id], d)
    agora = datetime.utcnow()
    no_prazo, base, pct = servico.aderencia(tarefas, agora)
    extras = (Execucao.query.filter(Execucao.client_id == loc.id, Execucao.extra.is_(True))
              .filter(Execucao.concluida_em >= tempo.para_utc(d, datetime.min.time()))
              .order_by(Execucao.concluida_em).all())
    extras = [e for e in extras if tempo.local(e.concluida_em).date() == d]
    return render_template('rotas/dia.html', local=loc, data=d, tarefas=tarefas, agora=agora,
                           situacao=servico.situacao, situacoes=SITUACOES,
                           motivos=MOTIVOS_NAO_REALIZADA, extras=extras,
                           aderencia={'no_prazo': no_prazo, 'base': base, 'pct': pct})


def _execucao(eid):
    ex = db.get_or_404(Execucao, eid)
    permitidos = allowed_client_ids_or_none()
    if permitidos is not None and ex.client_id not in permitidos:
        raise Forbidden('Esta execução é de um local que não está entre os seus.')
    if not (_pode_acompanhar() or ex.user_id == current_user.id):
        raise Forbidden('Sem acesso a esta execução.')
    return ex


@bp.get('/rotas/execucoes/<int:eid>')
@login_required
def execucao(eid):
    ex = _execucao(eid)
    return render_template('rotas/execucao.html', ex=ex,
                           itens=servico.itens_da_versao(ex.versao),
                           respostas=servico.respostas_vigentes(ex),
                           originais=json.loads(ex.respostas_json or '{}'),
                           pode_corrigir=current_user.e_gestao())


@bp.post('/rotas/execucoes/<int:eid>/corrigir')
@login_required
def corrigir(eid):
    ex = _execucao(eid)
    novas = {k[len('r_'):]: v for k, v in request.form.items() if k.startswith('r_')}
    return _gravar(servico.corrigir, ex, current_user, request.form.get('motivo'), novas,
                   sucesso='Correção registrada. A resposta original continua na trilha.',
                   destino=url_for('rotas.execucao', eid=ex.id))


@bp.post('/rotas/nao-conformidades/<int:nid>/chamado')
@login_required
def chamado_da_nc(nid):
    nc = db.get_or_404(NaoConformidade, nid)
    ex = _execucao(nc.execucao_id)
    from facilities.chamados.servico import RecusaChamado
    try:
        servico.abrir_chamado_da_nc(nc, current_user)
        db.session.commit()
    except RecusaChamado as erro:
        db.session.rollback()
        flash(erro.mensagem, 'danger')
        return redirect(url_for('rotas.execucao', eid=ex.id))
    return redirect(url_for('chamados.ver', chamado_id=nc.chamado_id))


@bp.get('/rotas/fotos/<int:fid>')
@login_required
def foto(fid):
    from facilities.core.anexos import storage
    f = db.get_or_404(ExecucaoFoto, fid)
    _execucao(f.execucao_id)
    try:
        dados = storage().load(f.storage_key)
    except Exception:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype=f.mime or 'image/jpeg')


# ── Agendador por HTTP (o relógio externo da hospedagem) ──────────────────

@bp.post('/rotas/agendador')
@csrf.exempt
def agendador_http():
    """Uma rodada do agendador, chamada pelo relógio da hospedagem com
    ``Authorization: Bearer <AGENDADOR_TOKEN>``. Sem o token configurado, a
    rota não existe (404)."""
    import hmac
    import os
    token = (os.environ.get('AGENDADOR_TOKEN') or '').strip()
    if not token:
        abort(404)
    enviado = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    if not hmac.compare_digest(enviado.encode(), token.encode()):
        abort(403)
    try:
        reg = servico.rodar(origem='http')
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('agendador falhou')
        return jsonify({'ok': False}), 500
    return jsonify({'ok': True, 'geradas': reg.tarefas_geradas,
                    'perdidas': reg.tarefas_perdidas})


# ── Aplicativo: o turno de quem está no posto ─────────────────────────────

def _dados_do_turno(locais):
    """Tudo que a tela "Meu turno" precisa, também SEM internet: as tarefas
    de hoje, os checklists delas e os pontos (pelo código do QR)."""
    ids = [c.id for c in locais]
    servico.garantir_hoje(ids)
    db.session.commit()
    hoje = tempo.hoje()
    tarefas = []
    for d in (hoje - timedelta(days=1), hoje):
        tarefas += servico.tarefas_do_dia(ids, d)
    agora = datetime.utcnow()
    vivas = [t for t in tarefas if t.fim_do_turno >= agora or t.data == hoje]
    versoes, pontos = {}, {}
    for t in vivas:
        versoes[t.versao_id] = t.versao
    for p in PontoInspecao.query.filter(PontoInspecao.client_id.in_(ids or [-1]),
                                        PontoInspecao.is_active.is_(True)):
        pontos[p.codigo_qr] = p
    modelos = (ChecklistModelo.query.filter(ChecklistModelo.client_id.in_(ids or [-1]),
                                            ChecklistModelo.is_active.is_(True)).all())
    for m in modelos:
        if m.versao_atual:
            versoes[m.versao_atual.id] = m.versao_atual

    def v_json(v):
        return {'id': v.id, 'modelo': v.modelo.nome, 'numero': v.numero,
                'procedimento': v.modelo.descricao or '', 'itens': servico.itens_da_versao(v),
                'foto_antes': v.exige_foto_antes, 'foto_depois': v.exige_foto_depois}
    return {
        'usuario': current_user.id,
        'agora': agora.isoformat() + 'Z',
        'tarefas': [{
            'id': t.id, 'ponto': t.ponto.codigo_qr, 'ponto_nome': t.ponto.nome,
            'ambiente': t.ponto.ambiente.nome, 'local': t.rota.local.name,
            'rota': t.rota.nome, 'hora': tempo.fmt(t.previsto_para, '%H:%M'),
            'previsto': t.previsto_para.isoformat() + 'Z', 'tolerancia': t.tolerancia_min,
            'fim_turno': t.fim_do_turno.isoformat() + 'Z', 'versao': t.versao_id,
            'minha': t.user_id == current_user.id, 'escalado': t.pessoa.name if t.pessoa else '',
            'status': t.status, 'situacao': servico.situacao(t, agora),
        } for t in vivas],
        'versoes': {str(k): v_json(v) for k, v in versoes.items()},
        'pontos': {codigo: {'id': p.id, 'nome': p.nome, 'ambiente': p.ambiente.nome,
                            'descricao': p.descricao or '', 'local': p.ambiente.setor.local.name,
                            'extras': [m.versao_atual.id for m in modelos
                                       if m.client_id == p.client_id and m.versao_atual]}
                   for codigo, p in pontos.items()},
        'motivos': MOTIVOS_NAO_REALIZADA,
        'situacoes': SITUACOES,
    }


@bp.get('/app/turno')
@login_required
def turno():
    locais = clientes_visiveis()
    return render_template('campo/turno.html', dados=_dados_do_turno(locais))


def _api_erro(erro):
    db.session.rollback()
    return jsonify({'error': erro.mensagem}), erro.codigo


@bp.post('/app/api/leitura')
@login_required
def api_leitura():
    """O QR lido COM sinal: devolve o selo com a hora do servidor."""
    dados = request.get_json(silent=True) or {}
    ponto = PontoInspecao.query.filter_by(codigo_qr=str(dados.get('ponto') or '')).first()
    if ponto is None:
        return jsonify({'error': 'QR não reconhecido.'}), 404
    require_client(ponto.client_id)
    return jsonify({'selo': servico.registrar_leitura(current_user, ponto),
                    'hora': tempo.fmt(datetime.utcnow(), '%H:%M')})


@bp.post('/app/api/execucoes')
@login_required
def api_execucao():
    """A execução: ``corpo`` (JSON) e as fotos (antes, depois, item:<código>)."""
    try:
        dados = json.loads(request.form.get('corpo') or '{}')
    except ValueError:
        return jsonify({'error': 'Envio ilegível. Tente de novo.'}), 400
    fotos = {}
    for chave in request.files:
        fotos[chave] = [f for f in request.files.getlist(chave) if f and f.filename]
    try:
        ex, nova = servico.registrar_execucao(current_user, dados, fotos)
        db.session.commit()
    except RegraDaRota as erro:
        return _api_erro(erro)
    t = ex.tarefa
    return jsonify({'id': ex.id, 'nova': nova, 'status': t.status if t else 'extra',
                    'situacao': SITUACOES.get(t.status) if t else 'Atividade extra',
                    'nao_conformes': ex.n_nao_conformes}), 201 if nova else 200


@bp.post('/app/api/tarefas/<int:tid>/nao-realizada')
@login_required
def api_nao_realizada(tid):
    t = db.get_or_404(TarefaDia, tid)
    dados = request.get_json(silent=True) or {}
    from facilities.chamados.servico import RecusaChamado
    try:
        servico.marcar_nao_realizada(t, current_user, dados.get('motivo'), dados.get('texto'),
                                     abrir_chamado=bool(dados.get('abrir_chamado')))
        db.session.commit()
    except RegraDaRota as erro:
        return _api_erro(erro)
    except RecusaChamado as erro:
        db.session.rollback()
        return jsonify({'error': erro.mensagem}), 400
    return jsonify({'ok': True, 'chamado_id': t.chamado_id})
