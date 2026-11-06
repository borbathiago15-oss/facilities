# Uma passagem só por turno (migração `c85ddc846b35`)

Auditoria, Fase 3, leva L2 (aprovada pelo dono).

## O problema

Quando o "Encerrar turno" chegava duas vezes ao mesmo tempo (o celular sem
sinal reenviando da fila + o toque na tela), o sistema gravava **duas
passagens encerradas** do mesmo contrato, modelo, dia e turno, com as
pendências e ocorrências em dobro. O rascunho salvo em dois aparelhos ao
mesmo tempo duplicava pendências e ocorrências. E, antes de uma correção
antiga, cada "Salvar rascunho" criava uma linha nova — então pode haver
passagens repetidas no banco desde aquela época.

## A correção

1. **Trava do contrato** antes de procurar a passagem (`salvar_turno`): o
   segundo envio espera o primeiro gravar e encontra a passagem (e as
   pendências) que ele deixou. Sem migração.
2. **Chave única** `uq_diario_turnos_chave` em `diario_operacional_turnos`
   (`client_id`, `configuracao_id`, `data_turno`, `turno`), com migração.

## O que a migração faz com as passagens repetidas que já existirem

Em cada grupo repetido fica UMA:

- havendo encerrada, a **encerrada mais antiga** (a que chegou primeiro ao
  turno seguinte);
- só rascunhos: o **rascunho mais novo** (o que a tela já abria).

Tudo o que apontava para as outras (pendências, ocorrências, fotos e PDFs,
correções, trilha das pendências) passa a apontar para a que fica — nada é
apagado. As que saem são copiadas, inteiras, para
`_quarentena_c85ddc846b35_diario_operacional_turnos`; as linhas filhas, com o
turno de antes, para `_quarentena_c85ddc846b35_<tabela>`. A volta da migração
(`downgrade`) devolve tudo exatamente como estava. As quarentenas não são
apagadas por ninguém além de uma pessoa, depois de conferir.

## Antes do deploy: quantas repetidas existem hoje (só leitura)

Rode no banco de produção (não altera nada). A primeira consulta diz quantos
grupos e quantas passagens vão sair; a segunda lista cada grupo, para
conferir antes.

```sql
-- Resumo: grupos repetidos e passagens que vão para a quarentena.
SELECT count(*)                 AS grupos_repetidos,
       coalesce(sum(n - 1), 0)  AS passagens_que_saem
FROM (SELECT count(*) AS n
      FROM diario_operacional_turnos
      GROUP BY client_id, configuracao_id, data_turno, turno
      HAVING count(*) > 1) g;

-- Detalhe: cada grupo, com o contrato, o modelo e o que cada passagem tem.
SELECT c.name                                   AS contrato,
       g.nome                                   AS modelo,
       t.data_turno, t.turno, t.id, t.status, t.submitted_at,
       (SELECT count(*) FROM diario_operacional_pendencias p WHERE p.turno_id = t.id)  AS pendencias,
       (SELECT count(*) FROM diario_operacional_ocorrencias o WHERE o.turno_id = t.id) AS ocorrencias,
       (SELECT count(*) FROM diario_operacional_anexos a WHERE a.turno_id = t.id)      AS anexos
FROM diario_operacional_turnos t
JOIN clients c ON c.id = t.client_id
JOIN diario_operacional_configuracoes g ON g.id = t.configuracao_id
WHERE (t.client_id, t.configuracao_id, t.data_turno, t.turno) IN (
      SELECT client_id, configuracao_id, data_turno, turno
      FROM diario_operacional_turnos
      GROUP BY client_id, configuracao_id, data_turno, turno
      HAVING count(*) > 1)
ORDER BY c.name, g.nome, t.data_turno, t.turno, t.id;
```

Se a primeira consulta der `0`, a migração só cria o índice.

## Durante a migração

A tabela das passagens fica travada para **escrita** (leitura continua) do
começo da deduplicação até o índice ficar pronto — segundos, na escala de
hoje. Um encerramento que chegar nessa hora espera e entra em seguida.

## Ensaio

`python scripts/ensaio_migracoes_postgres.py postgresql://.../banco_test`
semeia passagens repetidas com filhos, sobe, confere quem ficou e para onde
foram os filhos, volta (todas as tabelas idênticas às de antes) e sobe de
novo.
