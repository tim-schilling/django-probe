# Architecture

This repository builds two separate things from one source tree.

## `django_probe`

This is the Python package that is installed into Django projects and reports aggregate information. Each probe walks the standard library `ast` module's parse tree.

| File | Role |
|---|---|
| `main.py` | CLI entry point. |
| `probes/` | Individual probes. |

## djangoprobe.org

The central Django application that receives submissions, hosted at [djangoprobe.org](https://djangoprobe.org/).

## How a submission flows

1. `django-probe scan` walks the project and runs every registered probe, producing a
   `{key: count}` payload via `payload.py`.
2. `django-probe submit` sends that payload, plus `probe_sources`, to the ingest
   server's `views.py`.
3. `validation.py` checks shape, `throttle.py` checks rate limits, and the raw
   submission is stored as-is — see [Third-party probe packages](third-party-probes.md)
   for why nothing gets normalized or described at this point.
