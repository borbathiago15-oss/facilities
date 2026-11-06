"""Conexão com o banco: tamanho do pool e tempos limite (auditoria, Fase 3).

Sem nada disto o banco "pendurado" (a rede para no meio, o pooler trava)
segurava TODA requisição para sempre — inclusive o ``/healthz`` —, e o pool
esperava 30 s antes de desistir. Agora cada espera tem um teto curto e o
erro vira 503 com "tente de novo em instantes" (``core/erros.py``):

* ``pool_timeout`` 5 s: sem conexão livre no pool, desiste em 5 s;
* ``connect_timeout`` 5 s: o banco não atende o aperto de mão;
* ``keepalives*`` e ``tcp_user_timeout`` 15 s: a conexão aberta cujo outro
  lado sumiu é derrubada pelo sistema operacional em vez de esperar ~15 min;
* ``pool_recycle`` 300 s: o pooler/nuvem derruba conexão ociosa — o app
  troca antes; ``pool_pre_ping`` confere a conexão antes de usar.

Tudo isso são parâmetros do libpq (lado do cliente) ou o ``application_name``,
que o PgBouncer aceita. **Nunca** ``options=-c statement_timeout=...`` na URL:
o pooler em modo transação (Neon, Supabase) recusa a conexão. O tempo limite
de cada consulta fica no papel do banco (``ALTER ROLE ... SET``), passo manual
descrito em ``docs/BANCO_E_POOLER.md``.

Quem é quem (``processo()``): o site (gunicorn, ``flask run``, testes) usa a
URL do pooler (``DATABASE_URL``) e um pool do tamanho das threads; o
agendador e os comandos (``flask db upgrade``, ``anexos ...``) usam a URL
direta (``DIRECT_DATABASE_URL``, se existir) — transação longa e trava
consultiva não passam bem por pooler em modo transação.
"""
import os
import re
import sys

from sqlalchemy.engine import make_url

WEB = 'web'
AGENDADOR = 'agendador'
CLI = 'cli'
_PROCESSOS = (WEB, AGENDADOR, CLI)

# Threads de cada processo do gunicorn (docker-entrypoint.sh lê a mesma).
THREADS_PADRAO = 8


def _inteiro(nome, padrao, env=None, minimo=0):
    env = os.environ if env is None else env
    bruto = (env.get(nome) or '').strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        valor = minimo - 1
    if valor < minimo:
        raise RuntimeError(f'{nome}={bruto!r} inválido: use um número inteiro '
                           f'maior ou igual a {minimo}.')
    return valor


def processo(argv=None, env=None):
    """``web``, ``agendador`` ou ``cli`` — quem está abrindo o banco.

    ``FACILITIES_PROCESSO`` manda. Sem ela: comando ``flask ... agendador``
    é o agendador, outro comando ``flask`` (menos ``flask run``) é ``cli``,
    e o resto (gunicorn, pytest) é o site.
    """
    env = os.environ if env is None else env
    argv = sys.argv if argv is None else argv
    pedido = (env.get('FACILITIES_PROCESSO') or '').strip().lower()
    if pedido:
        if pedido not in _PROCESSOS:
            raise RuntimeError(f'FACILITIES_PROCESSO={pedido!r} inválido: use '
                               + ', '.join(_PROCESSOS) + '.')
        return pedido
    if not argv:
        return WEB
    exe = str(argv[0]).replace('\\', '/')
    nome = exe.rsplit('/', 1)[-1]
    eh_flask = nome in ('flask', 'flask.exe') or exe.endswith('flask/__main__.py')
    if not eh_flask:
        return WEB
    args = [a for a in argv[1:] if not a.startswith('-')]
    if 'agendador' in args:
        return AGENDADOR
    if 'run' in args:
        return WEB
    return CLI


def url_do_processo(proc, env=None):
    """A URL crua do ambiente: direta para agendador/comandos, se houver."""
    env = os.environ if env is None else env
    url = (env.get('DATABASE_URL') or '').strip()
    if proc != WEB:
        direta = (env.get('DIRECT_DATABASE_URL') or '').strip()
        if direta:
            return direta
    return url


def threads_do_web(env=None):
    return _inteiro('GUNICORN_THREADS', THREADS_PADRAO, env, minimo=1)


def opcoes_do_engine(uri, proc=WEB, env=None):
    """``SQLALCHEMY_ENGINE_OPTIONS`` para esta URL e este processo.

    SQLite (desenvolvimento e testes) fica como sempre: só o ``pre_ping``.
    Postgres ganha pool dimensionado e tempos limite; todos os números podem
    ser trocados por variável de ambiente (``DB_POOL_SIZE``,
    ``DB_MAX_OVERFLOW``, ``DB_POOL_TIMEOUT``, ``DB_POOL_RECYCLE``,
    ``DB_CONNECT_TIMEOUT``, ``DB_TCP_USER_TIMEOUT_MS``).
    """
    if make_url(uri).get_backend_name() != 'postgresql':
        return {'pool_pre_ping': True}
    # O site: uma conexão por thread (cada pedido segura a sua do começo ao
    # commit). Agendador e comandos são uma linha só: pool pequeno.
    pool_padrao = threads_do_web(env) if proc == WEB else 2
    return {
        'pool_pre_ping': True,
        'pool_size': _inteiro('DB_POOL_SIZE', pool_padrao, env, minimo=1),
        'max_overflow': _inteiro('DB_MAX_OVERFLOW', 2, env),
        'pool_timeout': _inteiro('DB_POOL_TIMEOUT', 5, env, minimo=1),
        'pool_recycle': _inteiro('DB_POOL_RECYCLE', 300, env, minimo=1),
        'connect_args': {
            'connect_timeout': _inteiro('DB_CONNECT_TIMEOUT', 5, env, minimo=1),
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 3,
            'tcp_user_timeout': _inteiro('DB_TCP_USER_TIMEOUT_MS', 15000, env, minimo=0),
            'application_name': f'facilities-{proc}',
        },
    }


# Agendador e comandos na URL DIRETA: limites maiores que os do papel do site
# (``ALTER ROLE ... SET statement_timeout = '15s'``, passo manual). A rodada
# do agendador é uma transação só — e espera o aviso no celular de cada
# aparelho com ela aberta —, e uma migração pode reescrever uma tabela: com
# os 15 s / 30 s do site as duas seriam cortadas no meio.
LIMITES_DAS_TAREFAS = (
    ('statement_timeout', 'DB_TAREFAS_STATEMENT_TIMEOUT', '5min'),
    ('lock_timeout', 'DB_TAREFAS_LOCK_TIMEOUT', '1min'),
    ('idle_in_transaction_session_timeout', 'DB_TAREFAS_IDLE_TIMEOUT', '10min'),
)
_DURACAO = re.compile(r'^\d+(ms|s|min|h)?$')


def limites_das_tarefas(proc, env=None):
    """Os ``SET`` da sessão do agendador e dos comandos — ou ``[]``.

    Só com ``DIRECT_DATABASE_URL`` definida: ``SET`` de sessão por um pooler
    em modo transação vazaria para a conexão de outra pessoa. Sem a URL
    direta, valem os limites do papel do banco para todo mundo."""
    env = os.environ if env is None else env
    if proc == WEB or not (env.get('DIRECT_DATABASE_URL') or '').strip():
        return []
    sets = []
    for parametro, variavel, padrao in LIMITES_DAS_TAREFAS:
        valor = (env.get(variavel) or '').strip() or padrao
        if not _DURACAO.match(valor):
            raise RuntimeError(f'{variavel}={valor!r} inválido: use um número com '
                               'ms, s, min ou h (ex.: 5min); 0 tira o limite.')
        sets.append(f"SET {parametro} = '{valor}'")
    return sets


def aplicar_limites_das_tarefas(engine, proc, env=None):
    """Cada conexão nova do agendador/comandos já nasce com os limites dela."""
    sets = limites_das_tarefas(proc, env)
    if not sets or engine.dialect.name != 'postgresql':
        return

    from sqlalchemy import event

    @event.listens_for(engine, 'connect')
    def _limites(dbapi_con, _registro):
        cur = dbapi_con.cursor()
        try:
            for comando in sets:
                cur.execute(comando)
        finally:
            cur.close()
        # psycopg2 abre transação no primeiro comando: sem o commit, o
        # rollback da devolução ao pool desfaria os SET.
        dbapi_con.commit()
