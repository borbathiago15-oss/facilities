"""Rotas prontas da biblioteca (pedido do dono, 19/10/2026).

Um modelo por tipo de local (escritório, centro de distribuição...) com as
linhas "setor · ambiente · checklist · horários · quantidade". A gestão
APLICA o modelo num local: vê a prévia, tira o que o local não tem, ajusta
nomes e horários, e o sistema cria o que faltar — setor, ambiente, ponto com
QR, a cópia do checklist e a rota com os horários. Tudo numa transação: ou
entra inteiro, ou nada.

A rota criada nasce com a confirmação de presença DESLIGADA (0 por turno):
a presença aleatória só liga depois da validação de RH e jurídico (D48).
"""
from facilities.extensions import db
from facilities.rotas import servico
from facilities.rotas.models import ChecklistModelo, RotaModelo, RotaModeloItem
from facilities.rotas.servico import RegraDaRota

QUANTIDADE_MAX = 10
LINHAS_MAX = 60


def _texto(valor, limite, rotulo):
    t = (valor or '').strip()[:limite]
    if not t:
        raise RegraDaRota(f'Informe {rotulo}.')
    return t


def _quantidade(bruto):
    bruto = str(bruto or '1').strip()
    if not bruto.isascii() or not bruto.isdigit() or not 1 <= int(bruto) <= QUANTIDADE_MAX:
        raise RegraDaRota(f'Quantidade de 1 a {QUANTIDADE_MAX}.')
    return int(bruto)


def _checklist_da_biblioteca(bruto):
    bruto = str(bruto or '').strip()
    m = db.session.get(ChecklistModelo, int(bruto)) if bruto.isascii() and bruto.isdigit() \
        else None
    if m is None or m.client_id is not None or not m.is_active or m.versao_atual is None:
        raise RegraDaRota('Escolha um checklist publicado da biblioteca.')
    return m


def salvar_modelo(modelo, dados, linhas):
    """Cria ou edita a rota pronta (só o administrador, na tela). ``linhas``:
    [{'setor', 'ambiente', 'checklist_id', 'horarios', 'quantidade'}]; linha
    sem ambiente é ignorada (é a linha em branco do formulário)."""
    nome = _texto(dados.get('nome'), 150, 'o nome da rota pronta')
    outro = RotaModelo.query.filter(db.func.lower(RotaModelo.nome) == nome.lower()).first()
    if outro is not None and (modelo is None or outro.id != modelo.id):
        raise RegraDaRota('Já existe uma rota pronta com este nome.')
    turno = _texto(dados.get('turno'), 50, 'o turno')
    inicio = servico._hora(dados.get('hora_inicio'), 'Início do turno')
    fim = servico._hora(dados.get('hora_fim'), 'Fim do turno')
    if inicio == fim:
        raise RegraDaRota('O turno precisa ter duração (início e fim iguais).')
    try:
        tolerancia = int(dados.get('tolerancia_min') or 30)
    except ValueError:
        raise RegraDaRota('Tolerância em minutos, só o número.')
    if not 0 <= tolerancia <= 240:
        raise RegraDaRota('A tolerância vai de 0 a 240 minutos.')
    novas = []
    for i, ln in enumerate(linhas[:LINHAS_MAX]):
        ambiente = (ln.get('ambiente') or '').strip()[:120]
        if not ambiente:
            continue
        setor = _texto(ln.get('setor'), 120, f'o setor de "{ambiente}"')
        checklist = _checklist_da_biblioteca(ln.get('checklist_id'))
        horarios = servico._horarios_fixos(ln.get('horarios'))
        if not horarios:
            raise RegraDaRota(f'Informe os horários de "{ambiente}" (ex.: 08:00, 12:00).')
        novas.append(RotaModeloItem(
            ordem=len(novas), setor=setor, ambiente=ambiente, checklist_id=checklist.id,
            horarios=', '.join(h.strftime('%H:%M') for h in horarios),
            quantidade=_quantidade(ln.get('quantidade'))))
    if not novas:
        raise RegraDaRota('Inclua pelo menos um ambiente na rota pronta.')
    modelo = modelo or RotaModelo()
    modelo.nome = nome
    modelo.segmento = (dados.get('segmento') or 'Outro').strip()[:60] or 'Outro'
    modelo.descricao = (dados.get('descricao') or '').strip()[:2000] or None
    modelo.turno = turno
    modelo.hora_inicio, modelo.hora_fim = inicio, fim
    modelo.tolerancia_min = tolerancia
    modelo.dias_semana = servico._dias(dados.get('dias_semana'))
    if modelo.id is None:
        db.session.add(modelo)
    modelo.itens = novas
    db.session.flush()
    return modelo


def linhas_da_previa(modelo):
    """As linhas expandidas para a prévia: "2 banheiros masculinos" vira
    "Banheiro masculino 1" e "Banheiro masculino 2"."""
    linhas = []
    for it in modelo.itens:
        for n in range(1, it.quantidade + 1):
            nome = it.ambiente if it.quantidade == 1 else f'{it.ambiente} {n}'
            linhas.append({'setor': it.setor, 'ambiente': nome[:120],
                           'checklist_id': it.checklist_id, 'checklist': it.checklist.nome,
                           'horarios': it.horarios})
    return linhas


def _setor(local, nome, autor):
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Setor
    s = Setor.query.filter_by(client_id=local.id, nome=nome).first()
    if s is not None:
        if not s.is_active:
            raise RegraDaRota(f'O setor "{nome}" está desativado neste local. Reative-o ou '
                              'use outro nome.')
        return s, False
    s = cad.salvar_setor(local, None, {'nome': nome}, autor)
    db.session.flush()
    return s, True


def _ambiente(local, setor, nome, autor):
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import Ambiente
    a = Ambiente.query.filter_by(setor_id=setor.id, nome=nome).first()
    if a is not None:
        if not a.is_active:
            raise RegraDaRota(f'O ambiente "{nome}" está desativado neste local. Reative-o ou '
                              'use outro nome.')
        return a, False
    a = cad.salvar_ambiente(local, None, {'nome': nome, 'setor_id': setor.id}, autor)
    db.session.flush()
    return a, True


def _ponto(local, ambiente, autor):
    from facilities.cadastros import servico as cad
    from facilities.cadastros.models import PontoInspecao
    p = (PontoInspecao.query.filter_by(ambiente_id=ambiente.id, is_active=True)
         .order_by(PontoInspecao.id).first())
    if p is not None:
        return p, False
    p = cad.salvar_ponto(local, None, {'nome': f'Entrada — {ambiente.nome}'[:120],
                                       'ambiente_id': ambiente.id}, autor)
    db.session.flush()
    return p, True


def _checklist_do_local(local, origem, autor):
    m = ChecklistModelo.query.filter_by(client_id=local.id, origem_id=origem.id).first()
    if m is not None and m.is_active and m.versao_atual is not None:
        return m, False
    if m is not None:
        raise RegraDaRota(f'A cópia de "{origem.nome}" neste local está desativada ou sem '
                          'versão publicada. Ajuste em Rotas antes de aplicar.')
    return servico.copiar_da_biblioteca(origem, local.id, autor), True


def aplicar(modelo, local, dados_rota, linhas, autor):
    """Cria no local o que faltar e a rota com os itens. ``linhas``: as da
    prévia que a gestão manteve (ambiente e horários podem ter sido
    editados). Devolve (rota, resumo). O commit é de quem chama."""
    from facilities.cadastros.servico import CadastroInvalido
    escolhidas = [ln for ln in linhas if (ln.get('ambiente') or '').strip()][:LINHAS_MAX * 2]
    if not escolhidas:
        raise RegraDaRota('Marque pelo menos um ambiente para aplicar.')
    resumo = {'setores': 0, 'ambientes': 0, 'pontos': 0, 'checklists': 0, 'itens': 0}
    try:
        rota = servico.salvar_rota(local, None, {
            'nome': dados_rota.get('nome') or modelo.nome,
            'turno': dados_rota.get('turno') or modelo.turno,
            'hora_inicio': dados_rota.get('hora_inicio') or modelo.hora_inicio.strftime('%H:%M'),
            'hora_fim': dados_rota.get('hora_fim') or modelo.hora_fim.strftime('%H:%M'),
            'tolerancia_min': dados_rota.get('tolerancia_min') or modelo.tolerancia_min,
            'dias_semana': dados_rota.get('dias_semana') or modelo.dias_semana,
            'presencas_por_turno': '0'})
        validos = {it.checklist_id for it in modelo.itens}
        for ln in escolhidas:
            setor_nome = _texto(ln.get('setor'), 120, 'o setor')
            amb_nome = _texto(ln.get('ambiente'), 120, 'o ambiente')
            origem = _checklist_da_biblioteca(ln.get('checklist_id'))
            if origem.id not in validos:
                raise RegraDaRota('Um dos checklists não é desta rota pronta.')
            setor, novo = _setor(local, setor_nome, autor)
            resumo['setores'] += novo
            amb, novo = _ambiente(local, setor, amb_nome, autor)
            resumo['ambientes'] += novo
            ponto, novo = _ponto(local, amb, autor)
            resumo['pontos'] += novo
            copia, novo = _checklist_do_local(local, origem, autor)
            resumo['checklists'] += novo
            servico.salvar_item(rota, None, {'ponto_id': ponto.id, 'modelo_id': copia.id,
                                             'horarios': ln.get('horarios') or ''})
            resumo['itens'] += 1
    except CadastroInvalido as erro:
        raise RegraDaRota(str(erro))
    db.session.flush()
    return rota, resumo
