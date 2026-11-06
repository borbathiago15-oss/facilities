# Banco: conexões, tempos limite e pooler

O que o sistema faz sozinho, o que o dono precisa fazer **à mão** no painel
da hospedagem e como ligar um pooler (Neon, Supabase). Vem da auditoria de
carga (Fase 3, novembro de 2026): sem tempo limite nenhum, um banco
"pendurado" (a rede para no meio do caminho) segurava **todas** as telas,
inclusive o `/healthz`, enquanto durasse — e a pessoa via só "carregando".

## O que já vem no código (sem fazer nada)

| O quê | Valor | Variável para trocar |
|---|---|---|
| Processos do site (gunicorn) | 4 | `WEB_CONCURRENCY` |
| Threads por processo | 8 | `GUNICORN_THREADS` |
| Tempo limite do gunicorn / desligamento / keep-alive | 30 s / 25 s / 5 s | `GUNICORN_TIMEOUT`, `GUNICORN_GRACEFUL_TIMEOUT`, `GUNICORN_KEEPALIVE` |
| Conexões guardadas por processo (pool) | = threads (8) + 2 extras | `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` |
| Espera por conexão livre no pool | 5 s (era 30 s) | `DB_POOL_TIMEOUT` |
| Troca de conexão parada | a cada 300 s | `DB_POOL_RECYCLE` |
| Espera para o banco atender a conexão nova | 5 s (era sem limite) | `DB_CONNECT_TIMEOUT` |
| Conexão cujo outro lado sumiu | derrubada em ~15 s (era ~15 min) | `DB_TCP_USER_TIMEOUT_MS` |
| Nome da conexão no banco (`pg_stat_activity`) | `facilities-web`, `facilities-agendador`, `facilities-cli` | — |

Isso só vale para o Postgres; o SQLite de desenvolvimento e dos testes fica
como era (`facilities/core/banco.py`).

Quando o banco não responde a tempo, a pessoa recebe **503** com a frase
"O sistema está com dificuldade para falar com o banco. Tente de novo em
instantes." (e `Retry-After: 5`), em vez do 500 "algo deu errado". A fila
sem internet do aplicativo de campo entende o 503 como "tentar de novo
depois" e não perde o que estava guardado.

Sondas da hospedagem:

* `GET /healthz` — o processo está de pé? Não olha o banco nem a pessoa
  logada: responde mesmo com o banco fora. É o *Healthcheck Path* do Railway.
* `GET /readyz` — o processo fala com o banco? Faz `SELECT 1` com 2 s de
  limite (no máximo ~5 s se o pool estiver cheio): 200 pronto, 503 não.
  Use para monitoramento externo (UptimeRobot etc.) ou para o balanceador
  tirar a instância da rota. **Não** ponha o `/readyz` como *Healthcheck
  Path* do Railway: com o banco fora por uns minutos, o deploy seria
  recusado e o site antigo continuaria no ar sem as correções.

## Passo manual 1 — tempos limite no banco (`ALTER ROLE`)

O tempo limite de cada consulta fica **no papel (usuário) do banco**, não
no código nem na URL. Motivo: pooler em modo transação (Neon, Supabase)
**recusa** a conexão com `options=-c statement_timeout=...` na URL
(conferido na auditoria: `FATAL: unsupported startup parameter in options`).
O `ALTER ROLE ... SET` vale em qualquer caso, com ou sem pooler.

O sistema **não** roda isto sozinho (nem na migração, nem no boot): é uma
decisão do dono, num banco de cada vez. Rode uma vez, no editor SQL do painel
(Railway: *Postgres › Data › Query*; Neon/Supabase: *SQL Editor*), conectado
como administrador do banco. Troque `facilities_app` pelo usuário que está na
`DATABASE_URL` (o trecho entre `postgresql://` e `:`; no Railway costuma ser
`postgres`).

```sql
-- O site: nenhuma consulta passa de 15 s; ninguém fica com transação
-- aberta parada mais de 30 s; ninguém espera trava mais de 5 s.
ALTER ROLE facilities_app SET statement_timeout = '15s';
ALTER ROLE facilities_app SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE facilities_app SET lock_timeout = '5s';
```

Vale para as conexões **novas** (o site troca todas em até 5 minutos, ou
faça um *Redeploy*). Para conferir, numa conexão nova:

```sql
SHOW statement_timeout;                     -- 15s
SHOW idle_in_transaction_session_timeout;   -- 30s
SHOW lock_timeout;                          -- 5s
```

**O agendador e as migrações precisam de limites maiores.** A rodada do
agendador é uma transação só (com a trava consultiva) e espera o aviso no
celular de cada aparelho com ela aberta; uma migração pode reescrever uma
tabela inteira. Com 15 s / 30 s as duas seriam cortadas no meio (sem perder
dado — a transação volta atrás —, mas o trabalho não anda). Por isso:

* **Defina a `DIRECT_DATABASE_URL`** no `web` e no `agendador` (no Railway,
  sem pooler, pode ser a mesma: `DIRECT_DATABASE_URL=${{Postgres.DATABASE_URL}}`).
  Com ela, cada conexão do agendador e dos comandos `flask` (inclusive o
  `flask db upgrade` do boot) nasce com limites próprios, por cima dos do
  papel: `statement_timeout = 5min`, `lock_timeout = 1min`,
  `idle_in_transaction_session_timeout = 10min`
  (`DB_TAREFAS_STATEMENT_TIMEOUT`, `DB_TAREFAS_LOCK_TIMEOUT`,
  `DB_TAREFAS_IDLE_TIMEOUT` mudam; `0` tira o limite). Isso funciona com um
  usuário só no banco, como o Railway entrega.
  **Atenção:** a `DIRECT_DATABASE_URL` tem de ser a conexão direta com o
  Postgres (no Supabase, `db.<projeto>.supabase.co:5432`), nunca a do
  pooler: os limites vão como `SET` de sessão, e por um pooler em modo
  transação eles vazariam para a conexão de outra pessoa.
* **Sem a `DIRECT_DATABASE_URL`**, o agendador e as migrações ficam com os
  limites do papel (15 s / 5 s / 30 s). Nesse caso **não** rode o
  `ALTER ROLE` acima — ou rode só o `lock_timeout` e o `statement_timeout`,
  deixando o `idle_in_transaction_session_timeout` de fora.
* **Opcional — um papel separado** para o agendador e as migrações (quem
  quiser separar as permissões também). Ponha o novo usuário na
  `DIRECT_DATABASE_URL`:

  ```sql
  -- Troque a senha por uma sorteada e guarde no cofre; nunca no repositório.
  CREATE ROLE facilities_tarefas LOGIN PASSWORD '<senha-sorteada>' IN ROLE facilities_app;
  -- Tudo o que ele criar (tabelas de migração nova) fica do papel do site:
  ALTER ROLE facilities_tarefas SET role = 'facilities_app';
  ```

O agendador chamado pela rota HTTP (`AGENDADOR_TOKEN`, relógio externo)
roda dentro do site, com os limites do site: com o `ALTER ROLE` acima, prefira
o comando `flask --app facilities agendador rodar` (o serviço `agendador`).

**Ordem:** primeiro a `DIRECT_DATABASE_URL` no `web` e no `agendador` e um
deploy; depois o `ALTER ROLE`. Assim o agendador já nasce com os limites
dele quando os do site passarem a valer.

O `pg_dump` do serviço de backup não é afetado: ele desliga esses limites
sozinho no começo da cópia. No Railway o usuário do banco (`postgres`) é o
mesmo do editor SQL do painel: as consultas que você rodar lá também ficam
com 15 s de limite (para uma consulta longa de propósito, rode antes
`SET statement_timeout = 0;` na mesma janela).

Para desfazer: `ALTER ROLE facilities_app RESET statement_timeout;` (idem
para os outros dois).

Por que não há um `SET LOCAL statement_timeout` em cada transação pelo
código: custaria uma ida e volta a mais ao banco em **toda** transação (com o
banco a ~10 ms, isso pesa — a auditoria mostrou que as idas e voltas são o
gargalo), e o `ALTER ROLE` faz o mesmo de graça. O `/readyz` usa `SET LOCAL`
só para ele.

## Passo manual 2 — variáveis na hospedagem

No `web` (Railway: *web › Variables*):

```
WEB_CONCURRENCY=4
DIRECT_DATABASE_URL=${{Postgres.DATABASE_URL}}
```

No `agendador`, só a `DIRECT_DATABASE_URL` (a mesma linha). Com pooler, ela
é a URL direta (ver abaixo), não a mesma da `DATABASE_URL`.

(Se a `WEB_CONCURRENCY` já existe com `2`, troque para `4`; sem ela o padrão
já é 4.)
4 processos × 8 threads usam mais memória: acompanhe *Metrics › Memory* no
primeiro dia. Com pouca memória ou 1 vCPU, volte para `WEB_CONCURRENCY=2`.

Nada mais é obrigatório. As outras variáveis da tabela acima só se quiser
mudar os números.

## Pooler (Neon, Supabase)

Com um pooler em **modo transação** (PgBouncer do Neon ou o Supavisor do
Supabase na porta 6543), cada conexão do app é emprestada só durante a
transação. O sistema é compatível: driver psycopg2 (sem *prepared
statements* no servidor), sem `SET` de sessão, `LISTEN` ou tabela temporária,
e a trava do agendador é por transação (`pg_try_advisory_xact_lock`).

Duas URLs:

* `DATABASE_URL` = a URL **com pooler** ("pooled", "transaction") — o site.
* `DIRECT_DATABASE_URL` = a URL **direta**, sem pooler — usada pelo
  agendador e pelos comandos `flask` (inclusive o `flask db upgrade` que o
  site roda ao subir e os laços de anexos). A rodada do agendador é uma
  transação longa e a migração usa DDL; as duas vão melhor sem pooler.
  Sem `DIRECT_DATABASE_URL`, todo mundo usa a `DATABASE_URL` (como hoje).

Quem é "agendador" ou "comando" é descoberto pelo comando (`flask ...
agendador rodar` é o agendador; outro `flask ...` é comando; gunicorn e
`flask run` são o site). Para forçar: `FACILITIES_PROCESSO=web|agendador|cli`.

| Serviço | Variáveis |
|---|---|
| `web` | `DATABASE_URL=<pooled>`, `DIRECT_DATABASE_URL=<direta>` |
| `agendador` | `DATABASE_URL=<pooled>`, `DIRECT_DATABASE_URL=<direta>` |

**Tamanho do pool do pooler.** Cada pedido deste sistema segura uma conexão
do servidor do primeiro `SELECT` até o `commit` (inclusive enquanto monta a
tela e enquanto espera o aviso no celular ou a foto no R2). Por isso o pool
do pooler (`default_pool_size` no PgBouncer; *Pool Size* no painel do
Supabase) precisa ser pelo menos:

```
processos × threads × 2 + 5
```

O `× 2` cobre o deploy, quando a instância nova e a velha ficam de pé juntas
por um tempo; o `+ 5` é o agendador, os comandos e a folga. Com o padrão
(4 × 8): **4 × 8 × 2 + 5 = 69 → 70**. Com 2 × 4: 21 → 25. Pool menor que
isso vira o teto de pedidos ao mesmo tempo (medido: pool 20 com 4 × 8 e 300
pessoas, a ação passou de 3,0 s para 5,4 s).

Confira também o `max_connections` do banco (padrão 100): ele precisa caber o
pool do pooler + a URL direta + o backup.

Se um dia o driver mudar para psycopg 3, ponha `prepare_threshold=None` nas
opções de conexão (o pooler em modo transação não guarda *prepared
statements* entre transações).

## Como conferir que está valendo

No editor SQL do banco, com o site em uso:

```sql
SELECT application_name, state, count(*)
  FROM pg_stat_activity
 WHERE application_name LIKE 'facilities-%'
 GROUP BY 1, 2 ORDER BY 1, 2;
```

`facilities-web` deve aparecer com no máximo processos × (threads + 2)
conexões por instância; `facilities-agendador` só durante a rodada.
