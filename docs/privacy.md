# Privacy

No source code, file paths, or repository names leave your machine. A payload contains
only integers, package names, and version strings.

## Verify it yourself

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.

The optional `[tool.django_probe.usage] django_settings = true` setting adds a
`django_settings` inventory. It contains only names assigned at module level in
settings-like files that are defined by the installed Django distribution's
`global_settings.py`, along with integer occurrence counts. It never includes
project-defined setting names, setting values, environment-variable names, or
application import paths. If Django's vocabulary cannot be read, the inventory is
empty and `django_settings_scanned` is `false`.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).
