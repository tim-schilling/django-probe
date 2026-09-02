from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

from config.sentry import initialize_sentry

BASE_DIR = Path(__file__).resolve().parent.parent

initialize_sentry()

SECRET_KEY = os.environ.get("DJANGO_PROBE_SECRET_KEY", "insecure-development-key")
DEBUG = os.environ.get("DJANGO_PROBE_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_PROBE_ALLOWED_HOSTS", "*").split(",")

# Coolify (and most PaaS-style hosts) terminate TLS at a proxy in front of the
# container, so Django only ever sees plain HTTP. Without these two settings it
# would think every request is insecure and reject admin/allauth POSTs with a CSRF
# failure once ALLOWED_HOSTS is locked down to a real domain.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.environ.get("DJANGO_PROBE_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    "ingest",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Skip whitenoise in dev/test so it doesn't warn about a missing directory
    *([] if DEBUG else ["whitenoise.middleware.WhiteNoiseMiddleware"]),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:55432/django_probe",
        ),
        conn_max_age=600,
    )
}

# Rate limiting is cache-backed. LocMemCache is per-process, so a real deployment
# must point this at Redis via REDIS_URL, or limits apply per worker rather than per
# server.
_REDIS_URL = os.environ.get("REDIS_URL")
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "django-probe",
        }
    }

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_USER_MODEL = "ingest.User"

SITE_ID = 1
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

LOGIN_REDIRECT_URL = "/account/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_REDIRECT_URL = "/token/"

# Accounts are strictly optional, so the server must run and ingest normally with no
# GitHub credentials configured. The provider is only wired up when both are present.
_GITHUB_CLIENT_ID = os.environ.get("DJANGO_PROBE_GITHUB_CLIENT_ID")
_GITHUB_SECRET = os.environ.get("DJANGO_PROBE_GITHUB_SECRET")

SOCIALACCOUNT_PROVIDERS = {}
if _GITHUB_CLIENT_ID and _GITHUB_SECRET:
    SOCIALACCOUNT_PROVIDERS["github"] = {
        "APPS": [
            {
                "client_id": _GITHUB_CLIENT_ID,
                "secret": _GITHUB_SECRET,
                "key": "",
            }
        ],
        # Only the default public scope: we want an identity, not the user's repos.
        "SCOPE": ["read:user"],
    }

SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = "none"
