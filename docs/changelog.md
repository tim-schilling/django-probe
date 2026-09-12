# `django-probe` CLI Changelog

## Unreleased

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
