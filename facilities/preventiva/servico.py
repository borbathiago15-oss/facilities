"""As regras da preventiva (Fase 5). O commit é de quem chama.

* Plano: ponto, checklist e equipamento do MESMO local; intervalo de 1 a 730
  dias; antecedência de 0 a 60 dias; responsável que atende o local.
* Agendador: chegou a data (vencimento − antecedência), abre a ordem do
  ciclo e empurra o próximo vencimento. Ficou parado e perdeu ciclos? Abre
  UMA ordem (a do ciclo mais antigo em aberto) e pula para o próximo futuro —
  não despeja uma pilha de ordens velhas de uma vez.
* O prazo da ordem é o fim do dia do vencimento (horário de Brasília).
* Fazer o checklist da preventiva no aplicativo resolve a ordem; a gestão
  confere e fecha, como em qualquer chamado.
"""
from datetime import datetime, time, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.preventiva.models import PlanoPreventivo, PreventivaOrdem


class RegraDaPreventiva(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def _int(dados, campo, minimo, maximo, rotulo, padrao=None):
    bruto = str(dados.get(campo) if dados.get(campo) not in (None, '') else
                ('' if padrao is None else padrao)).strip()
    if not bruto.isdigit() or not minimo <= int(bruto) <= maximo:
        raise RegraDaPreventiva(f'{rotulo}: de {minimo} a {maximo}.')
    return int(bruto)


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


def salvar_plano(local, plano, dados, autor):
    from facilities.cadastros.models import Equipamento, PontoInspecao
    from facilities.chamados.models import PRIORIDADES
    from facilities.chamados.servico import tecnicos_do_contrato
    from facilities.rotas.models import ChecklistModelo
    nome = (dados.get('nome') or '').strip()[:150]
    if not nome:
        raise RegraDaPreventiva('Dê um nome ao plano (ex.: Limpeza do filtro do ar).')
    ponto = db.session.get(PontoInspecao, _id(dados, 'ponto_id'))
    if ponto is None or ponto.client_id != local.id or not ponto.is_active:
        raise RegraDaPreventiva('Escolha um ponto ativo deste local (onde o técnico lê o QR).')
    eq = None
    if str(dados.get('equipamento_id') or '').isdigit():
        eq = db.session.get(Equipamento, int(dados['equipamento_id']))
        if eq is None or eq.client_id != local.id:
            raise RegraDaPreventiva('Escolha um equipamento deste local.')
    modelo = db.session.get(ChecklistModelo, _id(dados, 'modelo_id'))
    if modelo is None or modelo.client_id != local.id or not modelo.is_active \
            or modelo.versao_atual is None:
        raise RegraDaPreventiva('Escolha um checklist publicado deste local.')
    intervalo = _int(dados, 'intervalo_dias', 1, 730, 'Intervalo em dias')
    antecedencia = _int(dados, 'antecedencia_dias', 0, 60, 'Antecedência em dias', 0)
    if antecedencia >= intervalo:
        raise RegraDaPreventiva('A antecedência precisa ser menor que o intervalo.')
    try:
        proxima = datetime.strptime(dados.get('proxima_em') or '', '%Y-%m-%d').date()
    except ValueError:
        raise RegraDaPreventiva('Informe a data do próximo vencimento.')
    prioridade = dados.get('prioridade') or 'media'
    if prioridade not in PRIORIDADES:
        raise RegraDaPreventiva('Prioridade inválida.')
    resp = None
    if str(dados.get('responsavel_id') or '').isdigit():
        resp = int(dados['responsavel_id'])
        if resp not in {u.id for u in tecnicos_do_contrato(local.id)}:
            raise RegraDaPreventiva('O responsável precisa atender este local.')
    plano = plano or PlanoPreventivo(client_id=local.id, criado_por=autor.id)
    plano.nome, plano.ponto_id, plano.modelo_id = nome, ponto.id, modelo.id
    plano.equipamento_id = eq.id if eq else None
    plano.intervalo_dias, plano.antecedencia_dias = intervalo, antecedencia
    plano.proxima_em, plano.prioridade, plano.responsavel_id = proxima, prioridade, resp
    if plano.id is None:
        db.session.add(plano)
    db.session.flush()
    return plano


def _prazo_do_vencimento(dia):
    return tempo.para_utc(dia, time(23, 59))


def _abrir_ordem(plano, vencimento, agora_utc):
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import ABERTO, ORIGEM_PREVENTIVA, Chamado
    ciclo = PreventivaOrdem(plano_id=plano.id, vencimento=vencimento, criada_em=agora_utc)
    db.session.add(ciclo)
    db.session.flush()
    onde = f'{plano.ponto.ambiente.nome} · {plano.ponto.nome}'
    ch = Chamado(client_id=plano.client_id,
                 titulo=f'Preventiva: {plano.nome}'[:200],
                 descricao=(f'Plano preventivo "{plano.nome}", a cada {plano.intervalo_dias} '
                            f'dia(s). Vencimento {vencimento.strftime("%d/%m/%Y")}. Faça o '
                            f'checklist "{plano.modelo.nome}" lendo o QR do ponto.'),
                 local=onde[:200], categoria='equipamento' if plano.equipamento_id else 'outro',
                 prioridade=plano.prioridade, status=ABERTO, solicitante_id=plano.criado_por,
                 responsavel_id=plano.responsavel_id, prazo=_prazo_do_vencimento(vencimento),
                 origem=ORIGEM_PREVENTIVA, origem_id=ciclo.id, aberto_em=agora_utc)
    db.session.add(ch)
    db.session.flush()
    ciclo.chamado_id = ch.id
    chamados._evento(ch, 'aberto', None, 'Aberto pelo plano preventivo.')
    quem = {plano.responsavel_id} if plano.responsavel_id else \
        chamados.gestores_do_contrato(plano.client_id)
    chamados._avisar(quem, ch, f'Preventiva: {plano.nome}',
                     f'{onde} · vence em {vencimento.strftime("%d/%m")}.')
    return ch


def gerar_ordens(hoje=None, agora_utc=None):
    """Abre as ordens que chegaram na data. Devolve quantas abriu."""
    agora_utc = agora_utc or datetime.utcnow()
    hoje = hoje or tempo.local(agora_utc).date()
    abertas = 0
    for plano in PlanoPreventivo.query.filter(PlanoPreventivo.is_active.is_(True)).all():
        if plano.local is None or not plano.local.is_active or plano.local.is_deleted:
            continue
        if plano.proxima_em - timedelta(days=plano.antecedencia_dias) > hoje:
            continue
        vencimento = plano.proxima_em
        if PreventivaOrdem.query.filter_by(plano_id=plano.id, vencimento=vencimento).first() \
                is None:
            _abrir_ordem(plano, vencimento, agora_utc)
            abertas += 1
        # Próximo vencimento: o primeiro que ainda não chegou na data.
        while plano.proxima_em - timedelta(days=plano.antecedencia_dias) <= hoje:
            plano.proxima_em += timedelta(days=plano.intervalo_dias)
    return abertas


def ordem_do_chamado(ch):
    from facilities.chamados.models import ORIGEM_PREVENTIVA
    if ch is None or ch.origem != ORIGEM_PREVENTIVA or not ch.origem_id:
        return None
    return db.session.get(PreventivaOrdem, ch.origem_id)


def resolver_pela_execucao(ch, user, execucao, agora_utc):
    """O checklist da preventiva foi feito: a ordem fica resolvida (a gestão
    confere e fecha)."""
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import RESOLVIDO
    chamados._retomar_relogio(ch, agora_utc)
    ch.status = RESOLVIDO
    ch.resolvido_em = agora_utc
    ch.motivo_espera = None
    ch.iniciado_em = ch.iniciado_em or execucao.iniciada_em
    if ch.responsavel_id is None:
        ch.responsavel_id = user.id
    ch.solucao = (f'Checklist da preventiva feito por {user.name} '
                  f'({tempo.fmt(execucao.concluida_em)}).'
                  + (f' {execucao.n_nao_conformes} item(ns) não conforme(s).'
                     if execucao.n_nao_conformes else ''))
    chamados._evento(ch, 'resolvido', user, ch.solucao)
    chamados._avisar([ch.solicitante_id], ch, f'Preventiva feita: {ch.titulo}',
                     'Confira o checklist e feche a ordem.', exceto=user.id)
