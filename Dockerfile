# Trino Facilities — imagem de produção.

# Estágio 1: as telas novas (React, frontend/). O Node só existe aqui, na
# compilação; a imagem final não leva Node nenhum, só os arquivos prontos.
FROM node:22-slim AS telas
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build -- --outDir /telas

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

# gosu: o contêiner começa como root só para acertar o dono do volume dos
# anexos e, em seguida, larga o privilégio (docker-entrypoint.sh). O app em
# si nunca roda como root (auditoria SEC-008 / N-05).
RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m facilities

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# O código pertence ao root e é SÓ LEITURA para o app: quem conseguir
# executar algo no processo não grava um .py que sobreviva até o próximo
# deploy. O que NÃO entra (.env, instance/, .venv, .git, testes) está no
# .dockerignore.
COPY . .
COPY --from=telas /telas facilities/static/app
# Só a instance/ (anexos em disco quando não há volume) precisa ser
# gravável. O volume (/data) é acertado no entrypoint, porque só existe lá.
RUN chmod +x docker-entrypoint.sh && mkdir -p instance && chown facilities instance

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
