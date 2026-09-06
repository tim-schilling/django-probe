# Privacy

No source code, file paths, or repository names leave your machine. By default a
payload contains dependency names, version strings, curated pattern counts, and the
names of the Django settings your project defines. It also contains statically
resolved Django API usage because `packages` defaults to `["django"]`.

You can control dependency detail and opt out of the inventory of defined Django
settings through [Django Probe's configuration](configuration.md).

## Highest privacy settings

The following is the configuration for maximizing your project's privacy while still
sharing some information with the community.

```toml
[tool.django_probe]
packages = []  # Don't include detailed package API usage
dependencies = "none"  # Don't include dependencies
django_settings = false  # Don't include names of the defined Django settings
```

Package usage contains only statically resolved dotted names and integer occurrence
counts. The scanner does not report attributes called on values returned by package
functions, because those attributes may be defined by the application. For
`django.conf.settings`, project-defined names are collapsed to
`django.conf.settings` rather than reported.

## Verify it yourself

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).

## Deleting data

A user can delete all their data, including their submissions if needed. Otherwise
the submissions are left permanently anonymous.

A project and organization can only be deleted when the organization has a single
user. When this is done, the user has the option to also delete any associated
submissions or leave them anonymous.

Deleting an account removes organizations where the user is the only member, along
with their projects.
