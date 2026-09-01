# Django Probe

Count how often specific code patterns appear in a Django project, and report only the
counts to a central server.

There is currently no public data on which Django patterns are still in use.
Maintainers deprecate APIs without knowing how many projects are affected, and tooling
authors have to guess at which patterns matter. This project collects that data.

## Privacy

No source code, file paths, or repository names leave your machine. A payload contains
only integers, package names, and version strings.

You can verify this yourself:

```console
$ django-probe scan .
```

`scan` prints the exact payload that `submit` would send, without sending anything.
Everything the server can receive is assembled in one file,
[`payload.py`](src/django_probe/payload.py).

## Usage

```console
$ pip install django-probe
$ django-probe scan .                    # inspect the payload
$ django-probe submit .                  # send it, anonymously
```

No account is required. Anonymous submission is the default path and supports every
feature. An account only lets you see your own submissions listed under your name. It
does not unlock functionality or change the data you contribute.

### Grouping your submissions over time

```console
$ django-probe init
wrote project_key 9f2c1e04-… to pyproject.toml
```

This writes a random UUID to `pyproject.toml`. If you commit it, every developer and CI
run reports as a single project rather than as many separate ones.

The key is a random UUID rather than a hash of your git remote. Hashing the remote
would require no configuration, but public repositories can be enumerated, so anyone
could hash every repository on GitHub and match yours. A random UUID cannot be reversed
in that way. Project keys work with or without an account.

### Attaching submissions to an account

This step is optional. Sign in to the server with GitHub, copy your token from
`/token/`, then:

```console
$ export DJANGO_PROBE_TOKEN=…
$ django-probe submit .
```

Tokens are read from the environment or the `--token` flag. They are never written to
`pyproject.toml`, because that file is normally committed.

## What gets counted

Probes measure which APIs a codebase uses, rather than which patterns are out of date.

| Probe | Question it answers |
|---|---|
| `queryset_filter` `_exclude` `_annotate` `_alias` `_extra` | Which ORM methods do projects use? `.extra()` is of particular interest, as it has long been discouraged but never formally deprecated, and cannot be fixed automatically. |
| `django_task` | Django 6.0 added a built-in Tasks framework. How widely is it being adopted? |
| `cache_page` | How common is per-view caching? |
| `custom_user_model` / `auth_user_model_setting` | How many projects define their own user model rather than using the default? |
| `signal_receiver` | How widely are signals used? |
| `transaction_atomic` | How often do projects manage transactions explicitly? |

### Accuracy of the counts

`queryset_*` precision is approximately 98%, measured across Django, Wagtail,
django-oscar, and djangopackages. The probes match on method name, because there are no
types available at parse time. Requiring a recognisable receiver such as `.objects`
would raise precision to nearly 100%, but would also discard about a third of genuine
ORM calls, which is not a worthwhile trade for a usage survey.

`migrations/` directories are skipped. They contain generated code, and a single
migration file can contain many model classes and `.filter()` calls that no one wrote
by hand.

## Writing a probe

```python
from django_probe.probes import Probe, hit, resolves_to

my_probe = Probe("my_probe")


@my_probe.register(ast.FunctionDef)
def visit_FunctionDef(state, node, parents):
    for decorator in node.decorator_list:
        if resolves_to(state, decorator, "some.module", "thing"):
            yield from hit(node)
```

Yield once per occurrence, and the visitor will tally the yields.

Always resolve names through `resolves_to()` rather than matching a bare name.
Otherwise you will count every similarly named function in the project: `@task` from
`invoke` is not the same as `@task` from `django.tasks`. `resolves_to()` handles the
three import forms that reach the same object (`from a.b import c`; `from a import b`
followed by `@b.c`; and `import a.b` followed by `@a.b.c`). Aliased imports using `as`
are intentionally not resolved, as tracking rebindings would require full scope
analysis.

## Forward compatibility

Support for third-party packages shipping their own probes has not been built yet, but
the design allows for it. Pattern keys use a `namespace:name` format and are stored in a
flat `{key: count}` JSON field. The server does not validate pattern keys against a
known vocabulary, so a new namespace requires no server release and no migration. This
behaviour is covered by a test in `tests/ingest/`, so that adding such validation later
will cause a visible failure rather than silently discarding data.

Every payload also includes `probe_sources`, which records the packages that supplied
probes and their versions. Without it, a count of zero would be ambiguous: the pattern
might be absent, or nothing might have looked for it.

Display metadata for patterns, such as labels, descriptions, and documentation links,
belongs in a server-side registry that submissions do not reference when they are
written. Storing submissions first and describing them later keeps the ingest endpoint
from becoming a coordination point between the server and every probe author.

## Repository layout

```
src/django_probe/   the client package published to PyPI
src/webapp/         the Django server that receives submissions
```

## Development

Requires [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/).

```console
$ just install
$ just test
$ just lint
$ just migrate && just serve
```

`just --list` shows the remaining commands.

The server runs and accepts submissions without GitHub OAuth credentials configured, so
a deployment that never sets up allauth is still valid. Set
`DJANGO_PROBE_GITHUB_CLIENT_ID` and `DJANGO_PROBE_GITHUB_SECRET` to enable sign-in.

For production deployments, point `CACHES` at Redis. Rate limiting is cache-backed, and
LocMemCache is per-process, so limits would otherwise apply per worker rather than
across the server.

## License

MIT
