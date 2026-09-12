from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest import TestCase

from django_probe import __version__

ROOT = Path(__file__).resolve().parent.parent
#: Every file showing the reusable workflow example to a user setting up CI.
WORKFLOW_EXAMPLES = (
    "README.md",
    "docs/getting-started.md",
    "docs/configuration.md",
    "src/webapp/templates/home.html",
    "src/webapp/templates/project_detail.html",
)
WORKFLOW_REF = re.compile(r"django-probe-submit-uv\.yml@(?P<version>[^\s\"']+)")
YAML_BLOCK = re.compile(
    r"^(?P<indent> *)```yaml\n(?P<body>.*?)^(?P=indent)```$",
    re.DOTALL | re.MULTILINE,
)
#: Each CI example in docs/getting-started.md, and the pages repeating it verbatim.
#: docs/configuration.md is excluded: it shows the same workflow cut down to one input.
CI_EXAMPLES = {
    "django-probe-submit-uv.yml": (
        "README.md",
        "src/webapp/templates/home.html",
        "src/webapp/templates/project_detail.html",
    ),
    "actions/setup-python": ("src/webapp/templates/home.html",),
    "astral-sh/uv:python3.14": (
        "src/webapp/templates/home.html",
        "src/webapp/templates/project_detail.html",
    ),
    "python:3.14-slim": ("src/webapp/templates/home.html",),
}


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def yaml_block(text: str, needle: str) -> str | None:
    """The fenced YAML block containing `needle`, undented out of any tab it sits in."""
    for match in YAML_BLOCK.finditer(text):
        body = textwrap.dedent(match.group("body"))
        if needle in body:
            return body.strip()
    return None


class WorkflowExampleTests(TestCase):
    def test_examples_pin_current_version(self):
        """Each copy of the reusable workflow example points at this release."""
        for relative_path in WORKFLOW_EXAMPLES:
            with self.subTest(path=relative_path):
                versions = [
                    match.group("version")
                    for match in WORKFLOW_REF.finditer(read(relative_path))
                ]

                self.assertNotEqual(
                    versions,
                    [],
                    f"Expected a django-probe-submit-uv.yml@<version> reference in {relative_path}",
                )
                self.assertEqual(versions, [__version__] * len(versions))

    def test_ci_examples_match_getting_started(self):
        """The landing page and project page show what the docs tell people to commit."""
        getting_started = read("docs/getting-started.md")
        for needle, relative_paths in CI_EXAMPLES.items():
            expected = yaml_block(getting_started, needle)

            self.assertIsNotNone(
                expected,
                f"No YAML block containing {needle!r} in docs/getting-started.md",
            )
            for relative_path in relative_paths:
                with self.subTest(example=needle, path=relative_path):
                    self.assertIn(expected, read(relative_path))
