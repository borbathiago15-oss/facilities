# Trino Facilities — imagem de produção.
FROM python:3.11-slim

# O fuso da operação: date.today() e os carimbos de hora acertam em todo o
# sistema (lição do Trino Intelligence: sem isto, depois das 21h o "hoje"
# virava amanhã).
ENV TZ=America/Sao_Paulo \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x docker-entrypoint.sh && useradd -m facilities && chown -R facilities /app
USER facilities

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
