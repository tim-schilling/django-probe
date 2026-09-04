from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from config import environment
from config.sentry import initialize_sentry

BASE_DIR = Path(__file__).resolve().parent.parent

initialize_sentry()

ENVIRONMENT = environment.name()
IS_PRODUCTION = environment.is_production()

# Both fall back to a development value outside production and are a hard error
# inside it: a deployment that boots on the shared SECRET_KEY or with a wildcard
# ALLOWED_HOSTS looks perfectly healthy from the outside.
SECRET_KEY = environment.required(
    "DJANGO_PROBE_SECRET_KEY", default="insecure-development-key"
)
ALLOWED_HOSTS = environment.required("DJANGO_PROBE_ALLOWED_HOSTS", default="*").split(
    ","
)

DEBUG = os.environ.get("DJANGO_PROBE_DEBUG", "0") == "1"
if DEBUG and IS_PRODUCTION:
    raise ImproperlyConfigured(
        "DJANGO_PROBE_DEBUG must not be enabled when "
        f"DJANGO_PROBE_ENVIRONMENT={environment.PRODUCTION}: Django's debug pages "
        "expose the settings module, including SECRET_KEY and DATABASE_URL."
    )

CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.environ.get("DJANGO_PROBE_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin
]

# Transport hardening, production only. Each of these assumes TLS actually
# terminates in front of the app, which holds for the Coolify/Cloudflare deployment
# and not for a local runserver: enabling them in development would redirect plain
# HTTP to a port nothing is listening on and set cookies the browser then refuses
# to send back.
if IS_PRODUCTION:
    # Coolify (and most PaaS-style hosts) terminate TLS at a proxy in front of the
    # container, so Django only ever sees plain HTTP. Without this it would treat
    # every request as insecure and reject admin/allauth POSTs with a CSRF failure
    # once ALLOWED_HOSTS is locked down to a real domain. It trusts a header the
    # proxy sets, which is only sound while the origin cannot be reached except
    # through that proxy - see the deployment guide.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Deliberately short to start with. Raise it towards a year once you are
    # satisfied nothing needs plain HTTP; browsers cache the directive, so an
    # over-long value is painful to walk back.
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # security.W021 asks for SECURE_HSTS_PRELOAD. Preloading is a separate, largely
    # one-way commitment - it needs a year-long max-age and a submission browsers
    # ship in their binaries - so it is declined deliberately rather than left as a
    # standing warning that trains everyone to skim `check --deploy` output.
    SILENCED_SYSTEM_CHECKS = ["security.W021"]

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
    # Only enable whitenoise in production so it doesn't warn about a missing
    # staticfiles manifest; only that collectstatic (see src/webapp/Dockerfile) ever writes one.
    *(["whitenoise.middleware.WhiteNoiseMiddleware"] if IS_PRODUCTION else []),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# Nothing here is ever legitimately framed, and the CLI approval page turns a single
# click into an issued credential, so a clickjacked frame is worth more than usual.
X_FRAME_OPTIONS = "DENY"

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
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if IS_PRODUCTION
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

LOGIN_REDIRECT_URL = "/account/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_REDIRECT_URL = "/account/"

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
