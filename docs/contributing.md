# Contributing

Thanks for helping improve Django Probe. The guides in this section cover the
repository's conventions as well as the mechanics of running and deploying it.

## Suggesting new probes

See [Writing a probe](writing-probes.md) for the pattern, then open a PR.

## Frontend changes

Read the [frontend style guide](frontend-style.md) before changing webapp templates,
styles, or shared interface components. It describes the visual foundations,
accessibility requirements, and checks expected for frontend contributions.

## Development setup

Requires [uv](https://docs.astral.sh/uv/), [pre-commit](https://pre-commit.com/) and [just](https://just.systems/).

```console
$ just bootstrap
$ just test
$ just test-e2e
$ just lint
$ just migrate && just serve
```

`just --list` shows the remaining commands.

`just test` runs against the project's default Python/Django combination. `just
test-all` runs the full [tox](https://tox.wiki/) matrix.

## Deployment

`src/webapp/Dockerfile` builds `src/webapp` only. On start, the
container's `src/webapp/docker/entrypoint.sh` serves via gunicorn. Coolify is configured to collectstatic
and migrate the database on the pre-deployment step.

```console
$ just bootstrap  # installs dependencies and hooks, starts PostgreSQL, runs migrations
$ just serve      # serves on http://localhost:8000
```

`just bootstrap` is safe to rerun. It starts the existing
`django-probe-postgres` container when present instead of creating a duplicate.

Images are built in CI rather than by Coolify itself:
[`.github/workflows/webapp-image.yml`](https://github.com/tim-schilling/django-probe/blob/main/.github/workflows/webapp-image.yml)
builds and pushes `ghcr.io/<owner>/<repo>:latest` (plus a short-SHA tag) on every push
to `main` that touches `src/webapp/`. It's scoped to
that path, and never triggers on tags, so it can't collide with tag-based PyPI
releases of `django_probe` later.

Note: The first push creates the GHCR package as private
even on a public repo. So go to the package's settings on GitHub once and set it public,
so Coolify can pull it with no registry credentials.

In Coolify, add the app as a **Docker Image** resource (not a Dockerfile build)
pointing at that image tag. To redeploy automatically when CI publishes a new image,
copy the resource's deploy webhook URL and an API token from Coolify, and add them to
the repo as Actions secrets: `COOLIFY_WEBHOOK_URL` and `COOLIFY_API_TOKEN`.

Whichever way the image reaches Coolify, set these environment variables on the
resource:

| Variable | Required | Purpose |
|---|---|---|
| `DJANGO_PROBE_SECRET_KEY` | yes | Django's `SECRET_KEY`. Startup fails when `DJANGO_PROBE_ENVIRONMENT=production` and this is unset; outside production it falls back to a shared development value. |
| `DJANGO_PROBE_DEBUG` | no | Defaults to `0`. Setting it to `1` in production is a startup error: Django's debug pages expose the settings module, including `SECRET_KEY` and `DATABASE_URL`. |
| `DJANGO_PROBE_ENVIRONMENT` | yes | Set to `production`. Gates the TLS/cookie settings and whitenoise's manifest static storage, and tags Sentry events; defaults to `dev` so a stray local/test run can't be mistaken for production. |
| `DJANGO_PROBE_ALLOWED_HOSTS` | yes | Comma-separated hostnames, e.g. `probe.example.com`. Startup fails when unset in production; defaults to `*` outside it. |
| `DJANGO_PROBE_CSRF_TRUSTED_ORIGINS` | yes | Comma-separated origins with scheme, e.g. `https://probe.example.com`. Needed because Coolify's proxy terminates TLS in front of the container. |
| `DATABASE_URL` | yes | e.g. `postgres://user:pass@host:5432/dbname`, pointing at your PostgreSQL database. |
| `DJANGO_PROBE_GITHUB_CLIENT_ID` / `DJANGO_PROBE_GITHUB_SECRET` | optional | Enables GitHub sign-in. |
| `SENTRY_DSN` | optional | Enables Sentry error and performance monitoring. Leave unset to disable Sentry; do not use a production DSN for local development or tests. |
| `SENTRY_RELEASE` | recommended with Sentry | Deployed release identifier, ideally an immutable image or Git SHA such as `django-probe@abc123`. |
| `SENTRY_TRACES_SAMPLE_RATE` | optional | Fraction of requests whose performance traces are sent, from `0` to `1`. Defaults to `0.1` when Sentry is enabled; set to `0` to retain error monitoring while disabling traces. |
| `DJANGO_PROBE_LOG_LEVEL` | optional | Level for the application logs. Defaults to `INFO`. |
| `WEB_CONCURRENCY` | optional | gunicorn worker count. Defaults to `3`. |
| `PORT` | optional | Port gunicorn binds to. Defaults to `8000`; set this to match whatever port Coolify expects the container to listen on. |

Sentry never initializes without `SENTRY_DSN`. When enabled, the integration does not
send default personally identifiable information and does not capture request bodies.

### Logs

The container writes every request and the application logs to stdout and stderr.
Coolify shows them on the application's **Logs** tab. Each request line includes the
`cf-ray` ID, which finds the same request in Cloudflare's logs.

### Cloudflare set up

Cloudflare's SSL mode must be Full or Full (strict), not Flexible.

A Cache Rule must make the stats pages eligible for caching. Add rules for
`/stats/*` and `/api/stats/*` that respects the origin's `Cache-Control`.

**Rate limiting must cover every unauthenticated endpoint.** Note that this is wider
than the endpoints that create rows:

| Endpoint | Why |
|---|---|
| `POST /api/submissions/` | Unauthenticated by design; the only bound on volume. |
| `POST /api/cli/auth/` | Unauthenticated row creation, once per request. |
| `GET /api/cli/auth/<code>/poll/` | Issues the CLI credential. It is a **GET**, so a rule scoped to POSTs or to "create" endpoints will miss it. |
| `/accounts/login/`, `/accounts/signup/` | allauth; otherwise unbounded credential stuffing. |

### New Django and Python releases

When Django or Python ships a new feature release:

- Update `DJANGO_VERSIONS` or `PYTHON_VERSIONS` in `src/webapp/ingest/stats.py`.
- Update `tox.ini` matrix and the `pyproject.toml` classifiers.
- For Django, add the new series to the `vendor-django-vocabularies` recipe in
  `justfile`, then refresh the vendored catalogs.

### Vendored Django catalogs

`just vendor-django-vocabularies` installs the latest patch release of each Django
feature series, plus `main`, and writes the names found in each one:

| Path | Contents |
|---|---|
| `src/django_probe/_vendor/django_settings/<version>.json` | Setting names. Ships with the CLI. |
| `src/webapp/ingest/django_api/<version>.json.gz` | Public API names. |
| `src/webapp/ingest/django_api/all.json.gz` | API names from every version. The stats pages only show and accept keys in this list. |

Afterwards, update the expected versions and counts in the tests and commit them
with the catalogs.

### Scheduled maintenance

CLI login requests and credentials accumulate as rows nothing can use. Run this
daily, alongside the pre-deployment steps:

```console
$ python src/webapp/manage.py purge_cli_credentials
```

It deletes rows unusable for more than seven days (`--days` to change,
`--dry-run` to preview). Active credentials are never touched.
