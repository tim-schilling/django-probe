from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class DjangoTaskTests(TestCase):
    def test_bare_and_called_decorator(self):
        result = counts(
            """
            from django.tasks import task

            @task
            def send_email():
                pass

            @task(priority=1)
            def resize():
                pass
            """,
            filename="tasks.py",
        )
        self.assertEqual(result["probe:django_task"], 2)

    def test_module_import_form(self):
        result = counts(
            """
            from django import tasks

            @tasks.task
            def send_email():
                pass
            """,
            filename="tasks.py",
        )
        self.assertEqual(result["probe:django_task"], 1)

    def test_fully_dotted_form(self):
        result = counts(
            """
            import django.tasks

            @django.tasks.task
            def send_email():
                pass
            """,
            filename="tasks.py",
        )
        self.assertEqual(result["probe:django_task"], 1)

    def test_async_task(self):
        result = counts(
            """
            from django.tasks import task

            @task
            async def send_email():
                pass
            """,
            filename="tasks.py",
        )
        self.assertEqual(result["probe:django_task"], 1)

    def test_celery_excluded(self):
        """Scoped to django.tasks; Celery is a different question."""
        result = counts(
            """
            from celery import shared_task

            @shared_task
            def send_email():
                pass

            @app.task
            def resize():
                pass
            """,
            filename="tasks.py",
        )
        self.assertEqual(result, {})

    def test_unrelated_task_decorator_excluded(self):
        """`invoke` also exports a `task` decorator, and is common in Django repos."""
        result = counts(
            """
            from invoke import task

            @task
            def build(c):
                pass
            """,
            filename="tasks.py",
        )
        self.assertNotIn("probe:django_task", result)
