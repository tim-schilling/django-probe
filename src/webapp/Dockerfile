# syntax=docker/dockerfile:1

# Runs the src/webapp server. The django-probe client package (src/django_probe) is
# copied in because the webapp reads its __version__ to flag outdated clients.
FROM ghcr.io/astral-sh/uv:0.13.8-python3.14-trixie-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=config.settings \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Installing dependencies before the rest of the source keeps this layer cached
# across code-only changes. hatchling reads the dynamic version from __init__.py while
# preparing project metadata, so that file is needed here.
COPY pyproject.toml uv.lock ./
COPY src/django_probe/__init__.py ./src/django_probe/__init__.py
RUN uv sync --locked --no-dev --no-install-project --group webapp

COPY src/django_probe ./src/django_probe
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
