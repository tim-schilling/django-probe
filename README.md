# Django Probe

It's hard to remove features in open-source software. [Deprecation warnings exist, but people tend to ignore them](https://sethmlarson.dev/deprecations-via-warnings-dont-work-for-python-libraries). What maintainers want to know is how many people are using a feature. That's where Django Probe comes in.

Django Probe allows you to share how your project uses Django. This package counts how often specific code patterns appear in your Django project and shares the aggregated information with the community.

By sharing what your project uses, you help support the Django community. This allows maintainers to know what features and APIs are actually being used, removing guess work.

## Quickstart

Install Django Probe in your project, then create a project token:

```console
$ uv add --dev django-probe
$ uv run django-probe login
$ uv run django-probe init
```

`login` stores an organization credential in your user configuration directory.
`init` prints a separate project token; copy it, then inspect and submit the first scan:

```console
$ export DJANGO_PROBE_TOKEN=&lt;the token printed by init&gt;
$ uv run django-probe scan .      # inspect the payload; sends nothing
$ uv run django-probe submit .    # share the first scan
```

Next, [add Django Probe to CI](https://docs.djangoprobe.org/getting-started/#add-django-probe-to-ci)
so the project shares data on a schedule. See
[Privacy](https://docs.djangoprobe.org/privacy/) for exactly what a payload contains.

## What we're looking to learn

This list will grow over time, but for now there are two main usages:

- The [`.extra()` ORM API method](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#extra)
  - The [`.extra()` ORM API method](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#extra) has had a note about avoiding its usage for years. Let's determine if this is something that is central to a signficant number of Django projects.
- The [`@cache_page` decorator](https://docs.djangoproject.com/en/6.1/topics/cache/#the-per-view-cache)
  - The `@cache_page` decorator can easily cause problems for projects by storing and serving sensitive information such as CSRF tokens and CSP nonces. Understanding how widespread the usage is of it can help determine what further changes are needed.
