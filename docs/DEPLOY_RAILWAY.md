# Publicar o Trino Facilities no Railway

Guia do primeiro deploy (decisão D2, 18/10/2026: Railway, plano Hobby, anexos
num volume do Railway). Tudo é feito no painel do Railway, a partir do
repositório do GitHub; nenhum segredo passa pelo repositório.

## O desenho

| Serviço | O que é | Como é configurado |
|---|---|---|
| **Postgres** | o banco (template do Railway, com volume próprio) | *Create › Database › PostgreSQL* |
| **web** | o site, o aplicativo de campo e o portal; migra o banco ao subir | repositório + `railway/web.json` (referência) + volume em `/data` |
| **agendador** | uma rodada a cada 5 minutos: tarefas do dia, perdidas, presença, preventivas, visitas, avisos de prazo | repositório + `railway/agendador.json` (Cron `*/5 * * * *`) |
| **backup** | cópia diária do banco (o plano Hobby não faz backup automático) | imagem `postgres` + Cron diário + volume em `/backup` |

Onde os dados ficam, e o que apaga:

* Banco: no volume do serviço **Postgres**. Deploy, reinício e troca de
  versão do app não tocam nele.
* Fotos e anexos: no volume do serviço **web**, montado em `/data`. Por isso o
  web roda com **1 réplica** (um volume só se liga a um serviço).
* Apagam dados: excluir o serviço Postgres ou o web, excluir um volume,
  "Wipe volume", excluir o projeto. Ninguém além do dono deve ter acesso de
  administrador ao projeto.

## Passo a passo

1. **Projeto:** railway.com › *New Project* › *Deploy from GitHub repo* ›
   `borbathiago15-oss/facilities`, branch `main`. Renomeie o serviço para
   `web`.
2. **Banco:** *Create › Database › PostgreSQL*. Mantenha o nome `Postgres`.
3. **Volume dos anexos:** no `web`, *Settings › Volumes › Add volume*, ponto de
   montagem `/data`.
4. **Variáveis do `web`** (*Variables › Raw Editor*):

   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SECRET_KEY=${{secret(64)}}
   STORAGE_BACKEND=local
   UPLOAD_FOLDER=/data/uploads
   RAILWAY_RUN_UID=0
   PROXY_HOPS=1
   WEB_CONCURRENCY=2
   CLIENTE_EXTERNO_LIBERADO=0
   ```

   * `${{secret(64)}}` faz o Railway sortear a chave uma vez e guardar. **Não
     troque depois**: trocar derruba todas as sessões (ninguém perde dado).
   * `RAILWAY_RUN_UID=0`: o volume do Railway é do usuário root; sem isso o
     app (que roda como usuário comum) não consegue gravar as fotos.
   * `CLIENTE_EXTERNO_LIBERADO=0` até o jurídico entregar os termos (Grupo C).
5. **Configuração do `web`:** *Settings › Deploy*: *Healthcheck Path*
   `/healthz`; *Replicas* 1. *Networking › Generate Domain* (endereço
   `…up.railway.app`; o domínio próprio pode vir depois em *Custom Domain*).
   Não precisa de *Pre-deploy Command*: a imagem migra o banco ao subir.
6. **Agendador:** *Create › GitHub Repo* › o mesmo repositório, nome
   `agendador`. Em *Variables*, só:

   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SECRET_KEY=${{web.SECRET_KEY}}
   STORAGE_BACKEND=local
   ```

   Em *Settings › Deploy*: *Custom Start Command*
   `flask --app facilities agendador rodar` e *Cron Schedule* `*/5 * * * *`.
   Sem volume e sem domínio. (Ele só mexe no banco; rodar duas vezes não
   duplica nada.)
7. **Primeiro administrador:** com a CLI do Railway na sua máquina
   (`npm i -g @railway/cli`, `railway login`, `railway link`):

   ```
   railway ssh --service web
   flask --app facilities criar-admin --email voce@grupotrino.com.br --nome "Seu nome"
   ```

   A senha temporária aparece só no seu terminal; o sistema pede a troca no
   primeiro login. Depois ative a segunda etapa em *Segurança da conta*.
8. **Avisos no celular (opcional, recomendado):** no mesmo `railway ssh`,
   `flask --app facilities push chaves` e cole as três linhas
   (`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`) nas variáveis do
   `web` **e** do `agendador`. Sem elas, os avisos ficam só no sino.
9. **Backup diário:** *Create › Docker Image* › `postgres:17` (use a MESMA
   versão principal do Postgres do projeto, ou maior — veja em *Postgres ›
   Settings*). Nome `backup`. Volume em `/backup`. Variável
   `DATABASE_URL=${{Postgres.DATABASE_URL}}`. *Cron Schedule* `30 6 * * *`
   (03:30 em Brasília) e *Custom Start Command*:

   ```
   sh -c 'pg_dump "$DATABASE_URL" -Fc -f /backup/facilities-$(date +%F).dump && find /backup -name "*.dump" -mtime +14 -delete && ls -lh /backup'
   ```

   Ficam as cópias dos últimos 14 dias. **Atenção:** elas estão no mesmo
   Railway; uma vez por mês, baixe a mais recente para fora
   (`railway ssh --service backup` e `cat /backup/<arquivo> > ...`, ou
   *Volume › Download*, se o painel oferecer) e guarde no drive da empresa.
   Restaurar: `pg_restore --clean --no-owner -d "$DATABASE_URL" arquivo.dump`.
10. **Conferir:**
    * abrir o domínio → tela de login;
    * entrar com o administrador, trocar a senha, ativar a segunda etapa;
    * cadastrar empresa, cliente, local e um ponto; abrir um chamado com foto;
      fazer um deploy de novo (*Redeploy*) e conferir que a foto continua lá;
    * em *agendador › Deployments*, ver uma rodada a cada 5 minutos com
      "N tarefa(s) gerada(s)".

## Antes do piloto (decisões que não são de infraestrutura)

* **Presença aleatória (D48):** toda rota nasce com 2 confirmações por turno.
  Até RH e jurídico validarem e os colaboradores serem avisados, deixe
  **0** em cada rota (desliga).
* **Portal do cliente:** `CLIENTE_EXTERNO_LIBERADO=0` até os termos.
* **Nome de quem fez o checklist no portal:** interruptor do cliente
  desligado (padrão) até a D25.

## Atualizar

Cada merge no `main` faz o Railway publicar de novo o `web` e o `agendador`.
O `web` aplica as migrações ao subir (`docker-entrypoint.sh`); o banco e as
fotos continuam nos volumes. Migração nova só entra com o ok do dono (regra do
repositório).

## Custo

Plano Hobby: assinatura mínima mensal + uso. Quatro serviços, dois deles
(agendador e backup) só existem durante a rodada. Acompanhe *Usage* nas
primeiras semanas.
