# Telas novas em React

Decisão do dono (31/10/2026): o servidor (regras, banco, migrações, testes)
**continua em Python**; só as telas mudam para React, **módulo por módulo**,
com o sistema sempre no ar. Cada fase é um PR por tema; a tela nova entra ao
lado da antiga e a substitui depois do aceite do dono.

## Fases

| Fase | O que entra | Estado |
|---|---|---|
| 0. Base | Projeto React, API `/api/v1`, casca (menu, barra, gaveta do celular), build no CI e no Docker | no `main` (PR #32) |
| 1a. App de campo: Início | `/novo/app`: turno por local, avisos do público, tarefas, pendências, chamados, presença, avisos no celular (`/api/v1/campo/inicio`) | no `main` (PR #33) |
| 1b. App de campo: turno e QR | `/novo/app/turno` e `/novo/app/ler-qr`: lista do turno, chegada, checklist, fotos antes/depois e por item, "Não deu", GPS, motivo de atraso, troca de área, não realizada, avisos do público e preventivas no ponto, leitor de QR. Dados em `/api/v1/campo/turno` (o mesmo `_dados_do_turno` da tela antiga); as ações seguem nas `/app/api/...`; a fila sem internet ainda é a de sempre (`fila-offline.js`, carregada pela casca), com as mesmas chaves no aparelho. Os e2e do turno rodam nas duas telas | no `main` (PR #34) |
| Admin: Armazenamento de fotos | `/novo/admin/armazenamento` (só do administrador, menu "Administração do sistema"): quanto as fotos ocupam, crescimento por mês, locais com mais fotos, prazo e arquivamento das fotos antigas (`/api/v1/admin/armazenamento`; regras em `facilities/arquivo_fotos/`, ver `docs/ARQUIVO_FOTOS.md`). Tela nova sem antiga correspondente | no `main` (PR #36) |
| 1c. App de campo: sem internet | `/novo/app`, `/novo/app/turno` e `/novo/app/ler-qr` abrem sem sinal, com as regras das telas antigas: o mesmo service worker (`static/pwa/sw.js`) guarda a casca, o JS/CSS compilado (`/static/`) e os dados que elas buscam (`/api/v1/eu`, `/api/v1/campo/inicio`, `/turno`, `/links`) no mesmo cache das telas antigas (`trino-telas`: apagado ao sair e na tela de login), uma cópia por endereço, idade máxima de 20 h no início e no turno, só GET e só quando quem pede é uma tela do campo (a gestão nunca tem cópia). Na tela, o selo "Sem sinal" e o aviso "esta é a cópia guardada neste aparelho às HH:MM"; o `/eu` da cópia é conferido com o dono da casca. A fila do aparelho continua a de sempre (`fila-offline.js`). E2e: `e2e/test_sem_internet.py` (o servidor de teste sai do ar de verdade: o `set_offline` do Playwright não alcança o service worker) | no `main` (PR #37) |
| 2a. Passagem de turno: a nova passagem e a leitura | `/novo/passagem-de-turno/turno` (o encarregado preenche: as duas abas — o que recebeu e o que entrega —, área, data e turno pré-selecionado no primeiro em aberto, perguntas do modelo, fotos, observação, ocorrências, pendências, tarefas da gestão, "Resolver"/"Continua", rascunho e encerramento) e `/novo/passagem-de-turno/turno/<id>` (a leitura, com as provas, a trilha das pendências e "Corrigir"). Mesma porta das antigas (a diretoria não abre a de lançar; a leitura confere a carteira). Dados em `/api/v1/passagem/turno?client_id=` e `/api/v1/passagem/turno/<id>`, da MESMA função das telas antigas (`passagem.rotas.contexto_turno` e `contexto_ver_turno`); as ações seguem nas `/passagem-de-turno/api/...`. Sem sinal, abre da cópia como a antiga (sw.js: a casca, `/api/v1/eu` e `/api/v1/passagem/turno`, só quando quem pede é ela) e guarda na fila de sempre (`fila-offline.js`). Os estilos são os do `<style>` das telas antigas (`frontend/src/passagem/passagem.css`). O painel, o relatório e a configuração (2b) continuam nas telas antigas; o início do campo novo já leva à passagem nova. E2e nas duas telas (fixture `passagem`) | no `main` (PR #38) |
| 2b. Passagem de turno: painel, relatório mensal e configuração | `/novo/passagem-de-turno/` (o painel: o recorte da query string — contrato, período, De/Até, área, turno —, os quatro indicadores, os três gráficos com o mesmo Chart.js de `static/vendor/chart`, carregado só nesta tela, as ocorrências com "Abrir chamado"/"Ver OS", as pendências críticas com "marcar resolvida", os últimos turnos, "Deixar pendência" e "Tarefa para um turno"), `/novo/passagem-de-turno/relatorio-mensal` (os cinco blocos do fechamento; o PDF continua no servidor, o "Baixar PDF" é o `?format=pdf` da rota antiga, com a área da tela) e `/novo/passagem-de-turno/configuracao` (modelos prontos, áreas, a lista e o editor do modelo: turnos, perguntas na ordem, tipos de ocorrência). Mesma porta das antigas (a configuração só com a permissão fina `diario_config`; o relatório confere a carteira; quem só lê não recebe as ações). Dados em `/api/v1/passagem/painel`, `/relatorio-mensal` e `/configuracao`, da MESMA função das telas antigas (`passagem.rotas.contexto_painel`, `contexto_relatorio_mensal` e `contexto_configuracao`); as ações seguem nas `/passagem-de-turno/api/...` e no formulário dos modelos prontos (o recado dele chega pela API). Os estilos são os do `<style>` das três telas antigas (`passagem.css`); os recados de uma vez só (`fc-aviso`) aparecem como nas antigas. Sem cópia no aparelho (são da gestão). Dentro das telas novas, a passagem nova e a leitura voltam ao painel novo. E2e nas duas telas (fixture `passagem`): `e2e/test_passagem_gestao.py`, `test_csp.py`, `test_visual.py` | este PR |
| 3. Cadastros e rotas da gestão | | |
| 4. Chamados, equipes, materiais, visitas, preventiva, relatórios, painéis | | |
| 5. Portal do cliente e QR público | | |
| 6. Login, 2FA, administração; sai o Jinja das telas | | |

## Como está montado

```
frontend/            o código das telas (React 19 + TypeScript + Vite)
  src/main.tsx       entrada; rotas abaixo de /novo
  src/api.ts         conversa com /api/v1 (mesma sessão, CSRF no cabeçalho)
  src/Casca.tsx      menu lateral + barra do topo (as classes do app.css)
  src/paginas/       uma pasta por tela
facilities/telas/    /novo/... (entrega a casca) e /api/v1 (a API das telas)
facilities/core/menu.py  quem vê cada item do menu — fonte única das telas
                     antigas (_menu.html) e das novas (/api/v1/eu)
facilities/static/app/   a compilação (gerada; fora do git)
```

* **Segurança não muda.** O login é a mesma sessão do Flask (cookie
  `HttpOnly`); os envios levam o CSRF no cabeçalho `X-CSRFToken`. Nenhum token
  novo (nada de JWT no navegador). A CSP continua `script-src 'self'`: o
  build não tem script embutido. As travas da sessão (segunda etapa, senha a
  trocar, portal do cliente) respondem JSON na `/api/v1`.
* **Visual.** As telas novas carregam o mesmo Bootstrap, os mesmos ícones e o
  mesmo `app.css` do site: as cores da marca (bordô `#9d202c`, moldura preta,
  faixa de quatro cores) e a fonte vêm de um lugar só.
* **Custo.** React, Vite, TypeScript e as bibliotecas são gratuitos (MIT). O
  Node só existe na compilação (estágio `telas` do Dockerfile e o CI); a
  imagem de produção não leva Node.
* **Versões fixadas** no `package.json`, todas publicadas há mais de duas
  semanas quando entraram; `npm audit` no CI. O `.npmrc` liga
  `legacy-peer-deps` por um defeito do npm 10.9 com as dependências opcionais
  do vitest.

## Comandos

```bash
cd frontend
npm ci                 # dependências (exatamente as do package-lock.json)
npm run build          # compila para facilities/static/app (o Flask serve)
npm run build -- --watch   # recompila a cada mudança, com o Flask rodando
npm run tipos          # TypeScript
npm test               # testes das telas (vitest)
```

Depois, `flask --app facilities run` e abrir `http://localhost:5000/novo/`.
Sem a compilação, `/novo/` responde 503 dizendo o que falta.

Testes: `pytest tests/test_telas_novas.py` (servidor) e
`pytest e2e/test_telas_novas.py` (navegador, celular e PC; precisa do build).

## Regras para cada módulo migrado

1. Regra de negócio fica no Python (`facilities/<módulo>/`); a tela só mostra
   e envia. Endpoint novo em `/api/v1/<módulo>/...`, com o mesmo
   `login_required` e as mesmas checagens de acesso da rota antiga; os dados
   vêm da MESMA função que monta a tela antiga (ex.:
   `campo.rotas.contexto_inicio`). As APIs JSON que já existem (as do
   aplicativo de campo, `/app/api/...`) são reaproveitadas como estão:
   `chamar('/app/api/...')`.
2. Toda rota nova com id entra na varredura de isolamento
   (`tests/test_isolamento_varredura.py`).
3. Os e2e do módulo passam a abrir a tela nova e continuam verdes nos dois
   perfis (celular e PC) — eles são o critério de aceite da fase.
4. O item do menu passa a apontar para `/novo/...` (em `core/menu.py`) só
   quando o dono aceitar; a tela antiga sai no mesmo PR.
5. Enquanto as duas telas convivem, os e2e do módulo rodam nas duas (as
   fixtures `campo` e `passagem` do `e2e/conftest.py`: `/app` e `/novo/app`,
   `/passagem-de-turno` e `/novo/passagem-de-turno`). A tela nova
   marca `data-tela-pronta` quando termina de desenhar; os testes esperam por
   ela (`abrir`/`tela_pronta`). Dentro das telas novas, os endereços já
   migrados apontam para `/novo/...` (a moldura e o início do campo levam ao
   turno e ao leitor novos); as telas antigas não mudam.
