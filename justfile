default:
    @just --list

# Prepare a local development checkout
bootstrap:
    uv sync --group dev
    uv run pre-commit install
    just docker-postgres
    uv run python src/webapp/manage.py migrate

# Install the dev environment (lint, test, and webapp dependencies) into the local venv
install:
    uv sync --group dev

# Run the test suite
test *ARGS:
    uv run pytest {{ARGS}}

# Run browser end-to-end tests in their dedicated tox environment
test-e2e *ARGS:
    uvx --with tox-uv tox run -e e2e -- {{ARGS}}

# Run the test suite against every supported Python/Django combination
test-all *ARGS:
    uvx tox {{ARGS}}

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src/django_probe

fmt:
    uv run ruff format .
    uv run ruff check --fix .

migrate:
    uv run python src/webapp/manage.py migrate

makemigrations:
    uv run python src/webapp/manage.py makemigrations

serve:
    uv run python src/webapp/manage.py runserver

createsuperuser:
    uv run python src/webapp/manage.py createsuperuser

# Print the payload that `submit` would send, without sending it
scan path=".":
    uv run django-probe scan {{path}}

# Scan and send to a running local server
submit path="." url="http://localhost:8000":
    uv run django-probe submit {{path}} --server-url {{url}}

# Build the deployment image for src/webapp
docker-build:
    docker build -f src/webapp/Dockerfile -t django-probe-webapp .

docker-postgres:
    #!/usr/bin/env bash
    set -euo pipefail
    if docker container inspect django-probe-postgres >/dev/null 2>&1; then
        docker start django-probe-postgres >/dev/null
    else
        docker run --name django-probe-postgres --detach --publish 55432:5432 --env POSTGRES_DB=django_probe --env POSTGRES_USER=postgres --env POSTGRES_PASSWORD=postgres postgres:18 >/dev/null
    fi
    until docker exec django-probe-postgres pg_isready -U postgres -d django_probe >/dev/null 2>&1; do
        sleep 1
    done
    echo "PostgreSQL is ready on localhost:55432"

# Run the deployment image locally; pass a container-reachable DATABASE_URL
docker-run:
    docker run --rm -p 8000:8000 -e DJANGO_PROBE_SECRET_KEY=local -e DATABASE_URL django-probe-webapp

# Serve the documentation site locally with live reload
docs-serve:
    uv run --group docs zensical serve

# Build the documentation site into site/
docs-build:
    uv run --group docs zensical build
