"""As regras das rotas e checklists (Fase 4A). As telas só chamam aqui.

Em uma frase cada:

* Checklist: publicar cria a versão seguinte (se algo mudou); a versão
  publicada nunca muda.
* Biblioteca: o modelo da Trino (sem local) é COPIADO para o local; a rota
  só usa modelo do próprio local.
* Rota: do local e do turno, com itens (ponto + modelo + horários fixos e/ou
  frequência) e escala (quem, em que dias).
* Agendador: gera as tarefas de hoje e amanhã — rodar duas vezes não
  duplica — e marca como PERDIDA a tarefa do turno que já acabou.
* Execução: só com o QR do ponto certo; a partir de (horário − tolerância);
  no prazo se começou até (horário + tolerância); obrigatórios respondidos;
  fotos exigidas presentes; o mesmo envio repetido não duplica.
* "Não realizada": motivo obrigatório; pode abrir chamado na hora.

O commit é sempre de quem chama.
"""
import json
import re
import unicodedata
import uuid
from datetime import datetime, time, timedelta, timezone

from itsdangerous import BadSignature, URLSafeTimedSerializer
from flask import current_app
from sqlalchemy.exc import IntegrityError

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import User
from facilities.cadastros.models import PontoInspecao
from facilities.rotas.models import (
    CONCLUIDA_COM_ATRASO, CONCLUIDA_NO_PRAZO, ENCERRADAS, MOTIVOS_NAO_REALIZADA, NAO_REALIZADA,
    PERDIDA, PREVISTA, TIPOS_DE_ITEM, AgendadorExecucao, ChecklistModelo, ChecklistVersao,
    Execucao, ExecucaoCorrecao, ExecucaoFoto, NaoConformidade, Rota, RotaEscala, RotaItem,
    TarefaDia)

DIAS_DA_SEMANA = {'1': 'seg', '2': 'ter', '3': 'qua', '4': 'qui', '5': 'sex', '6': 'sáb',
                  '7': 'dom'}
PERFIS_QUE_EXECUTAM = ('encarregado', 'tecnico', 'supervisor', 'pleno', 'gerente', 'master')
PERFIS_ESCALAVEIS = ('encarregado', 'tecnico', 'supervisor')
ITENS_MAX = 60
FREQUENCIA_MIN, FREQUENCIA_MAX = 15, 12 * 60
VALIDADE_DA_LEITURA = timedelta(hours=14)
# O aparelho pode estar alguns minutos adiantado; mais que isso é relógio errado.
FOLGA_DO_RELOGIO = timedelta(minutes=10)
JANELA_SEM_SINAL = timedelta(days=7)


class RegraDaRota(ValueError):
    """Recusa com mensagem pronta para a tela; ``codigo`` é o HTTP."""

    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


# ── Checklist ─────────────────────────────────────────────────────────────

def _slug(texto):
    s = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '_', s).strip('_').lower()
    return s[:50] or 'item'


def _numero(bruto):
    if bruto in (None, ''):
        return None
    try:
        return float(str(bruto).replace(',', '.'))
    except ValueError:
        raise RegraDaRota(f'"{bruto}" não é um número.')


COMO_FAZER_MAX = 400
CHAVE_DA_REFERENCIA = re.compile(r'^checklists/\d+/ref/[0-9a-f]{32}\.(jpg|png|webp)$')


def guardar_referencia(modelo, arquivo):
    """A foto de referência de um item (como deve ficar) → a chave guardada."""
    from facilities.core.anexos import storage
    dados, ext, mime = ler_imagem(arquivo)
    chave = f'checklists/{modelo.id}/ref/{uuid.uuid4().hex}.{ext}'
    storage().save(chave, dados, mime)
    return chave


def normalizar_itens(brutos, modelo=None):
    """Os itens do formulário → a lista que vai para a versão (ou erro).

    Com ``modelo``, a foto de referência só vale se a chave for deste
    checklist (ou do modelo da biblioteca de onde ele foi copiado): a chave
    de outro local, conhecida por quem já teve acesso a ele, não é aceita
    (auditoria SEC-019)."""
    donos = None
    if modelo is not None:
        donos = {str(modelo.id)} | ({str(modelo.origem_id)} if modelo.origem_id else set())
    itens, codigos = [], set()
    for b in brutos:
        texto = (b.get('texto') or '').strip()[:300]
        if not texto:
            continue
        tipo = b.get('tipo') or 'sim_nao'
        if tipo not in TIPOS_DE_ITEM:
            raise RegraDaRota(f'Tipo de pergunta desconhecido em "{texto}".')
        codigo = (b.get('codigo') or '').strip() or _slug(texto)
        base, n = codigo, 2
        while codigo in codigos:
            codigo = f'{base}_{n}'
            n += 1
        codigos.add(codigo)
        item = {'codigo': codigo, 'texto': texto, 'tipo': tipo,
                'obrigatorio': bool(b.get('obrigatorio')),
                'exige_foto': bool(b.get('exige_foto'))}
        # "Como fazer" e a foto de referência (como deve ficar): o que o ASG
        # vê no celular embaixo da pergunta. Ficam no JSON da versão — não
        # precisam de coluna — e a versão publicada não muda depois.
        como = (b.get('como_fazer') or '').strip()[:COMO_FAZER_MAX]
        if como:
            item['como_fazer'] = como
        ref = (b.get('foto_ref') or '').strip()
        if ref and CHAVE_DA_REFERENCIA.match(ref) and (
                donos is None or ref.split('/')[1] in donos):
            item['foto_ref'] = ref
        if tipo == 'escolha':
            brutas = b.get('opcoes') or ''
            if isinstance(brutas, (list, tuple)):     # item já normalizado (cópia, nova versão)
                brutas = ';'.join(brutas)
            opcoes = [o.strip()[:80] for o in re.split(r'[;\n]', brutas) if o.strip()]
            if len(opcoes) < 2:
                raise RegraDaRota(f'"{texto}": escreva pelo menos duas opções, separadas '
                                  'por ponto e vírgula.')
            item['opcoes'] = opcoes
        if tipo == 'numero':
            mn, mx = _numero(b.get('minimo')), _numero(b.get('maximo'))
            if mn is not None and mx is not None and mn > mx:
                raise RegraDaRota(f'"{texto}": o mínimo é maior que o máximo.')
            item['minimo'], item['maximo'] = mn, mx
        if tipo == 'sim_nao':
            problema = b.get('problema_se') or ''
            item['problema_se'] = problema if problema in ('sim', 'nao') else ''
        se = b.get('mostrar_se') or ''
        if isinstance(se, dict):
            se = f"{se.get('codigo', '')}={se.get('valor', '')}"
        se = se.strip()
        if se:
            # "codigo=valor": a pergunta só aparece quando a outra tem esse valor.
            alvo, _, valor = se.partition('=')
            alvo = alvo.strip()
            if alvo not in codigos - {codigo}:
                raise RegraDaRota(f'"{texto}": a condição precisa citar uma pergunta '
                                  'anterior (pelo código dela).')
            item['mostrar_se'] = {'codigo': alvo, 'valor': valor.strip()}
        itens.append(item)
    if not itens:
        raise RegraDaRota('O checklist precisa de pelo menos uma pergunta.')
    if len(itens) > ITENS_MAX:
        raise RegraDaRota(f'No máximo {ITENS_MAX} perguntas por checklist.')
    return itens


def criar_modelo(client_id, dados, autor):
    nome = (dados.get('nome') or '').strip()[:150]
    if not nome:
        raise RegraDaRota('Dê um nome ao checklist (ex.: Limpeza de banheiro).')
    q = ChecklistModelo.query.filter(db.func.lower(ChecklistModelo.nome) == nome.lower())
    q = q.filter(ChecklistModelo.client_id.is_(None) if client_id is None
                 else ChecklistModelo.client_id == client_id)
    if q.first() is not None:
        raise RegraDaRota('Já existe um checklist com este nome aqui.')
    m = ChecklistModelo(client_id=client_id, nome=nome,
                        descricao=(dados.get('descricao') or '').strip() or None)
    db.session.add(m)
    db.session.flush()
    return m


def publicar(modelo, itens, dados, autor):
    """Publica a versão seguinte se algo mudou; devolve (versão, publicou?)."""
    antes = bool(dados.get('exige_foto_antes'))
    depois = bool(dados.get('exige_foto_depois'))
    modelo.exige_foto_antes, modelo.exige_foto_depois = antes, depois
    if 'descricao' in dados:
        modelo.descricao = (dados.get('descricao') or '').strip() or None
    atual = modelo.versao_atual
    novo_json = json.dumps(itens, ensure_ascii=False, sort_keys=True)
    if atual is not None and atual.itens_json == novo_json \
            and atual.exige_foto_antes == antes and atual.exige_foto_depois == depois:
        return atual, False
    v = ChecklistVersao(modelo_id=modelo.id, numero=(atual.numero + 1) if atual else 1,
                        itens_json=novo_json, exige_foto_antes=antes,
                        exige_foto_depois=depois, publicada_por=getattr(autor, 'id', None))
    db.session.add(v)
    db.session.flush()
    db.session.refresh(modelo)
    return v, True


# ── POP / FIT do checklist ────────────────────────────────────────────────

DOCUMENTOS_POR_CHECKLIST = 10


def anexar_documento(modelo, arquivo, autor):
    """Guarda o POP/FIT (PDF, Excel, Word ou imagem — extensão E assinatura
    conferidas, a mesma regra dos anexos da casa)."""
    from facilities.core.anexos import (ANEXO_ASSINATURA, ANEXO_MAX, ANEXO_TIPOS,
                                        imagem_aceitavel, storage)
    from facilities.rotas.models import ChecklistDocumento
    if arquivo is None or not getattr(arquivo, 'filename', ''):
        raise RegraDaRota('Escolha o arquivo do POP ou da FIT.')
    if len(documentos_ativos(modelo)) >= DOCUMENTOS_POR_CHECKLIST:
        raise RegraDaRota(f'No máximo {DOCUMENTOS_POR_CHECKLIST} documentos por checklist. '
                          'Retire um antigo antes.')
    nome = arquivo.filename.replace('\\', '/').rsplit('/', 1)[-1].strip()[:200] or 'documento'
    ext = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
    dados = arquivo.read(ANEXO_MAX + 1)
    assinaturas = ANEXO_ASSINATURA.get(ext)
    if ext not in ANEXO_TIPOS or ext == 'csv' or not dados or len(dados) > ANEXO_MAX \
            or (assinaturas and not any(dados.startswith(a) for a in assinaturas)) \
            or not imagem_aceitavel(dados, ext):
        raise RegraDaRota('Envie o POP/FIT em PDF, Excel, Word ou imagem (até 25 MB).')
    chave = f'checklists/{modelo.id}/docs/{uuid.uuid4().hex}.{ext}'
    storage().save(chave, dados, ANEXO_TIPOS[ext])
    doc = ChecklistDocumento(modelo_id=modelo.id, nome=nome, mime=ANEXO_TIPOS[ext],
                             tamanho=len(dados), storage_key=chave,
                             enviado_por=autor.id if autor else None)
    db.session.add(doc)
    db.session.flush()
    return doc


def documentos_ativos(modelo):
    from facilities.rotas.models import ChecklistDocumento
    return (ChecklistDocumento.query.filter_by(modelo_id=modelo.id, is_active=True)
            .order_by(ChecklistDocumento.id).all())


def copiar_da_biblioteca(origem, client_id, autor):
    if origem.client_id is not None or origem.versao_atual is None:
        raise RegraDaRota('Escolha um checklist publicado da biblioteca.')
    existe = ChecklistModelo.query.filter_by(client_id=client_id, origem_id=origem.id).first()
    if existe is not None:
        raise RegraDaRota(f'Este local já tem uma cópia: "{existe.nome}".')
    nome = origem.nome
    if ChecklistModelo.query.filter(ChecklistModelo.client_id == client_id,
                                    db.func.lower(ChecklistModelo.nome) == nome.lower()).first():
        nome = f'{nome} (cópia)'[:150]
    m = ChecklistModelo(client_id=client_id, nome=nome, descricao=origem.descricao,
                        origem_id=origem.id)
    db.session.add(m)
    db.session.flush()
    # O POP/FIT da biblioteca vai junto (o mesmo arquivo; interno ao copiar).
    from facilities.rotas.models import ChecklistDocumento
    for doc in documentos_ativos(origem):
        db.session.add(ChecklistDocumento(modelo_id=m.id, nome=doc.nome, mime=doc.mime,
                                          tamanho=doc.tamanho, storage_key=doc.storage_key,
                                          enviado_por=autor.id if autor else None))
    v = origem.versao_atual
    publicar(m, json.loads(v.itens_json), {'exige_foto_antes': v.exige_foto_antes,
                                           'exige_foto_depois': v.exige_foto_depois}, autor)
    return m


def itens_da_versao(versao):
    return json.loads(versao.itens_json or '[]')


# ── Rotas ─────────────────────────────────────────────────────────────────

def _hora(bruto, rotulo):
    try:
        h, m = str(bruto or '').strip().split(':')[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        raise RegraDaRota(f'{rotulo}: use o formato 07:00.')


def _dias(bruto):
    dias = ''.join(sorted({d for d in str(bruto or '') if d in DIAS_DA_SEMANA}))
    if not dias:
        raise RegraDaRota('Escolha pelo menos um dia da semana.')
    return dias


def salvar_rota(local, rota, dados):
    nome = (dados.get('nome') or '').strip()[:150]
    turno = (dados.get('turno') or '').strip()[:50]
    if not nome or not turno:
        raise RegraDaRota('Informe o nome da rota e o turno.')
    outra = Rota.query.filter(Rota.client_id == local.id,
                              db.func.lower(Rota.nome) == nome.lower()).first()
    if outra is not None and (rota is None or outra.id != rota.id):
        raise RegraDaRota('Já existe uma rota com este nome neste local.')
    inicio = _hora(dados.get('hora_inicio'), 'Início do turno')
    fim = _hora(dados.get('hora_fim'), 'Fim do turno')
    if inicio == fim:
        raise RegraDaRota('O turno precisa ter duração (início e fim iguais).')
    try:
        tolerancia = int(dados.get('tolerancia_min') or 15)
    except ValueError:
        raise RegraDaRota('Tolerância em minutos, só o número.')
    if not 0 <= tolerancia <= 240:
        raise RegraDaRota('A tolerância vai de 0 a 240 minutos.')
    try:
        presencas = int(dados.get('presencas_por_turno') if dados.get('presencas_por_turno')
                        not in (None, '') else (rota.presencas_por_turno if rota else 2))
        prazo_presenca = int(dados.get('presenca_prazo_min') or
                             (rota.presenca_prazo_min if rota else 10))
    except ValueError:
        raise RegraDaRota('Confirmação de presença: use só números.')
    if not 0 <= presencas <= 6 or not 5 <= prazo_presenca <= 60:
        raise RegraDaRota('Confirmação de presença: de 0 a 6 por turno, com 5 a 60 minutos '
                          'para responder.')
    rota = rota or Rota(client_id=local.id)
    rota.nome, rota.turno = nome, turno
    rota.hora_inicio, rota.hora_fim = inicio, fim
    rota.tolerancia_min = tolerancia
    rota.presencas_por_turno, rota.presenca_prazo_min = presencas, prazo_presenca
    rota.dias_semana = _dias(dados.get('dias_semana'))
    if rota.id is None:
        db.session.add(rota)
    db.session.flush()
    return rota


def _janela(rota, dia):
    """Início e fim do turno que COMEÇA em ``dia`` (horas locais, sem fuso)."""
    ini = datetime.combine(dia, rota.hora_inicio)
    fim = datetime.combine(dia, rota.hora_fim)
    if fim <= ini:
        fim += timedelta(days=1)
    return ini, fim


def _horarios_fixos(bruto):
    out = set()
    for pedaco in re.split(r'[,;\s]+', bruto or ''):
        if pedaco:
            out.add(_hora(pedaco, f'Horário "{pedaco}"'))
    return sorted(out)


def salvar_item(rota, item, dados):
    from facilities.cadastros.models import PontoInspecao
    ponto = db.session.get(PontoInspecao, int(dados.get('ponto_id') or 0))
    if ponto is None or ponto.client_id != rota.client_id or not ponto.is_active:
        raise RegraDaRota('Escolha um ponto ativo deste local.')
    modelo = db.session.get(ChecklistModelo, int(dados.get('modelo_id') or 0))
    if modelo is None or modelo.client_id != rota.client_id or not modelo.is_active:
        raise RegraDaRota('Escolha um checklist deste local (copie da biblioteca, se precisar).')
    if modelo.versao_atual is None:
        raise RegraDaRota('Publique o checklist antes de usá-lo numa rota.')
    fixos = _horarios_fixos(dados.get('horarios'))
    freq = dados.get('frequencia_min')
    freq = int(freq) if str(freq or '').strip().isdigit() else None
    if freq is not None and not FREQUENCIA_MIN <= freq <= FREQUENCIA_MAX:
        raise RegraDaRota(f'A frequência vai de {FREQUENCIA_MIN} minutos a '
                          f'{FREQUENCIA_MAX // 60} horas.')
    if not fixos and not freq:
        raise RegraDaRota('Diga os horários (ex.: 07:00, 09:00) ou a frequência '
                          '(ex.: a cada 60 minutos).')
    ini, fim = _janela(rota, tempo.hoje())
    for h in fixos:
        momento = datetime.combine(ini.date(), h)
        if momento < ini:
            momento += timedelta(days=1)
        if not ini <= momento <= fim:
            raise RegraDaRota(f'{h.strftime("%H:%M")} está fora do turno '
                              f'({rota.hora_inicio.strftime("%H:%M")} às '
                              f'{rota.hora_fim.strftime("%H:%M")}).')
    item = item or RotaItem(rota_id=rota.id)
    item.ponto_id, item.modelo_id = ponto.id, modelo.id
    item.horarios = ', '.join(h.strftime('%H:%M') for h in fixos) or None
    item.frequencia_min = freq
    item.ordem = int(dados.get('ordem') or 0) if str(dados.get('ordem') or '').isdigit() \
        else (item.ordem or len(rota.itens) + 1)
    if item.id is None:
        # Pela relação: a lista ``rota.itens`` já carregada nesta sessão passa
        # a ter o item (o agendador rodando na mesma operação o enxerga).
        rota.itens.append(item)
    db.session.flush()
    return item


def salvar_itens_em_lote(rota, ponto_ids, dados):
    """Vários pontos de uma vez, com o mesmo checklist e os mesmos horários
    (ex.: os 10 banheiros da rota de limpeza). Tudo ou nada: um ponto inválido
    recusa o lote inteiro, dizendo qual."""
    ids = []
    for bruto in ponto_ids:
        bruto = str(bruto).strip()
        if bruto.isdigit() and int(bruto) not in ids:
            ids.append(int(bruto))
    if not ids:
        raise RegraDaRota('Marque pelo menos um ponto.')
    proxima = max([i.ordem or 0 for i in rota.itens] or [0]) + 1
    base = str(dados.get('ordem') or '').strip()
    inicio = int(base) if base.isdigit() else proxima
    itens = []
    for n, pid in enumerate(ids):
        linha = {k: dados.get(k) for k in ('modelo_id', 'horarios', 'frequencia_min')}
        linha['ponto_id'] = pid
        linha['ordem'] = str(inicio + n)
        itens.append(salvar_item(rota, None, linha))
    return itens


def pessoas_escalaveis(local_id):
    from facilities.core.hierarquia import carteira
    pessoas = (User.query.filter(User.is_active.is_(True), User.is_deleted.is_(False),
                                 User.role.in_(PERFIS_ESCALAVEIS))
               .order_by(User.name).all())
    saida = []
    for p in pessoas:
        c = carteira(p)
        if c is None or local_id in c:
            saida.append(p)
    return saida


def salvar_escala(rota, dados):
    uid = int(dados.get('user_id') or 0)
    pessoa = db.session.get(User, uid)
    if pessoa is None or pessoa not in pessoas_escalaveis(rota.client_id):
        raise RegraDaRota('Escolha uma pessoa ativa deste local (encarregado, ASG, técnico '
                          'ou supervisor).')
    try:
        inicio = datetime.strptime(dados.get('data_inicio') or tempo.hoje().isoformat(),
                                   '%Y-%m-%d').date()
        fim = (datetime.strptime(dados['data_fim'], '%Y-%m-%d').date()
               if dados.get('data_fim') else None)
    except ValueError:
        raise RegraDaRota('Data inválida.')
    if fim is not None and fim < inicio:
        raise RegraDaRota('O fim da escala é antes do começo.')
    e = RotaEscala(user_id=pessoa.id, dias_semana=_dias(dados.get('dias_semana')),
                   data_inicio=inicio, data_fim=fim)
    rota.escalas.append(e)
    db.session.flush()
    return e


def escalado(rota, dia):
    dia_semana = str(dia.isoweekday())
    for e in rota.escalas:
        if (e.is_active and dia_semana in e.dias_semana and e.data_inicio <= dia
                and (e.data_fim is None or dia <= e.data_fim)
                and e.pessoa is not None and e.pessoa.is_active):
            return e.user_id
    return None


# ── Agendador ─────────────────────────────────────────────────────────────

def horarios_do_item(rota, item, dia):
    """Os instantes (horas locais) em que o item acontece no turno de ``dia``."""
    ini, fim = _janela(rota, dia)
    momentos = set()
    for h in _horarios_fixos(item.horarios):
        m = datetime.combine(dia, h)
        if m < ini:
            m += timedelta(days=1)
        if ini <= m <= fim:
            momentos.add(m)
    if item.frequencia_min:
        m = ini
        while m < fim:
            momentos.add(m)
            m += timedelta(minutes=item.frequencia_min)
    return sorted(momentos)


def gerar(dia, client_ids=None, agora_utc=None):
    """Cria as tarefas do turno que começa em ``dia``. Devolve quantas criou."""
    from facilities.core.models import Client
    q = Rota.query.join(Client, Client.id == Rota.client_id).filter(
        Rota.is_active.is_(True), Client.is_active.is_(True), Client.is_deleted.is_(False))
    if client_ids is not None:
        q = q.filter(Rota.client_id.in_(list(client_ids) or [-1]))
    criadas = 0
    for rota in q.all():
        if str(dia.isoweekday()) not in rota.dias_semana:
            continue
        _ini, fim = _janela(rota, dia)
        fim_utc = tempo.para_utc(fim.date(), fim.time())
        pessoa = escalado(rota, dia)
        # Fase 6: faltou e alguém cobriu? A tarefa nasce com quem cobriu.
        from facilities.equipes.servico import substituto
        pessoa = substituto(rota, dia, pessoa)
        from facilities.rotas import presenca
        presenca.gerar(rota, dia, pessoa, agora_utc)
        for item in rota.itens:
            versao = item.modelo.versao_atual if item.modelo else None
            if (not item.is_active or versao is None or not item.modelo.is_active
                    or item.ponto is None or not item.ponto.is_active):
                continue
            existentes = {t.previsto_para for t in TarefaDia.query.filter_by(
                rota_item_id=item.id, data=dia)}
            for m in horarios_do_item(rota, item, dia):
                previsto = tempo.para_utc(m.date(), m.time())
                if previsto in existentes:
                    continue
                t = TarefaDia(rota_id=rota.id, rota_item_id=item.id, client_id=rota.client_id,
                              ponto_id=item.ponto_id, versao_id=versao.id, user_id=pessoa,
                              data=dia, previsto_para=previsto, fim_do_turno=fim_utc,
                              tolerancia_min=rota.tolerancia_min, status=PREVISTA)
                try:
                    with db.session.begin_nested():
                        db.session.add(t)
                    criadas += 1
                except IntegrityError:
                    # Outra rodada ao mesmo tempo já criou este horário.
                    pass
    return criadas


def fechar_perdidas(agora_utc):
    """Turno terminado sem nada registrado → PERDIDA."""
    q = TarefaDia.query.filter(TarefaDia.status == PREVISTA,
                               TarefaDia.fim_do_turno < agora_utc)
    n = 0
    for t in q.all():
        t.status = PERDIDA
        t.encerrada_em = agora_utc
        n += 1
    return n


def avisar_tarefas(agora_utc):
    """Chegou a hora: aviso no celular de quem está escalado (uma vez só)."""
    from facilities.core import push
    n = 0
    for t in TarefaDia.query.filter(TarefaDia.status == PREVISTA, TarefaDia.avisada_em.is_(None),
                                    TarefaDia.previsto_para <= agora_utc + timedelta(minutes=2),
                                    TarefaDia.user_id.isnot(None)).all():
        if agora_utc > t.previsto_para + timedelta(minutes=t.tolerancia_min):
            t.avisada_em = agora_utc            # passou: não avisa atrasado
            continue
        push.avisar([t.user_id], f'{tempo.fmt(t.previsto_para, "%H:%M")} · {t.ponto.nome}',
                    f'{t.versao.modelo.nome} — {t.ponto.ambiente.nome}. Leia o QR do local.',
                    f'/app/turno?ponto={t.ponto.codigo_qr}', marca=f'tarefa-{t.id}')
        t.avisada_em = agora_utc
        n += 1
    return n


# Chave da trava do agendador no Postgres (pg_advisory_xact_lock): um
# número qualquer, fixo, só deste uso.
TRAVA_DO_AGENDADOR = 7_314_202_610


def _outra_rodada_em_andamento():
    """Duas rodadas ao mesmo tempo (relógio atrasado + comando manual, ou um
    deploy no meio) mandariam o mesmo aviso duas vezes e esbarrariam nas
    regras de unicidade. No Postgres, só uma passa; a trava cai no commit.
    No SQLite (testes, desenvolvimento) não há concorrência."""
    bind = db.session.get_bind()
    if bind.dialect.name != 'postgresql':
        return False
    from sqlalchemy import text
    return not db.session.execute(text('SELECT pg_try_advisory_xact_lock(:k)'),
                                  {'k': TRAVA_DO_AGENDADOR}).scalar()


def rodar(origem='comando', agora_utc=None):
    """Uma rodada: hoje e amanhã gerados; avisos da hora (tarefas e presença);
    perdidas e presenças vencidas fechadas. Fica registrada.

    Devolve ``None`` se outra rodada já está em andamento (não faz nada).
    Se falhar, desfaz o que fez, GRAVA o registro da falha (com o erro) e
    repassa a exceção — antes a falha sumia junto com o desfazer."""
    agora_utc = agora_utc or datetime.utcnow()
    if _outra_rodada_em_andamento():
        return None
    hoje = tempo.local(agora_utc).date()
    iniciada = datetime.utcnow()
    reg = AgendadorExecucao(origem=origem, iniciada_em=iniciada)
    db.session.add(reg)
    db.session.flush()
    try:
        from facilities.chamados.servico import avisar_prazos
        from facilities.preventiva.servico import gerar_ordens
        from facilities.rotas import presenca
        reg.tarefas_geradas = (gerar(hoje, agora_utc=agora_utc)
                               + gerar(hoje + timedelta(days=1), agora_utc=agora_utc))
        gerar_ordens(hoje, agora_utc)
        from facilities.visitas.servico import fechar_vencidas, gerar_visitas
        gerar_visitas(hoje, agora_utc)
        fechar_vencidas(agora_utc)
        avisar_tarefas(agora_utc)
        presenca.avisar_e_fechar(agora_utc)
        avisar_prazos(agora_utc)
        from facilities.chamados.servico import lembrar_confirmacao
        lembrar_confirmacao(agora_utc)
        reg.tarefas_perdidas = fechar_perdidas(agora_utc)
        from facilities.core import retencao
        retencao.aplicar(agora_utc)
        reg.ok = True
    except Exception as erro:
        db.session.rollback()
        db.session.add(AgendadorExecucao(origem=origem, iniciada_em=iniciada,
                                         concluida_em=datetime.utcnow(), ok=False,
                                         erro=f'{type(erro).__name__}: {erro}'[:2000]))
        db.session.commit()
        raise
    reg.concluida_em = datetime.utcnow()
    return reg


def garantir_hoje(client_ids):
    """Gera (se faltar) as tarefas de hoje dos locais pedidos — a rede de
    segurança para quando o agendador ainda não rodou: abrir "Meu turno"
    nunca mostra uma lista vazia por falta de rodada."""
    hoje = tempo.hoje()
    return gerar(hoje, client_ids) + gerar(hoje - timedelta(days=1), client_ids) \
        if client_ids else 0


# ── Situação e acompanhamento ─────────────────────────────────────────────

def situacao(tarefa, agora_utc=None):
    if tarefa.status in ENCERRADAS:
        return tarefa.status
    agora_utc = agora_utc or datetime.utcnow()
    tol = timedelta(minutes=tarefa.tolerancia_min)
    if agora_utc < tarefa.previsto_para - tol:
        return 'prevista'
    if agora_utc <= tarefa.previsto_para + tol:
        return 'no_horario'
    return 'atrasada'


def aderencia(tarefas, agora_utc=None):
    """Concluídas no prazo ÷ previstas que já venceram (ou foram encerradas).

    Devolve (no_prazo, base, percentual ou None)."""
    agora_utc = agora_utc or datetime.utcnow()
    base = [t for t in tarefas if t.status in ENCERRADAS
            or agora_utc > t.previsto_para + timedelta(minutes=t.tolerancia_min)]
    no_prazo = sum(1 for t in base if t.status == CONCLUIDA_NO_PRAZO)
    return no_prazo, len(base), (round(100 * no_prazo / len(base), 1) if base else None)


def tarefas_do_dia(client_ids, dia, user=None):
    q = TarefaDia.query.filter(TarefaDia.client_id.in_(list(client_ids) or [-1]),
                               TarefaDia.data == dia)
    if user is not None:
        q = q.filter(db.or_(TarefaDia.user_id == user.id, TarefaDia.user_id.is_(None)))
    return q.order_by(TarefaDia.previsto_para, TarefaDia.id).all()


# ── Leitura do QR (o horário do servidor) ─────────────────────────────────

def _assinador():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='leitura-qr')


def registrar_leitura(user, ponto, agora_utc=None):
    """O QR foi lido COM sinal: o servidor carimba a hora e devolve um selo
    assinado, que a execução traz de volta (o aparelho não escolhe a hora)."""
    agora_utc = agora_utc or datetime.utcnow()
    return _assinador().dumps({'p': ponto.id, 'u': user.id, 't': agora_utc.isoformat()})


def _hora_da_leitura(selo, user, ponto):
    if not selo:
        return None
    try:
        dados = _assinador().loads(selo, max_age=int(VALIDADE_DA_LEITURA.total_seconds()))
    except BadSignature:
        return None
    if dados.get('p') != ponto.id or dados.get('u') != user.id:
        return None
    try:
        return datetime.fromisoformat(dados['t'])
    except (KeyError, ValueError):
        return None


def _hora_do_aparelho(bruto, agora_utc):
    """ISO do aparelho → UTC ingênuo, conferido contra o relógio do servidor."""
    try:
        dt = datetime.fromisoformat(str(bruto).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        raise RegraDaRota('Horário do aparelho inválido. Confira a data e a hora do celular.')
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if dt > agora_utc + FOLGA_DO_RELOGIO or dt < agora_utc - JANELA_SEM_SINAL:
        raise RegraDaRota('O horário do celular não confere com o do sistema. Acerte a data '
                          'e a hora do aparelho e envie de novo.', 409)
    return dt


# ── Execução ──────────────────────────────────────────────────────────────

def _visivel(item, respostas):
    se = item.get('mostrar_se')
    if not se:
        return True
    return str(respostas.get(se['codigo'], '')).strip().lower() == se['valor'].strip().lower()


def conferir_respostas(itens, respostas, fotos_por_item):
    """Valida as respostas; devolve (respostas limpas, não conformidades)."""
    limpas, ncs = {}, []
    for item in itens:
        cod = item['codigo']
        if not _visivel(item, respostas):
            continue
        bruto = respostas.get(cod)
        valor = '' if bruto is None else str(bruto).strip()[:300]
        if not valor:
            if item.get('obrigatorio'):
                raise RegraDaRota(f'Responda: "{item["texto"]}".')
            continue
        tipo = item['tipo']
        problema = False
        if tipo == 'sim_nao':
            if valor not in ('sim', 'nao'):
                raise RegraDaRota(f'"{item["texto"]}": responda sim ou não.')
            problema = item.get('problema_se') == valor
        elif tipo == 'conforme':
            if valor not in ('conforme', 'nao_conforme'):
                raise RegraDaRota(f'"{item["texto"]}": conforme ou não conforme.')
            problema = valor == 'nao_conforme'
        elif tipo == 'numero':
            n = _numero(valor)
            mn, mx = item.get('minimo'), item.get('maximo')
            problema = (mn is not None and n < mn) or (mx is not None and n > mx)
        elif tipo == 'escolha':
            if valor not in item.get('opcoes', []):
                raise RegraDaRota(f'"{item["texto"]}": escolha uma das opções.')
        elif tipo == 'data_hora':
            try:
                datetime.fromisoformat(valor)
            except ValueError:
                raise RegraDaRota(f'"{item["texto"]}": data e hora inválidas.')
        if item.get('exige_foto') and not fotos_por_item.get(cod):
            raise RegraDaRota(f'Tire a foto pedida em "{item["texto"]}".')
        limpas[cod] = valor
        if problema:
            ncs.append(item)
    return limpas, ncs


def ler_imagem(arquivo):
    """Lê e confere a foto (extensão E assinatura, tamanho) → (dados, ext, mime).

    Também usada pela visita de supervisão (Fase 10)."""
    from facilities.core.anexos import (ANEXO_ASSINATURA, ANEXO_MAX, ANEXO_TIPOS,
                                        imagem_aceitavel)
    nome = (getattr(arquivo, 'filename', '') or 'foto.jpg').lower()
    ext = nome.rsplit('.', 1)[-1] if '.' in nome else 'jpg'
    ext = 'jpg' if ext == 'jpeg' else ext
    dados = arquivo.read(ANEXO_MAX + 1)
    if ext not in ('jpg', 'png', 'webp') or not dados or len(dados) > ANEXO_MAX or \
            not any(dados.startswith(a) for a in ANEXO_ASSINATURA[ext]) or \
            not imagem_aceitavel(dados, ext):
        raise RegraDaRota('Uma das fotos não é imagem (ou é grande demais). Tire de novo.')
    return dados, ext, ANEXO_TIPOS[ext]


def _guardar_foto(execucao, arquivo, momento, item_codigo=None):
    from facilities.core.anexos import storage
    dados, ext, mime = ler_imagem(arquivo)
    chave = f'execucoes/{execucao.id}/{uuid.uuid4().hex}.{ext}'
    storage().save(chave, dados, mime)
    db.session.add(ExecucaoFoto(execucao_id=execucao.id, momento=momento,
                                item_codigo=item_codigo, mime=mime,
                                tamanho=len(dados), storage_key=chave))


def registrar_execucao(user, dados, fotos, agora_utc=None):
    """Grava a execução de uma tarefa (ou atividade extra). → (execucao, nova?)

    ``dados``: envio_id, ponto (código do QR), tarefa_id ou modelo_id (extra),
    respostas {código: valor}, selo_leitura (com sinal) ou os horários do
    aparelho (lido_em, concluida_em) com sem_sinal, observacao.
    ``fotos``: {'antes': [arq], 'depois': [arq], 'item:<codigo>': [arq]}.
    """
    from facilities.core.acesso import allowed_client_ids_or_none
    agora_utc = agora_utc or datetime.utcnow()
    envio = str(dados.get('envio_id') or '').strip()[:64]
    if len(envio) < 8:
        raise RegraDaRota('Envio sem identificação. Recarregue a tela.')
    ja = Execucao.query.filter_by(envio_id=envio).first()
    if ja is not None:
        if ja.user_id != user.id:
            raise RegraDaRota('Este envio pertence a outra pessoa.', 409)
        return ja, False
    if not user.can_access('diario_operacional') or user._effective_role() \
            not in PERFIS_QUE_EXECUTAM:
        raise RegraDaRota('Seu perfil não executa checklist.', 403)
    ponto = PontoInspecao.query.filter_by(codigo_qr=str(dados.get('ponto') or '')).first()
    if ponto is None:
        raise RegraDaRota('QR não reconhecido. Leia a etiqueta do local de novo.', 404)
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and ponto.client_id not in permitidos:
        raise RegraDaRota('Este local não está entre os seus.', 403)
    if not ponto.is_active:
        raise RegraDaRota('Este ponto foi desativado. Avise a gestão.', 409)

    tarefa = None
    chamado = None
    if dados.get('chamado_id'):
        # Fase 5: o checklist da preventiva, no ponto do plano.
        from facilities.chamados.models import STATUS_EM_ABERTO, Chamado
        from facilities.chamados.servico import pode_agir
        from facilities.preventiva.servico import ordem_do_chamado
        bruto = str(dados.get('chamado_id')).strip()
        chamado = db.session.get(Chamado, int(bruto)) if bruto.isdigit() else None
        ordem = ordem_do_chamado(chamado)
        if ordem is None or chamado.client_id != ponto.client_id:
            raise RegraDaRota('Ordem de serviço preventiva não encontrada.', 404)
        if not pode_agir(user, chamado):
            raise RegraDaRota('Você não pode atender esta ordem de serviço.', 403)
        if ordem.plano.ponto_id != ponto.id:
            raise RegraDaRota(f'Este QR é de outro ponto. A preventiva é em '
                              f'"{ordem.plano.ponto.nome}".', 409)
        if chamado.status not in STATUS_EM_ABERTO:
            raise RegraDaRota(f'A ordem {chamado.numero} já foi resolvida.', 409)
        # Como na atividade extra: vale a versão que a pessoa viu na tela,
        # se ainda for do checklist do plano (ela pode ter ficado sem sinal).
        from facilities.rotas.models import ChecklistVersao
        versao = ordem.plano.modelo.versao_atual
        vista = str(dados.get('versao_id') or '').strip()
        if vista.isdigit():
            v = db.session.get(ChecklistVersao, int(vista))
            if v is not None and v.modelo_id == ordem.plano.modelo_id:
                versao = v
        if versao is None:
            raise RegraDaRota('O checklist desta preventiva não está publicado. Avise a gestão.',
                              409)
    elif dados.get('tarefa_id'):
        bruto = str(dados.get('tarefa_id')).strip()
        # Trava a tarefa até o commit: duas pessoas no mesmo ponto não
        # registram a MESMA tarefa (a segunda vê "já registrada").
        tarefa = (db.session.execute(db.select(TarefaDia).where(TarefaDia.id == int(bruto))
                                     .with_for_update()).scalar_one_or_none()
                  if bruto.isdigit() else None)
        if tarefa is None or tarefa.client_id != ponto.client_id:
            raise RegraDaRota('Tarefa não encontrada.', 404)
        if tarefa.ponto_id != ponto.id:
            raise RegraDaRota(f'Este QR é de outro ponto. A tarefa é em '
                              f'"{tarefa.ponto.nome}".', 409)
        versao = tarefa.versao
    else:
        # Atividade extra (D53): um checklist do local, na versão em vigor. O
        # aplicativo manda a versão que tinha na tela; se ela ficou velha
        # enquanto estava sem sinal, vale a que ele mostrou à pessoa.
        from facilities.rotas.models import ChecklistVersao
        versao = None
        if str(dados.get('versao_id') or '').strip().isdigit():
            versao = db.session.get(ChecklistVersao, int(dados['versao_id']))
            modelo = versao.modelo if versao else None
        else:
            modelo = db.session.get(ChecklistModelo, int(dados['modelo_id']) if str(dados.get('modelo_id') or '').strip().isdigit() else 0)
            versao = modelo.versao_atual if modelo else None
        if modelo is None or versao is None or modelo.client_id != ponto.client_id \
                or not modelo.is_active:
            raise RegraDaRota('Escolha um checklist deste local.')

    # Os horários: o selo do servidor (com sinal) ou o aparelho (sem sinal).
    sem_sinal = bool(dados.get('sem_sinal'))
    lido = _hora_da_leitura(dados.get('selo_leitura'), user, ponto)
    if lido is None:
        lido = _hora_do_aparelho(dados.get('lido_em'), agora_utc)
        sem_sinal = True
    if sem_sinal and dados.get('concluida_em'):
        concluida = max(lido, _hora_do_aparelho(dados.get('concluida_em'), agora_utc))
    else:
        concluida = agora_utc
    virou_extra = None
    if tarefa is not None:
        tol = timedelta(minutes=tarefa.tolerancia_min)
        if lido < tarefa.previsto_para - tol:
            raise RegraDaRota(
                'Ainda não chegou o horário desta tarefa. Ela pode ser feita a partir das '
                f'{tempo.fmt(tarefa.previsto_para - tol, "%H:%M")}.', 409)
        # O trabalho FOI feito: se a tarefa já tinha dono ou o turno acabou
        # (comum quando o envio ficou guardado sem sinal), vira atividade extra
        # em vez de ser recusado — antes a fila só oferecia "descartar".
        if tarefa.status in (CONCLUIDA_NO_PRAZO, CONCLUIDA_COM_ATRASO, NAO_REALIZADA):
            quem = tarefa.execucoes[0].pessoa.name if tarefa.execucoes else 'outra pessoa'
            virou_extra = f'a tarefa já tinha sido registrada por {quem}'
        elif lido > tarefa.fim_do_turno:
            virou_extra = 'o turno da tarefa já tinha terminado'
        if virou_extra:
            tarefa = None

    itens = itens_da_versao(versao)
    fotos_por_item = {k.split(':', 1)[1]: v for k, v in fotos.items()
                      if k.startswith('item:') and v}
    respostas = dados.get('respostas') or {}
    if not isinstance(respostas, dict):
        raise RegraDaRota('Respostas inválidas.')
    limpas, ncs = conferir_respostas(itens, respostas, fotos_por_item)
    if versao.exige_foto_antes and not fotos.get('antes'):
        raise RegraDaRota('Tire a foto de ANTES.')
    if versao.exige_foto_depois and not fotos.get('depois'):
        raise RegraDaRota('Tire a foto de DEPOIS.')

    ex = Execucao(tarefa_id=tarefa.id if tarefa else None, client_id=ponto.client_id,
                  chamado_id=chamado.id if chamado else None,
                  ponto_id=ponto.id, versao_id=versao.id, user_id=user.id,
                  extra=tarefa is None and chamado is None,
                  lido_em=lido, iniciada_em=lido, concluida_em=concluida,
                  sem_sinal=sem_sinal, recebida_em=agora_utc,
                  respostas_json=json.dumps(limpas, ensure_ascii=False),
                  observacao=((f'[Registrada como atividade extra: {virou_extra}.] '
                               if virou_extra else '')
                              + (dados.get('observacao') or '').strip())[:2000] or None,
                  envio_id=envio, n_nao_conformes=len(ncs))
    ex.virou_extra = virou_extra
    db.session.add(ex)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        ja = Execucao.query.filter_by(envio_id=envio).first()
        if ja is not None and ja.user_id == user.id:
            return ja, False
        raise RegraDaRota('Envio repetido.', 409)
    for chave, arquivos in fotos.items():
        for arq in arquivos[:5]:
            if chave in ('antes', 'depois'):
                _guardar_foto(ex, arq, chave)
            elif chave.startswith('item:'):
                _guardar_foto(ex, arq, 'item', chave.split(':', 1)[1])
    novas_ncs = []
    for item in ncs:
        nc = NaoConformidade(execucao_id=ex.id, client_id=ex.client_id,
                             item_codigo=item['codigo'], item_texto=item['texto'],
                             resposta=limpas.get(item['codigo']))
        db.session.add(nc)
        novas_ncs.append(nc)
    if novas_ncs:
        _chamado_das_ncs(ex, novas_ncs, user)
    if chamado is not None:
        from facilities.preventiva.servico import resolver_pela_execucao
        resolver_pela_execucao(chamado, user, ex, agora_utc)
    if tarefa is not None:
        tarefa.status = (CONCLUIDA_NO_PRAZO if lido <= tarefa.previsto_para + tol
                         else CONCLUIDA_COM_ATRASO)
        tarefa.encerrada_em = concluida
        tarefa.encerrada_por = user.id
    return ex, True


def marcar_nao_realizada(tarefa, user, motivo, texto='', abrir_chamado=False):
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import ORIGEM_TAREFA_ROTA
    from facilities.core.acesso import allowed_client_ids_or_none
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and tarefa.client_id not in permitidos:
        raise RegraDaRota('Este local não está entre os seus.', 403)
    if user._effective_role() not in PERFIS_QUE_EXECUTAM:
        raise RegraDaRota('Seu perfil não registra tarefa.', 403)
    if tarefa.status not in (PREVISTA, PERDIDA):
        raise RegraDaRota('Esta tarefa já foi registrada.', 409)
    if motivo not in MOTIVOS_NAO_REALIZADA:
        raise RegraDaRota('Escolha o motivo.')
    texto = (texto or '').strip()[:300]
    if motivo == 'outro' and not texto:
        raise RegraDaRota('Diga em poucas palavras o que aconteceu.')
    tarefa.status = NAO_REALIZADA
    tarefa.motivo, tarefa.motivo_texto = motivo, texto or None
    tarefa.encerrada_em = datetime.utcnow()
    tarefa.encerrada_por = user.id
    if abrir_chamado:
        ch = chamados.abrir(
            user, tarefa.client_id,
            f'{tarefa.ponto.nome}: {MOTIVOS_NAO_REALIZADA[motivo].lower()}'[:200],
            descricao=(f'Tarefa da rota "{tarefa.rota.nome}" das '
                       f'{tempo.fmt(tarefa.previsto_para, "%H:%M")} não realizada. {texto}'),
            local=f'{tarefa.ponto.ambiente.nome} · {tarefa.ponto.nome}'[:200],
            categoria='limpeza' if motivo != 'equipamento' else 'equipamento',
            origem=ORIGEM_TAREFA_ROTA, origem_id=tarefa.id)
        tarefa.chamado_id = ch.id
    return tarefa


def _chamado_das_ncs(ex, ncs, user):
    """Decisão do dono (18/10/2026): item não conforme no checklist da rota
    ABRE chamado na hora — um por execução, com os itens na descrição e as
    fotos da execução (como a visita de supervisão). Antes o app dizia
    "avisado à gestão" e ninguém era avisado.

    O chamado nasce ligado à primeira não conformidade (o índice de origem viva
    impede duplicar) e todas as da execução apontam para ele."""
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import ORIGEM_NAO_CONFORMIDADE, ChamadoAnexo
    db.session.flush()
    lista = '; '.join(f'"{nc.item_texto}": {nc.resposta or "—"}' for nc in ncs)
    try:
        ch = chamados.abrir(
            user, ex.client_id,
            f'{ex.ponto.nome}: {len(ncs)} item(ns) não conforme(s) — '
            f'{ex.versao.modelo.nome}'[:200],
            descricao=(f'Checklist feito por {user.name} em {tempo.fmt(ex.concluida_em)}. '
                       f'Não conforme: {lista}.'
                       + (f' Observação: {ex.observacao}' if ex.observacao else '')),
            local=f'{ex.ponto.ambiente.nome} · {ex.ponto.nome}'[:200],
            origem=ORIGEM_NAO_CONFORMIDADE, origem_id=ncs[0].id)
    except chamados.RecusaChamado:
        # Perfil sem chamados (não deveria acontecer no campo): as não
        # conformidades ficam registradas e a gestão abre pela execução.
        return None
    for nc in ncs:
        nc.chamado_id = ch.id
    for f in ex.fotos:
        ext = f.storage_key.rsplit('.', 1)[-1]
        db.session.add(ChamadoAnexo(chamado_id=ch.id, nome=f'checklist-{f.id}.{ext}', mime=f.mime,
                                    tamanho=f.tamanho, storage_key=f.storage_key,
                                    momento='antes', uploaded_by=user.id))
    return ch


def abrir_chamado_da_nc(nc, user):
    from facilities.chamados import servico as chamados
    from facilities.chamados.models import ORIGEM_NAO_CONFORMIDADE
    if nc.chamado_id:
        return nc.chamado_id
    ex = nc.execucao
    ch = chamados.abrir(
        user, nc.client_id, f'{ex.ponto.nome}: {nc.item_texto}'[:200],
        descricao=f'Não conformidade no checklist: "{nc.item_texto}" — resposta: '
                  f'{nc.resposta or "—"}.',
        local=f'{ex.ponto.ambiente.nome} · {ex.ponto.nome}'[:200],
        origem=ORIGEM_NAO_CONFORMIDADE, origem_id=nc.id)
    nc.chamado_id = ch.id
    return ch.id


def corrigir(execucao, user, motivo, respostas_novas):
    if not user.e_gestao():
        raise RegraDaRota('Só a gestão corrige uma execução.', 403)
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise RegraDaRota('Diga o motivo da correção.')
    itens = itens_da_versao(execucao.versao)
    atuais = respostas_vigentes(execucao)
    combinadas = dict(atuais)
    combinadas.update({k: v for k, v in (respostas_novas or {}).items()
                       if k in {i['codigo'] for i in itens}})
    fotos = {i['codigo']: [True] for i in itens}      # as fotos já estão na execução
    limpas, _ncs = conferir_respostas(itens, combinadas, fotos)
    if limpas == atuais:
        raise RegraDaRota('Nada mudou.')
    db.session.add(ExecucaoCorrecao(execucao_id=execucao.id, motivo=motivo[:500],
                                    respostas_antes_json=json.dumps(atuais, ensure_ascii=False),
                                    respostas_depois_json=json.dumps(limpas, ensure_ascii=False),
                                    user_id=user.id))


def respostas_vigentes(execucao):
    """As respostas valendo agora: as originais, ou as da última correção."""
    if execucao.correcoes:
        return json.loads(execucao.correcoes[-1].respostas_depois_json)
    return json.loads(execucao.respostas_json or '{}')
