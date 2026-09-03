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

A project's token is what groups its submissions and attributes them to your
organization.

### Get a token

```console
$ django-probe login               # once per machine, approve in your browser
$ django-probe init                # once per repo, creates a project and prints its token
```

`login` authenticates this machine for a single organization. Pass `--org
<slug>` (find it on the organization's page) to skip picking one in the
browser — handy when scripting `init` across many repos:

```console
$ django-probe login --org my-team
```

`init` then creates a project — its name defaults to the current directory — and
prints the resulting token. Nothing is written to disk; run it once per repository:

```console
$ django-probe init
Created project 'my-repo' in My Team.
Token: 1f2e3d4c5b6a...
Set this as DJANGO_PROBE_TOKEN wherever you run `django-probe submit`.
```

Prefer not to run the CLI locally, or bootstrapping the very first CI secret?
Create an organization and a project directly at
[djangoprobe.org](https://djangoprobe.org) — the token is generated for you on the
project's page.

### Use it in CI

Add the token as a repository secret at **Settings → Secrets and variables → Actions → New
repository secret**, named `DJANGO_PROBE_TOKEN`, then add a workflow like:

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
          DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
        run: django-probe submit .
```

On GitLab CI, add a masked CI/CD variable named `DJANGO_PROBE_TOKEN` under
**Settings → CI/CD → Variables** — GitLab exposes it to the job automatically:

```yaml
report_probe:
  stage: test
  script:
    - pip install . django-probe
    - django-probe submit .
```

## CLI reference

| Command | Description |
|---|---|
| `django-probe scan [path]` | Print the payload as JSON without sending anything. |
| `django-probe submit [path] [--server-url] [--dry-run]` | Scan, then send the payload to a server. |
| `django-probe login [--org] [--server-url]` | Authenticate this machine via your browser. |
| `django-probe init [path] [--org] [--name] [--server-url]` | Create a project using your stored login and print its token. |

| Env var | Purpose |
|---|---|
| `DJANGO_PROBE_SERVER` | Overrides the default submit target (`https://djangoprobe.org`). |
| `DJANGO_PROBE_TOKEN` | The token from `django-probe init` or a project's page; attributes submissions to it. |
