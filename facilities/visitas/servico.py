"""As regras das visitas de supervisão (Fase 6, D56). O commit é de quem chama.

* Programação: checklist publicado DO LOCAL, a cada 1 a 365 dias, com um
  supervisor (ou vazio: qualquer supervisor ou gestor do local).
* Fotos (Fase 10): a visita obedece ao que o checklist pede (antes, depois,
  por item) e aceita até 5 fotos livres. Com não conformidade, as fotos vão
  para o chamado como foto de "antes" (o problema).
* Agendador: chegou a data, abre a visita e avisa quem faz (sino e celular).
  Ficou parado e perdeu datas? Abre UMA e pula para a próxima futura.
* Feita a visita, o que vier não conforme abre UM chamado (F6-3), com os
  itens na descrição; ele avisa a gestão e entra no painel de demandas.
"""
import json
from datetime import datetime, time, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import PERFIS_DE_GESTAO, User
from facilities.visitas.models import (FEITA, PERDIDA, PREVISTA, Visita, VisitaFoto,
                                       VisitaProgramada)

PERFIS_QUE_VISITAM = ('supervisor',) + tuple(PERFIS_DE_GESTAO)


class RegraDaVisita(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


FOTOS_LIVRES = 5
FOTOS_POR_CAMPO = 5


def supervisores_do_local(local_id):
    """Quem pode fazer a visita: supervisores e gestores que atendem o local."""
    from facilities.core.hierarquia import carteira
    pessoas = (User.query.filter(User.is_active.is_(True), User.is_deleted.is_(False),
                                 User.role.in_(PERFIS_QUE_VISITAM))
               .order_by(User.name).all())
    saida = []
    for p in pessoas:
        c = carteira(p)
        if c is None or local_id in c:
            saida.append(p)
    return saida


def salvar_programada(local, prog, dados, autor):
    from facilities.rotas.models import ChecklistModelo
    nome = (dados.get('nome') or '').strip()[:150]
    if not nome:
        raise RegraDaVisita('Dê um nome à visita (ex.: Visita semanal de qualidade).')
    modelo = db.session.get(ChecklistModelo, _id(dados, 'modelo_id'))
    if modelo is None or modelo.client_id != local.id or not modelo.is_active \
            or modelo.versao_atual is None:
        raise RegraDaVisita('Escolha um checklist publicado deste local.')
    bruto = str(dados.get('intervalo_dias') or '').strip()
    if not bruto.isdigit() or not 1 <= int(bruto) <= 365:
        raise RegraDaVisita('A cada quantos dias: de 1 a 365.')
    try:
        proxima = datetime.strptime(dados.get('proxima_em') or '', '%Y-%m-%d').date()
    except ValueError:
        raise RegraDaVisita('Informe a data da próxima visita.')
    sup = _id(dados, 'supervisor_id') or None
    if sup and sup not in {u.id for u in supervisores_do_local(local.id)}:
        raise RegraDaVisita('O supervisor escolhido não atende este local.')
    prog = prog or VisitaProgramada(client_id=local.id, criado_por=autor.id)
    prog.nome, prog.modelo_id, prog.intervalo_dias = nome, modelo.id, int(bruto)
    prog.proxima_em, prog.supervisor_id = proxima, sup
    if prog.id is None:
        db.session.add(prog)
    db.session.flush()
    return prog


def _avisar_quem_faz(visita):
    from facilities.core import push
    from facilities.core.rotas import avisar
    quem = {visita.supervisor_id} if visita.supervisor_id else \
        {u.id for u in supervisores_do_local(visita.client_id)
         if u._effective_role() == 'supervisor'}
    if not quem:
        from facilities.chamados.servico import gestores_do_contrato
        quem = gestores_do_contrato(visita.client_id)
    titulo = f'Visita de supervisão: {visita.programada.nome}'
    texto = f'{visita.local.name} · até {visita.vencimento.strftime("%d/%m")}.'
    link = f'/app/visitas/{visita.id}'
    quem = avisar(quem, titulo, texto, link, tipo='visita', client_id=visita.client_id)
    push.avisar(quem, titulo, texto, link, marca=f'visita-{visita.id}')


def gerar_visitas(hoje=None, agora_utc=None):
    """Abre as visitas que chegaram na data. Devolve quantas abriu."""
    agora_utc = agora_utc or datetime.utcnow()
    hoje = hoje or tempo.local(agora_utc).date()
    abertas = 0
    for prog in VisitaProgramada.query.filter(VisitaProgramada.is_active.is_(True),
                                              VisitaProgramada.proxima_em <= hoje).all():
        if prog.local is None or not prog.local.is_active or prog.local.is_deleted:
            continue
        venc = prog.proxima_em
        if Visita.query.filter_by(programada_id=prog.id, vencimento=venc).first() is None:
            v = Visita(programada_id=prog.id, client_id=prog.client_id, vencimento=venc,
                       supervisor_id=prog.supervisor_id, status=PREVISTA, criada_em=agora_utc)
            db.session.add(v)
            db.session.flush()
            _avisar_quem_faz(v)
            abertas += 1
        while prog.proxima_em <= hoje:
            prog.proxima_em += timedelta(days=prog.intervalo_dias)
    return abertas


def prazo(visita):
    """Fim do dia do vencimento, em Brasília (UTC)."""
    return tempo.para_utc(visita.vencimento, time(23, 59))


# Quanto tempo depois do vencimento a visita ainda pode ser feita (o
# supervisor que foi um dia depois ainda registra); passou disso, fecha.
FOLGA_DA_VISITA = timedelta(days=2)


def fechar_vencidas(agora_utc=None):
    """A parte do agendador: visita não feita, vencida há mais que a folga,
    vira PERDIDA (antes ficava "a fazer" para sempre)."""
    agora_utc = agora_utc or datetime.utcnow()
    limite = tempo.local(agora_utc - FOLGA_DA_VISITA).date()
    n = 0
    for v in Visita.query.filter(Visita.status == PREVISTA, Visita.vencimento < limite).all():
        if agora_utc > prazo(v) + FOLGA_DA_VISITA:
            v.status = PERDIDA
            n += 1
    return n


def pode_fazer(user, visita):
    from facilities.core.acesso import allowed_client_ids_or_none
    if user._effective_role() not in PERFIS_QUE_VISITAM:
        return False
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and visita.client_id not in permitidos:
        return False
    return visita.supervisor_id in (None, user.id) or user.e_gestao()


def abertas(client_ids, user=None):
    q = Visita.query.filter(Visita.client_id.in_(list(client_ids) or [-1]),
                            Visita.status == PREVISTA).order_by(Visita.vencimento)
    lista = q.all()
    if user is not None:
        lista = [v for v in lista if pode_fazer(user, v)]
    return lista


def _ler_fotos(fotos):
    """Confere TODAS as fotos antes de gravar qualquer coisa → {campo: [(dados, ext, mime)]}."""
    from facilities.rotas.servico import RegraDaRota, ler_imagem
    lidas = {}
    for campo, arquivos in (fotos or {}).items():
        limite = FOTOS_LIVRES if campo == 'livre' else FOTOS_POR_CAMPO
        arquivos = [a for a in arquivos if a and getattr(a, 'filename', '')]
        if campo == 'livre' and len(arquivos) > FOTOS_LIVRES:
            raise RegraDaVisita(f'No máximo {FOTOS_LIVRES} fotos livres por visita.')
        try:
            lidas[campo] = [ler_imagem(a) for a in arquivos[:limite]]
        except RegraDaRota as erro:
            raise RegraDaVisita(erro.mensagem)
    return {k: v for k, v in lidas.items() if v}


def _guardar_fotos(visita, lidas):
    import uuid
    from facilities.core.anexos import storage
    gravadas = []
    for campo, lista in lidas.items():
        if campo in ('antes', 'depois', 'livre'):
            momento, item = campo, None
        elif campo.startswith('item:'):
            momento, item = 'item', campo.split(':', 1)[1][:60]
        else:
            continue
        for dados, ext, mime in lista:
            chave = f'visitas/{visita.id}/{uuid.uuid4().hex}.{ext}'
            storage().save(chave, dados, mime)
            f = VisitaFoto(visita_id=visita.id, momento=momento, item_codigo=item, mime=mime,
                           tamanho=len(dados), storage_key=chave)
            db.session.add(f)
            gravadas.append(f)
    db.session.flush()
    return gravadas


def _fotos_no_chamado(chamado, fotos, user):
    """As fotos da visita viram fotos de "antes" do chamado (o mesmo arquivo)."""
    from facilities.chamados.models import ChamadoAnexo
    for f in fotos:
        ext = f.storage_key.rsplit('.', 1)[-1]
        db.session.add(ChamadoAnexo(chamado_id=chamado.id, nome=f'visita-{f.id}.{ext}',
                                    mime=f.mime, tamanho=f.tamanho, storage_key=f.storage_key,
                                    momento='antes', uploaded_by=user.id))


def registrar(user, visita, respostas, observacao='', agora_utc=None, fotos=None):
    """``fotos``: {'antes': [arq], 'depois': [arq], 'item:<código>': [arq], 'livre': [arq]}."""
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import ORIGEM_VISITA
    from facilities.rotas.servico import RegraDaRota, conferir_respostas, itens_da_versao
    agora_utc = agora_utc or datetime.utcnow()
    if not pode_fazer(user, visita):
        raise RegraDaVisita('Esta visita é de outro supervisor ou de outro local.', 403)
    if visita.status != PREVISTA:
        quem = visita.quem_fez.name if visita.quem_fez else 'outra pessoa'
        raise RegraDaVisita(f'Esta visita já foi registrada por {quem}.', 409)
    versao = visita.programada.modelo.versao_atual
    if versao is None:
        raise RegraDaVisita('O checklist da visita não está publicado. Avise a gestão.', 409)
    lidas = _ler_fotos(fotos)
    itens = itens_da_versao(versao)
    por_item = {k.split(':', 1)[1]: v for k, v in lidas.items() if k.startswith('item:')}
    try:
        limpas, ncs = conferir_respostas(itens, respostas or {}, por_item)
    except RegraDaRota as erro:
        raise RegraDaVisita(erro.mensagem)
    if versao.exige_foto_antes and not lidas.get('antes'):
        raise RegraDaVisita('Tire a foto de ANTES.')
    if versao.exige_foto_depois and not lidas.get('depois'):
        raise RegraDaVisita('Tire a foto de DEPOIS.')
    visita.status = FEITA
    visita.feita_por, visita.feita_em = user.id, agora_utc
    visita.versao_id = versao.id
    visita.respostas_json = json.dumps(limpas, ensure_ascii=False)
    visita.observacao = (observacao or '').strip()[:2000] or None
    visita.n_nao_conformes = len(ncs)
    gravadas = _guardar_fotos(visita, lidas)
    if ncs:
        lista = '; '.join(f'"{i["texto"]}": {limpas.get(i["codigo"], "—")}' for i in ncs)
        ch = chamados.abrir(
            user, visita.client_id,
            f'Visita de supervisão: {len(ncs)} não conformidade(s) — '
            f'{visita.programada.nome}'[:200],
            descricao=(f'Visita de {user.name} em {tempo.fmt(agora_utc)}. '
                       f'Não conforme: {lista}.'
                       + (f' Observação: {visita.observacao}' if visita.observacao else '')),
            origem=ORIGEM_VISITA, origem_id=visita.id)
        visita.chamado_id = ch.id
        db.session.flush()
        _fotos_no_chamado(ch, gravadas, user)
    db.session.flush()
    return visita


def respostas_de(visita):
    try:
        return json.loads(visita.respostas_json or '{}')
    except ValueError:
        return {}
