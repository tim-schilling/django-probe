#!/bin/sh
set -eu

python src/webapp/manage.py migrate --noinput

exec gunicorn config.wsgi:application \
    --chdir src/webapp \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-3}"
