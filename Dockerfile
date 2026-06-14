FROM node:26-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY frontend ./frontend
RUN npm run build

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEWS_DASHBOARD_DB=/data/news-dashboard.db
WORKDIR /app
RUN adduser --disabled-password --gecos '' appuser && mkdir -p /data && chown -R appuser:appuser /data
COPY pyproject.toml ./
COPY backend ./backend
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir . && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "news-dashboard init && uvicorn news_dashboard.main:app --host 0.0.0.0 --port 8080 --app-dir backend"]
