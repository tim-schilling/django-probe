# Privacy

No source code, file paths, or repository names leave your machine. A payload contains
only integers, package names, and version strings.

## Verify it yourself

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.

If you want to see the code, please see [`payload.py`](https://github.com/django-probe/django-probe/blob/main/src/django_probe/payload.py).

## Deleting projects and accounts

Deleting a project removes its token. Its submissions are retained by default, but
without a link to the deleted project. The confirmation provides an explicit option
to permanently delete those submissions instead.

Deleting an account removes organizations where the user is the only member, along
with their projects. Submissions from those projects are retained without a project
link by default, with an explicit option to permanently delete them. Shared
organizations, their projects, and their submissions remain available to other
members. Permanent deletion cannot be undone.
