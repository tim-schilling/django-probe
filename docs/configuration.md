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

The scanner follows aliases such as `from django.shortcuts import render as show`
but does not follow attributes through function return values. Thus it records
`django.shortcuts.get_object_or_404`, but not an application method called on the
returned model instance. Reads from `django.conf.settings` include a setting name
only when Django 4.2 through the current development version defines it.

## Django settings

The probe shares the names of the Django settings used in the project by default.
It only shares that the setting was defined; the value is not shared. Set
`django_settings` to `false` to disable it:

```toml
[tool.django_probe]
django_settings = false
```

## Dependencies

Dependency names and versions are captured by default. Set dependencies to "names"
to omit versions, or to "none" to disable dependency capture:

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

### Where they come from

Django Probe reads `uv.lock`, `poetry.lock`, or `pdm.lock` from the project root, in
that order. When a lock file pins one package at several versions across environment
markers, the highest is reported.

_Without a lock file, Django Probe falls back to the installed Python packages._


### When dependencies can't be resolved

Django Probe refuses to report dependencies it can't verify. If Django is missing from
the lock file or the environment, `scan` and `submit` print an explanation and exit
without sharing any dependencies. `scan` still prints the rest of the payload first.

To resolve, a user can fix the resolution, or set `dependencies = "none"` to opt out
of dependency capture entirely.

### What gets excluded

Local-path, editable, and VCS installs (for example `pip install -e .` or a
`git+ssh://` requirement) are excluded automatically.

`uv.lock` and `poetry.lock` record the index each package was resolved from, so
anything that did not come from PyPI is excluded as well. A package from an internal
index or mirror of PyPI is excluded.

`pdm.lock` does not record the index so packages from private indexes must be excluded
explicitly.

Use
[`dependencies_exclude`](#dependencies-exclude) to omit packages by name.

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
    uses: tim-schilling/django-probe/.github/workflows/django-probe-submit-uv.yml@0.3.2
    with:
      environment: django-probe-submit
    secrets:
      DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
```

Create the `django-probe-submit` environment under **Settings → Environments → New
environment** with a required reviewer. Each run prints the payload and pauses for
that reviewer's approval before submitting it. Leave `environment` unset to submit
without a gate.

## Other workflow inputs

Pass `python-version` to pin the Python version uv sets up, and `path` to scan a
project that isn't at the repository root.

See [`django-probe-submit-uv.yml`](https://github.com/tim-schilling/django-probe/blob/main/.github/workflows/django-probe-submit-uv.yml)
for the full set of inputs.
