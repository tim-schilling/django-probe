"""Collect Django setting names without inspecting setting values."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from django_probe.config import django_settings_enabled

_DJANGO_42_SETTING_NAMES = frozenset(
    {
        "ABSOLUTE_URL_OVERRIDES",
        "ADMINS",
        "ALLOWED_HOSTS",
        "APPEND_SLASH",
        "AUTHENTICATION_BACKENDS",
        "AUTH_PASSWORD_VALIDATORS",
        "AUTH_USER_MODEL",
        "CACHES",
        "CACHE_MIDDLEWARE_ALIAS",
        "CACHE_MIDDLEWARE_KEY_PREFIX",
        "CACHE_MIDDLEWARE_SECONDS",
        "CSRF_COOKIE_AGE",
        "CSRF_COOKIE_DOMAIN",
        "CSRF_COOKIE_HTTPONLY",
        "CSRF_COOKIE_MASKED",
        "CSRF_COOKIE_NAME",
        "CSRF_COOKIE_PATH",
        "CSRF_COOKIE_SAMESITE",
        "CSRF_COOKIE_SECURE",
        "CSRF_FAILURE_VIEW",
        "CSRF_HEADER_NAME",
        "CSRF_TRUSTED_ORIGINS",
        "CSRF_USE_SESSIONS",
        "DATABASES",
        "DATABASE_ROUTERS",
        "DATA_UPLOAD_MAX_MEMORY_SIZE",
        "DATA_UPLOAD_MAX_NUMBER_FIELDS",
        "DATA_UPLOAD_MAX_NUMBER_FILES",
        "DATETIME_FORMAT",
        "DATETIME_INPUT_FORMATS",
        "DATE_FORMAT",
        "DATE_INPUT_FORMATS",
        "DEBUG",
        "DEBUG_PROPAGATE_EXCEPTIONS",
        "DECIMAL_SEPARATOR",
        "DEFAULT_AUTO_FIELD",
        "DEFAULT_CHARSET",
        "DEFAULT_EXCEPTION_REPORTER",
        "DEFAULT_EXCEPTION_REPORTER_FILTER",
        "DEFAULT_FILE_STORAGE",
        "DEFAULT_FROM_EMAIL",
        "DEFAULT_INDEX_TABLESPACE",
        "DEFAULT_TABLESPACE",
        "DISALLOWED_USER_AGENTS",
        "EMAIL_BACKEND",
        "EMAIL_HOST",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_HOST_USER",
        "EMAIL_PORT",
        "EMAIL_SSL_CERTFILE",
        "EMAIL_SSL_KEYFILE",
        "EMAIL_SUBJECT_PREFIX",
        "EMAIL_TIMEOUT",
        "EMAIL_USE_LOCALTIME",
        "EMAIL_USE_SSL",
        "EMAIL_USE_TLS",
        "FILE_UPLOAD_DIRECTORY_PERMISSIONS",
        "FILE_UPLOAD_HANDLERS",
        "FILE_UPLOAD_MAX_MEMORY_SIZE",
        "FILE_UPLOAD_PERMISSIONS",
        "FILE_UPLOAD_TEMP_DIR",
        "FIRST_DAY_OF_WEEK",
        "FIXTURE_DIRS",
        "FORCE_SCRIPT_NAME",
        "FORMAT_MODULE_PATH",
        "FORM_RENDERER",
        "IGNORABLE_404_URLS",
        "INSTALLED_APPS",
        "INTERNAL_IPS",
        "LANGUAGES",
        "LANGUAGES_BIDI",
        "LANGUAGE_CODE",
        "LANGUAGE_COOKIE_AGE",
        "LANGUAGE_COOKIE_DOMAIN",
        "LANGUAGE_COOKIE_HTTPONLY",
        "LANGUAGE_COOKIE_NAME",
        "LANGUAGE_COOKIE_PATH",
        "LANGUAGE_COOKIE_SAMESITE",
        "LANGUAGE_COOKIE_SECURE",
        "LOCALE_PATHS",
        "LOGGING",
        "LOGGING_CONFIG",
        "LOGIN_REDIRECT_URL",
        "LOGIN_URL",
        "LOGOUT_REDIRECT_URL",
        "MANAGERS",
        "MEDIA_ROOT",
        "MEDIA_URL",
        "MESSAGE_STORAGE",
        "MIDDLEWARE",
        "MIGRATION_MODULES",
        "MONTH_DAY_FORMAT",
        "NUMBER_GROUPING",
        "PASSWORD_HASHERS",
        "PASSWORD_RESET_TIMEOUT",
        "PREPEND_WWW",
        "SECRET_KEY",
        "SECRET_KEY_FALLBACKS",
        "SECURE_CONTENT_TYPE_NOSNIFF",
        "SECURE_CROSS_ORIGIN_OPENER_POLICY",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "SECURE_HSTS_PRELOAD",
        "SECURE_HSTS_SECONDS",
        "SECURE_PROXY_SSL_HEADER",
        "SECURE_REDIRECT_EXEMPT",
        "SECURE_REFERRER_POLICY",
        "SECURE_SSL_HOST",
        "SECURE_SSL_REDIRECT",
        "SERVER_EMAIL",
        "SESSION_CACHE_ALIAS",
        "SESSION_COOKIE_AGE",
        "SESSION_COOKIE_DOMAIN",
        "SESSION_COOKIE_HTTPONLY",
        "SESSION_COOKIE_NAME",
        "SESSION_COOKIE_PATH",
        "SESSION_COOKIE_SAMESITE",
        "SESSION_COOKIE_SECURE",
        "SESSION_ENGINE",
        "SESSION_EXPIRE_AT_BROWSER_CLOSE",
        "SESSION_FILE_PATH",
        "SESSION_SAVE_EVERY_REQUEST",
        "SESSION_SERIALIZER",
        "SHORT_DATETIME_FORMAT",
        "SHORT_DATE_FORMAT",
        "SIGNING_BACKEND",
        "SILENCED_SYSTEM_CHECKS",
        "STATICFILES_DIRS",
        "STATICFILES_FINDERS",
        "STATICFILES_STORAGE",
        "STATIC_ROOT",
        "STATIC_URL",
        "STORAGES",
        "TEMPLATES",
        "TEST_NON_SERIALIZED_APPS",
        "TEST_RUNNER",
        "THOUSAND_SEPARATOR",
        "TIME_FORMAT",
        "TIME_INPUT_FORMATS",
        "TIME_ZONE",
        "USE_DEPRECATED_PYTZ",
        "USE_I18N",
        "USE_L10N",
        "USE_THOUSAND_SEPARATOR",
        "USE_TZ",
        "USE_X_FORWARDED_HOST",
        "USE_X_FORWARDED_PORT",
        "WSGI_APPLICATION",
        "X_FRAME_OPTIONS",
        "YEAR_MONTH_FORMAT",
    }
)

_DJANGO_50_SETTING_NAMES = (
    _DJANGO_42_SETTING_NAMES | {"FORMS_URLFIELD_ASSUME_HTTPS"}
) - {"CSRF_COOKIE_MASKED", "USE_DEPRECATED_PYTZ", "USE_L10N"}
_DJANGO_51_SETTING_NAMES = _DJANGO_50_SETTING_NAMES - {
    "DEFAULT_FILE_STORAGE",
    "STATICFILES_STORAGE",
}
_DJANGO_52_SETTING_NAMES = _DJANGO_51_SETTING_NAMES | {
    "SIGNED_COOKIE_LEGACY_SALT_FALLBACK"
}
_DJANGO_60_SETTING_NAMES = (
    _DJANGO_52_SETTING_NAMES
    | {
        "SECURE_CSP",
        "SECURE_CSP_REPORT_ONLY",
        "TASKS",
        "URLIZE_ASSUME_HTTPS",
    }
) - {"FORMS_URLFIELD_ASSUME_HTTPS"}
_DJANGO_61_SETTING_NAMES = _DJANGO_60_SETTING_NAMES | {"USE_BLANK_CHOICE_DASH"}
_DJANGO_62_SETTING_NAMES = _DJANGO_61_SETTING_NAMES

DJANGO_SETTING_NAMES_BY_VERSION = {
    "4.2": _DJANGO_42_SETTING_NAMES,
    "5.0": _DJANGO_50_SETTING_NAMES,
    "5.1": _DJANGO_51_SETTING_NAMES,
    "5.2": _DJANGO_52_SETTING_NAMES,
    "6.0": _DJANGO_60_SETTING_NAMES,
    "6.1": _DJANGO_61_SETTING_NAMES,
    "6.2": _DJANGO_62_SETTING_NAMES,
}
DJANGO_SETTINGS_VERSIONS = tuple(DJANGO_SETTING_NAMES_BY_VERSION)
DJANGO_SETTING_NAMES = frozenset(
    name for names in DJANGO_SETTING_NAMES_BY_VERSION.values() for name in names
)


def _assignment_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assignment_names(element))
        return names
    return []


def configured_django_settings(
    root: Path,
    settings_files: list[ast.Module],
    vocabulary: frozenset[str] = DJANGO_SETTING_NAMES,
) -> tuple[Counter[str], bool]:
    """Count recognized module-level assignments in settings-like files."""
    if not django_settings_enabled(root):
        return Counter(), False

    counts: Counter[str] = Counter()
    for tree in settings_files:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                counts.update(
                    name for name in _assignment_names(target) if name in vocabulary
                )
    return counts, True
