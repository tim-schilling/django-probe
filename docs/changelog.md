# Changelog

## Unreleased

- Mention when the user is being rate limited.

## 0.3.1

- Added a footer with relevant links and a trademark notice.
- Linked the `@cache_page` decorator to Django's docs.
- Rounded out the privacy docs and fixed their links.
- Linked the docs from the landing page.
- Corrected the repository URL throughout the docs and package metadata.

## 0.3.0

- Captured Django migrations data in the payload.
- Added package API usage collection, enabled by default for `django`. See
  [Package usage](configuration.md#package-usage).
- Added a privacy-scoped Django settings inventory, enabled by default. See
  [Django settings](configuration.md#django-settings).
- Allowed configuring how dependencies are shared, including excluding packages
  by name. See [Dependencies](configuration.md#dependencies).
- Added a reusable GitHub Actions workflow for submitting scans with `uv`, with
  an optional approval gate. See [GitHub Actions approval
  gate](configuration.md#github-actions-approval-gate).
- Added safe project and account deletion to the web app.
- Prevented duplicate project names within an organization.
