from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class SignalReceiverTests(TestCase):
    def test_decorator(self):
        result = counts(
            """
            from django.dispatch import receiver
            from django.db.models.signals import post_save

            @receiver(post_save)
            def handler(sender, **kwargs):
                pass
            """
        )
        self.assertEqual(result["probe:signal_receiver"], 1)

    def test_requires_django_import(self):
        """A local function named `receiver` is not a Django signal handler."""
        result = counts(
            """
            def receiver(signal):
                return lambda fn: fn

            @receiver("anything")
            def handler():
                pass
            """
        )
        self.assertNotIn("probe:signal_receiver", result)
