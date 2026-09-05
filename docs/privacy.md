# Privacy

No source code, file paths, or repository names leave your machine. By default a
payload contains package names, version strings and Django classes and functions.

It is possible to include more information through configuration.

## Verify it yourself

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).
