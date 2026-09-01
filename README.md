# Django Probe

It's hard to remove features in open-source software. [Deprecation warnings exist, but people tend to ignore them](https://sethmlarson.dev/deprecations-via-warnings-dont-work-for-python-libraries). What maintainers want to know is how many people are using a feature. That's where Django Probe comes in.

Django Probe allows you to share how your project uses Django. This package counts how often specific code patterns appear in your Django project and shares the aggregated information with the community.

By sharing what your project uses, you help support the Django community. This allows maintainers to know what features and APIs are actually being used, removing guess work.

## Quickstart

```console
$ pip install django-probe
$ django-probe scan .                    # inspect the payload
$ django-probe submit .                  # send it, anonymously
```

No account is required. See [Getting started](https://docs.djangoprobe.org/getting-started/)
for project keys, and [Privacy](https://docs.djangoprobe.org/privacy/)
for exactly what a payload contains.

### Reporting automatically

You should avoid reporting this manually. The project key can be set as an environment
variable (`DJANGO_PROBE_PROJECT_KEY`), so it drops straight into a scheduled GitHub
Action as a repository secret. See
[Getting started](https://docs.djangoprobe.org/getting-started/#reporting-on-a-schedule)
for a workflow you can copy.

## What we're looking to learn

This list will grow over time, but for now there are two main usages:

- The [`.extra()` ORM API method](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#extra)
  - The [`.extra()` ORM API method](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#extra) has had a note about avoiding its usage for years. Let's determine if this is something that is central to a signficant number of Django projects.
- The [`@cache_page` decorator](https://docs.djangoproject.com/en/6.1/topics/cache/#the-per-view-cache)
  - The `@cache_page` decorator can easily cause problems for projects by storing and serving sensitive information such as CSRF tokens and CSP nonces. Understanding how widespread the usage is of it can help determine what further changes are needed.
