# API + compile worker image. Build from the repo root:
#   docker build -f infra/core.Dockerfile -t watchonce-core .
# The runner (Playwright) image is separate and lands with the runner (D8).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /usr/local/bin/uv

WORKDIR /app/services/core
COPY services/core/pyproject.toml services/core/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Same relative layout as the repo: the spec validator reads ../../packages/spec.
COPY packages/spec/workflow.schema.json /app/packages/spec/workflow.schema.json
COPY services/core/ ./

RUN useradd --system --uid 10001 --home /app app \
    && DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=build-only-$(head -c 48 /dev/urandom | base64 | tr -d '\n') \
       SECRETS_MASTER_KEY=build-only DATABASE_URL=sqlite:///tmp/build.db \
       python manage.py collectstatic --noinput \
    && chown -R app /app
USER app

EXPOSE 8000
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
