# Privacy

No source code, file paths, or repository names leave your machine. By default a
payload contains dependency names, version strings, curated pattern counts, and the
names of the Django settings your project defines. It also contains statically
resolved Django API usage because `packages` defaults to `["django"]`.

You can control dependency detail and opt out of the inventory of defined Django
settings through [Django Probe's configuration](configuration.md). If you want to
keep scheduled submissions but review each payload before it's shared, see the
[GitHub Actions approval gate](configuration.md#github-actions-approval-gate).

Dependency capture excludes local-path, editable, and VCS installs automatically.
If your project has private dependencies from another source, such as a private
package index, list their name patterns in `dependencies_exclude` to omit them. See
[Configuration](configuration.md#dependencies) for details.

## Highest privacy settings

The following is the configuration for maximizing your project's privacy while still
sharing some information with the community.

```toml
[tool.django_probe]
packages = []  # Don't include detailed package API usage
dependencies = "none"  # Don't include dependencies
dependencies_exclude = []  # e.g. ["mycompany-*"]
django_settings = false  # Don't include names of the defined Django settings
```

Package usage contains only statically resolved dotted names and integer occurrence
counts. The scanner does not report attributes called on values returned by package
functions, because those attributes may be defined by the application. For
`django.conf.settings`, project-defined names are collapsed to
`django.conf.settings` rather than reported.

## Verify it yourself

=== "uv"

    ```console
    $ uv run django-probe scan .
    ```

=== "pip"

    ```console
    $ django-probe scan .
    ```

`scan` prints the exact payload that `submit` would send, without sending anything.
Run it with the project's dependencies installed, the same way `submit` runs.

If you want to see the code, please see [`payload.py`](https://github.com/tim-schilling/django-probe/blob/main/src/django_probe/payload.py).

## Public aggregate data

Submissions inform aggregated, filterable statistics (e.g. by Django version,
Python version, dependency, or pattern usage) that anyone can view. This view
never identifies which project or organization a figure came from, and there is
no way to filter by date or otherwise reconstruct a history for a single source.

Any filter combination narrow enough to describe fewer than a set minimum number
of submissions is withheld rather than shown, so a filtered result can't be used
to single out one project's data.

## Deleting data

A user can delete all their data, including their submissions if needed. Otherwise
the submissions are left permanently anonymous.

A project and organization can only be deleted when the organization has a single
user. When this is done, the user has the option to also delete any associated
submissions or leave them anonymous.

Deleting an account removes organizations where the user is the only member, along
with their projects.

## Data retention

Account data (username, email, GitHub identity) and organization/project data are
kept for as long as the account exists. CLI device-login requests that never turn
into a credential are purged automatically after 7 days.

The database is backed up in two places:

- **Hetzner** server backups: 7 daily snapshots, rolling. A given backup is gone
  within 7 days of being taken.
- **S3**: backups expire after 90 days and move to Glacier Instant Retrieval
  storage immediately, so a given backup is fully deleted within 90 days.

Deleting your account, an organization, or a project (see above) removes the data
from the live database immediately. A copy can still exist in a database backup
until that backup rolls off on the schedules above.

The service also sits behind a CDN and reports errors to a monitoring provider; see
[Subprocessors](#subprocessors) for what each of those sees and retains.

## Subprocessors

Django Probe uses the following third parties to run the service. A signed data
processing agreement is in place with each one, incorporating Standard
Contractual Clauses for transfers outside the EEA where applicable.

- **GitHub** — OAuth sign-in for the web dashboard (`read:user` and `user:email`
  scopes only; no repository access). Acts as an identity provider rather than a
  processor.
- **AWS S3** — encrypted database backups (`us-east-2`).
- **Hetzner** — application hosting and daily server backups.
- **Cloudflare** — CDN and reverse proxy in front of the application.
- **Sentry** — error and performance monitoring. IP addresses, request bodies,
  and cookies are never sent to Sentry; events are retained for 30 days.
