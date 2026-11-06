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
    mkdir -p "$UPLOAD_FOLDER"
    # Recursivo só na primeira vez (arquivos gravados quando ainda era root);
    # depois disso tudo nasce do usuário certo e o boot não percorre o volume.
    if [ "$(stat -c %U "$UPLOAD_FOLDER")" != "facilities" ]; then
      chown -R facilities "$UPLOAD_FOLDER"
    fi
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
# Arquivo das fotos antigas (ARQUIVO_FOTOS_NO_WEB=1): o lote que o
# administrador começa na tela anda aqui, a cada 5 minutos, quando as fotos
# estão no volume deste serviço (o agendador do Railway não o enxerga).
if [ "${ARQUIVO_FOTOS_NO_WEB:-0}" = "1" ]; then
  ( while true; do
      sleep "${ARQUIVO_FOTOS_INTERVALO:-300}"
      flask --app facilities anexos arquivar || echo "anexos arquivar: falhou (o site segue)"
    done ) &
fi
# Processos × threads (auditoria, Fase 3: 4 × 8 em 2 vCPU atendeu ~300
# pessoas; 2 × 4 parava em ~50). O pool do banco de cada processo tem o
# tamanho das threads (facilities/core/banco.py lê o mesmo GUNICORN_THREADS).
# Atrás de pooler, o pool dele precisa de >= processos × threads × 2 + 5
# (ver docs/BANCO_E_POOLER.md). Tudo pode ser trocado pelo painel.
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-4}"
export GUNICORN_THREADS="${GUNICORN_THREADS:-8}"
exec gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers "$WEB_CONCURRENCY" \
  --threads "$GUNICORN_THREADS" --timeout "${GUNICORN_TIMEOUT:-30}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-25}" \
  --keep-alive "${GUNICORN_KEEPALIVE:-5}" --access-logfile -
