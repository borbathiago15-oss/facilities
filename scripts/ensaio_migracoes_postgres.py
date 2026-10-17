"""Ensaio das migrações num Postgres de verdade: ida → volta → ida, com dados.

    python scripts/ensaio_migracoes_postgres.py postgresql://u:s@host/banco_test

O banco é ZERADO (precisa ter "test" no nome). O ensaio:

1. sobe todas as migrações;
2. semeia dado em todas as tabelas das fases novas (``SEMENTES``);
3. para cada migração, de trás para a frente: volta um passo e sobe de novo;
4. confere que a contagem de cada tabela e a "impressão digital" das linhas
   (todas as colunas, ordenadas) ficaram iguais — nada se perdeu nem mudou;
5. ``flask db check`` sem diferença.

Sai com código 1 e diz a tabela quando algo se perde.
"""
import hashlib
import os
import subprocess
import sys

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dado de exemplo, na ordem de dependência. Cada fase acrescenta o seu.
SEMENTES = [
    "INSERT INTO users (name,email,password_hash,role,is_active,is_deleted,all_clients,"
    "must_change_password,failed_login_count,session_epoch) VALUES "
    "('Gerente','gerente@ensaio','x','pleno',true,false,false,false,0,0)",
    "INSERT INTO clients (name,cost_center,is_active,is_deleted) VALUES "
    "('GL Armazém 1','GL-01',true,false)",
    "INSERT INTO empresas (nome,is_active) VALUES ('Trino Serviços',true)",
    "INSERT INTO contratantes (empresa_id,nome,centro_custo,gerente_id,is_active) "
    "SELECT e.id,'Grupo GL','GL',u.id,true FROM empresas e, users u "
    "WHERE u.email='gerente@ensaio'",
    "UPDATE estados SET is_active=true WHERE sigla IN ('BA','MG')",
    "UPDATE clients SET contratante_id=(SELECT id FROM contratantes), "
    "estado_id=(SELECT id FROM estados WHERE sigla='BA') WHERE name='GL Armazém 1'",
    "INSERT INTO setores (client_id,nome,is_active) SELECT id,'Administrativo',true "
    "FROM clients WHERE name='GL Armazém 1'",
    "INSERT INTO ambientes (setor_id,client_id,nome,is_active) "
    "SELECT s.id,s.client_id,'Banheiro 2º andar',true FROM setores s",
    "INSERT INTO equipamentos (ambiente_id,client_id,nome,is_active) "
    "SELECT a.id,a.client_id,'Secador',true FROM ambientes a",
    "INSERT INTO pontos_inspecao (ambiente_id,client_id,equipamento_id,nome,codigo_qr,"
    "is_active) SELECT a.id,a.client_id,e.id,'Porta','QR-ENSAIO-1',true "
    "FROM ambientes a, equipamentos e",
    "INSERT INTO cadastro_eventos (entidade,entidade_id,client_id,acao,depois_json,criado_em)"
    " SELECT 'ponto',p.id,p.client_id,'criado','{}',now() FROM pontos_inspecao p",
]


def _flask(*args, url):
    env = dict(os.environ, DATABASE_URL=url, SECRET_KEY=os.environ.get('SECRET_KEY', 'ensaio'),
               STORAGE_BACKEND='local', SESSION_COOKIE_SECURE='0')
    r = subprocess.run([sys.executable, '-m', 'flask', '--app', 'facilities', 'db', *args],
                       cwd=RAIZ, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'flask db {" ".join(args)} falhou:\n{r.stdout}\n{r.stderr}')
    return r.stdout + r.stderr


def _revisoes(url):
    saida = _flask('history', url=url)
    revs = []
    for linha in saida.splitlines():
        if '->' in linha:
            destino = linha.split('->', 1)[1].strip().split(' ', 1)[0].strip(',')
            revs.append(destino)
    return revs   # da mais nova para a mais velha


def _digitais(engine):
    insp = sa.inspect(engine)
    out = {}
    with engine.connect() as c:
        for t in sorted(insp.get_table_names()):
            if t.startswith('_quarentena_') or t == 'alembic_version':
                continue
            linhas = c.execute(sa.text(f'SELECT * FROM {t} ORDER BY 1')).fetchall()
            h = hashlib.sha256(repr([tuple(map(str, r)) for r in linhas]).encode()).hexdigest()
            out[t] = (len(linhas), h[:12])
    return out


def ensaiar(url, sementes=SEMENTES):
    nome = sa.engine.make_url(url).database or ''
    if 'test' not in nome.lower():
        raise SystemExit(f'O banco {nome!r} não tem "test" no nome: o ensaio o zera.')
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text('DROP SCHEMA public CASCADE'))
        c.execute(sa.text('CREATE SCHEMA public'))
    _flask('upgrade', url=url)
    with engine.begin() as c:
        for sql in sementes:
            c.execute(sa.text(sql))
    antes = _digitais(engine)
    revs = _revisoes(url)
    for i, rev in enumerate(revs[:-1]):            # a inicial não tem volta com dados
        anterior = revs[i + 1]
        _flask('downgrade', anterior, url=url)
        _flask('upgrade', url=url)
        depois = _digitais(engine)
        for t, v in antes.items():
            if depois.get(t) != v:
                raise SystemExit(f'Volta e ida de {rev}: a tabela {t} mudou '
                                 f'({v} → {depois.get(t)}).')
        print(f'ok: {rev} — volta e ida sem perder nada')
    saida = _flask('check', url=url)
    if 'No new upgrade operations detected' not in saida:
        raise SystemExit(f'flask db check acusou diferença:\n{saida}')
    print('ok: flask db check sem diferença')
    engine.dispose()
    return antes


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    ensaiar(sys.argv[1])
