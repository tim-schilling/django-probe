from __future__ import annotations

import re
from pathlib import Path
from unittest import TestCase

from django_probe import __version__

CONFIGURATION_DOCS = (
    Path(__file__).resolve().parent.parent / "docs" / "configuration.md"
)
WORKFLOW_REF = re.compile(r"django-probe-submit-uv\.yml@(?P<version>[^\s\"']+)")


class ConfigurationDocsTests(TestCase):
    def test_reusable_workflow_example_pins_current_version(self):
        match = WORKFLOW_REF.search(CONFIGURATION_DOCS.read_text())

        self.assertIsNotNone(
            match,
            f"Expected a django-probe-submit-uv.yml@<version> reference in {CONFIGURATION_DOCS}",
        )
        self.assertEqual(match.group("version"), __version__)
