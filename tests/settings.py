"""Minimal Django settings for the library's own test suite.

Don't re-use the webapp's settings as the Python versions are
incompatible.
"""

from __future__ import annotations

SECRET_KEY = "not-used-for-library-tests"
USE_TZ = True
INSTALLED_APPS: list[str] = []
