# Privacy

No source code, file paths, or repository names leave your machine. A payload contains
only integers, package names, and version strings.

## Inspect the CI payload

Before adding `django-probe submit .` to CI, run:

```console
$ uv run django-probe scan .
```

`scan` prints the exact payload that the CI job's `submit` command would send, without
sending anything. You can also run `submit` manually when testing the integration.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).
