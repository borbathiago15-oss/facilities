"""Cadastro simplificado: Cliente › Centro de custo › Áreas › Rotas
(decisões do dono, 27/10/2026).

* O CENTRO DE CUSTO é o local de sempre (``Client``) — o nome muda só na tela.
* A ÁREA é um ponto com QR (``PontoInspecao``): "Banheiro 01", "Recepção". O
  setor fica escondido ("Geral") e o ambiente leva o mesmo nome da área. Quem
  precisa de vários QRs numa área usa a tela completa ("modo avançado").
* Cada área tem o SEU checklist (o escopo do que fazer ali): a área nova já
  nasce com o modelo da biblioteca que combina com o nome ("Banheiro" → o de
  banheiro; sem combinação, o de recepção e escritório), copiado para o
  centro de custo. A gestão troca quando quiser.
* A ROTA é digitada em linhas — "06:00 · Banheiro 01", "06:30 · Banheiro 02" —
  e o checklist de cada linha vem da área.

O commit é de quem chama.
"""
from datetime import datetime

from facilities.extensions import db
from facilities.cadastros import servico as cadastros
from facilities.cadastros.models import Ambiente, PontoInspecao, Setor
from facilities.cadastros.servico import CadastroInvalido

SETOR_PADRAO = 'Geral'
AREAS_POR_VEZ = 50
LINHAS_POR_VEZ = 30

# Palavra no nome da área → o modelo da biblioteca que combina com ela. A
# primeira que aparecer vale; sem nenhuma, o de recepção e escritório.
SUGESTOES = (
    (('banheiro', 'sanit', 'lavabo', 'wc'), 'Limpeza de banheiro — padrão Trino'),
    (('vesti',), 'Limpeza de vestiário — padrão Trino'),
    (('copa', 'cozinha', 'refeit'), 'Limpeza de copa e cozinha — padrão Trino'),
    (('extern', 'calçada', 'calcada', 'estacionamento', 'jardim', 'pátio', 'patio'),
     'Área externa e calçada — padrão Trino'),
    (('armaz', 'doca', 'galp', 'expedi', 'operacional', 'estoque'),
     'Piso operacional, docas e armazém — padrão Trino'),
)
SUGESTAO_PADRAO = 'Limpeza de recepção e escritório — padrão Trino'


def _sem_acento(texto):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower())
                   if unicodedata.category(c) != 'Mn')


def nome_sugerido(nome_area):
    alvo = _sem_acento(nome_area or '')
    for palavras, modelo in SUGESTOES:
        if any(_sem_acento(p) in alvo for p in palavras):
            return modelo
    return SUGESTAO_PADRAO


# ── Centros de custo do cliente ───────────────────────────────────────────

def centros_do_cliente(contratante):
    """Os centros de custo (locais) do cliente que a pessoa vê."""
    from facilities.core.acesso import clientes_visiveis
    return sorted((c for c in clientes_visiveis() if c.contratante_id == contratante.id),
                  key=lambda c: c.name.lower())


def resumo_do_centro(local):
    from facilities.rotas.models import Rota
    return {'areas': PontoInspecao.query.filter_by(client_id=local.id, is_active=True).count(),
            'rotas': Rota.query.filter_by(client_id=local.id, is_active=True).count()}


# ── Áreas ─────────────────────────────────────────────────────────────────

def areas(local):
    """As áreas ativas (pontos com QR), na ordem em que foram cadastradas —
    a mesma do número da etiqueta."""
    return (PontoInspecao.query.filter_by(client_id=local.id, is_active=True)
            .order_by(PontoInspecao.id).all())


def _setor_padrao(local, autor):
    setor = Setor.query.filter(Setor.client_id == local.id, Setor.is_active.is_(True),
                               Setor.nome == SETOR_PADRAO).first()
    return setor or cadastros.salvar_setor(local, None, {'nome': SETOR_PADRAO}, autor)


def _modelo_da_biblioteca(nome, autor):
    from facilities.rotas.biblioteca_pronta import semear
    from facilities.rotas.models import ChecklistModelo

    def achar():
        return ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                            ChecklistModelo.nome == nome,
                                            ChecklistModelo.is_active.is_(True)).first()
    modelo = achar()
    if modelo is None:
        semear(autor)              # a biblioteca da Trino ainda não foi instalada
        modelo = achar()
    return modelo


def checklist_sugerido(local, nome_area, autor):
    """O checklist do centro de custo para uma área com este nome: a cópia
    que o centro já tem do modelo da biblioteca, ou uma cópia nova."""
    from facilities.rotas import servico as rotas
    from facilities.rotas.models import ChecklistModelo
    origem = _modelo_da_biblioteca(nome_sugerido(nome_area), autor)
    if origem is None or origem.versao_atual is None:
        return None
    copia = ChecklistModelo.query.filter_by(client_id=local.id, origem_id=origem.id).first()
    if copia is None:
        return rotas.copiar_da_biblioteca(origem, local.id, autor)
    # A cópia desativada pela gestão não volta sozinha: a área fica sem
    # checklist e a gestão escolhe um na lista.
    return copia if copia.is_active and copia.versao_atual is not None else None


def criar_areas(local, texto, autor):
    """Uma área por linha: cada uma vira um ponto com QR, com o checklist
    sugerido pelo nome. Tudo ou nada: um nome repetido recusa o lote."""
    nomes = []
    for linha in (texto or '').splitlines():
        nome = ' '.join(linha.split())[:120]
        if nome and nome.lower() not in {n.lower() for n in nomes}:
            nomes.append(nome)
    if not nomes:
        raise CadastroInvalido('Escreva as áreas, uma por linha (ex.: Banheiro 01).')
    if len(nomes) > AREAS_POR_VEZ:
        raise CadastroInvalido(f'No máximo {AREAS_POR_VEZ} áreas por vez.')
    existentes = {p.nome.lower() for p in areas(local)}
    repetidas = [n for n in nomes if n.lower() in existentes]
    if repetidas:
        raise CadastroInvalido('Já existe neste centro de custo: ' + ', '.join(repetidas) +
                               '. Use outro nome (ex.: Banheiro 01 — 2º andar).')
    setor = _setor_padrao(local, autor)
    db.session.flush()
    criadas = []
    for nome in nomes:
        amb = Ambiente.query.filter(Ambiente.setor_id == setor.id,
                                    db.func.lower(Ambiente.nome) == nome.lower()).first()
        if amb is None or not amb.is_active:
            amb = cadastros.salvar_ambiente(local, None, {'nome': nome, 'setor_id': setor.id},
                                            autor)
            db.session.flush()
        ponto = cadastros.salvar_ponto(local, None, {'nome': nome, 'ambiente_id': amb.id},
                                       autor)
        modelo = checklist_sugerido(local, nome, autor)
        ponto.checklist_id = modelo.id if modelo else None
        criadas.append(ponto)
    db.session.flush()
    return criadas


def checklists_do_centro(local):
    from facilities.rotas.models import ChecklistModelo
    return [m for m in ChecklistModelo.query.filter_by(client_id=local.id, is_active=True)
            .order_by(ChecklistModelo.nome) if m.versao_atual is not None]


def trocar_checklist(local, ponto, modelo_id):
    from facilities.rotas.models import ChecklistModelo
    if ponto.client_id != local.id:
        raise CadastroInvalido('Esta área não é deste centro de custo.')
    m = db.session.get(ChecklistModelo, int(modelo_id)) if str(modelo_id).isdigit() else None
    if m is None or m.client_id != local.id or not m.is_active or m.versao_atual is None:
        raise CadastroInvalido('Escolha um checklist publicado deste centro de custo.')
    ponto.checklist_id = m.id
    return m


def checklist_da_area(ponto, autor):
    """O checklist da área; a área antiga (sem checklist) ganha o sugerido."""
    m = ponto.checklist
    if m is not None and m.is_active and m.versao_atual is not None:
        return m
    local = ponto.ambiente.setor.local if ponto.ambiente else None
    m = checklist_sugerido(local, ponto.nome, autor) if local is not None else None
    if m is None:
        raise CadastroInvalido(f'A área "{ponto.nome}" está sem checklist. Escolha um na aba '
                               'Áreas.')
    ponto.checklist_id = m.id
    return m


# ── Rotas em linhas ───────────────────────────────────────────────────────

def _hora(bruto):
    try:
        return datetime.strptime((bruto or '').strip(), '%H:%M').time()
    except ValueError:
        return None


def adicionar_linhas(rota, linhas, autor):
    """``linhas``: [(hora 'HH:MM', ponto_id)]. Cada linha vira um horário da
    área na rota, com o checklist da área. A mesma área com o mesmo checklist
    fica num item só, com os horários juntos ("06:00, 10:00")."""
    from facilities.rotas import servico as rotas
    from facilities.rotas.models import RotaItem
    validas = []
    for n, (bruto_hora, bruto_ponto) in enumerate(linhas, start=1):
        if not (bruto_hora or '').strip() and not str(bruto_ponto or '').strip():
            continue
        h = _hora(bruto_hora)
        if h is None:
            raise CadastroInvalido(f'Linha {n}: escreva o horário (ex.: 06:00).')
        ponto = (db.session.get(PontoInspecao, int(bruto_ponto))
                 if str(bruto_ponto or '').isdigit() else None)
        if ponto is None or ponto.client_id != rota.client_id or not ponto.is_active:
            raise CadastroInvalido(f'Linha {n}: escolha a área.')
        validas.append((h, ponto))
    if not validas:
        raise CadastroInvalido('Preencha ao menos uma linha: horário e área.')
    if len(validas) > LINHAS_POR_VEZ:
        raise CadastroInvalido(f'No máximo {LINHAS_POR_VEZ} linhas por vez.')
    for h, ponto in validas:
        modelo = checklist_da_area(ponto, autor)
        item = RotaItem.query.filter_by(rota_id=rota.id, ponto_id=ponto.id, modelo_id=modelo.id,
                                        is_active=True, frequencia_min=None,
                                        horarios_por_dia=None).first()
        if item is None:
            rotas.salvar_item(rota, None, {'ponto_id': ponto.id, 'modelo_id': modelo.id,
                                           'horarios': h.strftime('%H:%M')})
            continue
        atuais = [x.strip() for x in (item.horarios or '').split(',') if x.strip()]
        if h.strftime('%H:%M') in atuais:
            continue
        rotas.salvar_item(rota, item, {
            'ponto_id': ponto.id, 'modelo_id': modelo.id,
            'horarios': ', '.join(atuais + [h.strftime('%H:%M')]),
            'tempo_previsto_min': item.tempo_previsto_min or '', 'ordem': item.ordem,
            'dias_semana': item.dias_semana or ''})
    db.session.flush()


def linhas_da_rota(rota):
    """[{'hora', 'item', 'ponto', 'checklist'}] em ordem de horário (as de
    frequência, "a cada N min", no fim)."""
    linhas = []
    for item in rota.itens:
        if not item.is_active:
            continue
        horas = [x.strip() for x in (item.horarios or '').split(',') if x.strip()]
        for h in horas:
            linhas.append({'hora': h, 'item': item, 'ponto': item.ponto,
                           'checklist': item.modelo})
        if item.frequencia_min:
            linhas.append({'hora': f'a cada {item.frequencia_min} min', 'item': item,
                           'ponto': item.ponto, 'checklist': item.modelo})
        if item.horarios_por_dia and not horas and not item.frequencia_min:
            linhas.append({'hora': 'horários por dia', 'item': item, 'ponto': item.ponto,
                           'checklist': item.modelo})
    return sorted(linhas, key=lambda x: (not x['hora'][:1].isdigit(), x['hora']))


def remover_horario(rota, item, hora):
    """Tira um horário da área na rota; sem horário nenhum, a área sai da
    rota (o histórico fica)."""
    if item.rota_id != rota.id:
        raise CadastroInvalido('Esta linha não é desta rota.')
    atuais = [x.strip() for x in (item.horarios or '').split(',') if x.strip()]
    if hora in atuais and len(atuais) > 1:
        item.horarios = ', '.join(x for x in atuais if x != hora)
    else:
        item.is_active = False
    db.session.flush()
