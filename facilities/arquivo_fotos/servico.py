"""As regras do arquivo das fotos: o painel, o prazo, o início do lote e a
rodada (chamada pelo agendador, ``rotas.servico.rodar``).

Cada foto, NESTA ordem: lê do principal → grava no arquivo → lê de volta do
arquivo e compara o SHA-256 → registra (``FotoArquivada``). A remoção do
principal fica para a rodada SEGUINTE, quando o registro já está gravado no
banco: se a rodada cair no meio, nada se perde (no máximo a foto fica em dois
lugares até a próxima). Qualquer falha deixa a foto no principal, anota o
erro no lote e tenta de novo numa rodada seguinte.

Só fotos entram: as da execução da rota, da visita, os anexos de imagem do
chamado e da passagem, a foto do aviso do público e a do pedido de material.
Nunca as fotos de referência do checklist, POP/FIT, logos nem relatórios.
"""
import hashlib
import logging
import os
import time
from collections import namedtuple
from datetime import datetime, timedelta

from sqlalchemy import exists, extract, func, or_

from facilities import tempo
from facilities.core import log_seguro
from facilities.extensions import db
from facilities.arquivo_fotos.models import (
    DIAS_PADRAO, LOTE_CONCLUIDO, LOTE_CONCLUIDO_COM_FALHAS, LOTE_EM_ANDAMENTO,
    ArquivoAjustes, FalhaArquivo, FotoArquivada, LoteArquivo)
from facilities.object_storage import LocalStorage, NotFound

log = logging.getLogger(__name__)

# Por rodada (o agendador roda a cada 5 minutos): no máximo tantas fotos e
# tantos segundos — o que sobrar vai na próxima.
POR_RODADA = 200
SEGUNDOS_POR_RODADA = 40
# Foto que falhou tantas vezes no MESMO lote fica no principal até o próximo
# lote (sem isso, uma foto com defeito travaria o lote para sempre).
TENTATIVAS_POR_LOTE = 3
DIAS_MIN, DIAS_MAX = 1, 3650


class RegraDoArquivo(Exception):
    """Pedido recusado, com a mensagem para a tela."""

    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


# Uma tabela de fotos: a linha, a chave do arquivo, quando nasceu, o tamanho
# (None quando a tabela não guarda), o tipo, o filtro "é foto" e o local.
Fonte = namedtuple('Fonte', 'nome modelo chave criada tamanho mime filtro local junta')


def fontes():
    from facilities.chamados.models import Chamado, ChamadoAnexo
    from facilities.materiais.models import PedidoInsumo
    from facilities.passagem.models import DiarioAnexo, DiarioTurno
    from facilities.rotas.models import Execucao, ExecucaoFoto, OcorrenciaPublica
    from facilities.visitas.models import Visita, VisitaFoto
    imagem = lambda m: m.like('image/%')        # noqa: E731
    return (
        # As fotos da rota e da visita são sempre imagem (a gravação recusa o
        # resto); as linhas antigas sem tipo também são foto.
        Fonte('execucao_fotos', ExecucaoFoto, ExecucaoFoto.storage_key,
              ExecucaoFoto.created_at, ExecucaoFoto.tamanho, ExecucaoFoto.mime,
              or_(ExecucaoFoto.mime.is_(None), imagem(ExecucaoFoto.mime)),
              Execucao.client_id, (Execucao, Execucao.id == ExecucaoFoto.execucao_id)),
        Fonte('visita_fotos', VisitaFoto, VisitaFoto.storage_key,
              VisitaFoto.created_at, VisitaFoto.tamanho, VisitaFoto.mime,
              or_(VisitaFoto.mime.is_(None), imagem(VisitaFoto.mime)),
              Visita.client_id, (Visita, Visita.id == VisitaFoto.visita_id)),
        # Chamado e passagem também aceitam PDF e planilha: só a imagem sai.
        Fonte('chamado_anexos', ChamadoAnexo, ChamadoAnexo.storage_key,
              ChamadoAnexo.created_at, ChamadoAnexo.tamanho, ChamadoAnexo.mime,
              imagem(ChamadoAnexo.mime),
              Chamado.client_id, (Chamado, Chamado.id == ChamadoAnexo.chamado_id)),
        Fonte('diario_operacional_anexos', DiarioAnexo, DiarioAnexo.storage_key,
              DiarioAnexo.created_at, DiarioAnexo.tamanho, DiarioAnexo.mime,
              imagem(DiarioAnexo.mime),
              DiarioTurno.client_id, (DiarioTurno, DiarioTurno.id == DiarioAnexo.turno_id)),
        Fonte('ocorrencias_publicas', OcorrenciaPublica, OcorrenciaPublica.foto_key,
              OcorrenciaPublica.criada_em, None, OcorrenciaPublica.foto_mime,
              OcorrenciaPublica.foto_key.isnot(None),
              OcorrenciaPublica.client_id, None),
        Fonte('pedidos_insumo', PedidoInsumo, PedidoInsumo.foto_key,
              PedidoInsumo.criado_em, None, PedidoInsumo.foto_mime,
              PedidoInsumo.foto_key.isnot(None),
              PedidoInsumo.client_id, None),
    )


def _armazenamento():
    from facilities.core.anexos import storage
    return storage()


def _destino():
    """(storage do arquivo ou None, info) — ver ``object_storage.arquivo_do_ambiente``."""
    st = _armazenamento()
    return getattr(st, 'arquivo', None), getattr(st, 'info', {}) or {}


# ── Prazo ──────────────────────────────────────────────────────────────────

def ajustes():
    return db.session.get(ArquivoAjustes, 1)


def dias_do_prazo():
    a = ajustes()
    return a.dias if a else DIAS_PADRAO


def salvar_dias(user, bruto, agora_utc=None):
    try:
        dias = int(str(bruto).strip())
    except (TypeError, ValueError):
        raise RegraDoArquivo('Escreva o prazo em dias, só com números.')
    if not DIAS_MIN <= dias <= DIAS_MAX:
        raise RegraDoArquivo(f'O prazo vai de {DIAS_MIN} a {DIAS_MAX} dias.')
    a = ajustes()
    if a is None:
        a = ArquivoAjustes(id=1)
        db.session.add(a)
    a.dias = dias
    a.atualizado_em = agora_utc or datetime.utcnow()
    a.atualizado_por = user.id
    return a


# ── O que está guardado ───────────────────────────────────────────────────

def _nao_arquivada(fonte):
    return ~exists().where(FotoArquivada.storage_key == fonte.chave)


def _pendentes(corte):
    """Fotos de antes do ``corte`` que ainda não estão no arquivo →
    (quantidade, bytes conhecidos, quantas sem tamanho registrado)."""
    n = total = sem_tamanho = 0
    for f in fontes():
        q = db.session.query(func.count(), func.sum(f.tamanho) if f.tamanho is not None
                             else func.count()).select_from(f.modelo) \
            .filter(f.filtro, f.criada < corte, _nao_arquivada(f))
        qtd, soma = q.one()
        n += qtd or 0
        if f.tamanho is None:
            sem_tamanho += qtd or 0
        else:
            total += int(soma or 0)
    return n, total, sem_tamanho


def _meses(agora_utc, n=12):
    """Os ``n`` últimos meses, do mais velho ao atual, como (ano, mês)."""
    ano, mes = agora_utc.year, agora_utc.month
    saida = []
    for _ in range(n):
        saida.append((ano, mes))
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return list(reversed(saida))


def painel(agora_utc=None):
    """Tudo o que a tela "Armazenamento de fotos" mostra."""
    from facilities.core.models import Client
    agora_utc = agora_utc or datetime.utcnow()
    dias = dias_do_prazo()
    corte = agora_utc - timedelta(days=dias)

    total_fotos = total_bytes = sem_tamanho = 0
    por_local = {}
    meses = _meses(agora_utc)
    por_mes = {m: [0, 0] for m in meses}
    inicio_meses = datetime(meses[0][0], meses[0][1], 1)
    for f in fontes():
        soma = func.sum(f.tamanho) if f.tamanho is not None else func.count()
        qtd, b = db.session.query(func.count(), soma).select_from(f.modelo) \
            .filter(f.filtro).one()
        total_fotos += qtd or 0
        if f.tamanho is None:
            sem_tamanho += qtd or 0
            continue
        total_bytes += int(b or 0)
        q = db.session.query(f.local, func.sum(f.tamanho)).select_from(f.modelo)
        if f.junta is not None:
            q = q.join(*f.junta)
        for cid, b in q.filter(f.filtro).group_by(f.local):
            por_local[cid] = por_local.get(cid, 0) + int(b or 0)
        ano, mes = extract('year', f.criada), extract('month', f.criada)
        for a, m, qtd, b in (db.session.query(ano, mes, func.count(), func.sum(f.tamanho))
                             .select_from(f.modelo)
                             .filter(f.filtro, f.criada >= inicio_meses)
                             .group_by(ano, mes)):
            chave = (int(a), int(m))
            if chave in por_mes:
                por_mes[chave][0] += qtd or 0
                por_mes[chave][1] += int(b or 0)

    top = sorted(((b, cid) for cid, b in por_local.items() if b), reverse=True)[:10]
    nomes = dict(db.session.query(Client.id, Client.name)
                 .filter(Client.id.in_([cid for _b, cid in top])).all()) if top else {}

    arq_n, arq_b = db.session.query(func.count(FotoArquivada.id),
                                    func.sum(FotoArquivada.tamanho)).one()
    fora_n, fora_b = db.session.query(func.count(FotoArquivada.id),
                                      func.sum(FotoArquivada.tamanho)) \
        .filter(FotoArquivada.removida_do_principal_em.isnot(None)).one()
    pend_n, pend_b, pend_sem = _pendentes(corte)
    arquivo, info = _destino()
    em_andamento = LoteArquivo.query.filter_by(situacao=LOTE_EM_ANDAMENTO) \
        .order_by(LoteArquivo.id).first()
    lotes = LoteArquivo.query.order_by(LoteArquivo.id.desc()).limit(10).all()
    nao_sairam = FalhaArquivo.query.count()
    return {
        'dias': dias,
        'dias_min': DIAS_MIN,
        'dias_max': DIAS_MAX,
        'corte': tempo.fmt(corte, '%d/%m/%Y'),
        'destino': {
            'disponivel': arquivo is not None,
            'tipo': info.get('tipo'),
            'rotulo': info.get('rotulo') or '',
            'mesmo_disco': bool(info.get('mesmo_disco')),
            'problema': info.get('problema'),
        },
        'total': {'fotos': total_fotos, 'bytes': total_bytes, 'sem_tamanho': sem_tamanho},
        'por_mes': [{'mes': f'{m:02d}/{a}', 'fotos': por_mes[(a, m)][0],
                     'bytes': por_mes[(a, m)][1]} for a, m in meses],
        'locais': [{'local': nomes.get(cid) or f'Local {cid}', 'bytes': b} for b, cid in top],
        'arquivadas': {'fotos': arq_n or 0, 'bytes': int(arq_b or 0),
                       'fora_do_principal': fora_n or 0,
                       'bytes_fora_do_principal': int(fora_b or 0)},
        'no_principal_bytes': max(total_bytes - int(fora_b or 0), 0),
        'pendentes': {'fotos': pend_n, 'bytes': pend_b, 'sem_tamanho': pend_sem},
        'nao_sairam': nao_sairam,
        'em_andamento': _lote(em_andamento) if em_andamento else None,
        'lotes': [_lote(lt) for lt in lotes],
    }


def _lote(lt):
    return {
        'id': lt.id,
        'situacao': lt.situacao,
        'situacao_rotulo': lt.situacao_rotulo,
        'quem': (lt.pessoa.name if lt.pessoa else '') or '',
        'iniciado_em': tempo.fmt(lt.iniciado_em, '%d/%m/%Y %H:%M'),
        'concluido_em': tempo.fmt(lt.concluido_em, '%d/%m/%Y %H:%M') if lt.concluido_em else None,
        'corte': tempo.fmt(lt.corte_em, '%d/%m/%Y'),
        'dias': lt.dias,
        'destino': lt.destino,
        'previstas': lt.previstas,
        'arquivadas': lt.arquivadas,
        'bytes': lt.bytes_arquivados,
        'nao_arquivadas': lt.nao_arquivadas,
        'tentativas_com_erro': lt.tentativas_com_erro,
        'ultimo_erro': lt.ultimo_erro,
        'ultima_rodada_em': (tempo.fmt(lt.ultima_rodada_em, '%d/%m/%Y %H:%M')
                             if lt.ultima_rodada_em else None),
    }


# ── Começar ───────────────────────────────────────────────────────────────

def iniciar(user, agora_utc=None):
    """O administrador confirmou: abre o lote. O trabalho é do agendador."""
    agora_utc = agora_utc or datetime.utcnow()
    arquivo, info = _destino()
    if arquivo is None:
        raise RegraDoArquivo(info.get('problema')
                             or 'O destino do arquivo não está configurado neste servidor.',
                             status=409)
    if LoteArquivo.query.filter_by(situacao=LOTE_EM_ANDAMENTO).first():
        raise RegraDoArquivo('Já há um arquivamento em andamento. Espere ele terminar.',
                             status=409)
    dias = dias_do_prazo()
    corte = agora_utc - timedelta(days=dias)
    previstas, _b, _s = _pendentes(corte)
    if not previstas:
        raise RegraDoArquivo(f'Nenhuma foto com mais de {dias} dias para arquivar.', status=409)
    lote = LoteArquivo(iniciado_por=user.id, iniciado_em=agora_utc, dias=dias, corte_em=corte,
                       destino=(info.get('rotulo') or '')[:300] or 'arquivo',
                       situacao=LOTE_EM_ANDAMENTO, previstas=previstas)
    db.session.add(lote)
    db.session.flush()
    return lote


# ── A rodada (agendador) ──────────────────────────────────────────────────

def _sha(dados):
    return hashlib.sha256(dados).hexdigest()


def _anotar_erro(lote, texto):
    lote.tentativas_com_erro += 1
    lote.ultimo_erro = texto[:2000]


def _falhou(lote, fonte, linha_id, chave, erro, agora_utc):
    texto = f'{fonte.nome} #{linha_id}: {erro}'[:500]
    _anotar_erro(lote, texto)
    f = FalhaArquivo.query.filter_by(storage_key=chave).first()
    if f is None:
        f = FalhaArquivo(storage_key=chave, origem=fonte.nome, origem_id=linha_id,
                         lote_id=lote.id, tentativas=0)
        db.session.add(f)
    elif f.lote_id != lote.id:
        # Lote novo: a foto ganha as tentativas de novo.
        f.lote_id, f.tentativas = lote.id, 0
    f.tentativas += 1
    f.erro = texto
    f.em = agora_utc


def _arquivar_uma(lote, fonte, linha_id, chave, mime, principal, arquivo, agora_utc):
    """Copia, confere e registra uma foto. Não apaga nada do principal."""
    try:
        try:
            dados = principal.load(chave)
        except NotFound:
            # Só no arquivo (rodada que caiu entre a cópia e o registro):
            # registra o que está lá. Em lugar nenhum: é erro, e nada muda.
            try:
                dados = arquivo.load(chave)
            except NotFound:
                raise NotFound('a foto não está no armazenamento principal nem no arquivo')
        else:
            arquivo.save(chave, dados, mime)
        volta = arquivo.load(chave)
        if _sha(volta) != _sha(dados):
            raise ValueError('a cópia no arquivo não confere com a original')
    except Exception as erro:                   # noqa: BLE001 — anotado; a foto fica
        _falhou(lote, fonte, linha_id, chave, log_seguro.resumo(erro), agora_utc)
        return False
    try:
        with db.session.begin_nested():
            db.session.add(FotoArquivada(storage_key=chave, origem=fonte.nome,
                                         origem_id=linha_id, tamanho=len(dados),
                                         sha256=_sha(dados), arquivada_em=agora_utc,
                                         lote_id=lote.id))
            FalhaArquivo.query.filter_by(storage_key=chave).delete()
    except Exception as erro:                   # noqa: BLE001 — ex.: chave repetida
        _falhou(lote, fonte, linha_id, chave, log_seguro.resumo(erro), agora_utc)
        return False
    lote.arquivadas += 1
    lote.bytes_arquivados += len(dados)
    return True


def _remover_do_principal(principal, arquivo, agora_utc, limite):
    """Fase 1 da rodada: o que já está registrado (numa rodada anterior) sai
    do principal — só depois de conferir que a cópia continua no arquivo.
    → (removidas, erros, avisos)."""
    removidas, erros, perdida = 0, [], []
    pendentes = (FotoArquivada.query.filter(FotoArquivada.removida_do_principal_em.is_(None))
                 .order_by(FotoArquivada.id).limit(limite).all())
    for fa in pendentes:
        try:
            if not arquivo.exists(fa.storage_key):
                # A cópia sumiu do arquivo: o registro sai e a foto (que
                # continua no principal) é copiada de novo.
                perdida.append(f'{fa.origem} #{fa.origem_id}: a cópia não estava mais no '
                               'arquivo; vai ser copiada de novo')
                db.session.delete(fa)
                continue
            principal.delete(fa.storage_key)
        except Exception as erro:               # noqa: BLE001 — fica para a próxima
            erros.append((fa, f'{fa.origem} #{fa.origem_id}: {log_seguro.resumo(erro)}'))
            continue
        fa.removida_do_principal_em = agora_utc
        removidas += 1
    return removidas, erros, perdida


def rodada(agora_utc=None, por_rodada=None, segundos=None):
    """Um passo do lote em andamento (se houver). Devolve um resumo, ou
    ``None`` quando não há lote."""
    agora_utc = agora_utc or datetime.utcnow()
    st = _armazenamento()
    principal, (arquivo, info) = getattr(st, 'principal', st), _destino()
    # Servidor que não enxerga as fotos ou o destino (no Railway, o
    # agendador não tem o volume do web): não mexe no lote. Quem enxerga é
    # que anda com ele (``flask anexos arquivar``; ver docs/ARQUIVO_FOTOS.md).
    if arquivo is None:
        log.info('arquivo das fotos: sem destino neste servidor (%s)', info.get('problema'))
        return None
    if isinstance(principal, LocalStorage) and not os.path.isdir(principal.base):
        log.info('arquivo das fotos: este servidor não enxerga a pasta das fotos')
        return None
    # Dois processos na mesma hora (agendador e web): o segundo pula a vez.
    lote = (LoteArquivo.query.filter_by(situacao=LOTE_EM_ANDAMENTO).order_by(LoteArquivo.id)
            .with_for_update(skip_locked=True).first())
    if lote is None:
        return None
    por_rodada = por_rodada or int(os.environ.get('ARQUIVO_FOTOS_POR_RODADA') or POR_RODADA)
    segundos = segundos or SEGUNDOS_POR_RODADA
    lote.ultima_rodada_em = agora_utc

    removidas, erros, avisos = _remover_do_principal(principal, arquivo, agora_utc, por_rodada)
    for texto in [t for _fa, t in erros] + avisos:
        _anotar_erro(lote, texto)
    db.session.flush()

    fim = time.monotonic() + segundos
    arquivadas = falhas = vistas = 0
    for f in fontes():
        if vistas >= por_rodada or time.monotonic() > fim:
            break
        linhas = (db.session.query(f.modelo.id, f.chave, f.mime).select_from(f.modelo)
                  .filter(f.filtro, f.criada < lote.corte_em, _nao_arquivada(f),
                          ~exists().where(FalhaArquivo.storage_key == f.chave,
                                          FalhaArquivo.lote_id == lote.id,
                                          FalhaArquivo.tentativas >= TENTATIVAS_POR_LOTE))
                  .order_by(f.modelo.id).limit(por_rodada - vistas).all())
        for linha_id, chave, mime in linhas:
            if time.monotonic() > fim:
                break
            vistas += 1
            if _arquivar_uma(lote, f, linha_id, chave, mime, principal, arquivo, agora_utc):
                arquivadas += 1
            else:
                falhas += 1

    # Terminou: nada novo para copiar e nada esperando sair do principal.
    if vistas == 0 and not erros and not avisos:
        restam = FotoArquivada.query.filter(
            FotoArquivada.lote_id == lote.id,
            FotoArquivada.removida_do_principal_em.is_(None)).count()
        if not restam:
            lote.nao_arquivadas = FalhaArquivo.query.filter_by(lote_id=lote.id).count()
            lote.situacao = LOTE_CONCLUIDO_COM_FALHAS if lote.nao_arquivadas else LOTE_CONCLUIDO
            lote.concluido_em = agora_utc
    return {'removidas': removidas, 'arquivadas': arquivadas, 'falhas': falhas}


def esquecer(chave):
    """A foto saiu de vez (retenção): o registro do arquivo também sai."""
    FotoArquivada.query.filter_by(storage_key=chave).delete()
    FalhaArquivo.query.filter_by(storage_key=chave).delete()
