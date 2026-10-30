# Publicar o Trino Facilities no Railway

Guia do primeiro deploy (decisão D2, 18/10/2026: Railway, plano Hobby, anexos
num volume do Railway). **O Railway é o ambiente de TESTES e de
aperfeiçoamento**; a produção virá depois, com o banco migrado (ver "Migrar
para a produção", no fim). Tudo é feito no painel do Railway, a partir do
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
3b. **Redis:** *Create › Database › Redis*. Mantenha o nome `Redis`. É só
   para os limites de acesso; não guarda dado da operação.
4. **Variáveis do `web`** (*Variables › Raw Editor*):

   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SECRET_KEY=${{secret(64)}}
   FIELD_ENCRYPTION_KEY=<a chave gerada abaixo>
   STORAGE_BACKEND=local
   UPLOAD_FOLDER=/data/uploads
   RATELIMIT_STORAGE_URI=${{Redis.REDIS_URL}}
   PROXY_HOPS=1
   WEB_CONCURRENCY=2
   CLIENTE_EXTERNO_LIBERADO=0
   ```

   * `${{secret(64)}}` faz o Railway sortear a chave uma vez e guardar. **Não
     troque depois**: trocar derruba todas as sessões (ninguém perde dado).
   * `FIELD_ENCRYPTION_KEY` cifra no banco e-mails, telefones, endereços, o
     segredo da segunda etapa e as chaves do aviso no celular
     (`docs/SEGURANCA_DADOS.md`). **Sem ela o site não sobe.** Ela NÃO pode
     ser `${{secret(...)}}` (o formato é próprio): gere com
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
     (ou `flask --app facilities chaves gerar`). **Antes de colar no
     Railway, guarde uma cópia no cofre offline** (1Password/Bitwarden do
     dono, ou envelope lacrado no cofre): perder a chave é perder esses
     dados — nem o backup os devolve. Não troque à toa; para trocar, siga o
     rodízio do `docs/SEGURANCA_DADOS.md`.
   * **Não** defina `RAILWAY_RUN_UID`. O contêiner começa como root só para
     acertar o dono do volume e larga o privilégio sozinho
     (`docker-entrypoint.sh`); o app nunca roda como root e o código fica só
     leitura (auditoria SEC-008).
   * `RATELIMIT_STORAGE_URI`: os limites de acesso (login, código, QR
     público, API) precisam de um lugar comum aos workers; sem Redis cada
     limite vale `WEB_CONCURRENCY` vezes e zera a cada deploy. Crie o Redis
     no passo 3b. Enquanto ele não existir, o site sobe com um aviso no log;
     com `RATELIMIT_EXIGIR_COMPARTILHADO=1` ele se recusa a subir sem Redis.
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
   FIELD_ENCRYPTION_KEY=${{web.FIELD_ENCRYPTION_KEY}}
   STORAGE_BACKEND=local
   ```

   Em *Settings › Deploy*: *Custom Start Command*
   `flask --app facilities agendador rodar` e *Cron Schedule* `*/5 * * * *`.
   Sem volume e sem domínio. (Ele só mexe no banco; rodar duas vezes não
   duplica nada.)
7. **Primeiro administrador (sem terminal):** nas variáveis do `web`, acrescente

   ```
   ADMIN_INICIAL_EMAIL=voce@grupotrino.com.br
   ADMIN_INICIAL_NOME=Seu nome
   ```

   e faça o deploy. Ao subir, o site cria o administrador **só se ainda não
   houver nenhum ativo** (a variável pode ficar; depois do primeiro, ela não
   faz nada). A senha temporária aparece **uma vez** no *Deploy Log*, na
   linha `admin-inicial: administrador ... Senha temporária: ...`. Se
   preferir não ver a senha no log, defina também `ADMIN_INICIAL_SENHA` (8+
   caracteres) — ela vale só para o primeiro login.

   No primeiro login o sistema pede a troca da senha e, em seguida, leva à
   tela *Segurança da conta*: a segunda etapa (código do aplicativo
   autenticador — Google Authenticator, Microsoft Authenticator ou similar)
   é **obrigatória** para administrador, gerente, coordenador e diretoria;
   sem ela nenhuma outra tela abre. Tenha o aplicativo instalado no celular
   antes do primeiro acesso. Depois, apague `ADMIN_INICIAL_SENHA` se tiver
   usado.

   Alternativa com terminal (`railway ssh --service web`):
   `flask --app facilities criar-admin --email ... --nome "..."` — também
   serve para gerar uma senha nova quando o administrador perder a dele.
8. **Avisos no celular (opcional, recomendado):** no mesmo `railway ssh`,
   `flask --app facilities push chaves` e cole as três linhas
   (`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`) nas variáveis do
   `web` **e** do `agendador` (volte ao passo 6 e acrescente lá também: é o
   agendador que manda o aviso da hora da tarefa). Sem elas, o aviso da
   tarefa não chega por canal nenhum; os demais ficam no sino.
8b. **Biblioteca de checklists e rotas prontas:** entre como administrador,
   abra *Cadastros › Biblioteca de checklists* e clique **Instalar na
   biblioteca** (ou `flask --app facilities semear-checklists` no
   `railway ssh`). Sem isso a biblioteca nasce vazia e "Usar uma rota
   pronta" não tem o que oferecer.
9. **Backup diário:** *Create › Docker Image* › `postgres:17` (use a MESMA
   versão principal do Postgres do projeto, ou maior — veja em *Postgres ›
   Settings*). Nome `backup`. Volume em `/backup`. Variáveis
   `DATABASE_URL=${{Postgres.DATABASE_URL}}` e `BACKUP_SENHA=${{secret(48)}}`
   (**copie a senha gerada para o cofre offline**, junto com a
   `FIELD_ENCRYPTION_KEY`). *Cron Schedule* `30 6 * * *` (03:30 em Brasília)
   e *Custom Start Command*:

   ```
   sh -c 'set -e; : "${BACKUP_SENHA:?defina BACKUP_SENHA}"; umask 077; d=/tmp/facilities.dump; pg_dump "$DATABASE_URL" -Fc -f "$d"; printf %s "$BACKUP_SENHA" > /tmp/senha; gpg --batch --yes --pinentry-mode loopback --passphrase-file /tmp/senha --symmetric --cipher-algo AES256 -o /backup/facilities-$(date +%F).dump.gpg "$d"; rm -f "$d" /tmp/senha; find /backup -name "*.dump.gpg" -mtime +14 -delete; ls -lh /backup'
   ```

   O arquivo sai **cifrado** (AES-256, `gpg`, que já vem na imagem do
   Postgres): quem baixar o volume ou o arquivo não lê nada sem a
   `BACKUP_SENHA`. E, dentro dele, os campos sensíveis continuam cifrados
   pela `FIELD_ENCRYPTION_KEY` — para restaurar e usar, são as DUAS.
   Ficam as cópias dos últimos 14 dias. Os `*.dump` antigos (de antes da
   cifra) estão abertos: depois do primeiro `.dump.gpg` conferido, apague-os
   (`railway ssh --service backup` e `rm /backup/*.dump`). **Atenção:** as
   cópias estão no mesmo Railway; uma vez por mês, baixe a mais recente
   para fora (`railway ssh --service backup` e `cat /backup/<arquivo> > ...`,
   ou *Volume › Download*, se o painel oferecer) e guarde no drive da empresa.
   Restaurar:
   `gpg --batch --pinentry-mode loopback --passphrase-file senha.txt -d arquivo.dump.gpg > arquivo.dump`
   e `pg_restore --clean --no-owner -d "$DATABASE_URL" arquivo.dump` (o app
   que ler esse banco precisa da MESMA `FIELD_ENCRYPTION_KEY`).
9b. **Backup das fotos e documentos.** O `pg_dump` **não** leva os anexos:
   eles estão no volume `/data/uploads`, que só o `web` enxerga. Perder o
   volume perde todas as fotos. Duas saídas, da melhor para a mais simples:
   * **Recomendado para produção:** guardar os anexos direto no Cloudflare R2
     em vez do volume (`STORAGE_BACKEND=r2` + `R2_ENDPOINT`,
     `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`). O bucket fica
     fora do Railway, com versionamento ligado no painel da Cloudflare.
   * **Com o volume:** mantenha `STORAGE_BACKEND=local` e acrescente nas
     variáveis do `web` as quatro `R2_*` de um bucket de cópia **e**
     `ANEXOS_ESPELHO_R2=1`. Uma vez por dia o próprio `web` copia para o
     bucket o que ainda não está lá (`flask anexos espelhar`; o intervalo é
     `ANEXOS_ESPELHO_INTERVALO`, em segundos). Para forçar agora:
     `railway ssh --service web` e `flask --app facilities anexos espelhar`.
   Restaurar os anexos: copiar a árvore do bucket de volta para
   `/data/uploads` (ou trocar para `STORAGE_BACKEND=r2`, que lê do bucket).
9c. **E-mail dos convites (opcional).** O assistente "Novo contrato"
   convida as pessoas por link. Sem servidor de e-mail, a tela abre o
   WhatsApp ou o e-mail do próprio aparelho com o texto pronto — funciona
   sem configurar nada. Para o convite sair sozinho por e-mail, acrescente
   no `web`: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USUARIO`, `SMTP_SENHA` e
   `SMTP_REMETENTE` (ex.: `Trino Facilities <nao-responda@grupotrino.com.br>`);
   `SMTP_SSL=1` se o provedor usar a porta 465.
10. **Conferir:**
    * abrir o domínio → tela de login;
    * entrar com o administrador, trocar a senha, ativar a segunda etapa;
    * cadastrar empresa, cliente, local e um ponto; abrir um chamado com foto;
      fazer um deploy de novo (*Redeploy*) e conferir que a foto continua lá;
    * em *agendador › Deployments*, ver uma rodada a cada 5 minutos com
      "N tarefa(s) gerada(s)".

## Enquanto for ambiente de testes

* Use dados de teste ou de um local piloto. Cadastrar colaboradores reais
  (nome, presença, fotos) já é tratamento de dado pessoal (LGPD): avise as
  pessoas antes.
* A presença aleatória pode ficar ligada numa rota de teste, para ver o fluxo;
  nas rotas com gente de verdade, siga a regra abaixo.
* O backup diário custa quase nada e protege o que for testado; mantenha.

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

## Migrar para a produção (depois)

O sistema não depende do Railway: é a mesma imagem Docker, um Postgres e a
pasta dos anexos. Para levar o que foi feito nos testes para a produção:

1. **Congelar:** avisar os usuários e parar o `web` e o `agendador` no
   Railway (ninguém grava durante a cópia).
2. **Banco:** `pg_dump "$DATABASE_URL" -Fc -f facilities.dump` (o próprio
   serviço `backup` já gera esse arquivo) e, no destino,
   `pg_restore --no-owner -d "$NOVO_DATABASE_URL" facilities.dump`. O
   Postgres do destino precisa ser da MESMA versão principal ou mais nova. A
   versão das migrações vai junto (tabela `alembic_version`): ao subir, o app
   só aplica o que faltar.
3. **Anexos:** copiar a pasta `/data/uploads` do volume para o destino,
   mantendo os caminhos (os registros guardam o caminho relativo, ex.
   `execucoes/12/ab3f….jpg`). Para o Cloudflare R2: a mesma árvore vira as
   chaves do bucket (`rclone copy /data/uploads r2:<bucket>`), e o app passa a
   usar `STORAGE_BACKEND=r2` + as variáveis `R2_*`.
4. **Variáveis:** a `FIELD_ENCRYPTION_KEY` tem de ser a MESMA (sem ela os
   e-mails e os demais campos cifrados não abrem: ninguém entra). Banco fora
   da rede interna: a conexão ganha `sslmode=require` sozinha
   (`DATABASE_SSLMODE` muda, ex. `verify-full` com o certificado da
   empresa). `SECRET_KEY` nova só derruba as sessões (todos entram de
   novo). Mantenha as MESMAS chaves `VAPID_*`, senão os celulares precisam
   aceitar os avisos de novo. Os códigos da segunda etapa vão no banco e
   continuam valendo.
5. **Conferir:** `flask --app facilities db current` igual à última revisão,
   login, uma foto antiga abrindo, uma rodada do agendador.
6. **Recomeçar do zero em vez de migrar** também é uma opção válida: subir a
   produção vazia e cadastrar só o que é real, deixando o Railway como
   ambiente de testes permanente.

