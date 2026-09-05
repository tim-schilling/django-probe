# Configuration

# Configuration

Django Probe reads project configuration from the `[tool.django_probe]` table in the
`pyproject.toml` at the project root.

## Django settings

The probe shares the names of the Django settings used in the project by default.
It only shares that the setting was defined; the value is not shared. Set
`django_settings` to `false` to disable it:

```toml
[tool.django_probe]
django_settings = false
```

## Dependencies

Installed dependency names and versions are captured by default. Set dependencies
to "names" to omit versions, or to "none" to disable dependency capture:

```toml
[tool.django_probe]
dependencies = "versions"
```

| Value        | Package names | Package versions |
| ------------ | :-----------: | :---------------: |
| `"versions"` (default) | Yes | Yes |
| `"names"`    | Yes           | No                |
| `"none"`     | No            | No                |

The names-only mode still includes normalized package names. Python, Django, and
client versions and the packages that supplied probes remain in the payload.
