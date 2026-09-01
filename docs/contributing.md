# Contributing

## Suggesting new probes

See [Writing a probe](writing-probes.md) for the pattern, then open a PR.

## Development setup

Requires [uv](https://docs.astral.sh/uv/), [pre-commit](https://pre-commit.com/) and [just](https://just.systems/).

```console
$ uv run pre-commit install
$ just install
$ just test
$ just lint
$ just migrate && just serve
```

`just --list` shows the remaining commands.

`just test` runs against the project's default Python/Django combination. `just
test-all` runs the full [tox](https://tox.wiki/) matrix.

## Deployment

The root `Dockerfile` builds `src/webapp` only. On start, the
container's `docker/entrypoint.sh` runs migrations and then serves via gunicorn, so no
separate release step is needed.

```console
$ just docker-build
$ just docker-run    # serves on http://localhost:8000, using sqlite + in-process cache
```

Images are built in CI rather than by Coolify itself:
[`.github/workflows/webapp-image.yml`](https://github.com/django-probe/django-probe/blob/main/.github/workflows/webapp-image.yml)
builds and pushes `ghcr.io/<owner>/<repo>:latest` (plus a short-SHA tag) on every push
to `main` that touches `src/webapp/`, the `Dockerfile`, or `docker/`. It's scoped to
those paths, and never triggers on tags, so it can't collide with tag-based PyPI
releases of `django_probe` later.

Note: The first push creates the GHCR package as private
even on a public repo. So go to the package's settings on GitHub once and set it public,
so Coolify can pull it with no registry credentials.

In Coolify, add the app as a **Docker Image** resource (not a Dockerfile build)
pointing at that image tag. To redeploy automatically when CI publishes a new image,
copy the resource's deploy webhook URL and an API token from Coolify, and add them to
the repo as Actions variables/secrets: `COOLIFY_WEBHOOK_URL` (repository variable) and
`COOLIFY_API_TOKEN` (repository secret). The workflow's last step calls that webhook
once the push succeeds; omit the variable to skip it and redeploy manually instead.

Whichever way the image reaches Coolify, set these environment variables on the
resource:

| Variable | Required | Purpose |
|---|---|---|
| `DJANGO_PROBE_SECRET_KEY` | yes | Django's `SECRET_KEY`. Falls back to an insecure default otherwise. |
| `DJANGO_PROBE_DEBUG` | yes | Set to `0` in production. Defaults to `1`. |
| `DJANGO_PROBE_ALLOWED_HOSTS` | yes | Comma-separated hostnames, e.g. `probe.example.com`. Defaults to `*`. |
| `DJANGO_PROBE_CSRF_TRUSTED_ORIGINS` | yes | Comma-separated origins with scheme, e.g. `https://probe.example.com`. Needed because Coolify's proxy terminates TLS in front of the container. |
| `DATABASE_URL` | yes | e.g. `postgres://user:pass@host:5432/dbname`, pointing at your existing database. Falls back to a local sqlite file if unset. |
| `REDIS_URL` | recommended | e.g. `redis://host:6379/0`. Falls back to per-process LocMemCache if unset, which breaks rate limiting across multiple workers/replicas. |
| `DJANGO_PROBE_GITHUB_CLIENT_ID` / `DJANGO_PROBE_GITHUB_SECRET` | optional | Enables GitHub sign-in. |
| `SENTRY_DSN` | optional | Enables Sentry error and performance monitoring. Leave unset to disable Sentry; do not use a production DSN for local development or tests. |
| `SENTRY_ENVIRONMENT` | recommended with Sentry | Deployment name such as `production` or `staging`, used to separate events in Sentry. |
| `SENTRY_RELEASE` | recommended with Sentry | Deployed release identifier, ideally an immutable image or Git SHA such as `django-probe@abc123`. |
| `SENTRY_TRACES_SAMPLE_RATE` | optional | Fraction of requests whose performance traces are sent, from `0` to `1`. Defaults to `0.1` when Sentry is enabled; set to `0` to retain error monitoring while disabling traces. |
| `WEB_CONCURRENCY` | optional | gunicorn worker count. Defaults to `3`. |
| `PORT` | optional | Port gunicorn binds to. Defaults to `8000`; set this to match whatever port Coolify expects the container to listen on. |

Sentry never initializes without `SENTRY_DSN`. When enabled, the integration does not
send default personally identifiable information and does not capture request bodies.
