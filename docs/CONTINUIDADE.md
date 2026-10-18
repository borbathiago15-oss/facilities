# Trino Facilities — documento de continuidade

Para quem continua o projeto (pessoa ou Claude Code num chat novo). Leia junto
com o `CLAUDE.md` da raiz, que tem as regras permanentes.

## De onde veio

A base foi criada em 16–17/10/2026, numa conversa que também cuidava do Trino
Intelligence (`claudeplanejamento-spec/sla-grupo-trino`). A partir daqui o
projeto segue em chat e repositório próprios, para não misturar as duas bases.

A **Passagem de Turno** foi trazida do Trino Intelligence (estado do PR #222 de
lá, já com as correções de contagem por área, rascunho fora dos indicadores,
tarefa sem resposta, "Não deu" que espera a passagem etc.). O Trino continua
com a sua própria Passagem: **os dois sistemas são independentes** e não
compartilham banco, login nem deploy.

## Decisões do dono do produto (não reabrir sem ele)

| Tema | Decisão |
|---|---|
| Objetivo | Sistema de **facilities** separado do Trino Intelligence; a base é a passagem de turno e as funcionalidades dela |
| O Trino | Não perde a Passagem de Turno dele; nada é retirado de lá |
| Login | **Próprio** (usuários e senhas separados do Trino) |
| Dados | **Começa do zero**; nenhum dado do Trino é migrado |
| Quem usa | **Só o Grupo Trino**, com vários contratos e áreas (não é multiempresa) |
| Serviços | Limpeza e conservação, portaria e segurança, manutenção predial |
| Versão 1 | Passagem completa (pendências, ocorrências, tarefas da gestão, painel, relatório mensal/PDF, uso sem internet, avisos) **+ chamados / ordens de serviço** |
| Hospedagem | **A decidir**. Por enquanto só construir e testar |
| Repositório | `borbathiago15-oss/facilities` (privado) |

## Como está organizado

```
facilities/
  __init__.py          create_app: config, extensões, blueprints, sessão, comandos CLI
  extensions.py        db, login_manager, migrate, csrf, limiter
  tempo.py             fuso da operação (grava UTC, exibe Brasília)
  object_storage.py    anexos: disco local (dev) ou Cloudflare R2
  core/                login (auth), cadastros (admin), acesso (carteira + decoradores),
                       avisos e início (rotas), app instalável (PWA), regras de anexo
  passagem/            o módulo do Trino: models (tabelas diario_operacional_*), rotas,
                       analitico (as contas), pdf (relatório), modelos_prontos
  chamados/            models, servico (TODAS as regras), rotas (telas)
  templates/, static/  telas (Bootstrap 5 + CSS da identidade Grupo Trino), JS, PWA
migrations/            Alembic — revisão inicial c6b7dccc9cae
tests/                 pytest (SQLite por padrão; Postgres com TEST_DATABASE_URL)
```

### Escolhas que não são óbvias

- **Nomes internos iguais aos do Trino** (`User.name`, `Client` = contrato,
  `client_id`, perfis `master`/`pleno`, tabelas `diario_operacional_*`). Foi o
  que permitiu trazer a Passagem e ~330 testes quase sem alteração, e é o que
  permite trazer correções futuras de lá. A tela fala a língua do Facilities.
- **Perfis**: `master` Administrador · `pleno` Gestor (configura a passagem dos
  contratos dele sem precisar de permissão extra) · `encarregado` · `tecnico`
  (atende chamados e faz passagem) · `visualizador` Diretoria (só lê). O
  perfil decide os módulos — não há caixinha de módulo no cadastro.
- **Carteira**: administrador e quem tem "todos os contratos" veem tudo; os
  demais, só os contratos vinculados (vazio = nada). Regra única em
  `facilities/core/acesso.py`.
- **Ocorrência → chamado** substitui o "abrir PDCA" do Trino.
- **Chamados**: prazo pela prioridade (urgente 4h, alta 24h, média 72h, baixa
  7 dias), gravado na abertura e recalculado da abertura quando a prioridade
  muda. Toda mudança vira evento na trilha. Regras em `chamados/servico.py`.
- **Modelos prontos** (`passagem/modelos_prontos.py`): área + modelo com
  turnos, rotina e tipos de ocorrência para os três serviços.
- **Sem agendador**: nada roda sozinho em segundo plano ainda (o resumo da
  manhã e o push do Trino não vieram). Avisos são só no sino do sistema.

## Estado atual

- Fluxo completo testado num navegador com tela de celular (administrador →
  contratos e pessoas → modelos prontos → encarregado passa o turno →
  gestor abre chamado da ocorrência e atribui → técnico atende, espera,
  resolve com foto → confirmação), sem erro de servidor nem de JavaScript.
- Suíte de testes verde em 17/10/2026: **523 passando em Postgres 16** e 518
  em SQLite (os 5 testes de concorrência só rodam no Postgres — no SQLite as
  escritas já são em fila). O schema dos testes vem das migrações.
- Migração inicial `c6b7dccc9cae` provada num Postgres limpo: upgrade →
  downgrade → upgrade, e `flask db check` sem diferença. Ela nunca foi aplicada
  em produção (não há produção ainda); a partir do primeiro deploy, NUNCA mais
  editar esta migração — mudança de schema vira migração nova.
- Revisão adversarial (segurança, regras dos chamados, fidelidade do porte,
  operação) feita em duas rodadas; os achados corrigidos estão no histórico
  de commits e cobertos por testes (`tests/test_nucleo_*`,
  `tests/test_chamados_concorrencia.py`, `tests/test_passagem_facilities_*`).
- Para quem tem um Postgres local com a migração antiga: recrie o banco de
  teste (a revisão inicial foi reescrita antes do primeiro push).

## Fases 1 a 4 (17/10/2026)

Aprovadas pelo dono do produto e entregues na branch
`claude/zealous-dijkstra-dkudbo` (um commit por fase). Planejamento
completo no plano oficial (v3) e nas decisões (v8), fora do repositório.

| Fase | O que entrou | Onde |
|---|---|---|
| 1 | Empresa, cliente (contratante), estado, local, setor, ambiente, equipamento, ponto com QR, etiquetas, histórico de cadastros | `facilities/cadastros/` |
| 2 | Cadeia de pessoas e carteira pela cadeia, sair encerra a sessão, segunda etapa (TOTP), perfil cliente bloqueado, varredura de isolamento | `core/hierarquia.py`, `core/totp.py`, `tests/test_isolamento_varredura.py` |
| 3 | Aplicativo de campo `/app/`, destino por perfil, leitor de QR (jsQR), testes de navegador | `facilities/campo/`, `e2e/` |
| 4A | Checklists com versão, rotas, escala, agendador, execução pelo QR (com e sem sinal), não conformidade, acompanhamento | `facilities/rotas/` |
| 4B | Web Push, QR público com acompanhamento, confirmação de presença aleatória | `core/push.py`, `rotas/ocorrencias.py`, `rotas/presenca.py`, `rotas/publico.py` |

Pontos de atenção:

- **Presença aleatória (D48)**: validar com RH e jurídico ANTES do piloto e
  constar no aviso de privacidade aos colaboradores. Toda rota nasce com 2
  por turno; 0 desliga.
- **Prazo padrão da ocorrência pública (Q2)**: decisão pendente do dono;
  enquanto isso, cada cliente configura o seu (vazio = sem prazo).
- **Nome de quem executou visível ao cliente (R5)**: só quando o cliente
  externo for liberado (Fase 9), depois do aviso aos colaboradores (D25).
- `totp_segredo` fica em texto no banco (como no Intelligence): proteger o
  banco e os backups como se protege as senhas.
- O agendador precisa rodar a cada 5 minutos (ver README, Produção).

## Pendências conhecidas (próximos passos sugeridos)

1. **Hospedagem e deploy** — decidir onde roda (o Dockerfile serve para
   Cloudflare Containers, Render, Fly, VM…). Precisa de Postgres, `SECRET_KEY`
   e, para anexos, R2 (sem R2 o boot recusa armazenar no disco do contêiner).
   Definir backup do banco.
2. **Notificação no celular (web push)** — feita na Fase 4B; falta definir as
   chaves VAPID e o relógio do agendador na hospedagem.
3. **Testes da fila sem internet** (`test_fila_offline.py` do Trino) não foram
   portados.
4. ~~Sair não revoga cookies copiados~~ — resolvido na Fase 2 (sair sobe a
   época da sessão, em todos os aparelhos).
5. **CSP**: as telas usam scripts inline (herança do Trino); uma CSP exigiria
   tirar o JS inline primeiro.
6. **Bloqueio de conta por tentativas** pode ser usado para travar a conta de
   alguém de propósito (é o custo do bloqueio por conta).
7. **Limite de login com vários workers**: o Flask-Limiter guarda as contagens
   na memória de cada processo (`memory://`); com N workers o limite real é N
   vezes maior. Em produção, apontar `RATELIMIT_STORAGE_URI` para um Redis.
8. **Atrás de proxy** (Cloudflare, balanceador): definir `PROXY_HOPS` com o
   número de proxies, senão todo login conta como vindo do mesmo IP.
9. **Ícone e marca**: logo oficial aplicada em 17/10/2026 —
   `static/marca/trino-facilities.png` (login) e o símbolo nos ícones do app
   (`static/pwa/icone-*.png`, `apple-touch-icon.png`). Trocar de novo: mesmos
   nomes de arquivo e subir `VERSAO` no `sw.js` (o ícone fica guardado no
   aparelho).
10. Ideias de produto ainda não decididas: rondas com QR code, preventiva
   (plano e agenda), relatório mensal de chamados, envio da senha temporária
   por e-mail.

## Como continuar num chat novo

1. Em claude.ai/code, abra uma sessão nova com o repositório
   **`borbathiago15-oss/facilities`** selecionado (não o do Trino).
2. Primeira mensagem sugerida: "Leia o `CLAUDE.md` e o
   `docs/CONTINUIDADE.md` e me diga o que falta para colocar no ar."
3. Banco local para os testes em Postgres: qualquer Postgres 16 com um banco
   UTF8 cujo nome tenha "test" (o `conftest.py` recusa outro nome, para não
   zerar banco de verdade):
   `TEST_DATABASE_URL=postgresql://usuario@host:porta/facilities_testes pytest -q`.

## Rodar

Ver o `README.md`.
