FROM --platform=$BUILDPLATFORM node:26-bookworm-slim@sha256:662933cf47f013bc8e4beb31a6116448427a82057ba7c42c97e4c5ba766504c2 AS frontend
# Static frontend assets are architecture-independent; build them without QEMU.
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY scripts/check-bundle-budget.mjs scripts/check-csp-build.mjs ./scripts/
COPY public ./public
COPY frontend ./frontend
RUN npm run build

# Build supported source distributions on the target architecture. No build
# toolchain or registry cache is copied into the final runtime image.
FROM rust:1.99.1-slim-bookworm@sha256:86234e857a413004348b471d11a4ebe1aa92d2eae2b6b143cac68fd1ac3c48be AS rust-toolchain
FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS dependencies
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup PATH="/usr/local/cargo/bin:${PATH}"
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml VERSION CHANGELOG.md ./
COPY backend ./backend
# Deliberately unconstrained, matching the production pip dependency path.
RUN pip wheel --no-cache-dir --wheel-dir=/wheels .

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS runtime
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
# Installation is complete before dropping the build-time package installer.
# Removing pip also removes its vulnerable vendored dependency tree.
COPY --from=dependencies /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels news-dashboard \
    && rm -rf /wheels \
    && pip check \
    && pip uninstall -y pip \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "news-dashboard init && uvicorn news_dashboard.main:app --host 0.0.0.0 --port 8080 --app-dir backend"]
