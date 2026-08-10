FROM node:26-bookworm-slim@sha256:cd565714d4da3e84bfd341e31448f81d47c6362198f152345297c9c1154e6341 AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY scripts/check-bundle-budget.mjs scripts/check-csp-build.mjs ./scripts/
COPY public ./public
COPY frontend ./frontend
RUN npm run build

FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data
COPY pyproject.toml VERSION CHANGELOG.md ./
COPY backend ./backend
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir . && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "news-dashboard init && uvicorn news_dashboard.main:app --host 0.0.0.0 --port 8080 --app-dir backend"]
