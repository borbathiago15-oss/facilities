"""O que pode ir para o log (e para o registro da rodada) sobre um erro.

A mensagem de um erro do banco carrega o que não deve sair do servidor: o
``OperationalError`` do psycopg2 diz o host, o usuário e o nome do banco
("connection to server at "db.x" ... user "facilities""), e todo erro do
SQLAlchemy traz a consulta e os PARÂMETROS dela — e-mail, telefone, nome de
quem estava sendo gravado. O log da hospedagem é lido por mais gente e
guardado por mais tempo que o banco.

``resumo(erro)`` devolve uma linha curta:

* erro do banco → só a classe, a classe do driver, o SQLSTATE e um motivo
  em palavras ("tempo esgotado", "conexão recusada"...), nunca a mensagem;
* outro erro → classe e a primeira linha da mensagem, com URL com senha,
  e-mail e os trechos de conexão (host/usuário/banco entre aspas) apagados.
"""
import re

from sqlalchemy import exc as sa_exc

# Palavras da mensagem do driver → motivo em português. Só a palavra entra
# no log; a mensagem, não.
_MOTIVOS = (
    ('statement timeout', 'consulta cortada pelo tempo limite'),
    ('lock timeout', 'espera de trava esgotada'),
    ('could not obtain lock', 'espera de trava esgotada'),
    ('idle-in-transaction', 'transação parada cortada pelo banco'),
    ('password authentication failed', 'usuário ou senha do banco recusados'),
    ('no pg_hba.conf entry', 'acesso ao banco recusado pela configuração do servidor'),
    ('too many connections', 'banco sem conexão livre'),
    ('remaining connection slots', 'banco sem conexão livre'),
    ('queuepool limit', 'pool sem conexão livre'),
    ('timeout expired', 'tempo esgotado'),
    ('timed out', 'tempo esgotado'),
    ('connection refused', 'conexão recusada'),
    ('could not translate host name', 'endereço do banco não encontrado'),
    ('server closed the connection', 'conexão caiu'),
    ('connection already closed', 'conexão caiu'),
    ('ssl', 'falha na conexão cifrada (TLS)'),
)

_URL_COM_CREDENCIAL = re.compile(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@]+@\S+')
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_TRECHO_DE_CONEXAO = re.compile(
    r'\b(server at|host|user|usu[aá]rio|database|banco|role|for user)\s+"[^"]*"',
    re.IGNORECASE)
LIMITE = 300


def _motivo(texto):
    baixo = texto.lower()
    for chave, motivo in _MOTIVOS:
        if chave in baixo:
            return motivo
    return None


def limpar(texto):
    """Apaga do texto URL com credencial, e-mail e host/usuário/banco."""
    texto = _URL_COM_CREDENCIAL.sub('<url omitida>', texto or '')
    texto = _EMAIL.sub('<e-mail omitido>', texto)
    return _TRECHO_DE_CONEXAO.sub(lambda m: f'{m.group(1)} "<omitido>"', texto)


def resumo(erro):
    """Uma linha sobre o erro que pode ir para o log sem dado de conexão nem
    dado pessoal."""
    nome = type(erro).__name__
    if isinstance(erro, sa_exc.SQLAlchemyError):
        partes = []
        orig = getattr(erro, 'orig', None)
        if orig is not None:
            partes.append(f'{type(orig).__module__.split(".")[0]} {type(orig).__name__}')
            codigo = getattr(orig, 'pgcode', None) or getattr(orig, 'sqlstate', None)
            if codigo:
                partes.append(f'SQLSTATE {codigo}')
        # A mensagem do driver só serve para escolher o motivo.
        motivo = _motivo(str(orig if orig is not None else erro))
        if motivo:
            partes.append(motivo)
        return f'{nome} ({", ".join(partes)})' if partes else nome
    primeira = (str(erro).splitlines() or [''])[0]
    primeira = limpar(primeira)[:LIMITE]
    return f'{nome}: {primeira}' if primeira else nome


def registrar_falha(logger, erro, mensagem, *args):
    """``logger.exception`` para erro do sistema; erro do banco vai como aviso
    com o ``resumo`` e SEM o rastro, porque o rastro repete a mensagem (host,
    usuário, consulta com os parâmetros). O SQLSTATE do resumo diz o tipo."""
    if isinstance(erro, sa_exc.SQLAlchemyError):
        logger.warning(mensagem + ': %s', *args, resumo(erro))
    else:
        logger.exception(mensagem, *args)
