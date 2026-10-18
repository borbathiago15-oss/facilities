"""Quarentena de dados em migrações — a regra da casa antes de qualquer DELETE.

Uma migração que precisa apagar ou reescrever linhas (deduplicar, mover,
corrigir) NÃO apaga: primeiro copia TODAS as linhas afetadas para uma tabela
``_quarentena_<revisão>_<tabela>``, e só então mexe no original. A cópia é o
que torna o ``downgrade()`` honesto — ele reinsere o que saiu — e o que
permite, semanas depois, responder "que linha era aquela?" sem restaurar
backup.

Trazido do Trino Intelligence (``trino/quarentena.py``), onde nasceu depois
que uma migração fundiu registros duplicados e a única prova do que existia
antes era o backup do dia. Quarentena é barata; dado perdido não tem preço.

Aqui ganhou um par para o ``downgrade()`` que apaga TABELAS (a volta de uma
migração que criou tabelas): ``quarentenar_tabela`` copia a tabela inteira
antes do ``drop_table``, e ``restaurar_tabela`` devolve as linhas no
``upgrade()`` seguinte. Sem isso, ida → volta → ida apagava em silêncio tudo
o que tinha sido cadastrado nas tabelas novas.

Uso, dentro de ``upgrade()``::

    from facilities.core.quarentena import quarentenar, restaurar_da_quarentena

    ids = [...]                              # o que vai ser apagado
    quarentenar(op, 'custo_gestao', ids, revisao='e1f2a3b4c5d6')
    op.execute(...DELETE... WHERE id IN ids)

E em ``downgrade()``::

    restaurar_da_quarentena(op, 'custo_gestao', revisao='e1f2a3b4c5d6')

A tabela de quarentena NÃO é apagada pelo downgrade: apagar a cópia seria
descartar registro sem quarentena prévia — exatamente o que ela existe para
impedir. Limpeza é decisão humana, depois de conferido.
"""
import sqlalchemy as sa


def nome_quarentena(tabela, revisao):
    return f'_quarentena_{revisao}_{tabela}'


def quarentenar(op, tabela, ids, revisao, coluna_id='id'):
    """Copia as linhas ``ids`` de ``tabela`` para a quarentena da revisão.

    Idempotente: linha já copiada não é duplicada (útil no re-upgrade depois
    de um downgrade). Devolve quantas linhas foram copiadas agora.
    """
    ids = sorted({int(i) for i in ids})
    if not ids:
        return 0
    bind = op.get_bind()
    insp = sa.inspect(bind)
    destino = nome_quarentena(tabela, revisao)
    if destino not in insp.get_table_names():
        # Mesmas colunas e tipos do original, sem constraints nem FKs: a
        # quarentena guarda, não valida. Carimba quando entrou.
        origem = sa.Table(tabela, sa.MetaData(), autoload_with=bind)
        colunas = [sa.Column(c.name, c.type, nullable=True) for c in origem.columns]
        colunas.append(sa.Column('_quarentena_em', sa.DateTime,
                                 server_default=sa.func.now()))
        op.create_table(destino, *colunas)
    ja = {r[0] for r in bind.execute(
        sa.text(f'SELECT {coluna_id} FROM {destino}')).fetchall()}
    novos = [i for i in ids if i not in ja]
    if not novos:
        return 0
    cols = [c['name'] for c in insp.get_columns(tabela)]
    lista = ', '.join(cols)
    marcas = ', '.join(f':{i}' for i in range(len(novos)))
    params = {str(i): v for i, v in enumerate(novos)}
    bind.execute(sa.text(
        f'INSERT INTO {destino} ({lista}) SELECT {lista} FROM {tabela} '
        f'WHERE {coluna_id} IN ({marcas})'), params)
    return len(novos)


def restaurar_da_quarentena(op, tabela, revisao, coluna_id='id'):
    """Reinsere no original o que está na quarentena e não existe mais lá.

    Devolve quantas linhas voltaram. A quarentena fica.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    origem = nome_quarentena(tabela, revisao)
    if origem not in insp.get_table_names():
        return 0
    cols = [c['name'] for c in insp.get_columns(tabela)]
    lista = ', '.join(cols)
    r = bind.execute(sa.text(
        f'INSERT INTO {tabela} ({lista}) SELECT {lista} FROM {origem} q '
        f'WHERE NOT EXISTS (SELECT 1 FROM {tabela} t '
        f'WHERE t.{coluna_id} = q.{coluna_id})'))
    return r.rowcount or 0


def quarentenar_tabela(op, tabela, revisao, coluna_id='id', onde=None):
    """Copia as linhas de ``tabela`` (todas, ou as do filtro ``onde``) para a
    quarentena, antes do drop.

    Diferente de ``quarentenar``: a linha que já estava na quarentena (de uma
    volta anterior) é TROCADA pela versão atual — a tabela viva é a verdade
    mais nova, e sem a troca o próximo ``upgrade`` devolveria a versão velha
    de um registro editado depois da última ida e volta.
    """
    bind = op.get_bind()
    if tabela not in sa.inspect(bind).get_table_names():
        return 0
    filtro = f' WHERE {onde}' if onde else ''
    ids = [r[0] for r in bind.execute(sa.text(
        f'SELECT {coluna_id} FROM {tabela}{filtro}'))]
    if not ids:
        return 0
    destino = nome_quarentena(tabela, revisao)
    if destino in sa.inspect(bind).get_table_names():
        marcas = ', '.join(f':{i}' for i in range(len(ids)))
        bind.execute(sa.text(f'DELETE FROM {destino} WHERE {coluna_id} IN ({marcas})'),
                     {str(i): v for i, v in enumerate(ids)})
    return quarentenar(op, tabela, ids, revisao, coluna_id=coluna_id)


def restaurar_tabela(op, tabela, revisao, coluna_id='id'):
    """Devolve à tabela recém-criada o que a quarentena guardou, e acerta a
    sequência do id no Postgres (senão o próximo INSERT colide)."""
    n = restaurar_da_quarentena(op, tabela, revisao, coluna_id=coluna_id)
    bind = op.get_bind()
    if n and bind.dialect.name == 'postgresql':
        bind.execute(sa.text(
            f"SELECT setval(pg_get_serial_sequence('{tabela}', '{coluna_id}'), "
            f"(SELECT MAX({coluna_id}) FROM {tabela}))"))
    return n
