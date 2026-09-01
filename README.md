# Django Probe

Count how often specific code patterns appear in a Django project, and report only the
counts to a central server.

There is currently no public data on which Django patterns are still in use.
Maintainers deprecate APIs without knowing how many projects are affected, and tooling
authors have to guess at which patterns matter. This project collects that data.

Full documentation, including the probe catalog and how to write a new probe, is at
[docs.djangoprobe.org](https://docs.djangoprobe.org/).

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

### Documentation site

The `docs/` directory holds the [Zensical](https://zensical.org/) source for
[docs.djangoprobe.org](https://docs.djangoprobe.org/), built by Read the Docs from
`.readthedocs.yaml`.

```console
$ just docs-serve   # live preview at localhost:8000
$ just docs-build    # build the static site into site/
```

## License

MIT
