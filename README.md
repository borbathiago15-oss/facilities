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
| Rotas e checklists | checklists com versão (biblioteca da Trino copiada por local, com modelos prontos de limpeza), cada pergunta com "como fazer" e foto de referência, rotas do local e turno com horários e/ou frequência (vários pontos de uma vez), escala, agendador das tarefas do dia, roteiro numerado no celular, execução pelo QR com fotos, não conformidades que viram chamado, acompanhamento com aderência à rota |
| Aplicativo de campo (`/app/`) | instalável no celular; meu turno, leitor de QR, execução também sem internet, avisos no celular, confirmação de presença, avisos do público |
| QR público | qualquer pessoa no local abre uma ocorrência pelo QR, sem login, e acompanha até resolver |
| Núcleo | pessoas, perfis e cadeia (superior direto), carteira que sobe pela cadeia, segunda etapa do login, avisos, troca obrigatória de senha, bloqueio por tentativas |

Perfis (a cadeia, de cima para baixo): **Gerente** (os clientes dele) ›
**Coordenador** (age como gestor nos seus locais) › **Supervisor**
(acompanha e faz checklist) › **Encarregado / ASG** e **Técnico de
manutenção**. Fora da cadeia: **Administrador** (tudo) e **Diretoria** (lê
tudo). **Cliente**: criado, mas sem login até a liberação do cliente externo.
Quem está acima vê tudo o que os de baixo veem.

## Rodar localmente

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY=desenvolvimento SESSION_COOKIE_SECURE=0
flask --app facilities db upgrade         # cria/atualiza o schema (SQLite em instance/)
flask --app facilities criar-admin        # mostra uma senha temporária
flask --app facilities run                # http://127.0.0.1:5000
```

Sem `DATABASE_URL`, usa SQLite em `instance/facilities.db`. O schema vem das
migrações também aqui — o boot não cria tabela nenhuma —, então rode
`flask --app facilities db upgrade` antes do primeiro uso e depois de cada
`git pull` que trouxer migração nova. Coluna nova no modelo: gere a migração
(`flask --app facilities db migrate -m "..."`) sobre um banco que esteja em
dia com `db upgrade`, e prove ida, volta e ida num Postgres antes do PR.

Primeiros passos na tela: cadastre um contrato, as pessoas, e em
**Passagem de Turno → Configurar** use "Começar com um modelo pronto".

## Testes

```bash
pytest -q                                                        # SQLite
TEST_DATABASE_URL=postgresql://.../facilities_testes pytest -q   # Postgres (zera o banco!)
python scripts/ensaio_migracoes_postgres.py postgresql://.../facilities_ensaio_test
pip install -r requirements-e2e.txt && pytest -q e2e             # navegador (celular e PC)
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
  | `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | sim, para anexos no Cloudflare R2 | não sobe, dizendo qual falta — a menos que `STORAGE_BACKEND=local` esteja escrito (anexos no disco do servidor: só com volume persistente) |

- **Agendador das rotas**: gera as tarefas do dia, avisa a hora de cada uma,
  pede e fecha as confirmações de presença e marca as perdidas. Precisa
  rodar **a cada 5 minutos**, por um destes caminhos:
  `flask --app facilities agendador rodar` (cron do servidor) ou
  `POST /rotas/agendador` com `Authorization: Bearer $AGENDADOR_TOKEN`
  (relógio externo da hospedagem; sem `AGENDADOR_TOKEN` a rota não existe).
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
  por processo: com `WEB_CONCURRENCY=2` o limite real dobra. Para um contador
  único entre os processos, `RATELIMIT_STORAGE_URI=redis://host:6379/0` (pede
  o pacote `redis` instalado).
- Cabeçalhos: HSTS (quando o acesso é https ou o cookie é Secure),
  Permissions-Policy (câmera só do próprio sistema), nosniff, X-Frame-Options.
  Content-Security-Policy com `script-src 'self'` (Fase 9A: nenhum script
  embutido nas telas).
- `GET /healthz` responde 200 sem login e sem banco (liveness).
- **Portal do cliente**: `CLIENTE_EXTERNO_LIBERADO=1` deixa a conta de cliente
  entrar (padrão desligado; ligar só com os termos do jurídico). O cliente
  ativa a segunda etapa no primeiro acesso, fica preso ao `/cliente` e vê só
  os locais do cliente ligado à conta. Desligar derruba as sessões abertas.
- Imagem: `docker build -t facilities .` (fuso `America/Sao_Paulo`). O
  `.dockerignore` deixa de fora `.env`, `instance/`, `.venv`, `.git` e os testes.
