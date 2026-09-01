"""Tests for name resolution, shared by every probe via ``resolves_to``."""

from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class ImportFormTests(TestCase):
    def test_all_three_forms_resolve(self):
        forms = [
            "from django.dispatch import receiver\n\n@receiver(post_save)\n",
            "from django import dispatch\n\n@dispatch.receiver(post_save)\n",
            "import django.dispatch\n\n@django.dispatch.receiver(post_save)\n",
        ]
        for form in forms:
            with self.subTest(form=form.splitlines()[0]):
                result = counts(f"{form}def handler(sender, **kwargs):\n    pass\n")
                self.assertEqual(result["probe:signal_receiver"], 1)

    def test_aliased_import_not_resolved(self):
        """Matching django-upgrade: rebindings would need real scope analysis."""
        result = counts(
            """
            from django.dispatch import receiver as listen

            @listen(post_save)
            def handler(sender, **kwargs):
                pass
            """
        )
        self.assertNotIn("probe:signal_receiver", result)

    def test_wrong_import_depth_not_resolved(self):
        """`import django.dispatch` binds `django`, so a bare `dispatch.` is not it."""
        result = counts(
            """
            import django.dispatch

            @dispatch.receiver(post_save)
            def handler(sender, **kwargs):
                pass
            """
        )
        self.assertNotIn("probe:signal_receiver", result)


class EdgeCaseTests(TestCase):
    def test_empty_module(self):
        self.assertEqual(counts(""), {})

    def test_module_with_no_hits(self):
        self.assertEqual(counts("import os\n\nx = os.getcwd()\n"), {})
