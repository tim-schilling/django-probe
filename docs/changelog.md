# `django-probe` CLI Changelog

## Unreleased

- Bundled the Django 4.2 through the current development version's setting names
  so settings collection no longer requires Django to be installed.
- Read dependencies from `uv.lock`, `poetry.lock`, or `pdm.lock` when one is present,
  falling back to the installed distributions. See
  [Dependencies](configuration.md#dependencies).
- Refused to report dependencies that can't be verified: when Django is missing from
  whatever was resolved, `scan` and `submit` now explain and exit non-zero instead of
  sharing another environment's packages.
- Excluded packages resolved from anywhere other than PyPI, for the lock files that
  record an index URL. See [What gets excluded](configuration.md#what-gets-excluded).
- Added `dependencies_source` to the payload, recording which of those layers answered.

## 0.3.2

- Mention when the user is being rate limited.

## 0.3.1

- Corrected the repository URL throughout the docs and package metadata.

## 0.3.0

- Captured Django migrations data in the payload.
- Added package API usage collection, enabled by default for `django`. See
  [Package usage](configuration.md#package-usage).
- Added a privacy-scoped Django settings inventory, enabled by default. See
  [Django settings](configuration.md#django-settings).
- Allowed configuring how dependencies are shared, including excluding packages
  by name. See [Dependencies](configuration.md#dependencies).
