# syntax=docker/dockerfile:1
# CareerGraph image: one slim, non-root image for the UI, the CLI and the CronJob.
#   docker build -f deploy/docker/Dockerfile -t careergraph .                  (runtime, default)
#   docker build -f deploy/docker/Dockerfile --target latex -t careergraph:latex .  (adds tectonic)

ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.8.23

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
# Editable install on purpose: the package locates config/, templates/ and data/demo/ relative
# to /app, exactly as in a source checkout.
RUN uv sync --locked --no-dev

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    APP_MODE=demo UI_HOST=0.0.0.0 UI_PORT=8501 \
    DATA_DIR=/data CACHE_DIR=/data/cache OUTPUT_DIR=/outputs LOG_FORMAT=json
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /data /outputs /app/profiles/me \
    && chown -R app:app /data /outputs /app/profiles/me
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY pyproject.toml .env.example ./
COPY src ./src
COPY ui ./ui
COPY config ./config
COPY templates ./templates
COPY data/demo ./data/demo
COPY profiles/example ./profiles/example
USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)" || exit 1
CMD ["careergraph", "ui"]

# Optional LaTeX engine. NOT built or tested in development (no network-heavy builds were run).
# Asset name and URL pattern from the tectonic GitHub release page (0.17.0); the tag contains
# "@", URL-encoded as %40. On first compile tectonic downloads the packages it needs and caches
# them in TECTONIC_CACHE_DIR; the RUN below warms that cache at build time.
FROM runtime AS latex
ARG TECTONIC_VERSION=0.17.0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
       | tar -xz -C /usr/local/bin tectonic \
    && apt-get purge -y curl && rm -rf /var/lib/apt/lists/*
ENV TECTONIC_CACHE_DIR=/home/app/.cache/tectonic LATEX_ENGINE=tectonic
USER app
RUN OUTPUT_DIR=/tmp/warm careergraph render-sample && rm -rf /tmp/warm
