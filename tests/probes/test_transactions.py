from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class TransactionAtomicTests(TestCase):
    def test_decorator_and_context_manager(self):
        result = counts(
            """
            from django.db import transaction

            @transaction.atomic
            def rebuild():
                with transaction.atomic():
                    pass
            """
        )
        self.assertEqual(result["probe:transaction_atomic"], 2)

    def test_nested_in_class(self):
        """Imports must be recorded before the code below them is visited."""
        result = counts(
            """
            from django.db import transaction

            class Service:
                def run(self):
                    with transaction.atomic():
                        pass
            """
        )
        self.assertEqual(result["probe:transaction_atomic"], 1)
