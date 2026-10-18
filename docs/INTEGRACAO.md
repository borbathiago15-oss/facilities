# Integração Facilities → Trino Intelligence (Fase 8)

API **só de leitura**. O Facilities entrega dados; o Intelligence nunca
escreve aqui (D13, D42). O custo de material **não sai** pela API (D37).

## Chave

O administrador cria a chave em **Integração** (`/admin/integracao/`),
escolhendo os locais que ela lê (ou "todos"). A chave aparece **uma vez**;
guarde-a no cofre de segredos do Intelligence (variável de ambiente, nunca
no código). Revogar corta o acesso na hora. Todo acesso fica registrado na
mesma tela (quando, rota, parâmetros, resposta) — sem a chave.

```
Authorization: Bearer fac_<prefixo>_<segredo>
```

Limite: 600 consultas por hora por chave. Período máximo: 92 dias por consulta.

## Rotas

Datas no formato `AAAA-MM-DD`, no horário de Brasília. Horários na resposta
em UTC (`...Z`). `local` (opcional) é o id do local; fora do escopo da chave
dá 403.

| Rota | O que devolve |
|---|---|
| `GET /api/integracao/v1/locais` | id, nome, `cost_center`, cliente, centro de custo do cliente, estado |
| `GET /api/integracao/v1/chamados?de=&ate=` | chamados abertos no período: número `OS-00001`, prioridade, situação, origem, prazo, resolvido, tempo parado, `no_prazo` |
| `GET /api/integracao/v1/aderencia?de=&ate=` | por local e dia: previstas, vencidas ou encerradas, no prazo, com atraso, não realizadas, perdidas, `aderencia_pct` |
| `GET /api/integracao/v1/nao-conformidades?de=&ate=` | `referencia` (`NC-123`), item, resposta, ponto, ambiente, checklist, chamado |
| `GET /api/integracao/v1/visitas?de=&ate=` | visitas de supervisão: vencimento, situação, não conformes, chamado |
| `GET /api/integracao/v1/nota?de=&ate=` | nota por local (0 a 100), faixa (`critica`, `atencao`, `boa`) e os quatro indicadores |

Resposta: `{"versao": 1, "de": "...", "ate": "...", "itens": [...], "truncado": false}`.
A mesma consulta devolve o mesmo corpo; a hora da geração vai no cabeçalho
`X-Gerado-Em`.

## Plano de ação (D42 — por referência)

O plano de ação continua sendo criado **no Intelligence**. Para ligar a não
conformidade, o plano guarda a `referencia` (`NC-123`), que também aparece na
tela da execução no Facilities.

## O que falta no Intelligence (repositório próprio, com as regras de lá)

Fica para uma tarefa no repositório do Intelligence (cota de CI e deploy de
lá):

1. Duas variáveis no `src/worker.js`: `FACILITIES_API_URL` e `FACILITIES_API_KEY`.
2. Job de busca diária (ex.: `nota` e `aderencia` do dia anterior), casando o
   local pelo `cost_center` — **antes, conferir a D34**: `cost_center`
   preenchido e sem repetição em todos os contratos do Intelligence.
3. Carona no `/healthz`: `GET /api/integracao/v1/locais` respondendo 200.

## Aceite

Um mês de dados conferido lado a lado nos dois sistemas: o painel do
Facilities (`/painel`) e o que o Intelligence leu pela API usam as mesmas
funções, então os números precisam bater.
