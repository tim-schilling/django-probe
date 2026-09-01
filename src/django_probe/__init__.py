"""Django Probe. Count Django code patterns and report only the counts."""

from __future__ import annotations

import os

__all__ = ["__version__"]

# Suffixed with DJANGO_PROBE_VERSION_DEV so CI can build throwaway dev
# distributions to test the release process. See .github/workflows/test_release.yml
__version__ = "0.1.0" + os.environ.get("DJANGO_PROBE_VERSION_DEV", "")
