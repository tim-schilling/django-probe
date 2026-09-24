from __future__ import annotations

import json

from django import template

from ingest.stats import query_string

register = template.Library()


@register.filter
def pretty_json(value):
    return json.dumps(value, indent=2, sort_keys=True)


@register.simple_tag
def stats_query(filters, name=None, value="", add_key=None, remove_key=None, **changes):
    """The stats query string for ``filters`` with changes applied.

    Changes are given as keyword arguments, or as a ``name`` and ``value`` when the
    filter name is itself a variable. An empty value removes that filter.
    ``add_key`` and ``remove_key`` change one of the chained keys.
    """
    if name:
        changes[name] = value
    keys = [key for key in filters.get("key", []) if key != remove_key]
    if add_key:
        keys.append(add_key)
    query = query_string({**filters, "key": keys, **changes})
    return f"?{query}" if query else ""
