# Configuration

Django Probe reads project configuration from the `[tool.django_probe]` table in the
`pyproject.toml` at the project root.

## Package usage

Detailed Django API usage is enabled by default. The equivalent configuration is:

```toml
[tool.django_probe]
packages = ["django"]
```

Set `packages` to an empty list to disable detailed API usage, or add other
top-level Python import names to scan more namespaces.

These are import names rather than distribution names. For example, Django REST
framework would be configured as `rest_framework`, not `djangorestframework`.

The scanner follows aliases such as `from django.shortcuts import render as show`
but does not follow attributes through function return values. Thus it records
`django.shortcuts.get_object_or_404`, but not an application method called on the
returned model instance. Reads from `django.conf.settings` include a setting name
only when the installed Django version defines it.

## Django settings

The probe shares the names of the Django settings used in the project by default.
It only shares that the setting was defined; the value is not shared. Set
`django_settings` to `false` to disable it:

```toml
[tool.django_probe]
django_settings = false
```

## Dependencies

Installed dependency names and versions are captured by default. Set dependencies
to "names" to omit versions, or to "none" to disable dependency capture:

```toml
[tool.django_probe]
dependencies = "versions"
```

| Value        | Package names | Package versions |
| ------------ | :-----------: | :---------------: |
| `"versions"` (default) | Yes | Yes |
| `"names"`    | Yes           | No                |
| `"none"`     | No            | No                |

The names-only mode still includes normalized package names. Python, Django, and
client versions and the packages that supplied probes remain in the payload.

### What gets excluded

Local-path, editable, and VCS installs (for example `pip install -e .` or a
`git+ssh://` requirement) are excluded automatically.

!!! warning "Private package indexes"
    A package from a private package index (an internal Artifactory or devpi
    instance, for example) isn't excluded automatically. Use
    [`dependencies_exclude`](#dependencies-exclude) to omit those by name.

## Dependencies exclude

Omit dependencies by name:

```toml
[tool.django_probe]
dependencies_exclude = ["acme-*"]
```

Patterns are [`fnmatch`](https://docs.python.org/3/library/fnmatch.html) wildcards,
matched against the normalized name.

## GitHub Actions approval gate

Set the `environment` input on the [reusable `uv`
workflow](getting-started.md#github-actions) to review each payload before it's
shared:

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
    uses: tim-schilling/django-probe/.github/workflows/django-probe-submit-uv.yml@0.3.1
    with:
      environment: django-probe-submit
    secrets:
      DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
```

Create the `django-probe-submit` environment under **Settings → Environments → New
environment** with a required reviewer. Each run prints the payload and pauses for
that reviewer's approval before submitting it. Leave `environment` unset to submit
without a gate.

## uv dependency groups

The scan only sees what uv installed. If production dependencies live outside uv's
default groups (for example, Django is installed only via a `production` group),
pass `dependency-groups` to the reusable workflow:

```yaml
jobs:
  django-probe:
    uses: tim-schilling/django-probe/.github/workflows/django-probe-submit-uv.yml@0.3.1
    with:
      dependency-groups: "production docs"
    secrets:
      DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
```

Each space-separated group becomes its own `uv sync --group`. Pass `python-version`
to pin the Python version uv sets up, and `path` to scan a project that isn't at the
repository root.

See [`django-probe-submit-uv.yml`](https://github.com/tim-schilling/django-probe/blob/main/.github/workflows/django-probe-submit-uv.yml)
for the full set of inputs.
