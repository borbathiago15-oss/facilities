#!/bin/sh
# O schema de produção vem SÓ das migrações: aplica antes de subir o app.
set -e
flask --app facilities db upgrade
exec gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers "${WEB_CONCURRENCY:-2}" \
  --threads 4 --timeout 60 --access-logfile -
