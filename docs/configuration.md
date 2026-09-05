# Configuration

Django has a lot of settings. You can share which settings are used in your project
by adding the following to your `pyproject.toml` file:

```toml
[tool.django_probe.usage]
django_settings = true
```

The probe will only collect Django settings. It only shares that the setting was
defined. The value is not shared.
