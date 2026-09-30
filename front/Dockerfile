# 1. construction de l'application React
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2. serveur Python qui rend le catalogue et sert l'application
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOSSIER_WEB=/app/web/dist
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server ./server
COPY --from=web /web/dist ./web/dist
RUN useradd --uid 1000 --no-create-home cinetint
USER cinetint
EXPOSE 8080
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
