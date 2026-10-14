# 1. construction de l'application React
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2. socle Python : le serveur qui rend le catalogue et sert l'application
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOSSIER_WEB=/app/web/dist
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server ./server

# 3. tests (docker compose --profile tests run --rm front-tests) : l'API est simulée
FROM base AS tests
COPY requirements-dev.txt pytest.ini ./
RUN pip install -r requirements-dev.txt
COPY tests ./tests
CMD ["pytest", "-q"]

# 4. image livrée
FROM base
COPY --from=web /web/dist ./web/dist
RUN useradd --uid 1000 --no-create-home cinetint
USER cinetint
EXPOSE 8080
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
