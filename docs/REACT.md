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
| 2b. Passagem de turno: painel, relatório mensal e configuração | `/novo/passagem-de-turno/` (o painel: o recorte da query string — contrato, período, De/Até, área, turno —, os quatro indicadores, os três gráficos com o mesmo Chart.js de `static/vendor/chart`, carregado só nesta tela, as ocorrências com "Abrir chamado"/"Ver OS", as pendências críticas com "marcar resolvida", os últimos turnos, "Deixar pendência" e "Tarefa para um turno"), `/novo/passagem-de-turno/relatorio-mensal` (os cinco blocos do fechamento; o PDF continua no servidor, o "Baixar PDF" é o `?format=pdf` da rota antiga, com a área da tela) e `/novo/passagem-de-turno/configuracao` (modelos prontos, áreas, a lista e o editor do modelo: turnos, perguntas na ordem, tipos de ocorrência). Mesma porta das antigas (a configuração só com a permissão fina `diario_config`; o relatório confere a carteira; quem só lê não recebe as ações). Dados em `/api/v1/passagem/painel`, `/relatorio-mensal` e `/configuracao`, da MESMA função das telas antigas (`passagem.rotas.contexto_painel`, `contexto_relatorio_mensal` e `contexto_configuracao`); as ações seguem nas `/passagem-de-turno/api/...` e no formulário dos modelos prontos (o recado dele chega pela API). Os estilos são os do `<style>` das três telas antigas (`passagem.css`); os recados de uma vez só (`fc-aviso`) aparecem como nas antigas. Sem cópia no aparelho (são da gestão). Dentro das telas novas, a passagem nova e a leitura voltam ao painel novo. E2e nas duas telas (fixture `passagem`): `e2e/test_passagem_gestao.py`, `test_csp.py`, `test_visual.py` | no `main` (PR #39) |
| 3a. Cadastros | Nos mesmos endereços das antigas, abaixo de `/novo`: `/novo/cadastros/` (início), `/empresas`, `/clientes`, `/estados` e `/trilha` (só o administrador), `/novo/cadastros/locais/<id>` (a estrutura do local: setores, ambientes, equipamentos e pontos, com `?inativos=1`) e o histórico do local; o cadastro simplificado `/novo/clientes`, `/novo/clientes/<id>`, `/novo/centros/<id>` (áreas e o "Marcar a posição deste local" pelo GPS, `?aba=rotas`) e `/novo/centros/<id>/rotas/<id>` (as linhas e quem faz); o assistente `/novo/novo-contrato`, `/novo-contrato/cliente/<id>/local`, `/novo-contrato/<id>/estrutura` e `/novo-contrato/<id>/equipe` (com a página "Convite pronto") e `/novo/convites`. Mesma porta das antigas (`admin_required`; a carteira e o perfil de cada módulo; a diretoria só lê). Dados em `GET /api/v1/cadastros/...`, da MESMA função das telas antigas (`contexto_*` em `cadastros/rotas.py`, `centros_telas.py` e `novo_contrato.py`). As telas antigas enviam formulários HTML; as novas enviam o mesmo formulário (`FormData`, com a logo) para `POST /api/v1/cadastros/...` — o mesmo caminho da antiga abaixo de `/api/v1/cadastros` (o do cadastro simplificado abaixo de `/api/v1/cadastros/centros`) —, que chama a MESMA ação (`acao_*`: a regra, o commit e o recado). A resposta é o recado (o flash da antiga), o endereço de volta já na tela nova e, na recusa, 400 com a mesma frase; o convite e o link novo respondem com a página "Convite pronto" (o link não passa por endereço nem pelo histórico). As etiquetas de QR (PDF), o `/q/<código>`, a logo e o link público do convite continuam no servidor; a rotina dos locais, a biblioteca e os modelos (3b) e as pessoas e locais do administrador seguem nas antigas. Sem cópia no aparelho. E2e nas duas telas (fixture `cadastros`): `e2e/test_centros.py`, `test_novo_contrato.py`, `test_gps.py`, `test_cadastros.py` | no `main` (PR #40) |
| 3b. Rotas da gestão | Nos mesmos endereços das antigas, abaixo de `/novo`: `/novo/rotas/` (um cartão por local), `/novo/rotas/locais/<id>` (checklists e rotas do local: copiar da biblioteca, criar checklist, criar rota do zero), `/novo/rotas/biblioteca` (instalar os modelos prontos, criar checklist), `/novo/rotas/biblioteca/rotas/nova` e `/<id>` (a rota pronta; só o administrador edita), `/novo/rotas/locais/<id>/rota-pronta?modelo=` (aplicar, com as linhas a marcar), `/novo/rotas/locais/<id>/importar-plano` (a planilha do cliente: a prévia e o "Criar"), `/novo/rotas/modelos/<id>` (o checklist: POP/FIT, resumo, perguntas, fotos de referência e a publicação da versão), `/novo/rotas/<id>` (a rota: atividades em lote, alterar e tirar, escala, turno e desativar), `/novo/rotas/locais/<id>/feriados?ano=`, `/novo/rotas/locais/<id>/dia?data=` (tarefas, ocorrências do público com "Resolvida", elogios, chegadas, presenças, fora da rota) e `/novo/rotas/execucoes/<id>` (respostas, fotos, não conformidades com "Abrir chamado", correção). Mesma porta das antigas (a gestão monta; a gestão, o supervisor e a diretoria acompanham; a biblioteca é do administrador; a carteira do local). Dados em `GET /api/v1/rotas/...`, da MESMA função das telas antigas (`contexto_*` em `rotas/telas.py`); os envios vão ao mesmo caminho abaixo de `/api/v1` e chamam a MESMA ação (`acao_*`, e `publico.acao_ocorrencia_no_site` para a ocorrência), com o mesmo recado, a mesma recusa (400) e o endereço de volta já na tela nova. A planilha e as fotos de referência vão no próprio `FormData`; a prévia da planilha, que na antiga é a página da resposta, volta como dados. Os arquivos (POP/FIT, fotos, referências, a foto da ocorrência), os chamados, as preventivas, a equipe e as visitas continuam nas telas antigas; a liberação de chegada pela gestão (`POST /rotas/locais/<id>/chegadas`) não tem formulário em tela nenhuma e ficou como está. Dentro das telas novas, os cadastros (3a) passam a levar à rotina nova. Junto, as telas novas passam a ser carregadas por grupo (`React.lazy`: campo, passagem, cadastros, rotas, admin — um arquivo por grupo em `static/app/assets/`): a entrada caiu de ~555 KB para ~304 KB; o service worker guarda os pedaços como todo `/static/` (o campo abre sem sinal como antes). Sem cópia no aparelho (gestão). E2e nas duas telas (fixture `rotas`): `e2e/test_rotas_gestao.py`; o dia e a execução também em `test_gps.py` | no `main` (PR #42) |
| 4a. Chamados, demandas e preventiva | Nos mesmos endereços das antigas, abaixo de `/novo`: `/novo/chamados/` (a lista: os cinco números do topo, os filtros de contrato, prioridade e categoria, as abas Em aberto, Atrasados, Comigo, Aguardando confirmação e Todos, os selos de prioridade, situação e prazo), `/novo/chamados/novo` (abrir: contrato, a área do contrato escolhido, categoria, prioridade e as fotos) e `/novo/chamados/<id>` (o chamado: "O que fazer agora" com as ações que a pessoa tem — iniciar, retomar, fechar, resolver com a foto do serviço, pôr em espera, reabrir, atribuir, mudar prioridade, comentar, cancelar —, o histórico, as fotos e arquivos com "Anexar" e o material usado com "Lançar material"); `/novo/demandas/` (a fila única com as contagens por situação e o filtro de local, tipo e situação) e `/novo/preventiva/locais/<id>` (os planos do local: os três últimos ciclos com a OS, "Editar", desativar/reativar e o "Novo plano"). Mesma porta das antigas (o módulo `chamados` — quem consulta e quem age —, a carteira, a gestão monta a preventiva, o supervisor e a diretoria acompanham; o cliente do portal não entra). Dados em `GET /api/v1/chamados/...`, `/api/v1/demandas/` e `/api/v1/preventiva/locais/<id>`, da MESMA função das telas antigas (`contexto_*` em `chamados/rotas.py`, `demandas.py` e `preventiva/telas.py`), com as horas, as datas e os números já escritos como as antigas escrevem (o selo do prazo, a % e o tempo médio com vírgula, o valor do material). Os envios vão ao mesmo caminho abaixo de `/api/v1` e chamam a MESMA ação (`acao_*`; o "Lançar material" chama `materiais.telas.acao_consumo`, de volta ao chamado), com o mesmo recado, a mesma recusa (400) e o endereço de volta já na tela nova; as fotos vão no próprio `FormData`. As fotos e os PDFs (`/chamados/anexos/<id>`) continuam servidos pelo servidor. Dentro das telas novas, os chamados, as demandas e a preventiva passam a levar às novas (a rotina dos locais, o painel da passagem depois do "Abrir chamado" e o aplicativo de campo novo); as visitas, os pedidos de insumo, as cobranças e a tela dos materiais continuam nas antigas. Sem cópia no aparelho (gestão). E2e nas duas telas (fixture `chamados`): `e2e/test_chamados_gestao.py` | este PR |
| 4b. Equipes, materiais, visitas, relatórios, painéis | | |
| 5. Portal do cliente e QR público | | |
| 6. Login, 2FA, administração; sai o Jinja das telas | | |

## Como está montado

```
frontend/            o código das telas (React 19 + TypeScript + Vite)
  src/main.tsx       entrada; rotas abaixo de /novo
  src/api.ts         conversa com /api/v1 (mesma sessão, CSRF no cabeçalho)
  src/Casca.tsx      menu lateral + barra do topo (as classes do app.css)
  src/paginas/       uma pasta por tela
  src/<grupo>/paginas.ts(x)  a entrada de cada grupo de telas (um arquivo do
                     build por grupo, carregado só quando uma tela dele abre)
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
   `chamar('/app/api/...')`. Onde a tela antiga envia formulário HTML (que
   redireciona), a ação dela sai da rota para uma função (`acao_*`, que deixa
   o recado e devolve o endereço de volta) e a API das telas novas a chama
   no mesmo caminho abaixo de `/api/v1/<módulo>` (Fase 3a).
2. Toda rota nova com id entra na varredura de isolamento
   (`tests/test_isolamento_varredura.py`).
3. Os e2e do módulo passam a abrir a tela nova e continuam verdes nos dois
   perfis (celular e PC) — eles são o critério de aceite da fase.
4. O item do menu passa a apontar para `/novo/...` (em `core/menu.py`) só
   quando o dono aceitar; a tela antiga sai no mesmo PR.
5. Enquanto as duas telas convivem, os e2e do módulo rodam nas duas (as
   fixtures `campo`, `passagem`, `cadastros`, `rotas` e `chamados` do
   `e2e/conftest.py`: `/app` e `/novo/app`, `/passagem-de-turno` e
   `/novo/passagem-de-turno`, e o prefixo `''` ou `/novo` dos cadastros, da
   rotina dos locais e dos chamados). A tela nova
   marca `data-tela-pronta` quando termina de desenhar; os testes esperam por
   ela (`abrir`/`tela_pronta`). Dentro das telas novas, os endereços já
   migrados apontam para `/novo/...` (a moldura e o início do campo levam ao
   turno e ao leitor novos); as telas antigas não mudam.
