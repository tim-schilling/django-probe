#!/bin/sh
set -eu

# A command, such as the crontask scheduler, runs in place of the web server.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

case "${DJANGO_PROBE_PROCESS:-web}" in
    web) ;;
    worker) exec python src/webapp/manage.py crontask ;;
    *)
        echo "Unknown DJANGO_PROBE_PROCESS: ${DJANGO_PROBE_PROCESS}" >&2
        exit 1
        ;;
esac

exec gunicorn config.wsgi:application \
    --chdir src/webapp \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-3}" \
    --access-logfile - \
    --access-logformat '%(t)s "%(r)s" %(s)s %(b)s %(M)sms "%(a)s" cf-ray=%({cf-ray}i)s user=%({django_probe.user}e)s'
