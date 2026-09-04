"""Django Probe. Count Django code patterns and report only the counts."""

from __future__ import annotations

import os

__all__ = ["USER_AGENT", "__version__"]

# Suffixed with DJANGO_PROBE_VERSION_DEV so CI can build throwaway dev
# distributions to test the release process. See .github/workflows/test_release.yml
__version__ = "0.2.0" + os.environ.get("DJANGO_PROBE_VERSION_DEV", "")

# Identifies requests as coming from this library rather than a browser, so the
# server can allowlist it separately from browser traffic (e.g. Cloudflare's Browser
# Integrity Check, which otherwise 403s Python's default urllib User-Agent).
USER_AGENT = f"django-probe/{__version__}"
