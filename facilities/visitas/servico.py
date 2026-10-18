"""As regras das visitas de supervisão (Fase 6, D56). O commit é de quem chama.

* Programação: checklist publicado DO LOCAL, a cada 1 a 365 dias, com um
  supervisor (ou vazio: qualquer supervisor ou gestor do local).
* O checklist de visita não pode pedir foto obrigatória por enquanto: a
  visita é lançada numa tela simples do aplicativo, sem câmera.
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
from facilities.visitas.models import FEITA, PREVISTA, Visita, VisitaProgramada

PERFIS_QUE_VISITAM = ('supervisor',) + tuple(PERFIS_DE_GESTAO)


class RegraDaVisita(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


def pede_foto(versao):
    from facilities.rotas.servico import itens_da_versao
    return bool(versao.exige_foto_antes or versao.exige_foto_depois
                or any(i.get('exige_foto') for i in itens_da_versao(versao)))


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
    if pede_foto(modelo.versao_atual):
        raise RegraDaVisita('Este checklist pede foto obrigatória; a visita ainda não tira '
                            'foto. Escolha outro ou tire a obrigatoriedade da foto.')
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
    avisar(quem, titulo, texto, link, tipo='visita')
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


def registrar(user, visita, respostas, observacao='', agora_utc=None):
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
    if pede_foto(versao):
        raise RegraDaVisita('O checklist passou a pedir foto obrigatória; a visita ainda não '
                            'tira foto. Avise a gestão.', 409)
    itens = itens_da_versao(versao)
    try:
        limpas, ncs = conferir_respostas(itens, respostas or {}, {})
    except RegraDaRota as erro:
        raise RegraDaVisita(erro.mensagem)
    visita.status = FEITA
    visita.feita_por, visita.feita_em = user.id, agora_utc
    visita.versao_id = versao.id
    visita.respostas_json = json.dumps(limpas, ensure_ascii=False)
    visita.observacao = (observacao or '').strip()[:2000] or None
    visita.n_nao_conformes = len(ncs)
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
    return visita


def respostas_de(visita):
    try:
        return json.loads(visita.respostas_json or '{}')
    except ValueError:
        return {}
