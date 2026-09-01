# Writing a probe

```python
from django_probe.probes import Probe, hit, resolves_to

login_required = Probe("login_required")


@login_required.register(ast.FunctionDef)
def visit_FunctionDef(state, node, parents):
    """Count views decorated with `@login_required`."""
    for decorator in node.decorator_list:
        # A view can carry several decorators.
        # There can only be one django.contrib.auth.decorators.login_required
        if resolves_to(
            state, decorator, "django.contrib.auth.decorators", "login_required"
        ):
            yield from hit(node)
```

Yield once per occurrence, and the visitor will tally the yields.

Always resolve names through `resolves_to()` rather than matching a bare name.
Otherwise, you will count every similarly named function in the project: `@task` from
`invoke` is not the same as `@task` from `django.tasks`. `resolves_to()` handles the
three import forms that reach the same object (`from a.b import c`; `from a import b`
followed by `@b.c`; and `import a.b` followed by `@a.b.c`).

**Aliased imports using `as` are not resolved**, to do so will require tracking
rebindings and require full scope analysis.

## Testing a probe

`tests/probes/helpers.py` exposes `counts(source)`, which runs every registered probe
over a source string and returns a `{key: count}` dict:

```python
from .helpers import counts


def test_login_required():
    assert counts("""
        from django.contrib.auth.decorators import login_required

        @login_required
        def view():
            ...
    """) == {"login_required": 1}
```

See `tests/probes/test_orm.py` and friends for existing examples.
