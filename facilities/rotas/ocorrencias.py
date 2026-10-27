"""Ocorrência do QR público (D47; Q1 a Q3).

* Qualquer pessoa no local lê o QR do banheiro e abre uma reclamação ou
  ocorrência, SEM login: tipo da lista, texto curto e foto opcional. Não se
  pede nem se guarda dado de quem abriu.
* Vira pendência para quem está na rota daquele ponto no turno (escalado
  numa tarefa de hoje ainda em aberto) e alerta o supervisor; sem ninguém
  escalado, alerta o supervisor e o coordenador do local (Q1).
* Prazo por tipo, configurável por cliente; sem valor configurado, fica
  sem prazo (Q2: o valor padrão é decisão do proprietário).
* Quem abriu acompanha pelo link com o código de acompanhamento (Q3).
* Bloco do técnico (22/10/2026): o formulário mostra os ITENS do checklist
  ativo do ponto como problemas marcáveis ("Falta papel", "Lixeira cheia";
  ``itens_reportaveis``). Com item marcado, o texto é opcional (menos no
  tipo "outro"). Quem está logado (o cliente do portal, a equipe) fica
  registrado como autor; sem login continua anônimo.
* Reclamação e elogio (27/10/2026): o aviso vai como tarefa "Checar aviso"
  para quem está ESCALADO no ponto no dia (mesmo que a passada dele já
  tenha sido feita); sem ninguém escalado, para o supervisor do local. O
  elogio (1 a 5 estrelas) avisa quem cuida do ponto e entra no painel e no
  relatório do cliente; não é demanda.
"""
import json
import secrets
import uuid
from datetime import datetime, timedelta

from facilities import tempo
from facilities.extensions import db
from facilities.rotas.models import (OCORRENCIA_ABERTA, OCORRENCIA_EM_ATENDIMENTO,
                                     OCORRENCIA_RESOLVIDA, PREVISTA, TIPO_ITENS_DO_CHECKLIST,
                                     TIPOS_OCORRENCIA_PUBLICA, ElogioPublico, OcorrenciaPublica,
                                     Rota, RotaItem, TarefaDia)

TEXTO_MAX = 300
ITENS_MAX = 30
# Só estes tipos de pergunta viram "problema" que o público marca: texto,
# número, data e escolha não têm um "deu errado" claro.
TIPOS_REPORTAVEIS = ('sim_nao', 'conforme')
FOTO_MAX = 3 * 1024 * 1024      # anônimo: 3 MB na entrada, e ainda é reduzida


def prazo_minutos(ponto, tipo):
    cli = ponto.ambiente.setor.local.contratante if ponto.ambiente else None
    if cli is None or not cli.prazos_ocorrencia_json:
        return None
    try:
        valor = json.loads(cli.prazos_ocorrencia_json).get(tipo)
        return int(valor) if valor else None
    except (ValueError, TypeError, AttributeError):
        return None


def itens_reportaveis(ponto):
    """Os itens do checklist ATIVO ligado ao ponto pela rota, como problemas
    que o público marca: [{'codigo', 'rotulo_problema'}]. O rótulo vem do
    campo ``problema`` do item ("Falta papel") ou, sem ele, da pergunta com
    "Problema: " na frente. Dois checklists no mesmo ponto: união, sem
    repetir o código."""
    from facilities.rotas.servico import itens_da_versao
    itens, vistos = [], set()
    q = (RotaItem.query.join(Rota, Rota.id == RotaItem.rota_id)
         .filter(RotaItem.ponto_id == ponto.id, RotaItem.is_active.is_(True),
                 Rota.is_active.is_(True)).order_by(RotaItem.rota_id, RotaItem.ordem))
    for ri in q:
        m = ri.modelo
        if m is None or not m.is_active or m.versao_atual is None:
            continue
        for it in itens_da_versao(m.versao_atual):
            if it.get('tipo') not in TIPOS_REPORTAVEIS or it['codigo'] in vistos:
                continue
            vistos.add(it['codigo'])
            itens.append({'codigo': it['codigo'],
                          'rotulo_problema': it.get('problema') or f'Problema: {it["texto"]}'})
    return itens[:ITENS_MAX]


def _itens_marcados(ponto, brutos):
    """Os códigos marcados que existem no checklist do ponto (os outros são
    ignorados: o formulário é público)."""
    if not brutos:
        return []
    validos = {it['codigo'] for it in itens_reportaveis(ponto)}
    saida = []
    for b in list(brutos)[:ITENS_MAX * 2]:
        cod = str(b or '').strip()[:60]
        if cod in validos and cod not in saida:
            saida.append(cod)
    return saida


def escalado_no_ponto(ponto, agora_utc):
    """Quem cuida do ponto agora (decisão do dono, 27/10/2026): primeiro quem
    ainda tem tarefa aberta ali dentro do turno (a mais próxima); senão, quem
    foi escalado no ponto hoje, mesmo com a passada já feita (a última do
    dia). Sem ninguém escalado, None — e a supervisão recebe."""
    hoje = tempo.local(agora_utc).date()
    aberta = (TarefaDia.query.filter(
        TarefaDia.ponto_id == ponto.id, TarefaDia.status == PREVISTA,
        TarefaDia.data.in_([hoje, hoje - timedelta(days=1)]),
        TarefaDia.fim_do_turno >= agora_utc, TarefaDia.user_id.isnot(None))
        .order_by(TarefaDia.previsto_para).first())
    if aberta is not None:
        return aberta.user_id
    do_dia = (TarefaDia.query.filter(TarefaDia.ponto_id == ponto.id, TarefaDia.data == hoje,
                                     TarefaDia.user_id.isnot(None))
              .order_by(TarefaDia.previsto_para.desc()).first())
    return do_dia.user_id if do_dia is not None else None


def _destinatarios(ponto, responsavel_id):
    """Quem acompanha o local: o supervisor; sem ninguém escalado no ponto,
    também o coordenador (Q1)."""
    from facilities.core.hierarquia import carteira
    from facilities.core.models import User
    papeis = ('supervisor',) if responsavel_id else ('supervisor', 'pleno')
    acompanham = set()
    for u in User.query.filter(User.role.in_(papeis), User.is_active.is_(True),
                               User.is_deleted.is_(False)):
        cart = carteira(u)
        if cart is not None and ponto.client_id in cart:
            acompanham.add(u.id)
    return acompanham


def abrir(ponto, tipo, texto, foto=None, agora_utc=None, itens=None, autor=None):
    """``itens``: códigos do checklist marcados (``itens_reportaveis``);
    ``autor``: quem está logado, ou None (anônimo)."""
    from facilities.core import push
    from facilities.core.rotas import avisar as avisar_no_sino
    from facilities.rotas.servico import RegraDaRota
    agora_utc = agora_utc or datetime.utcnow()
    if not ponto.is_active:
        raise RegraDaRota('Este ponto não recebe mais ocorrências.', 409)
    texto = (texto or '').strip()[:TEXTO_MAX] or None
    marcados = _itens_marcados(ponto, itens)
    # Sem tipo escolhido (a página do QR com checklist não pergunta): os itens
    # marcados dão o tipo; só texto é "outro"; nada marcado nem escrito, erro.
    if not tipo:
        tipo = TIPO_ITENS_DO_CHECKLIST if marcados else ('outro' if texto else None)
    if tipo not in TIPOS_OCORRENCIA_PUBLICA:
        raise RegraDaRota('Marque o que está acontecendo ou escreva em poucas palavras.')
    if tipo == 'outro' and not texto:
        raise RegraDaRota('Conte em poucas palavras o que está acontecendo.')
    autor_id = getattr(autor, 'id', None) if getattr(autor, 'is_authenticated', False) else None
    oc = OcorrenciaPublica(ponto_id=ponto.id, client_id=ponto.client_id, tipo=tipo, texto=texto,
                           token=secrets.token_urlsafe(16), criada_em=agora_utc,
                           status=OCORRENCIA_ABERTA,
                           itens_json=json.dumps(marcados) if marcados else None,
                           autor_id=autor_id)
    minutos = prazo_minutos(ponto, tipo)
    if minutos:
        oc.prazo = agora_utc + timedelta(minutes=minutos)
    if foto is not None and getattr(foto, 'filename', ''):
        _guardar_foto(oc, foto)
    if marcados:
        oc.resumo = ', '.join(rotulos_dos_itens(oc, ponto))[:300]
    oc.responsavel_id = escalado_no_ponto(ponto, agora_utc)
    db.session.add(oc)
    db.session.flush()
    na_rota = {oc.responsavel_id} if oc.responsavel_id else set()
    acompanham = _destinatarios(ponto, oc.responsavel_id)
    titulo = f'Checar aviso: {oc.titulo}'[:200]
    onde = f'{ponto.ambiente.setor.local.name} · {ponto.ambiente.nome} · {ponto.nome}'
    link_campo = f'/app/turno?ponto={ponto.codigo_qr}'
    link_gestao = f'/rotas/locais/{ponto.client_id}/dia'
    if na_rota:
        quem = avisar_no_sino(na_rota, titulo, onde, link_campo, tipo='ocorrencia',
                              client_id=ponto.client_id)
        push.avisar(quem, titulo, onde, link_campo, marca=f'ocorrencia-{oc.id}')
    so_gestao = acompanham - na_rota
    quem = avisar_no_sino(so_gestao, titulo, onde, link_gestao, tipo='ocorrencia',
                          client_id=ponto.client_id)
    push.avisar(quem, titulo, onde, link_gestao, marca=f'ocorrencia-{oc.id}')
    return oc


def _guardar_foto(oc, foto):
    from facilities.core.anexos import (ANEXO_ASSINATURA, ANEXO_TIPOS, imagem_aceitavel,
                                        reduzir_imagem, storage)
    from facilities.rotas.servico import RegraDaRota
    nome = (foto.filename or '').lower()
    ext = nome.rsplit('.', 1)[-1] if '.' in nome else 'jpg'
    ext = 'jpg' if ext == 'jpeg' else ext
    dados = foto.read(FOTO_MAX + 1)
    if not dados:
        return
    if ext not in ('jpg', 'png', 'webp') or len(dados) > FOTO_MAX or \
            not any(dados.startswith(a) for a in ANEXO_ASSINATURA[ext]) or \
            not imagem_aceitavel(dados, ext):
        raise RegraDaRota('A foto não foi aceita (formato ou tamanho). Envie sem foto ou '
                          'tire outra.')
    dados, ext = reduzir_imagem(dados, ext)
    oc.foto_key = f'ocorrencias/{uuid.uuid4().hex}.{ext}'
    oc.foto_mime = ANEXO_TIPOS[ext]
    storage().save(oc.foto_key, dados, oc.foto_mime)


def rotulos_dos_itens(oc, ponto=None):
    """Os rótulos ("Falta papel") dos itens marcados numa ocorrência, sem o
    "Problema: " da frente (na tela do gestor e do técnico ele sobra)."""
    marcados = oc.itens
    if not marcados:
        return []
    por_codigo = {it['codigo']: it['rotulo_problema']
                  for it in itens_reportaveis(ponto or oc.ponto)}
    return [_sem_prefixo(por_codigo.get(c, c)) for c in marcados]


def _sem_prefixo(rotulo):
    return rotulo[len('Problema: '):] if rotulo.startswith('Problema: ') else rotulo


def atender(oc, user, agora_utc=None):
    from facilities.rotas.servico import RegraDaRota
    if oc.status == OCORRENCIA_RESOLVIDA:
        raise RegraDaRota('Esta ocorrência já foi resolvida.', 409)
    if oc.status == OCORRENCIA_ABERTA:
        oc.status = OCORRENCIA_EM_ATENDIMENTO
        oc.atendida_por = user.id
        oc.atendida_em = agora_utc or datetime.utcnow()
    return oc


def resolver(oc, user, resolucao='', agora_utc=None):
    from facilities.rotas.servico import RegraDaRota
    if oc.status == OCORRENCIA_RESOLVIDA:
        raise RegraDaRota('Esta ocorrência já foi resolvida.', 409)
    agora_utc = agora_utc or datetime.utcnow()
    if oc.status == OCORRENCIA_ABERTA:
        oc.atendida_por, oc.atendida_em = user.id, agora_utc
    oc.status = OCORRENCIA_RESOLVIDA
    oc.resolvida_por, oc.resolvida_em = user.id, agora_utc
    oc.resolucao = (resolucao or '').strip()[:300] or None
    return oc


def abertas(client_ids):
    """As ocorrências em aberto dos locais, com ponto → ambiente → setor →
    local já carregados: a tela escreve o nome do local em cada linha, e sem
    isso seriam quatro consultas por ocorrência."""
    from sqlalchemy.orm import joinedload
    from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
    return (OcorrenciaPublica.query
            .options(joinedload(OcorrenciaPublica.ponto)
                     .joinedload(PontoInspecao.ambiente)
                     .joinedload(Ambiente.setor)
                     .joinedload(Setor.local),
                     joinedload(OcorrenciaPublica.responsavel),
                     joinedload(OcorrenciaPublica.quem_atendeu))
            .filter(OcorrenciaPublica.client_id.in_(list(client_ids) or [-1]),
                    OcorrenciaPublica.status != OCORRENCIA_RESOLVIDA)
            .order_by(OcorrenciaPublica.criada_em).all())


def atrasada(oc, agora_utc=None):
    return bool(oc.prazo and oc.status != OCORRENCIA_RESOLVIDA
                and (agora_utc or datetime.utcnow()) > oc.prazo)


# ── Elogio ────────────────────────────────────────────────────────────────

def elogiar(ponto, nota, texto, agora_utc=None, autor=None):
    """Registra o elogio (1 a 5 estrelas) e avisa quem cuida do ponto no dia
    — reconhecimento direto para a equipe. Sem escalado, ninguém é avisado
    na hora: o elogio aparece no painel e no relatório do mês."""
    from facilities.core import push
    from facilities.core.rotas import avisar as avisar_no_sino
    from facilities.rotas.servico import RegraDaRota
    agora_utc = agora_utc or datetime.utcnow()
    if not ponto.is_active:
        raise RegraDaRota('Este ponto não recebe mais avaliações.', 409)
    try:
        nota = int(nota)
    except (TypeError, ValueError):
        nota = 0
    if nota not in (1, 2, 3, 4, 5):
        raise RegraDaRota('Escolha de 1 a 5 estrelas.')
    autor_id = getattr(autor, 'id', None) if getattr(autor, 'is_authenticated', False) else None
    el = ElogioPublico(ponto_id=ponto.id, client_id=ponto.client_id, nota=nota,
                       texto=(texto or '').strip()[:TEXTO_MAX] or None, criado_em=agora_utc,
                       responsavel_id=escalado_no_ponto(ponto, agora_utc), autor_id=autor_id)
    db.session.add(el)
    db.session.flush()
    if el.responsavel_id:
        titulo = f'Elogio: {nota} de 5 estrelas'
        onde = f'{ponto.ambiente.setor.local.name} · {ponto.ambiente.nome} · {ponto.nome}'
        if el.texto:
            onde = f'{onde} — "{el.texto}"'[:300]
        quem = avisar_no_sino({el.responsavel_id}, titulo, onde, '/app/', tipo='elogio',
                              client_id=ponto.client_id)
        push.avisar(quem, titulo, onde, '/app/', marca=f'elogio-{el.id}')
    return el


def media_dos_elogios(client_ids, de_utc=None, ate_utc=None):
    """{local: (média, quantos)} dos elogios do período, numa consulta só."""
    q = db.session.query(ElogioPublico.client_id, db.func.avg(ElogioPublico.nota),
                         db.func.count(ElogioPublico.id)).filter(
        ElogioPublico.client_id.in_(list(client_ids) or [-1]))
    if de_utc is not None:
        q = q.filter(ElogioPublico.criado_em >= de_utc)
    if ate_utc is not None:
        q = q.filter(ElogioPublico.criado_em < ate_utc)
    return {cid: (round(float(m), 1), n)
            for cid, m, n in q.group_by(ElogioPublico.client_id)}


def do_periodo(client_ids, situacao=None, limite=300):
    """Os avisos dos locais para a aba "Avisos pelo QR" das cobranças: os em
    aberto primeiro, depois os resolvidos, mais novos antes."""
    from sqlalchemy.orm import joinedload
    from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
    q = (OcorrenciaPublica.query
         .options(joinedload(OcorrenciaPublica.ponto)
                  .joinedload(PontoInspecao.ambiente)
                  .joinedload(Ambiente.setor)
                  .joinedload(Setor.local),
                  joinedload(OcorrenciaPublica.responsavel))
         .filter(OcorrenciaPublica.client_id.in_(list(client_ids) or [-1])))
    if situacao:
        q = q.filter(OcorrenciaPublica.status == situacao)
    return (q.order_by(OcorrenciaPublica.status == OCORRENCIA_RESOLVIDA,
                       OcorrenciaPublica.criada_em.desc()).limit(limite).all())
