default:
    @just --list

# Install the dev environment (lint, test, and webapp dependencies) into the local venv
install:
    uv sync --group dev

# Run the test suite
test *ARGS:
    uv run pytest {{ARGS}}

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
    docker build -t django-probe-webapp .

# Run the deployment image locally, using sqlite + in-process cache
docker-run:
    docker run --rm -p 8000:8000 -e DJANGO_PROBE_SECRET_KEY=local django-probe-webapp

# Serve the documentation site locally with live reload
docs-serve:
    uv run --group docs zensical serve

# Build the documentation site into site/
docs-build:
    uv run --group docs zensical build
