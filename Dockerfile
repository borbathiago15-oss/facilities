# Trino Facilities — imagem de produção.
FROM python:3.11-slim

# O fuso da operação: date.today() e os carimbos de hora acertam em todo o
# sistema (lição do Trino Intelligence: sem isto, depois das 21h o "hoje"
# virava amanhã).
# EXIGIR_DATABASE_URL: sem DATABASE_URL o app subiria num SQLite dentro do
# contêiner, que some a cada reinício — com tudo o que foi lançado. Nesta
# imagem a fábrica recusa subir assim (facilities/__init__.py).
ENV TZ=America/Sao_Paulo \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    EXIGIR_DATABASE_URL=1

RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m facilities

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Já com o dono certo: o antigo "chown recursivo" numa camada própria
# duplicava todos os bytes da imagem. O que NÃO entra (.env, instance/,
# .venv, .git, testes) está no .dockerignore.
COPY --chown=facilities . .
# Só a pasta /app e a instance/ (anexos em disco, se STORAGE_BACKEND=local)
# precisam ser graváveis: chown só delas, sem copiar arquivo nenhum.
RUN chmod +x docker-entrypoint.sh && mkdir -p instance && chown facilities /app instance
USER facilities

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
