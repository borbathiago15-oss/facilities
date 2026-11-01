# Telas novas em React

Decisão do dono (31/10/2026): o servidor (regras, banco, migrações, testes)
**continua em Python**; só as telas mudam para React, **módulo por módulo**,
com o sistema sempre no ar. Cada fase é um PR por tema; a tela nova entra ao
lado da antiga e a substitui depois do aceite do dono.

## Fases

| Fase | O que entra | Estado |
|---|---|---|
| 0. Base | Projeto React, API `/api/v1`, casca (menu, barra, gaveta do celular), build no CI e no Docker | no `main` (PR #32) |
| 1a. App de campo: Início | `/novo/app`: turno por local, avisos do público, tarefas, pendências, chamados, presença, avisos no celular (`/api/v1/campo/inicio`) | este PR |
| 1b. App de campo: turno e QR | Lista do turno, checklist, fotos antes/depois, GPS, motivo de atraso, troca de área, leitor de QR (reusa `/app/api/...`) | a seguir |
| 1c. App de campo: sem internet | Fila do aparelho (IndexedDB) e cópia das telas para abrir sem sinal | |
| 2. Passagem de turno | | |
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
