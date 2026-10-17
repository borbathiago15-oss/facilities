# Trino Facilities

Sistema de facilities do Grupo Trino: **passagem de turno** e **chamados /
ordens de serviço** para os contratos de limpeza e conservação, portaria e
segurança e manutenção predial. Login próprio, funciona no celular (app
instalável, com fila para quando não há sinal).

A Passagem de Turno veio do Trino Intelligence, com os mesmos nomes internos
(tabelas `diario_operacional_*`, `client_id`, perfis `master`/`pleno`) — o que
permite trazer correções de lá para cá sem tradução. O Trino Intelligence
continua com a sua própria Passagem; os dois sistemas são independentes.

## O que tem

| Módulo | O que faz |
|---|---|
| Passagem de Turno | checklist da rotina, pendências que atravessam turnos (contadas por área), ocorrências, tarefas da gestão para o turno, correção de passagem, painel, relatório mensal em PDF, modelos prontos por serviço |
| Chamados | abrir (com fotos), atribuir a um técnico, prazo pela prioridade, em espera, resolver (foto do serviço), confirmar ou reabrir, trilha completa, números de prazo |
| Núcleo | pessoas e perfis, contratos, carteira de acesso por contrato, avisos, troca obrigatória de senha, bloqueio por tentativas |

Perfis: **Administrador** (tudo), **Gestor** (os contratos dele; configura a
passagem, atribui chamados), **Encarregado** (passagem e abrir chamados),
**Técnico de manutenção** (atende chamados e faz a passagem da equipe),
**Diretoria** (lê tudo, não altera nada).

## Rodar localmente

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY=desenvolvimento SESSION_COOKIE_SECURE=0
flask --app facilities criar-admin        # mostra uma senha temporária
flask --app facilities run                # http://127.0.0.1:5000
```

Sem `DATABASE_URL`, usa SQLite em `instance/facilities.db` (o schema é criado
sozinho). Primeiros passos na tela: cadastre um contrato, as pessoas, e em
**Passagem de Turno → Configurar** use "Começar com um modelo pronto".

## Testes

```bash
pytest -q                                                    # SQLite
TEST_DATABASE_URL=postgresql://.../facilities_testes pytest -q   # Postgres (zera o banco!)
```

## Produção

- Banco **Postgres**; o schema vem só das migrações (`flask db upgrade`, que o
  `docker-entrypoint.sh` roda antes do gunicorn). O boot não faz DDL.
- Variáveis: `DATABASE_URL`, `SECRET_KEY` (obrigatória), e para anexos no
  Cloudflare R2: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
  `R2_BUCKET` (sem elas, os anexos vão para o disco local — só para teste).
- `GET /healthz` responde 200 sem login e sem banco (liveness).
- Imagem: `docker build -t trino-facilities .` (fuso `America/Sao_Paulo`).
