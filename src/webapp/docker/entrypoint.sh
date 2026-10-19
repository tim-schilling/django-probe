#!/bin/sh
set -eu

exec gunicorn config.wsgi:application \
    --chdir src/webapp \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-3}" \
    --access-logfile - \
    --access-logformat '%(t)s "%(r)s" %(s)s %(b)s %(M)sms "%(a)s" cf-ray=%({cf-ray}i)s'
