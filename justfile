default:
    @just --list

# Install all dependency groups into the local venv
install:
    uv sync --all-groups

# Run the test suite
test *ARGS:
    uv run pytest {{ARGS}}

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src/django_probe

fmt:
    uv run ruff format .
    uv run ruff check --fix .

migrate:
    uv run python src/server/manage.py migrate

makemigrations:
    uv run python src/server/manage.py makemigrations

serve:
    uv run python src/server/manage.py runserver

createsuperuser:
    uv run python src/server/manage.py createsuperuser

# Print the payload that `submit` would send, without sending it
scan path=".":
    uv run django-probe scan {{path}}

# Scan and send to a running local server
submit path="." url="http://localhost:8000":
    uv run django-probe submit {{path}} --server-url {{url}}
