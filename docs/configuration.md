# Configuration

# Configuration

Django Probe reads project configuration from the `[tool.django_probe]` table in the
`pyproject.toml` at the project root.

## Django settings

Django has a lot of settings. You can share which settings are used in your project
by adding the following to your `pyproject.toml` file:

```toml
[tool.django_probe.usage]
django_settings = true
```

The probe will only collect Django settings. It only shares that the setting was
defined. The value is not shared.

## Dependencies

Installed dependency names and versions are captured by default. Set dependencies
to "names" to omit versions, or to "none" to disable dependency capture:

```toml
[tool.django_probe]
dependencies = "none"
```

The names-only mode still includes normalized package names. Python, Django, and
client versions and the packages that supplied probes remain in the payload.
