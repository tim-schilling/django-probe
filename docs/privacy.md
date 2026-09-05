# Privacy

No source code, file paths, or repository names leave your machine. By default a
payload contains package names, version strings, Django classes and functions, and
the names of the Django settings your project defines.

You can control dependency detail and opt out of the inventory of defined Django
settings through [Django Probe's configuration](configuration.md).

## Highest privacy settings

The following is the configuration for maximizing your project's privacy while still
sharing some information with the community.

```toml
[tool.django_probe]
dependencies = "none"  # Don't include dependencies
django_settings = false  # Don't include names of the defined Django settings
```

## Verify it yourself

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).
