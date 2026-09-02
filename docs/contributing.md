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
$ uv run pre-commit install
$ just install
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
[`.github/workflows/webapp-image.yml`](https://github.com/django-probe/django-probe/blob/main/.github/workflows/webapp-image.yml)
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
| `DJANGO_PROBE_SECRET_KEY` | yes | Django's `SECRET_KEY`. Falls back to an insecure default otherwise. |
| `DJANGO_PROBE_DEBUG` | no | Defaults to `0`. Leave unset in production; Django's debug pages leak internals. |
| `DJANGO_PROBE_ENVIRONMENT` | yes | Set to `production`. Gates whitenoise's manifest static storage and tags Sentry events; defaults to `dev` so a stray local/test run can't be mistaken for production. |
| `DJANGO_PROBE_ALLOWED_HOSTS` | yes | Comma-separated hostnames, e.g. `probe.example.com`. Defaults to `*`. |
| `DJANGO_PROBE_CSRF_TRUSTED_ORIGINS` | yes | Comma-separated origins with scheme, e.g. `https://probe.example.com`. Needed because Coolify's proxy terminates TLS in front of the container. |
| `DATABASE_URL` | yes | e.g. `postgres://user:pass@host:5432/dbname`, pointing at your PostgreSQL database. |
| `DJANGO_PROBE_GITHUB_CLIENT_ID` / `DJANGO_PROBE_GITHUB_SECRET` | optional | Enables GitHub sign-in. |
| `SENTRY_DSN` | optional | Enables Sentry error and performance monitoring. Leave unset to disable Sentry; do not use a production DSN for local development or tests. |
| `SENTRY_RELEASE` | recommended with Sentry | Deployed release identifier, ideally an immutable image or Git SHA such as `django-probe@abc123`. |
| `SENTRY_TRACES_SAMPLE_RATE` | optional | Fraction of requests whose performance traces are sent, from `0` to `1`. Defaults to `0.1` when Sentry is enabled; set to `0` to retain error monitoring while disabling traces. |
| `WEB_CONCURRENCY` | optional | gunicorn worker count. Defaults to `3`. |
| `PORT` | optional | Port gunicorn binds to. Defaults to `8000`; set this to match whatever port Coolify expects the container to listen on. |

Sentry never initializes without `SENTRY_DSN`. When enabled, the integration does not
send default personally identifiable information and does not capture request bodies.
