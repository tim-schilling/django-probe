# Writing a probe

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
