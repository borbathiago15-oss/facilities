"""Gerador de carga da auditoria (Fase 3): N pessoas logadas, cada uma com o
SEU login, fazendo a mistura real de tarefas com ~15 s entre uma ação e outra.

    python scripts/auditoria/carga.py --base http://127.0.0.1:8080 --usuarios 100 \
        --duracao 120 --contas contas.json --saida resultado.json [--pg DSN]

Só para o servidor LOCAL com o banco semeado por ``semear_carga.py``. Precisa
de ``httpx`` (e ``psycopg2`` para amostrar o ``pg_stat_activity``) — num venv
à parte, não no do projeto.

Mistura (por perfil):
  encarregado: início do app, "Meu turno" (gera as tarefas do dia), checklist
               com foto, rascunho da passagem, abrir chamado com foto, lista;
  técnico:     início do app, lista de chamados, comentar chamado, checklist;
  supervisor:  painel da passagem, lista de chamados, comentar, painel;
  gestão:      painel, chamados (todos), relatórios, painel da passagem.
Cada ação conta o tempo de TODOS os pedidos dela (o que a pessoa espera).
"""
import argparse
import asyncio
import json
import os
import random
import re
import statistics
import threading
import time
import uuid
from datetime import date, datetime, timezone

import httpx

MISTURA = {'encarregado': 0.66, 'tecnico': 0.24, 'supervisor': 0.06, 'gestao': 0.04}
CSRF_FORM = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
FOTO_ARQ = os.environ.get('CARGA_FOTO', '/tmp/claude-0/f3/foto.jpg')
FOTO = open(FOTO_ARQ, 'rb').read() if os.path.exists(FOTO_ARQ) else b''
COOKIES = '/tmp/claude-0/f3/cookies.json'


class Medidas:
    def __init__(self):
        self.pedidos = []    # (t, nome, ms, status)
        self.acoes = []      # (t, nome, ms, ok)
        self.inicio = None

    def pedido(self, nome, ms, status):
        self.pedidos.append((time.time(), nome, ms, status))

    def acao(self, nome, ms, ok):
        self.acoes.append((time.time(), nome, ms, ok))


def pct(v, p):
    if not v:
        return None
    v = sorted(v)
    k = max(0, min(len(v) - 1, int(round(p / 100 * (len(v) - 1)))))
    return round(v[k], 1)


class Pessoa:
    def __init__(self, conta, base, med, timeout, dados):
        self.c = conta
        self.med = med
        self.dados = dados
        self.cli = httpx.AsyncClient(base_url=base, timeout=timeout, follow_redirects=False,
                                     limits=httpx.Limits(max_connections=2))
        self.csrf = None
        self.local = conta['locais'][0] if conta['locais'] else int(
            random.choice(list(dados['qrs'])))

    async def req(self, nome, metodo, url, **kw):
        h = kw.pop('headers', {})
        if self.csrf and metodo != 'GET':
            h['X-CSRFToken'] = self.csrf
        t0 = time.perf_counter()
        try:
            r = await self.cli.request(metodo, url, headers=h, **kw)
            st = r.status_code
        except httpx.TimeoutException:
            r, st = None, 'timeout'
        except httpx.HTTPError as e:
            r, st = None, type(e).__name__
        self.med.pedido(nome, (time.perf_counter() - t0) * 1000, st)
        return r

    async def entrar(self, cache):
        if self.c['email'] in cache:
            for k, v in cache[self.c['email']].items():
                self.cli.cookies.set(k, v)
        else:
            r = await self.req('login_get', 'GET', '/login')
            m = CSRF_FORM.search(r.text) if r is not None else None
            r = await self.req('login_post', 'POST', '/login',
                               data={'email': self.c['email'], 'password': self.dados['senha'],
                                     'csrf_token': m.group(1) if m else ''})
            if r is None or r.status_code != 302:
                return False
        r = await self.req('eu', 'GET', '/api/v1/eu')
        if r is None or r.status_code != 200:
            cache.pop(self.c['email'], None)
            return False
        self.csrf = r.json()['csrf']
        cache[self.c['email']] = dict(self.cli.cookies)
        return True

    # ── ações ──
    async def inicio_app(self):
        r = await self.req('app_inicio', 'GET', '/app/')
        return r is not None and r.status_code == 200

    async def meu_turno(self):
        r = await self.req('app_turno', 'GET', '/app/turno')
        return r is not None and r.status_code == 200

    async def checklist(self):
        r = await self.req('app_api_turno', 'GET', f'/app/api/turno?local={self.local}')
        if r is None or r.status_code != 200:
            return False
        tarefas = [t for t in r.json()['tarefas'] if t['status'] == 'prevista']
        agora = datetime.now(timezone.utc).isoformat()
        corpo = {'envio_id': uuid.uuid4().hex,
                 'respostas': {'piso_limpo': 'sim', 'lixo_retirado': 'sim'},
                 'lido_em': agora, 'concluida_em': agora}
        if tarefas:
            t = random.choice(tarefas)
            corpo.update(ponto=t['ponto'], tarefa_id=t['id'])
        else:            # técnico (sem escala) ou rota toda feita: atividade extra
            corpo.update(ponto=random.choice(self.dados['qrs'][str(self.local)]),
                         modelo_id=self.dados['modelos'].get(str(self.local)))
        r = await self.req('app_execucao', 'POST', '/app/api/execucoes',
                           data={'corpo': json.dumps(corpo)},
                           files={'depois': ('depois.jpg', FOTO, 'image/jpeg')})
        return r is not None and r.status_code in (200, 201)

    async def passagem_rascunho(self):
        r = await self.req('passagem_form', 'GET', f'/passagem-de-turno/turno?client_id={self.local}')
        if r is None or r.status_code != 200:
            return False
        corpo = {'client_id': self.local, 'configuracao_id': self.dados['cfgs'][str(self.local)],
                 'data_turno': date.today().isoformat(), 'turno': f'Rascunho {self.c["id"]}',
                 'dados': {'banheiros': 'ok'}, 'observacao': 'Tudo em ordem.',
                 'pendencias': [{'titulo': f'Repor papel {random.randint(1, 5)}'}]}
        r = await self.req('passagem_salvar', 'POST', '/passagem-de-turno/api/turnos', json=corpo)
        return r is not None and r.status_code in (200, 201)

    async def abrir_chamado(self):
        r = await self.req('chamado_novo', 'GET', f'/chamados/novo?client_id={self.local}')
        if r is None or r.status_code != 200:
            return False
        r = await self.req('chamado_abrir', 'POST', '/chamados/', data={
            'client_id': str(self.local), 'titulo': f'Carga {uuid.uuid4().hex[:8]}',
            'descricao': 'Lâmpada queimada no corredor', 'categoria': 'eletrica',
            'prioridade': 'media'}, files={'arquivo': ('foto.jpg', FOTO, 'image/jpeg')})
        return r is not None and r.status_code == 302 and '/login' not in r.headers.get(
            'location', '')

    async def lista_chamados(self, visao='abertos'):
        r = await self.req(f'chamados_{visao}', 'GET', f'/chamados/?visao={visao}')
        return r is not None and r.status_code == 200

    async def comentar(self):
        ids = self.dados['chamados'].get(str(self.local)) or []
        if not ids:
            return await self.lista_chamados()
        cid = random.choice(ids)
        r = await self.req('chamado_ver', 'GET', f'/chamados/{cid}')
        if r is None or r.status_code != 200:
            return False
        r = await self.req('chamado_comentar', 'POST', f'/chamados/{cid}/acao',
                           data={'acao': 'comentar', 'texto': f'Visto {uuid.uuid4().hex[:6]}'})
        return r is not None and r.status_code == 302

    async def painel_passagem(self):
        r = await self.req('passagem_painel', 'GET', '/passagem-de-turno/')
        return r is not None and r.status_code == 200

    async def painel(self):
        r = await self.req('painel', 'GET', '/painel')
        return r is not None and r.status_code == 200

    async def relatorios(self):
        r = await self.req('relatorios', 'GET', '/relatorios/')
        return r is not None and r.status_code == 200

    def escolher(self):
        p = self.c['grupo']
        tabela = {
            'encarregado': [(self.inicio_app, 25), (self.meu_turno, 20), (self.checklist, 25),
                            (self.passagem_rascunho, 12), (self.abrir_chamado, 6),
                            (self.lista_chamados, 7), (self.comentar, 5)],
            'tecnico': [(self.inicio_app, 25), (self.lista_chamados, 25), (self.comentar, 25),
                        (self.checklist, 25)],
            'supervisor': [(self.painel_passagem, 30), (self.lista_chamados, 25),
                           (self.comentar, 15), (self.painel, 30)],
            'gestao': [(self.painel, 30), (lambda: self.lista_chamados('todos'), 25),
                       (self.relatorios, 20), (self.painel_passagem, 25)],
        }[p]
        fs, ps = zip(*tabela)
        return random.choices(fs, ps)[0]

    async def viver(self, fim, think):
        await asyncio.sleep(random.uniform(0, think))
        while time.time() < fim:
            f = self.escolher()
            nome = getattr(f, '__name__', 'acao')
            t0 = time.perf_counter()
            try:
                ok = await f()
            except Exception:              # noqa: BLE001
                ok = False
            self.med.acao(nome, (time.perf_counter() - t0) * 1000, ok)
            await asyncio.sleep(random.uniform(0.5, 1.5) * think)


def amostrar_pg(dsn, parar, saida):
    import psycopg2
    con = psycopg2.connect(dsn)
    con.autocommit = True
    cur = con.cursor()
    while not parar.is_set():
        try:
            cur.execute("select coalesce(state,'?'), count(*) from pg_stat_activity "
                        "where datname = 'f3_carga' and backend_type = 'client backend' "
                        "and pid <> pg_backend_pid() group by 1")
            d = dict(cur.fetchall())
            cur.execute("select count(*) from pg_stat_activity where datname='f3_carga' "
                        "and wait_event_type = 'Lock'")
            d['espera_lock'] = cur.fetchone()[0]
            saida.append((time.time(), d))
        except Exception as e:          # noqa: BLE001
            saida.append((time.time(), {'erro': str(e)[:80]}))
            try:
                con = psycopg2.connect(dsn, connect_timeout=2)
                con.autocommit = True
                cur = con.cursor()
            except Exception:           # noqa: BLE001
                pass
        parar.wait(1)


def amostrar_cpu(parar, saida):
    def ler():
        with open('/proc/stat') as f:
            return {ln.split()[0]: list(map(int, ln.split()[1:])) for ln in f
                    if ln.startswith('cpu')}
    a = ler()
    while not parar.wait(2):
        b = ler()
        uso = {}
        for k in b:
            d = [y - x for x, y in zip(a[k], b[k])]
            tot = sum(d) or 1
            uso[k] = {'ocupado': round(100 * (tot - d[3] - d[4]) / tot, 1),
                      'iowait': round(100 * d[4] / tot, 1)}
        saida.append((time.time(), uso))
        a = b


def montar_pessoas(dados, n):
    grupos = {'encarregado': [], 'tecnico': [], 'supervisor': [], 'gestao': []}
    for c in dados['contas']:
        g = c['papel'] if c['papel'] in grupos else 'gestao'
        grupos[g].append(dict(c, grupo=g))
    escolhidas = []
    for g, fr in MISTURA.items():
        k = max(1, round(n * fr))
        escolhidas += grupos[g][:k]
    random.shuffle(escolhidas)
    return escolhidas[:n]


def chamados_abertos(dsn):
    import psycopg2
    con = psycopg2.connect(dsn)
    cur = con.cursor()
    cur.execute("select client_id, id from chamados where status in "
                "('aberto','em_atendimento','aguardando') order by id desc")
    out = {}
    for cid, i in cur.fetchall():
        out.setdefault(str(cid), [])
        if len(out[str(cid)]) < 40:
            out[str(cid)].append(i)
    cur.execute('select client_id, min(id) from checklist_modelos group by 1')
    modelos = {str(c): i for c, i in cur.fetchall()}
    con.close()
    return out, modelos


def _agrupar(linhas):
    g = {}
    for x in linhas:
        g.setdefault(x[1], []).append(x)
    return g


def resumir(med, desde, ate):
    ped = [p for p in med.pedidos if desde <= p[0] <= ate]
    ac = [a for a in med.acoes if desde <= a[0] <= ate]
    dur = max(1e-9, ate - desde)
    lat = [p[2] for p in ped]
    erros = [p for p in ped if not (isinstance(p[3], int) and p[3] < 500)]
    por_nome = {}
    for p in ped:
        por_nome.setdefault(p[1], []).append(p)
    alat = [a[2] for a in ac]
    return {
        'pedidos': len(ped), 'req_s': round(len(ped) / dur, 1),
        'p50': pct(lat, 50), 'p95': pct(lat, 95), 'p99': pct(lat, 99),
        'max': round(max(lat), 1) if lat else None,
        'erros': len(erros), 'taxa_erro_pct': round(100 * len(erros) / max(1, len(ped)), 2),
        'tipos_erro': {str(k): sum(1 for e in erros if e[3] == k)
                       for k in {e[3] for e in erros}},
        'acoes': len(ac), 'acoes_s': round(len(ac) / dur, 2),
        'acao_p50': pct(alat, 50), 'acao_p95': pct(alat, 95), 'acao_p99': pct(alat, 99),
        'acoes_falhas': sum(1 for a in ac if not a[3]),
        'por_acao': {k: {'n': len(v), 'p95': pct([x[2] for x in v], 95),
                         'falhas': sum(1 for x in v if not x[3])}
                     for k, v in sorted(_agrupar(ac).items())},
        'por_rota': {k: {'n': len(v), 'p50': pct([x[2] for x in v], 50),
                         'p95': pct([x[2] for x in v], 95),
                         'erros': sum(1 for x in v if not (isinstance(x[3], int) and x[3] < 500))}
                     for k, v in sorted(por_nome.items())},
    }


async def principal(a):
    dados = json.load(open(a.contas))
    dados['chamados'], dados['modelos'] = chamados_abertos(a.pg) if a.pg else ({}, {})
    pessoas_c = montar_pessoas(dados, a.usuarios)
    med = Medidas()
    cache = {}
    if os.path.exists(COOKIES) and not a.sem_cache:
        cache = json.load(open(COOKIES))
    pessoas = [Pessoa(c, a.base, med, a.timeout, dados) for c in pessoas_c]
    sem = asyncio.Semaphore(16)

    async def entrar(p):
        async with sem:
            return await p.entrar(cache)
    t0 = time.time()
    oks = await asyncio.gather(*[entrar(p) for p in pessoas])
    json.dump(cache, open(COOKIES, 'w'))
    login_s = time.time() - t0
    vivos = [p for p, ok in zip(pessoas, oks) if ok]
    print(f'logados {len(vivos)}/{len(pessoas)} em {login_s:.1f}s', flush=True)
    parar = threading.Event()
    pg, cpu = [], []
    th = []
    if a.pg:
        th.append(threading.Thread(target=amostrar_pg, args=(a.pg, parar, pg), daemon=True))
    th.append(threading.Thread(target=amostrar_cpu, args=(parar, cpu), daemon=True))
    for t in th:
        t.start()
    med.pedidos.clear()
    med.acoes.clear()
    inicio = time.time()
    fim = inicio + a.duracao
    await asyncio.gather(*[p.viver(fim, a.think) for p in vivos])
    parar.set()
    for p in vivos:
        await p.cli.aclose()
    aquec = min(a.think, a.duracao / 4)
    res = {'usuarios': a.usuarios, 'logados': len(vivos), 'duracao': a.duracao,
           'rotulo': a.rotulo, 'login_s': round(login_s, 1),
           'janela': resumir(med, inicio + aquec, fim),
           'por_10s': [dict(t=round(s - inicio), **{k: v for k, v in resumir(
               med, s, s + 10).items() if k in ('req_s', 'p50', 'p95', 'erros')})
               for s in range(int(inicio), int(fim) + 30, 10)],
           'pg': {'max_' + k: max((d.get(k, 0) for _, d in pg), default=0)
                  for k in ('active', 'idle', 'idle in transaction', 'espera_lock')},
           'pg_total_max': max((sum(v for k, v in d.items() if k not in ('espera_lock', 'erro'))
                                for _, d in pg), default=0),
           'cpu_media': {k: round(statistics.mean(u[k]['ocupado'] for _, u in cpu), 1)
                         for k in (cpu[0][1] if cpu else {})},
           'iowait_media': round(statistics.mean(u['cpu']['iowait'] for _, u in cpu), 1)
           if cpu else None,
           'pg_serie': [(round(t - inicio), d) for t, d in pg]}
    if a.saida:
        json.dump(res, open(a.saida, 'w'), indent=1, default=str)
    j = res['janela']
    print(json.dumps({k: j[k] for k in ('req_s', 'p50', 'p95', 'p99', 'taxa_erro_pct',
                                        'tipos_erro', 'acao_p95', 'acoes_falhas')}),
          res['pg'], res['pg_total_max'], res['cpu_media'], flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8080')
    ap.add_argument('--usuarios', type=int, default=10)
    ap.add_argument('--duracao', type=float, default=90)
    ap.add_argument('--think', type=float, default=15)
    ap.add_argument('--timeout', type=float, default=60)
    ap.add_argument('--contas', default='/tmp/claude-0/f3/contas.json')
    ap.add_argument('--saida')
    ap.add_argument('--pg', default='dbname=f3_carga user=fac password=fac host=127.0.0.1 port=5432')
    ap.add_argument('--rotulo', default='')
    ap.add_argument('--sem-cache', action='store_true')
    asyncio.run(principal(ap.parse_args()))
