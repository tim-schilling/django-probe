# syntax=docker/dockerfile:1

# Runs the src/webapp server only. The django-probe client package (src/django_probe)
# is never imported by the webapp, so it isn't copied into this image.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Installing dependencies before the rest of the source keeps this layer cached
# across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --group webapp

COPY src/webapp ./src/webapp
# collectstatic must use the same whitenoise manifest storage as production, or no
# staticfiles.json is baked into the image and requests fail at runtime with
# "Missing staticfiles manifest entry". It asks for that directly rather than by
# setting ENVIRONMENT=production, which would also demand the real secrets that only
# exist at deploy time.
RUN chmod +x src/webapp/docker/entrypoint.sh \
    && DJANGO_PROBE_STATIC_MANIFEST=1 python src/webapp/manage.py collectstatic --noinput

EXPOSE 8000
ENTRYPOINT ["src/webapp/docker/entrypoint.sh"]
