# Configuração manual: tudo o que é clique ou variável no painel

Um lugar só para o que o sistema **não** faz sozinho: cada passo, onde e por
quê. O detalhe fica no documento de cada assunto (o link ao lado); aqui não
se repete texto longo. A lista completa de variáveis, com uma linha de
explicação cada, está no `.env.example` da raiz.

Onde: "Railway › web › Variables" quer dizer o painel do Railway, serviço
`web`, aba *Variables*. **Nenhum segredo vai para o repositório, para o chat
nem para um chamado**: só para as variáveis do serviço e para o cofre
offline do dono.

> **ATENÇÃO (06/11/2026):** a imagem de produção não sobe sem
> `FIELD_ENCRYPTION_KEY`. Num projeto que já está no ar, faça o item 2 da
> tabela abaixo **antes** de publicar a versão nova; senão o `web` e o
> `agendador` param. Ordem completa: `docs/SEGURANCA_DADOS.md`, "Primeira vez
> em produção".

## Obrigatório para o sistema subir

| # | O quê | Onde | Por quê | Detalhe |
|---|---|---|---|---|
| 1 | Criar o projeto, o `web` (do repositório), o `Postgres`, o volume `/data` no `web` e o `Redis` | Railway › *New Project* / *Create* | o site, o banco, as fotos e os limites de acesso | `DEPLOY_RAILWAY.md`, passos 1–3b |
| 2 | **Chave da cifra:** gerar no seu computador (`flask --app facilities chaves gerar`), guardar no cofre offline, pôr `FIELD_ENCRYPTION_KEY` no `web` **e** no `agendador` (a mesma), deploy, depois `flask --app facilities chaves girar` e `chaves conferir` | seu computador → cofre → Railway › web/agendador › Variables → `railway ssh --service web` | sem ela o sistema não sobe; os dados pessoais ficam cifrados no banco. Emergência: `CIFRA_OPCIONAL=1` | `SEGURANCA_DADOS.md` |
| 3 | `DATABASE_URL`, `SECRET_KEY=${{secret(64)}}`, `STORAGE_BACKEND`, `UPLOAD_FOLDER=/data/uploads`, `RATELIMIT_STORAGE_URI=${{Redis.REDIS_URL}}`, `PROXY_HOPS=1`, `WEB_CONCURRENCY=4`, `DIRECT_DATABASE_URL`, `CLIENTE_EXTERNO_LIBERADO=0` | Railway › web › Variables | banco, sessões que não caem ao acaso, fotos no volume, limites comuns aos processos, IP real atrás do proxy | `DEPLOY_RAILWAY.md`, passo 4 |
| 4 | *Healthcheck Path* `/healthz`, *Replicas* 1, *Generate Domain* | Railway › web › Settings | o volume só se liga a um serviço; `/readyz` **não** é o healthcheck | `DEPLOY_RAILWAY.md`, passo 5; `BANCO_E_POOLER.md`, "Sondas" |
| 5 | Serviço `agendador`: variáveis `DATABASE_URL`, `DIRECT_DATABASE_URL`, `SECRET_KEY=${{web.SECRET_KEY}}`, `FIELD_ENCRYPTION_KEY=${{web.FIELD_ENCRYPTION_KEY}}`, `STORAGE_BACKEND`; *Custom Start Command* `flask --app facilities agendador rodar`; *Cron Schedule* `*/5 * * * *` | Railway › agendador | gera as tarefas, avisos, presença, preventivas, retenção | `DEPLOY_RAILWAY.md`, passo 6 |
| 6 | Primeiro administrador: `ADMIN_INICIAL_EMAIL`, `ADMIN_INICIAL_NOME` (e, se quiser, `ADMIN_INICIAL_SENHA`); depois do primeiro login, apagar a senha | Railway › web › Variables → *Deploy Log* | entrar a primeira vez sem terminal; a senha temporária aparece uma vez no log | `DEPLOY_RAILWAY.md`, passo 7 |

## Recomendado antes do uso de verdade

| # | O quê | Onde | Por quê | Detalhe |
|---|---|---|---|---|
| 7 | Tempos limite no papel do banco (`ALTER ROLE ... SET statement_timeout` etc.) — **depois** da `DIRECT_DATABASE_URL` no `web` e no `agendador` | Railway › Postgres › Data › Query (ou o editor SQL do provedor) | consulta pendurada não segura o site; o código não pode pôr isso na URL | `BANCO_E_POOLER.md`, "Passo manual 1" |
| 8 | Avisos no celular: `flask --app facilities push chaves` e as três `VAPID_*` no `web` **e** no `agendador` | `railway ssh --service web` → Variables dos dois | sem elas o aviso da hora da tarefa não chega | `DEPLOY_RAILWAY.md`, passo 8 |
| 9 | Biblioteca de checklists: *Cadastros › Biblioteca de checklists › Instalar na biblioteca* | tela do sistema (administrador) | sem isso "Usar uma rota pronta" não tem o que oferecer | `DEPLOY_RAILWAY.md`, passo 8b |
| 10 | Serviço `backup`: imagem `postgres:<mesma versão>`, volume `/backup`, `DATABASE_URL`, Cron `30 6 * * *` e o comando do `pg_dump`; uma vez por mês, baixar a cópia mais recente para fora do Railway | Railway › *Create › Docker Image* | o plano Hobby não faz backup | `DEPLOY_RAILWAY.md`, passo 9; backup cifrado em `SEGURANCA_DADOS.md` |
| 11 | Cópia das fotos: `STORAGE_BACKEND=r2` + `R2_*` (recomendado), ou o volume com `R2_*` de um bucket de cópia + `ANEXOS_ESPELHO_R2=1`; versionamento ligado no bucket | Railway › web › Variables; painel da Cloudflare | o `pg_dump` não leva as fotos; perder o volume perde todas | `DEPLOY_RAILWAY.md`, passo 9b |
| 12 | Segunda etapa: ter um aplicativo autenticador no celular antes do primeiro login da gestão; avisar os supervisores | celular de cada pessoa | é obrigatória para administrador, gerente, coordenador, diretoria, supervisor e cliente | `SEGURANCA_DADOS.md`, "Contas e sessões" |

## Opcional

| # | O quê | Onde | Por quê | Detalhe |
|---|---|---|---|---|
| 13 | E-mail dos convites: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_REMETENTE` (`SMTP_SSL=1` na porta 465) | Railway › web › Variables | o convite sai sozinho por e-mail; sem isso, a tela abre o WhatsApp/e-mail do aparelho | `DEPLOY_RAILWAY.md`, passo 9c |
| 14 | Arquivo das fotos antigas: `ARQUIVO_R2_*` de um bucket **separado** (ou `ARQUIVO_FOTOS_PASTA` só para testar); com volume, `ARQUIVO_FOTOS_NO_WEB=1` | Railway › web › Variables; depois a tela *Armazenamento de fotos* | libera espaço do volume; o destino nunca se digita na tela. Não tire as variáveis depois de arquivar | `ARQUIVO_FOTOS.md` |
| 15 | Pooler (Neon, Supabase): `DATABASE_URL` com pooler e `DIRECT_DATABASE_URL` direta no `web` e no `agendador`; pool do pooler ≥ processos × threads × 2 + 5 | painel do provedor + Railway › Variables | o site usa o pooler; agendador e migrações vão direto | `BANCO_E_POOLER.md`, "Pooler" |
| 16 | `RATELIMIT_EXIGIR_COMPARTILHADO=1` depois de o Redis existir | Railway › web › Variables | o site passa a recusar subir sem Redis | `DEPLOY_RAILWAY.md`, passo 4 |
| 17 | Domínio próprio | Railway › web › Settings › *Custom Domain* | endereço da empresa em vez de `…up.railway.app` | `DEPLOY_RAILWAY.md`, passo 5 |
| 18 | Integração com o Trino Intelligence: criar a chave em *Integração* e guardá-la no cofre de segredos do Intelligence | tela do sistema (administrador) → variáveis do Intelligence | a chave aparece uma vez; o Intelligence lê os dados | `INTEGRACAO.md` |
| 19 | Portal do cliente: `CLIENTE_EXTERNO_LIBERADO=1` | Railway › web › Variables | só com os termos do jurídico | `DEPLOY_RAILWAY.md`, "Antes do piloto" |
| 20 | Presença aleatória: deixar **0** em cada rota até RH e jurídico validarem | tela de cada rota | decisão D48 | `DEPLOY_RAILWAY.md`, "Antes do piloto" |

## Uma vez por ano, ou quando alguém com acesso sair

* Trocar a chave da cifra (rodízio): `SEGURANCA_DADOS.md`, "Trocar a chave".
* Revisar quem tem acesso de administrador ao projeto no Railway (excluir um
  serviço ou um volume apaga dados): `DEPLOY_RAILWAY.md`, "O desenho".
* Conferir que o backup restaura: `DEPLOY_RAILWAY.md`, passo 9.

## Variáveis que NUNCA mudam depois do primeiro uso

* `FIELD_ENCRYPTION_KEY` — sem a mesma chave os campos cifrados não abrem
  (ninguém entra). Trocar só pelo rodízio.
* `VAPID_*` — trocar obriga cada celular a aceitar os avisos de novo.
* `SECRET_KEY` — trocar derruba todas as sessões (ninguém perde dado).
