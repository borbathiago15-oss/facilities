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
- **Nome de quem executou visível ao cliente (R5)**: o interruptor existe
  por cliente (Cadastros › Clientes, só o administrador), desligado. Ligar só
  depois do aviso aos colaboradores e do aval do jurídico (D25).
- `totp_segredo` fica em texto no banco (como no Intelligence): proteger o
  banco e os backups como se protege as senhas.
- O agendador precisa rodar a cada 5 minutos (ver README, Produção).

## Fase 5 (18/10/2026)

| O que entrou | Onde |
|---|---|
| Plano preventivo e ciclos (uma ordem por plano + vencimento; agendador parado não despeja ordens velhas) | `facilities/preventiva/` |
| Checklist da preventiva no aplicativo (`chamado_id` na execução) resolve a ordem | `rotas/servico.py`, `static/js/rotas-turno.js` |
| D8: "Aguardando" para o relógio do prazo; a pausa empurra o prazo ao sair | `chamados/servico.py` (`_pausar`, `_retomar_relogio`) |
| D9: régua de prazo por cliente (horas por prioridade); vale só para chamado aberto depois | `Contratante.prazos_chamado_json`, `regua_do_contrato` |
| Aviso de prazo (sino + celular) antes e no vencimento, uma vez só; vencido há mais de 24 h não dispara | `chamados.servico.avisar_prazos` (no agendador) |
| Painel de demandas | `facilities/demandas.py`, `/demandas/` |

Migração `d4057ab57d72`: só acrescenta (2 tabelas, 6 colunas). Os prazos dos
chamados já abertos não mudam.

## Fase 6 (18/10/2026)

| O que entrou | Onde |
|---|---|
| Funcionários do local (login opcional: o funcionário com login é o mesmo usuário, F6-1), postos, escala sem sobreposição (dias, horário que vira o dia, período) | `facilities/equipes/` |
| Presença no aplicativo (`/app/equipe`): só veio / faltou / atrasou, sem horário (F6-2); hoje e 7 dias para trás; falta dispensa o pedido de presença aleatória | `equipes/servico.py` |
| Cobertura com motivo: as tarefas da rota do posto passam para quem cobriu (sem login: ficam sem escalado); o agendador já gera com quem cobriu | `equipes.servico.reescalar_rota`, `substituto` |
| Conferência do mês no site | `/equipes/locais/<id>/mes` |
| Visitas de supervisão programadas (D56): abrem na data, avisam o supervisor, são feitas no aplicativo; o não conforme abre UM chamado (F6-3) | `facilities/visitas/` |

Migração `78a13bdef69f`: só acrescenta 7 tabelas.

Limites conhecidos: a visita ainda não tira foto (checklist com foto
obrigatória não serve para visita) e precisa de sinal. O motivo da cobertura
é texto livre — se a operação quiser uma lista fixa de motivos, é decisão do
dono.

Fase 7 (18/10/2026) — materiais e custo operacional (`facilities/materiais/`):

| Decisão do dono | Como ficou |
|---|---|
| F7-1 preço opcional, no site | `Material.preco_unitario` nulo pode; cada movimento guarda o preço do dia; sem preço = fora do custo, avisado na tela |
| F7-2 saldo negativo | só o gestor do contrato (`gestores_do_contrato`) ou o administrador, com justificativa; quem autorizou fica no movimento |
| F7-3 pedido de insumo | só aviso: o gestor marca "visto" e compra em outro sistema; prazo 48 h ou o do cliente (`contratantes.prazo_pedido_insumo_horas`); entra nas Demandas |
| F7-4 custo | supervisor, gestão e diretoria veem; cliente, encarregado e técnico, não |

Custo operacional = soma dos consumos do período (por local, cliente e estado,
das mesmas linhas). Migração `7da1bd3b5466`: 4 tabelas e 1 coluna, só
acrescenta. O catálogo de materiais é do grupo inteiro: qualquer gestor edita.

Fase 8 (18/10/2026) — painéis e integração (`facilities/paineis/`,
`facilities/integracao/`, `docs/INTEGRACAO.md`):

| Decisão do dono | Como ficou |
|---|---|
| F8-1 faixas da nota | < 70 crítica; 70 a < 85 atenção; ≥ 85 boa; indicador sem dado sai da média |
| F8-2 (D42) plano de ação | por referência: cada não conformidade tem `NC-<id>` (na API e na tela da execução) |
| F8-3 o que a API entrega | locais, chamados, aderência, não conformidades, visitas e nota — sem custo |
| F8-4 lado do Intelligence | fica para tarefa no repositório de lá; D34 (`cost_center`) antes do aceite |

Migração `184278e35887`: 3 tabelas (`integracao_chaves`,
`integracao_chave_locais`, `integracao_acessos`), só acrescenta.

Fase 9A (18/10/2026) — CSP: `Content-Security-Policy` com `script-src 'self'`
(sem `'unsafe-inline'`, sem `eval`). Nenhum `<script>` embutido nem `onclick=`
nas telas: os scripts foram para `static/js/` (`base.js`, `diario_dashboard.js`,
`diario_ver_turno.js`, `chamados_novo.js`) e as ações viraram atributos
`data-*` tratados por `static/js/acoes.js` (só função registrada em
`window.FC_ACOES` é chamada). `tests/test_csp.py` barra script embutido novo; o
e2e reprova qualquer violação de CSP no console. O estilo ainda aceita
`'unsafe-inline'` (as telas da Passagem têm `style=` e `<style>`): risco menor,
retirada para depois. No e2e, use `esperar()` do conftest em vez de
`wait_for_function` (que a CSP bloqueia).

Fase 9B (18/10/2026) — portal do cliente e cobrança (`facilities/portal/`):

| Decisão do dono | Como ficou |
|---|---|
| F9-1 o que o cliente vê | indicadores (a nota do painel), chamados (situação, prazo, solução, fotos — PDF não) e fotos dos checklists; nada de custo, material, comentário, trilha do chamado ou nome da equipe |
| F9-2 cobrança | o cliente escolhe a data (fim do dia, no mínimo 24 h, até 6 meses); a coordenação do contrato e o gerente do cliente são avisados (sino e celular); a gestão responde; só o cliente confirma ou reabre (com data nova); a trilha inteira aparece ao cliente, com a equipe como "Coordenação"; entra em Demandas |
| F9-3 (R5) | fotos sim; quem fez o checklist aparece pela função; o nome só com `contratantes.mostrar_nome_executor` (só o administrador liga, depois da D25) |
| F9-4 | tudo atrás de `CLIENTE_EXTERNO_LIBERADO` (padrão desligado) até o jurídico entregar o Grupo C |

Travas: o cliente entra só com o portal ligado e com `cliente_id`; sem a
segunda etapa, só abre a tela de segurança; com ela, só `portal.*`, avisos e a
própria conta (negação por padrão em `facilities/__init__._porta_do_cliente`:
rota nova do sistema não se abre ao cliente por descuido). Não desliga a
segunda etapa. A carteira do cliente são os locais ativos do cliente dele. A
cobrança tem tabela própria (`cobrancas` + `cobranca_eventos`), e não a
`DiarioTarefaTurno` da Passagem: aquela exige área, data e turno e é código
herdado do Intelligence. Migração `801f10ee6552`: 2 tabelas e 1 coluna, só
acrescenta. A varredura de isolamento roda também com um cliente de outro
contratante.

Fase 10 (18/10/2026) — fotos na visita de supervisão (`visita_fotos`):

| Decisão do dono | Como ficou |
|---|---|
| Que fotos | as que o checklist pede (antes, depois, por item — obrigatórias) e até 5 livres; caiu a trava "checklist de visita não pode pedir foto" |
| Chamado | com não conformidade, todas as fotos da visita entram no chamado como foto de "antes" (o mesmo arquivo, sem cópia) |
| Portal | o cliente vê as visitas feitas nos últimos 30 dias, com fotos; quem fez segue o R5 (função, ou nome com o interruptor) |

A conferência da imagem é a mesma do checklist da rota (`rotas.servico.ler_imagem`).
A foto é reduzida no aparelho (`data-foto-leve` em `foto-leve.js`, que também
segura o envio até terminar). A tela da visita continua pedindo sinal.
Migração `418d47bbc506`: 1 tabela, só acrescenta.

Visual (18/10/2026) — padrão do Trino Intelligence, analisado com a base de
design (ui-ux-pro-max: navegação, toque de 44 px, contraste, foco visível,
sem rolagem lateral, movimento reduzido):

| Decisão do dono | Como ficou |
|---|---|
| Menu do site | lateral escuro (`templates/_menu.html`), grupos Hoje · Operação · Recursos · Configuração em `<details>` (abrem sem script); "Rotina dos locais" entrou no menu (antes Rotas, Preventiva, Equipe e Visitas só se achavam por dentro de Cadastros); no celular vira gaveta (`base.js`) |
| Login | `core/_porta.html` (login e código): painel preto da marca com a faixa de quatro cores e o formulário claro; no celular, só o formulário; mostrar a senha e "Entrando…" em `static/js/porta.js` |
| Início | "o que espera você hoje": números clicáveis que abrem a fila de Demandas já filtrada, os 6 itens mais urgentes e os atalhos do perfil |

O aplicativo de campo mantém a navegação embaixo. As cores continuam só nos
tokens do `app.css` (os mesmos do Intelligence). A paleta sugerida pela base
de design (verde, fonte serifada) foi descartada: a identidade é a do Trino.
`e2e/test_visual.py` confere login, gaveta e ausência de rolagem lateral.

Bloco A — pronto para o piloto (18/10/2026), da análise de rotas e fluxos:

| Problema | Como ficou |
|---|---|
| Presença "sem resposta" falsa | pedido que nunca saiu (agendador atrasou) vira `nao_enviada`, sem alerta; horário que já passou não vira pedido (rota criada ou cobertura no meio do turno) |
| Agendador | trava no Postgres (`pg_try_advisory_xact_lock`): duas rodadas ao mesmo tempo, a segunda não faz nada; a rodada que falha fica registrada em `agendador_execucoes` com o erro |
| Item não conforme da rota | abre UM chamado por execução (decisão do dono), com os itens e as fotos; a preventiva com item não conforme também; a mensagem do app passou a ser verdadeira |
| QR | o selo do servidor ("leu no ponto") só sai com a câmera; link de aviso e código digitado ficam com a hora do celular (marcado na execução) |
| Envio recusado na fila | tarefa já feita por outra pessoa ou turno encerrado → vira atividade extra, com o motivo na observação; antes só "descartar" |
| Duas pessoas, mesma tarefa | a tarefa é travada até o commit |
| Avisos (presença, visita, insumo, ocorrência, cobrança) | só para quem está ativo e ainda tem o local na carteira |
| Chamado | urgente vai ao celular da gestão; resolvido avisa quem abriu no celular e, sem confirmação em 24 h, lembra UMA vez (não fecha sozinho — decisão do dono); reaberto ganha prazo novo pela régua e volta a avisar |
| Visita vencida | vira "Não feita (venceu)" dois dias depois do vencimento |
| Cópia sem sinal do app | uma por tela (a mais recente), no máximo 20 h para o turno, e rede lenta não prende a tela (8 s) |

Sem migração: os estados novos (`nao_enviada`, `perdida`) cabem nas colunas
de texto que já existem.

Rota e checklist simples (18/10/2026), decisões do dono:

| O quê | Como ficou |
|---|---|
| "Como fazer" + foto de referência | cada pergunta do checklist tem um texto curto e uma foto de como deve ficar; ficam no JSON da versão (`como_fazer`, `foto_ref` — chave `checklists/<modelo>/ref/<hex>.<ext>`, conferida por padrão; chave forjada é ignorada) e aparecem embaixo da pergunta no celular; a foto sai por `/rotas/referencias/<versão>/<código>` (do local, pela carteira; da biblioteca, para quem está logado) |
| Vários pontos de uma vez | na rota, "Incluir pontos": marque os banheiros, um checklist e os horários; tudo ou nada; ordem em sequência |
| Roteiro numerado | o "Meu turno" lista as tarefas na ordem dos horários (1, 2, 3…), com a próxima destacada e quantos passos tem cada uma |
| Modelos prontos de limpeza | banheiro, copa e cozinha, recepção e escritório, vestiário e área externa, com o "como fazer" (`facilities/rotas/biblioteca_pronta.py`); o administrador instala pela biblioteca ou `flask --app facilities semear-checklists`; não duplica |

Relatório do cliente (18/10/2026), decisões do dono — tela + PDF + Excel; o
do cliente primeiro; fotos em amostra automática que a gestão pode trocar:

* `facilities/relatorios/cliente.py`: os números do mês por local (nota e os
  4 indicadores contra o mês anterior, rotinas por ambiente, chamados com %
  no prazo e tempo médio, não conformidades e quantas viraram chamado
  resolvido, avisos do público, visitas, cobranças) — só leitura, das mesmas
  regras do painel. Sem custo e sem nome de ninguém da equipe.
* Fotos: candidatas do mês (checklists, chamados resolvidos, visitas);
  amostra automática (antes/depois de chamados, uma por ambiente, visitas);
  a gestão marca outras (até 12).
* Liberação: só mês fechado e só a gestão; o cliente vê no portal
  (`/cliente/relatorios`) e baixa PDF/Excel; "recolher" tira do portal.
* PDF em ReportLab (`relatorios/arquivos.py`, uma página no caso comum);
  Excel em openpyxl (nova dependência fixada).
* Migração `3e93dd45f02b`: tabela `relatorios_cliente` (fotos escolhidas,
  recado, liberação). Os números não são guardados.
* Próximos: relatório da Gestão (operacional, diário/semanal) e da Diretoria
  (consolidado, tendência de 6 meses, ranking de locais críticos).

POP/FIT do checklist (18/10/2026), decisões do dono — a gestão escreve o
resumo; o documento fica no checklist; o cliente só vê o que a gestão marcar:

* O resumo é o procedimento do checklist (`checklist_modelos.descricao`,
  agora rotulado "Resumo do procedimento (POP/FIT)"); no celular, o bloco
  "Como fazer (resumo do POP)" mostra o texto e "Ver o POP completo".
* O documento (PDF, Excel, Word ou imagem; extensão E assinatura conferidas,
  25 MB, até 10 por checklist) vai em `checklist_documentos`, chave
  `checklists/<modelo>/docs/<hex>.<ext>`. Retirar só tira de uso
  (`is_active`): o registro e o arquivo ficam.
* Download sempre como anexo: `/rotas/documentos/<id>` (do local, pela
  carteira — o ASG abre pelo aplicativo; da biblioteca, para quem está
  logado) e `/cliente/documentos/<id>` (só os marcados "Mostrar ao cliente";
  a página do local no portal lista em "Procedimentos (POP/FIT)").
* Copiar da biblioteca leva o documento junto (mesmo arquivo, só da equipe).
* Migração `c8b3aed4b482`: tabela `checklist_documentos`.

ATENÇÃO: a presença lançada pelo supervisor tem o mesmo risco da D48
(controle de jornada): validar com RH e jurídico antes do piloto e constar no
aviso aos colaboradores (D25).

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
5. ~~CSP~~ — feita na Fase 9A para script; falta tirar o `style=` e o
   `<style>` das telas da Passagem para fechar também o estilo.
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
