# The hosted server: the same application people sign in to over the internet.
# (The Windows desktop app is built separately and does not use this.)
#
#   docker build -t shabetz .
#   docker run -p 8000:8000 --env-file .env shabetz
#
# On first start with no administrator, the log prints a one-time setup code
# that the first visitor must enter.

# ---------------------------------------------------------------- frontend
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------ server
FROM python:3.12-slim

# Pango and friends are what WeasyPrint needs for PDF export; without them the
# app still runs and simply does not offer PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra pdf --no-install-project

COPY src/ ./src/
COPY --from=frontend /build/dist ./src/shabetz/web/
RUN uv sync --frozen --no-dev --extra pdf

# Never run the server as root.
RUN useradd --system --uid 10001 shabetz && chown -R shabetz /app
USER shabetz

ENV PATH="/app/.venv/bin:$PATH" \
    SHABETZ_ENVIRONMENT=prod \
    SHABETZ_DEPLOYMENT=server \
    SHABETZ_COOKIE_SECURE=true

# 8000 unless the host names another port in $PORT, as Render does.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/meta/health', timeout=4)"

CMD ["shabetz", "serve", "--host", "0.0.0.0"]
