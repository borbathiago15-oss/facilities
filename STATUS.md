# Situação do Trino Facilities

Atualizado em 06/11/2026. Para o histórico e as decisões do dono, veja
`docs/CONTINUIDADE.md`; para as regras de quem mexe no código, `CLAUDE.md`.
Atualize este arquivo no mesmo PR que mudar o que ele diz.

## O que funciona hoje

Todos os módulos abaixo estão no `main`, com testes em SQLite e em Postgres
(descrição de cada um no `README.md`, "O que tem"):

* Passagem de turno (vinda do Trino Intelligence), chamados / ordens de
  serviço, preventiva, painel de demandas, portal do cliente (desligado até
  os termos do jurídico: `CLIENTE_EXTERNO_LIBERADO=0`), equipe do posto,
  materiais, painel com a nota por local, relatórios mensais (tela, PDF e
  Excel), integração só de leitura com o Trino Intelligence, visitas de
  supervisão, cadastros, rotas e checklists com o agendador, aplicativo de
  campo (instalável, com fila sem internet e avisos no celular), QR público,
  arquivo das fotos antigas.
* Núcleo: login próprio com segunda etapa obrigatória para a gestão e o
  supervisor, bloqueio por tentativas, cifra dos campos sensíveis no banco
  (obrigatória na imagem de produção desde 06/11/2026), limites de acesso
  com Redis, tempos limite do banco com 503 "tente de novo em instantes".
* Hospedagem de testes no Railway (`docs/DEPLOY_RAILWAY.md`), com backup
  diário do banco.

## Telas novas (React) — `docs/REACT.md`

* Fases 0 a 5, 6a e 1d no `main`: todas as telas da equipe e do cliente
  existem também em `/novo`, chamando as mesmas funções das antigas.
* **Estreia (fase 6b) pendente:** as telas novas viram o padrão (menu,
  sino, depois do login) e as antigas saem — só depois do teste do dono no
  celular dele e do aceite.
* Ficam no servidor, de propósito: login, segunda etapa do login, aceite do
  convite, página de erro e o QR público.

## O que está pela metade

* As travas da sessão (trocar a senha, ativar a segunda etapa) ainda levam
  às telas antigas; a 6b decide.
* Envio do aviso no celular ainda acontece dentro da requisição de quem abriu
  o chamado (falta a fila — leva L5).
* Integração: o lado do Trino Intelligence (buscar os dados todo dia) não foi
  feito; fica no repositório de lá (`docs/INTEGRACAO.md`).
* CSP de estilo: as telas da Passagem ainda têm `style=` embutido.

## Defeitos conhecidos (testes `xfail(strict=True)`)

Cada um é um teste que falha de propósito enquanto o defeito existir;
corrigido, o teste passa a reprovar e é só tirar a marca. São 11 defeitos
em 13 casos de teste (alguns testes rodam com mais de uma entrada); em
06/11/2026 a suíte deu 13 `xfailed` no SQLite e no Postgres.

`tests/test_auditoria_entradas.py` (leva L4, validação das entradas):

1. Formulário antigo enviado com a sessão vencida mostra o JSON cru
   "Sessão expirada" em vez de levar ao login.
2. E1 — corpo JSON que não é objeto (lista, texto, número) dá 500.
3. E2 — campo de texto que chega como número no JSON dá 500 (Passagem, push).
4. E3 — id no corpo que não cabe na coluna dá 500 ao gravar (área e modelo
   da Passagem).
5. E3 (só SQLite) — id gigante no corpo estoura no `db.session.get`
   (chamados, materiais, preventiva, cadastros).
6. E4 — `int()` sem tratamento: modelo de passagem sem contrato e área com
   contrato "abc" dão 500.
7. E5 (Postgres) — byte nulo (`\x00`) num texto dá 500.
8. E6 (Postgres) — texto maior que a coluna dá 500 (nome do turno, título da
   tarefa do turno).
9. E7 (só SQLite, desenvolvimento) — id do caminho acima de 2^63 dá 500.
10. E9 — contrato que não existe aceito para o administrador na Passagem
    (no Postgres sai 500; no SQLite grava área órfã).

`tests/test_auditoria_externos.py` (leva L5, fila):

11. Quem abre um chamado urgente espera o tempo limite do push (3 s) com o
    serviço de push pendurado.

## Próximos passos

1. **Pacote rápido da linha de base (este):** `.env.example`, cifra
   obrigatória na produção, log sem dado de conexão nem dado pessoal, regra
   das dependências, este arquivo e `docs/CONFIG-MANUAL.md`. Antes do deploy,
   a chave da cifra no `web` e no `agendador` (ver o topo de
   `docs/SEGURANCA_DADOS.md`).
2. **Auditoria — redução de consultas** por tela (as idas e voltas ao banco
   são o gargalo medido na carga).
3. **Leva L4 — validação das entradas:** os 10 defeitos acima.
4. **Leva L5 — infraestrutura:** fila (RQ/Redis) para push e e-mail, fotos
   servidas por URL assinada do R2 em vez de passar pelo servidor, Redis
   também para a fila.
5. **Estreia das telas novas (6b)**, depois do teste do dono no celular.
6. **Banco de produção:** o novo provedor do banco está pendente de decisão
   (`docs/BANCO_E_POOLER.md` já cobre pooler Neon/Supabase).

## Dependências

Política (regra no `CLAUDE.md`): antes de acrescentar um pacote, dizer para
que serve e se dá para evitar; nunca uma versão publicada há menos de 7 dias;
versão exata fixada; anotar aqui, com o motivo.

* Python: `requirements.txt` (produção) e `requirements-dev.txt` /
  `requirements-e2e.txt` (testes). Todas com versão exata.
* Telas novas: `frontend/package.json` + `package-lock.json`, versões exatas.
* Auditoria de vulnerabilidades das dependências: no CI (`pip-audit` e `npm audit` em `.github/workflows/ci.yml`).

| Data | Pacote | Por quê |
|---|---|---|
| — | (nenhuma dependência nova desde a criação deste arquivo) | — |

## Pontos em que paramos para pedir decisão

* **Deploy desta versão:** só depois de a `FIELD_ENCRYPTION_KEY` estar no
  `web` e no `agendador` — senão o sistema não sobe. O dono põe a chave e
  autoriza o deploy.
* **Estreia das telas novas (6b):** aceite do dono depois do teste no celular.
* **Novo provedor do banco de produção:** a decidir.
* **Portal do cliente:** liberar só com os termos do jurídico (Grupo C).
* **Presença aleatória (D48):** RH e jurídico validarem antes de ligar nas
  rotas com gente de verdade.
* **Nome de quem fez o checklist no portal:** aguarda a D25.
* **Integração:** conferir a D34 (`cost_center` único) antes do job do
  Intelligence.
* **Leva L5 (fila e URL assinada):** muda a infraestrutura (Redis como fila,
  um processo a mais); precisa do ok do dono antes de começar.
