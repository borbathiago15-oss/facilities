"""As colunas cifradas, tabela a tabela, e as operações em lote sobre elas
(rodízio da chave e conferência). Trabalha em SQL cru: lê e grava o valor
GUARDADO, sem passar pelo tipo ``Cifrado``.

Campo sensível novo: ``Cifrado()`` no modelo, a coluna aqui e uma migração
que cifre as linhas que já existem.
"""
import sqlalchemy as sa

from facilities.core import cifra

CAMPOS = {
    'users': ('email', 'totp_segredo'),
    'convites': ('email', 'telefone'),
    'clients': ('endereco',),
    'push_inscricoes': ('p256dh', 'auth'),
}
# tabela → coluna de onde sai o índice cego ``email_index``
INDICES = {'users': 'email', 'convites': 'email'}


def _linhas(conn, tabela, colunas):
    lista = ', '.join(('id',) + colunas)
    return conn.execute(sa.text(f'SELECT {lista} FROM {tabela} ORDER BY id')).fetchall()


def cifrar_tabela(conn, tabela, colunas, indice_de=None, transformar=cifra.recifrar):
    """Aplica ``transformar`` em cada coluna (texto antigo → cifrado; cifrado
    → recifrado com a chave principal) e refaz o índice cego. Devolve
    quantas linhas mudaram."""
    n = 0
    for linha in _linhas(conn, tabela, colunas):
        valores = dict(zip(colunas, linha[1:]))
        novos = {c: transformar(v) for c, v in valores.items()}
        if indice_de:
            novos['email_index'] = cifra.indice(cifra.decifrar(valores[indice_de]))
        sets = ', '.join(f'{c} = :{c}' for c in novos)
        conn.execute(sa.text(f'UPDATE {tabela} SET {sets} WHERE id = :id'),
                     {**novos, 'id': linha[0]})
        n += 1
    return n


def decifrar_tabela(conn, tabela, colunas):
    """O caminho de volta (downgrade): grava o texto aberto."""
    for linha in _linhas(conn, tabela, colunas):
        novos = {c: cifra.decifrar(v) for c, v in zip(colunas, linha[1:])}
        sets = ', '.join(f'{c} = :{c}' for c in novos)
        conn.execute(sa.text(f'UPDATE {tabela} SET {sets} WHERE id = :id'),
                     {**novos, 'id': linha[0]})


def girar(session):
    conn = session.connection()
    return {t: cifrar_tabela(conn, t, cols, INDICES.get(t)) for t, cols in CAMPOS.items()}


def em_claro(session):
    """{(tabela, coluna): quantos valores estão sem cifra}."""
    conn = session.connection()
    faltando = {}
    for tabela, colunas in CAMPOS.items():
        for linha in _linhas(conn, tabela, colunas):
            for c, v in zip(colunas, linha[1:]):
                if not cifra.esta_cifrado(v):
                    faltando[(tabela, c)] = faltando.get((tabela, c), 0) + 1
    return faltando
