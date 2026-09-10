FROM node:26-bookworm-slim@sha256:367679cf9792759492a486e4aa4b421764d71a9546a6dae8aab81a99eb797b3e AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY scripts/check-bundle-budget.mjs scripts/check-csp-build.mjs ./scripts/
COPY public ./public
COPY frontend ./frontend
RUN npm run build

FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS runtime
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
