#!/bin/sh
# O schema de produção vem SÓ das migrações: aplica antes de subir o app.
#
# Com argumentos, roda o comando pedido SEM migrar — é o caso dos serviços
# agendados (ex.: Railway Cron com `flask --app facilities agendador rodar`),
# que não podem disputar a migração com o deploy do site.
set -e
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
flask --app facilities db upgrade
# Primeiro administrador pelo painel da hospedagem (ADMIN_INICIAL_EMAIL): só
# age quando não há administrador ativo. Falhar aqui não derruba o site.
flask --app facilities admin-inicial || echo "admin-inicial: falhou (o site sobe assim mesmo)"
exec gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers "${WEB_CONCURRENCY:-2}" \
  --threads 4 --timeout 60 --access-logfile -
