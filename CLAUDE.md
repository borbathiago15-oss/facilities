# Trino Facilities — instruções para o Claude Code

## O que é
Sistema de facilities do Grupo Trino (passagem de turno + chamados), separado
do Trino Intelligence. Repositório: borbathiago15-oss/facilities (privado).

## Regras permanentes
- **NÃO ARRISCAR PERDER DADOS.** Coluna/tabela nova → migração Alembic em
  `migrations/versions/`. Migração que apaga ou reescreve linhas → quarentena
  antes (cópia da tabela, e o `downgrade()` devolve). Nunca `try/except: pass`
  em DDL. Prove upgrade → downgrade → upgrade num Postgres antes do PR.
- **Testes nos dois bancos.** `pytest -q` (SQLite) e
  `TEST_DATABASE_URL=postgresql://... pytest -q` (Postgres, como produção).
  Rode localmente antes de qualquer push: o CI confirma, não descobre.
- **Cota de CI.** O CI roda só em PR para o main e no main. Commite à vontade;
  push quando o bloco estiver completo; um PR por tema.
- **Merge e deploy só com o ok explícito do dono do produto.** PR com migração:
  diga o que ela muda no schema e espere a confirmação.
- **Nomes internos herdados do Trino** (`diario_operacional`, `client_id`,
  `master`/`pleno`): não renomear. Eles permitem trazer correções da Passagem
  do Trino Intelligence para cá. Na tela, a língua é a do Facilities
  ("contrato", "gestor", "técnico").
- Grava-se em UTC, exibe-se em Brasília (`facilities/tempo.py`,
  filtro `hora_local`).
- Textos de tela em português claro, para quem está no posto — não para quem
  já conhece o sistema.
