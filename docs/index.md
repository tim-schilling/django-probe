# Django Probe

Count how often specific code patterns appear in a Django project, and report only the
counts to a central server.

There is currently no public data on which Django patterns are still in use.
Maintainers deprecate APIs without knowing how many projects are affected, and tooling
authors have to guess at which patterns matter. This project collects that data.

For installation and CLI usage, see the
[README](https://github.com/django-probe/django-probe#usage). This site covers what
gets counted, how to write a probe, and how the project stays forward compatible.

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
