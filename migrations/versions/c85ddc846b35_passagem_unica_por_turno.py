"""Uma passagem só por contrato, modelo, dia e turno (auditoria, Fase 3, L2;
aprovada pelo dono).

O que muda no schema:

* índice ÚNICO ``uq_diario_turnos_chave`` em ``diario_operacional_turnos``
  (``client_id``, ``configuracao_id``, ``data_turno``, ``turno``). As quatro
  colunas são NOT NULL desde a estrutura inicial, então o índice comum já
  pega toda duplicata (não há NULL para escapar), no Postgres e no SQLite.

Antes do índice, as passagens repetidas que já existirem são resolvidas — e
nada se perde:

1. Em cada grupo repetido fica UMA passagem (a "sobrevivente"):
   - havendo encerrada, a encerrada MAIS ANTIGA (menor ``submitted_at``, e na
     falta dele o menor id). É a que chegou primeiro ao turno seguinte: a que
     foi lida, a que abriu a janela de correção, a que os números já usaram.
     As outras encerradas são o mesmo envio chegando de novo (a fila do
     aparelho + o toque) ou o rascunho velho do tempo em que cada envio
     criava uma linha;
   - sem encerrada (só rascunhos), o rascunho de MAIOR id — é o que a tela
     já abria e onde os envios mais recentes caíram (``salvar_turno`` pega o
     de maior id).
2. As linhas que apontam para as outras passagens (pendências, ocorrências,
   anexos, correções, trilha das pendências — toda chave estrangeira para
   ``diario_operacional_turnos``, descoberta pelo Inspector) passam a apontar
   para a sobrevivente. Nenhuma é apagada: a pendência que alguém já baixou
   continua baixada, a foto continua presa a uma passagem.
3. As passagens que saem são COPIADAS para
   ``_quarentena_c85ddc846b35_diario_operacional_turnos`` (todas as colunas:
   respostas, observação, autor, horários) e só então apagadas. As linhas
   filhas reapontadas são copiadas, com o ``turno_id`` de antes, para
   ``_quarentena_c85ddc846b35_<tabela filha>``.

A volta (``downgrade``) apaga o índice, devolve as passagens da quarentena
(com os mesmos ids) e devolve a cada linha filha o ``turno_id`` que ela tinha
— só às que ainda apontam para a sobrevivente para onde esta migração as
levou. As quarentenas ficam (limpeza é decisão humana).

No Postgres a tabela fica travada para escrita (``SHARE ROW EXCLUSIVE``;
leitura continua) da conferência até o índice: uma passagem gravada no meio
pela versão antiga do sistema não escapa da deduplicação nem derruba a
criação do índice.

Revision ID: c85ddc846b35
Revises: f3b8d1a6c2e4
Create Date: 2026-11-06 12:00:00.000000

"""
from collections import defaultdict
from datetime import datetime

from alembic import op
import sqlalchemy as sa

from facilities.core.quarentena import (nome_quarentena, quarentenar_tabela,
                                        restaurar_da_quarentena)


# revision identifiers, used by Alembic.
revision = 'c85ddc846b35'
down_revision = 'f3b8d1a6c2e4'
branch_labels = None
depends_on = None

TABELA = 'diario_operacional_turnos'
INDICE = 'uq_diario_turnos_chave'
CHAVE = ('client_id', 'configuracao_id', 'data_turno', 'turno')


def _tem_indice(bind):
    return any(i['name'] == INDICE for i in sa.inspect(bind).get_indexes(TABELA))


def _filhos(bind):
    """``[(tabela, coluna)]`` de toda chave estrangeira para as passagens."""
    insp = sa.inspect(bind)
    saida = []
    for tabela in sorted(insp.get_table_names()):
        if tabela.startswith('_quarentena_'):
            continue
        for fk in insp.get_foreign_keys(tabela):
            if fk.get('referred_table') == TABELA:
                saida.extend((tabela, c) for c in fk['constrained_columns'])
    return saida


def _data(valor):
    """``submitted_at`` como datetime (o SQLite devolve texto)."""
    if valor is None or isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(str(valor))


def sobrevivente(linhas):
    """O id que fica, dentre ``linhas`` (``id``, ``status``, ``submitted_at``)."""
    encerradas = [x for x in linhas if x[1] == 'encerrado']
    if encerradas:
        return min(encerradas, key=lambda x: (_data(x[2]) is None,
                                              _data(x[2]) or datetime.max, x[0]))[0]
    return max(x[0] for x in linhas)


def _lista(ids):
    return ', '.join(str(int(i)) for i in sorted(ids))


def duplicatas(bind):
    """``{id que sai: id que fica}`` das passagens repetidas hoje."""
    chave = ', '.join(CHAVE)
    junta = ' AND '.join(f't.{c} = d.{c}' for c in CHAVE)
    linhas = bind.execute(sa.text(
        f'SELECT t.id, t.status, t.submitted_at, {", ".join("t." + c for c in CHAVE)} '
        f'FROM {TABELA} t JOIN (SELECT {chave} FROM {TABELA} GROUP BY {chave} '
        f'HAVING COUNT(*) > 1) d ON {junta} ORDER BY t.id')).fetchall()
    grupos = defaultdict(list)
    for r in linhas:
        grupos[tuple(r[3:])].append((r[0], r[1], r[2]))
    mapa = {}
    for grupo in grupos.values():
        fica = sobrevivente(grupo)
        mapa.update({x[0]: fica for x in grupo if x[0] != fica})
    return mapa


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(f'LOCK TABLE {TABELA} IN SHARE ROW EXCLUSIVE MODE')
    mapa = duplicatas(bind)
    if mapa:
        quarentenar_tabela(op, TABELA, revision, onde=f'id IN ({_lista(mapa)})')
        for tabela, coluna in _filhos(bind):
            ids = [r[0] for r in bind.execute(sa.text(
                f'SELECT id FROM {tabela} WHERE {coluna} IN ({_lista(mapa)})'))]
            if not ids:
                continue
            quarentenar_tabela(op, tabela, revision, onde=f'id IN ({_lista(ids)})')
            for sai, fica in sorted(mapa.items()):
                bind.execute(sa.text(f'UPDATE {tabela} SET {coluna} = :fica '
                                     f'WHERE {coluna} = :sai'), {'fica': fica, 'sai': sai})
        bind.execute(sa.text(f'DELETE FROM {TABELA} WHERE id IN ({_lista(mapa)})'))
    if not _tem_indice(bind):
        op.create_index(INDICE, TABELA, list(CHAVE), unique=True)


def downgrade():
    bind = op.get_bind()
    if _tem_indice(bind):
        op.drop_index(INDICE, table_name=TABELA)
    quarentena = nome_quarentena(TABELA, revision)
    if quarentena not in sa.inspect(bind).get_table_names():
        return
    # Para cada passagem da quarentena, a sobrevivente da mesma chave (ainda
    # há uma só viva por chave: nada voltou ainda). A que já está viva (de uma
    # volta anterior) não tem par e não mexe em nada.
    junta = ' AND '.join(f't.{c} = q.{c}' for c in CHAVE)
    pares = bind.execute(sa.text(
        f'SELECT q.id, t.id FROM {quarentena} q JOIN {TABELA} t ON {junta} '
        f'AND t.id <> q.id ORDER BY q.id')).fetchall()
    restaurar_da_quarentena(op, TABELA, revision)
    tabelas = set(sa.inspect(bind).get_table_names())
    for tabela, coluna in _filhos(bind):
        copia = nome_quarentena(tabela, revision)
        if copia not in tabelas:
            continue
        for saiu, ficou in pares:
            bind.execute(sa.text(
                f'UPDATE {tabela} SET {coluna} = :saiu WHERE {coluna} = :ficou '
                f'AND id IN (SELECT id FROM {copia} WHERE {coluna} = :saiu)'),
                {'saiu': saiu, 'ficou': ficou})
