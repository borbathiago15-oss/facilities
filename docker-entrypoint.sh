#!/bin/sh
# O schema de produção vem SÓ das migrações: aplica antes de subir o app.
#
# Com argumentos, roda o comando pedido SEM migrar — é o caso dos serviços
# agendados (ex.: Railway Cron com `flask --app facilities agendador rodar`),
# que não podem disputar a migração com o deploy do site.
set -e
# Começou como root (padrão da imagem, ou RAILWAY_RUN_UID=0): acerta o dono
# do volume dos anexos e larga o privilégio. O app nunca roda como root.
if [ "$(id -u)" = "0" ]; then
  if [ -n "${UPLOAD_FOLDER:-}" ]; then
    mkdir -p "$UPLOAD_FOLDER" && chown -R facilities "$UPLOAD_FOLDER"
  fi
  chown facilities /app/instance 2>/dev/null || true
  exec gosu facilities "$0" "$@"
fi
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
flask --app facilities db upgrade
# Primeiro administrador pelo painel da hospedagem (ADMIN_INICIAL_EMAIL): só
# age quando não há administrador ativo. Falhar aqui não derruba o site.
flask --app facilities admin-inicial || echo "admin-inicial: falhou (o site sobe assim mesmo)"
# Cópia diária dos anexos do volume para o R2 (ANEXOS_ESPELHO_R2=1 + R2_*):
# o único serviço que enxerga o volume é este, por isso o laço mora aqui.
if [ "${ANEXOS_ESPELHO_R2:-0}" = "1" ]; then
  ( while true; do
      sleep "${ANEXOS_ESPELHO_INTERVALO:-86400}"
      flask --app facilities anexos espelhar || echo "anexos espelhar: falhou (o site segue)"
    done ) &
fi
exec gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers "${WEB_CONCURRENCY:-2}" \
  --threads 4 --timeout 60 --access-logfile -
