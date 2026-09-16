# Django Probe

It's hard to remove features in open-source software. [Deprecation warnings exist, but people tend to ignore them](https://sethmlarson.dev/deprecations-via-warnings-dont-work-for-python-libraries). What maintainers want to know is how many people are using a feature. That's where Django Probe comes in.

Django Probe allows you to share which parts of Django your project uses. This package counts how often specific code patterns appear in your Django project and shares the aggregated information with the community.

By sharing what your project uses, you help support the Django community. No source code is shared, just the counts of which parts of Django are used, providing maintainers helpful information to direct the future of Django.

## Quickstart

To quickly see what Django Probe would share:

```console
# with uv
$ uvx django-probe scan .

# with pip
$ source .venv/bin/activate
$ pip install django-probe
$ django-probe scan .
```

To share the results, create a project token. If not using uv, you'll need to
add Django Probe to the development dependencies first:

```console
# with uv
$ uvx django-probe login
$ uvx django-probe init

# with Poetry
$ poetry add --group dev django-probe
$ poetry run django-probe login
$ poetry run django-probe init

# with PDM
$ pdm add -dG dev django-probe
$ pdm run django-probe login
$ pdm run django-probe init

# with pip
$ source .venv/bin/activate
$ pip install django-probe
$ django-probe login
$ django-probe init
```

`login` stores an organization credential in your user configuration directory.
`init` prints a separate project token; copy it, then inspect and submit the first scan:

```console
$ export DJANGO_PROBE_TOKEN=<token_from_init>

# with uv
$ uvx django-probe scan .      # inspect the payload; sends nothing
$ uvx django-probe submit .    # share the first scan

# with Poetry
$ poetry run django-probe scan .
$ poetry run django-probe submit .

# with PDM
$ pdm run django-probe scan .
$ pdm run django-probe submit .

# with pip
$ django-probe scan .      # inspect the payload; sends nothing
$ django-probe submit .    # share the first scan
```

## Add it to CI

Store the token as the `DJANGO_PROBE_TOKEN` repository secret, then call the
reusable workflow so the project shares data on a schedule:

```yaml
# .github/workflows/django-probe.yml
name: Django Probe

on:
  schedule:
    # Runs monthly. Choose a different minute and hour to help spread load on our servers.
    - cron: "17 4 1 * *"
  workflow_dispatch:

permissions: {}

jobs:
  django-probe:
    uses: tim-schilling/django-probe/.github/workflows/django-probe-submit-uv.yml@0.3.2
    with:
      # Path to the Django project to scan, relative to the repository root.
      path: "."
      # Environment to gate the submit job behind. Empty submits without an approval gate.
      environment: ""
      # Python version for uv to set up. Empty lets uv resolve its own.
      python-version: ""
    secrets:
      DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
```

Each option shows its default, so you can remove any you don't need to change. The reusable
workflow is uv-only; for pip, GitLab CI, and gating submission behind approval, see
[Getting started](https://docs.djangoprobe.org/getting-started/#add-django-probe-to-ci).

See [Privacy](https://docs.djangoprobe.org/privacy/) for exactly what a payload contains.

## What we're looking to learn

In general, we're looking to see what parts of Django are used and which aren't. That is in general captured by the usages and settings data (if shared).

Additionally, we're looking for specific usages. These are in the probes portion of the payload. This list will grow over time, but for now there are two main usages:

- The [`.extra()` ORM API method](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#extra) has had a note about avoiding its usage for years. Let's determine if this is something that is central to a signficant number of Django projects.
- The `@cache_page` decorator can easily cause problems for projects by storing and serving sensitive information such as CSRF tokens and CSP nonces. Understanding how widespread the usage is of it can help determine what further changes are needed.
