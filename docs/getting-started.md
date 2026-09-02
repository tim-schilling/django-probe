# Getting started

## Install

```console
$ pip install django-probe
```

## Scan and submit

```console
$ django-probe scan .      # inspect the payload, sends nothing
$ django-probe submit .    # send it, anonymously
```

## Reporting on a schedule

The project key is what groups all submissions to the same project. To configure, generate a project key:

```console
$ django-probe init
9f2c1e04-…
```

Then add it as a repository secret at **Settings → Secrets and variables → Actions → New
repository secret**, named `DJANGO_PROBE_PROJECT_KEY`, then add a workflow like:

```yaml
# .github/workflows/django-probe.yml
name: Django Probe

on:
  schedule:
    - cron: "0 0 1 * *"  # 00:00 UTC on the 1st of each month
  workflow_dispatch:

jobs:
  submit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      # Install your project too: django_version and dependencies are read from
      # what's installed, not from pyproject.toml.
      - run: pip install . django-probe

      - env:
          DJANGO_PROBE_PROJECT_KEY: ${{ secrets.DJANGO_PROBE_PROJECT_KEY }}
        run: django-probe submit .
```

## CLI reference

| Command | Description |
|---|---|
| `django-probe scan [path]` | Print the payload as JSON without sending anything. |
| `django-probe submit [path] [--server-url] [--dry-run]` | Scan, then send the payload to a server. |
| `django-probe init` | Print a random project key. |

| Env var | Purpose |
|---|---|
| `DJANGO_PROBE_SERVER` | Overrides the default submit target (`https://djangoprobe.org`). |
| `DJANGO_PROBE_PROJECT_KEY` | Groups submissions into a project. |
