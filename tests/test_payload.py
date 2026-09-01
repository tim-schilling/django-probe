from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from django_probe.payload import build_payload

SOURCE = (
    "from django.db import transaction\n\n"
    "def rebuild():\n"
    "    with transaction.atomic():\n"
    "        Book.objects.filter(stale=True).delete()\n"
)


class PayloadTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_shape(self):
        (self.root / "app").mkdir()
        (self.root / "app" / "views.py").write_text(SOURCE, encoding="utf-8")

        payload = build_payload(self.root)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["files_scanned"], 1)
        self.assertEqual(payload["patterns"]["probe:transaction_atomic"], 1)
        self.assertEqual(payload["patterns"]["probe:queryset_filter"], 1)
        self.assertIn("django-probe", payload["probe_sources"])
        self.assertIsNone(payload["project_key"])

    def test_leaks_nothing_identifying(self):
        """The privacy claim, asserted rather than assumed."""
        (self.root / "app").mkdir()
        (self.root / "app" / "views.py").write_text(SOURCE, encoding="utf-8")

        serialized = json.dumps(build_payload(self.root))

        self.assertNotIn("views.py", serialized)
        self.assertNotIn("transaction.atomic", serialized)
        self.assertNotIn("Book", serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(self.root.name, serialized)

    def test_pattern_keys_namespaced(self):
        (self.root / "m.py").write_text(SOURCE, encoding="utf-8")

        patterns = build_payload(self.root)["patterns"]

        self.assertTrue(patterns)
        for key in patterns:
            namespace, separator, name = key.partition(":")
            self.assertTrue(separator, f"{key!r} is not namespaced")
            self.assertTrue(namespace and name)
