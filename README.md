# Trino Facilities

Sistema de facilities do Grupo Trino: **passagem de turno** e **chamados /
ordens de serviço** para os contratos de limpeza e conservação, portaria e
segurança e manutenção predial. Login próprio, funciona no celular (app
instalável, com fila para quando não há sinal).

A Passagem de Turno veio do Trino Intelligence, com os mesmos nomes internos
(tabelas `diario_operacional_*`, `client_id`, perfis `master`/`pleno`) — o que
permite trazer correções de lá para cá sem tradução. O Trino Intelligence
continua com a sua própria Passagem; os dois sistemas são independentes.

## O que tem

| Módulo | O que faz |
|---|---|
| Passagem de Turno | checklist da rotina, pendências que atravessam turnos (contadas por área), ocorrências, tarefas da gestão para o turno, correção de passagem, painel, relatório mensal em PDF, modelos prontos por serviço |
| Chamados | abrir (com fotos), atribuir a um técnico, prazo pela prioridade (régua própria por cliente, se ele tiver), em espera com o prazo parado, resolver (foto do serviço), confirmar ou reabrir, trilha completa, números de prazo, aviso no sino e no celular antes e no vencimento |
| Preventiva | plano por ponto/equipamento (checklist, a cada N dias, quantos dias antes abrir, responsável); o agendador abre a ordem de serviço sozinho, sem duplicar; o técnico faz o checklist no aplicativo pelo QR e a ordem fica resolvida |
| Demandas | painel único do que espera alguém — chamados, preventivas, visitas de supervisão, pedidos de insumo, avisos do público e cobranças do cliente —, pela carteira, com o atrasado primeiro |
| Portal do cliente (`/cliente`) | o cliente vê os locais dele: nota e indicadores, chamados (situação, prazo, solução e fotos), as fotos dos checklists e as visitas de supervisão — sem custo nem comentário interno; abre cobrança com a data que escolhe (mínimo 24 h), a coordenação responde e só o cliente encerra ou reabre. Desligado por padrão (`CLIENTE_EXTERNO_LIBERADO`); segunda etapa obrigatória |
| Equipe do posto | funcionários do local (com ou sem login), postos com horário e rota, escala sem sobreposição; no aplicativo, o supervisor lança quem veio, faltou ou atrasou e quem cobriu a falta (com motivo) — as tarefas da rota passam para quem cobriu; conferência do mês no site |
| Materiais | catálogo do grupo (preço opcional), estoque por local (entrada, saída, ajuste pela gestão), consumo no aplicativo e na OS, saldo negativo só com o gestor do contrato, pedido de insumo do posto ao gestor (a compra é em outro sistema), custo operacional por local, cliente e estado — nunca alimenta o DRE |
| Painel | nota por local (média com pesos iguais de aderência à rota, ocorrências no prazo, visitas conformes e chamados no prazo; faixas crítica, atenção e boa) e o que está atrasado; o supervisor vê os locais dele, a gestão e a diretoria por cliente |
| Relatórios | relatório mensal do cliente por local (nota, rotinas por ambiente, chamados, correções, avisos, visitas, cobranças e fotos), em tela, PDF e Excel; a gestão escolhe as fotos e libera, o cliente vê no portal |
| Integração | API só de leitura `/api/integracao/v1` para o Trino Intelligence, com chave de servidor por local e registro de cada acesso (ver `docs/INTEGRACAO.md`) |
| Visitas de supervisão | programadas por local, com checklist; abrem sozinhas na data e avisam o supervisor; feitas no aplicativo com as fotos que o checklist pede (antes, depois, por item) e até 5 livres; o não conforme abre um chamado para a gestão, com as fotos |
| Cadastros | empresas do grupo, clientes (gerente e centro de custo), estados, locais (subcentro), e em cada local setores, ambientes, equipamentos e pontos com QR; etiquetas em PDF; histórico de alterações |
| Rotas e checklists | checklists com versão (biblioteca da Trino copiada por local, com modelos prontos de limpeza), cada pergunta com "como fazer" e foto de referência, POP/FIT anexado com resumo, rotas do local e turno com horários e/ou frequência (vários pontos de uma vez), escala, agendador das tarefas do dia, roteiro numerado no celular, execução pelo QR com fotos, não conformidades que viram chamado, acompanhamento com aderência à rota |
| Aplicativo de campo (`/app/`) | instalável no celular; meu turno, leitor de QR, execução também sem internet, avisos no celular, confirmação de presença, avisos do público |
| QR público | qualquer pessoa no local abre uma ocorrência pelo QR, sem login, e acompanha até resolver |
| Núcleo | pessoas, perfis e cadeia (superior direto), carteira que sobe pela cadeia, segunda etapa do login, avisos, troca obrigatória de senha, bloqueio por tentativas |

Perfis (a cadeia, de cima para baixo): **Gerente** (os clientes dele) ›
**Coordenador** (age como gestor nos seus locais; monta locais só nos
clientes da carteira dele) › **Supervisor** (acompanha, faz checklist,
distribui chamados — atribui, muda a prioridade, cancela, pode ser o
responsável — e responde cobrança do cliente) › **Encarregado / ASG** e
**Técnico de manutenção**. Fora da cadeia: **Administrador** (tudo) e
**Diretoria** (lê tudo, sempre todos os locais). **Cliente**: criado, mas
sem login até a liberação do cliente externo. Quem está acima vê tudo o que
os de baixo veem.

Regras de permissão do dono (05/11/2026, leva L3):

* "Acesso a todos os locais" abre o grupo inteiro só para gerente e
  coordenador. No supervisor, encarregado e técnico vale os locais da gestão
  logo acima na cadeia (sem gestão acima, nada a mais).
* Segunda etapa do login obrigatória: administrador, gerente, coordenador,
  diretoria, supervisor e cliente (`docs/SEGURANCA_DADOS.md`).
* Quem cuida do local — o gerente pelo cliente, o coordenador e o supervisor
  pela cadeia — recebe os avisos dele (chamado novo, insumo, cobrança,
  visita, prazo) e aparece para receber chamado; o supervisor também recebe
  "Novo chamado". Sem ninguém para avisar, a tela diz isso.
* "Configurar a passagem" é da gestão; o encarregado só configura se o
  gerente ou o coordenador dele autorizar, pessoa a pessoa, em Convites ›
  "Quem pode configurar a passagem de turno" (o administrador também, em
  Pessoas e acessos).
* Desativar quem é responsável não transfere nada sozinho: a ordem
  preventiva nasce sem responsável e os avisos de prazo e de reabertura vão
  à gestão do local até ela escolher outra pessoa.

## Rodar localmente

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY=desenvolvimento SESSION_COOKIE_SECURE=0
flask --app facilities db upgrade         # cria/atualiza o schema (SQLite em instance/)
flask --app facilities criar-admin        # mostra uma senha temporária
flask --app facilities run                # http://127.0.0.1:5000
```

Todas as variáveis que o sistema lê, com uma linha de explicação cada:
`.env.example` (copie para `.env`, que nunca vai para o git). Para subir a
produção do zero: `docs/DEPLOY_RAILWAY.md` (passo a passo) e
`docs/CONFIG-MANUAL.md` (tudo o que é clique ou variável no painel). O que
funciona hoje e o que falta: `STATUS.md`.

Sem `DATABASE_URL`, usa SQLite em `instance/facilities.db`. O schema vem das
migrações também aqui — o boot não cria tabela nenhuma —, então rode
`flask --app facilities db upgrade` antes do primeiro uso e depois de cada
`git pull` que trouxer migração nova. Coluna nova no modelo: gere a migração
(`flask --app facilities db migrate -m "..."`) sobre um banco que esteja em
dia com `db upgrade`, e prove ida, volta e ida num Postgres antes do PR.

Primeiros passos na tela: cadastre um contrato, as pessoas, e em
**Passagem de Turno → Configurar** use "Começar com um modelo pronto".

**Telas novas (React, em migração módulo por módulo):** `cd frontend && npm ci
&& npm run build`, depois abra `/novo/`. Arquitetura, fases e regras:
`docs/REACT.md`.

## Testes

```bash
pytest -q                                                        # SQLite
TEST_DATABASE_URL=postgresql://.../facilities_testes pytest -q   # Postgres (zera o banco!)
python scripts/ensaio_migracoes_postgres.py postgresql://.../facilities_ensaio_test
pip install -r requirements-e2e.txt && pytest -q e2e             # navegador (celular e PC)
cd frontend && npm run tipos && npm test                          # telas novas (React)
```

O ensaio das migrações semeia dado em todas as tabelas novas e prova que
cada migração faz ida, volta e ida sem perder linha (a volta guarda tudo em
quarentena, `_quarentena_<revisão>_<tabela>`). Os testes de navegador (`e2e/`)
usam Playwright e Chromium; sem eles, são pulados.

A suíte em Postgres APAGA todas as tabelas do banco no começo. Por isso ela
se recusa a rodar se o nome do banco não tiver "test" (`facilities_testes`,
`facilities_test`...) — nunca aponte para o banco de produção.

## Produção

Passo a passo do Railway (a hospedagem escolhida): `docs/DEPLOY_RAILWAY.md`.

- Banco **Postgres**; o schema vem só das migrações (`flask db upgrade`, que o
  `docker-entrypoint.sh` roda antes do gunicorn). O boot não faz DDL.
- O app **recusa subir** com configuração que perde dado ou derruba sessão:

  | Variável | Obrigatória? | O que acontece sem ela |
  |---|---|---|
  | `DATABASE_URL` | sim (a imagem Docker exige, via `EXIGIR_DATABASE_URL=1`) | não sobe — sem ela o app usaria um SQLite dentro do contêiner, que some a cada reinício |
  | `SECRET_KEY` | sim, fora do SQLite de desenvolvimento | não sobe — sem ela cada processo do gunicorn sortearia a sua, e o login e as sessões falhariam ao acaso |
  | `FIELD_ENCRYPTION_KEY` | sim, na imagem Docker | não sobe — sem ela os dados pessoais ficariam em texto aberto no banco (`CIFRA_OPCIONAL=1` só em emergência) |
  | `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | sim, para anexos no Cloudflare R2 | não sobe, dizendo qual falta — a menos que `STORAGE_BACKEND=local` esteja escrito (anexos no disco do servidor: só com volume persistente) |

- **Cifra dos campos sensíveis (obrigatória na imagem de produção):**
  `FIELD_ENCRYPTION_KEY` cifra no banco e-mails, telefones, endereços e o
  segredo da segunda etapa. Na imagem Docker o app **não sobe** sem ela
  (saída de emergência: `CIFRA_OPCIONAL=1`, com alerta no log); no
  desenvolvimento ela é opcional. A ordem para ligar (gerar → cofre → `web` e
  `agendador` → deploy → `chaves girar`), trocar a chave e o backup cifrado:
  `docs/SEGURANCA_DADOS.md`.

- **Agendador das rotas**: gera as tarefas do dia, avisa a hora de cada uma,
  pede e fecha as confirmações de presença e marca as perdidas. Precisa
  rodar **a cada 5 minutos** pelo comando
  `flask --app facilities agendador rodar` (o Cron do Railway, ou o cron do
  servidor). Não há mais agendador por endereço da internet: o antigo
  `POST /rotas/agendador` foi desligado (05/11/2026) e `AGENDADOR_TOKEN`
  não liga nada.
  Pode rodar quantas vezes quiser: não duplica nada. Sem agendador, as
  tarefas do dia ainda aparecem (a tela gera as de hoje), mas sem avisos.
- **Avisos no celular (Web Push)**: `flask --app facilities push chaves` gera
  `VAPID_PRIVATE_KEY` e `VAPID_PUBLIC_KEY`; defina também
  `VAPID_SUBJECT=mailto:...`. Sem as chaves, os avisos ficam só no sino e na
  tela do aplicativo. No iPhone, o aviso só funciona com o aplicativo
  instalado na Tela de Início (iOS 16.4 ou mais novo).
- `SESSION_COOKIE_SECURE` (padrão ligado) vale para o cookie de sessão e para
  o "Manter conectado". Aceita `1/true/yes/on` e `0/false/no/off`; qualquer
  outro valor para o boot (antes `true` desligava o Secure sem avisar). O
  mesmo vale para `RATELIMIT_ENABLED`.
- **Atrás de proxy** (Cloudflare, balanceador do PaaS), defina `PROXY_HOPS`
  com o número de proxies de confiança na frente do app (em geral `1`). Sem
  isso o IP de todo mundo é o do proxy. Não defina sem proxy: aí qualquer um
  forjaria o próprio IP pelo cabeçalho `X-Forwarded-For`.
- O limite de tentativas de login é por IP + e-mail (20 por minuto), além do
  bloqueio da conta após 5 senhas erradas. O contador padrão (`memory://`) é
  por processo: com `WEB_CONCURRENCY=4` o limite real é 4 vezes maior. Para um contador
  único entre os processos, `RATELIMIT_STORAGE_URI=redis://host:6379/0` (o
  pacote `redis` já vem na imagem). Na imagem de produção, `memory://` com
  mais de um worker gera aviso no log; com `RATELIMIT_EXIGIR_COMPARTILHADO=1`
  o app se recusa a subir sem Redis.
- Cabeçalhos: HSTS (quando o acesso é https ou o cookie é Secure),
  Permissions-Policy (câmera só do próprio sistema), nosniff, X-Frame-Options.
  Content-Security-Policy com `script-src 'self'` (Fase 9A: nenhum script
  embutido nas telas).
- `GET /healthz` responde 200 sem login, sem banco e sem carregar a pessoa
  logada (liveness). `GET /readyz` faz `SELECT 1` com 2 s de limite: 200
  pronto, 503 sem banco (readiness).
- **Banco**: pool do tamanho das threads, tempos limite curtos (conexão 5 s,
  pool 5 s, conexão perdida ~15 s) e 503 "tente de novo em instantes" quando
  o banco não responde. Processos e threads do gunicorn: `WEB_CONCURRENCY`
  (4) × `GUNICORN_THREADS` (8). Tempos limite no papel do banco (passo
  manual), pooler (Neon/Supabase) e `DIRECT_DATABASE_URL`:
  `docs/BANCO_E_POOLER.md`.
- **Portal do cliente**: `CLIENTE_EXTERNO_LIBERADO=1` deixa a conta de cliente
  entrar (padrão desligado; ligar só com os termos do jurídico). O cliente
  ativa a segunda etapa no primeiro acesso, fica preso ao `/cliente` e vê só
  os locais do cliente ligado à conta. Desligar derruba as sessões abertas.
- Imagem: `docker build -t facilities .` (fuso `America/Sao_Paulo`). O
  `.dockerignore` deixa de fora `.env`, `instance/`, `.venv`, `.git` e os testes.
