from __future__ import annotations

import ast
import textwrap
from unittest import TestCase

from django_probe.usage import count_package_usage


def usage(
    source: str,
    packages: tuple[str, ...] = ("django",),
    settings: frozenset[str] = frozenset({"DEBUG", "LOGGING"}),
) -> dict[str, int]:
    tree = ast.parse(textwrap.dedent(source))
    return dict(count_package_usage(tree, packages, settings))


class PackageUsageTests(TestCase):
    def test_resolves_imports_aliases_calls_and_class_bases(self):
        result = usage(
            """
            import django
            import django.db.models as models
            from django.shortcuts import render as render_page
            from django.views.generic import TemplateView

            django.setup()
            field = models.CharField()
            render_page(None, "home.html")

            class HomeView(TemplateView):
                pass
            """
        )

        self.assertEqual(result["django"], 1)
        self.assertEqual(result["django.setup"], 1)
        self.assertEqual(result["django.db.models"], 1)
        self.assertEqual(result["django.db.models.CharField"], 1)
        self.assertEqual(result["django.shortcuts.render"], 2)
        self.assertEqual(result["django.views.generic.TemplateView"], 2)

    def test_keeps_package_boundaries(self):
        result = usage(
            """
            import django_extensions
            import django
            import ninja

            django.setup()
            django_extensions.configure()
            ninja.Router()
            """,
            packages=("django", "ninja"),
        )

        self.assertNotIn("django_extensions", result)
        self.assertEqual(result["django.setup"], 1)
        self.assertEqual(result["ninja.Router"], 1)

    def test_stops_at_function_return_values(self):
        result = usage(
            """
            from django.shortcuts import get_object_or_404
            from django.utils import timezone

            get_object_or_404(Book, pk=1).private_recalculate()
            timezone.now().strftime("%Y")
            """
        )

        self.assertEqual(result["django.shortcuts.get_object_or_404"], 2)
        self.assertEqual(result["django.utils.timezone"], 1)
        self.assertEqual(result["django.utils.timezone.now"], 1)
        self.assertNotIn("private_recalculate", " ".join(result))
        self.assertNotIn("strftime", " ".join(result))

    def test_folds_unknown_and_chained_django_settings(self):
        result = usage(
            """
            from django.conf import settings

            debug = settings.DEBUG
            region = settings.INTERNAL_BILLING_REGION
            logging = settings.LOGGING.get("handlers")
            """
        )

        self.assertEqual(result["django.conf.settings"], 2)
        self.assertEqual(result["django.conf.settings.DEBUG"], 1)
        self.assertEqual(result["django.conf.settings.LOGGING"], 1)
        self.assertNotIn("INTERNAL_BILLING_REGION", result)
        self.assertNotIn("get", " ".join(result))

    def test_reassigned_and_shadowed_imports_do_not_leak_names(self):
        result = usage(
            """
            from django import forms
            forms = application_forms
            forms.PrivateCheckoutForm()

            from django import shortcuts

            def render(shortcuts):
                return shortcuts.internal_render()

            private = [shortcuts.PrivateView for shortcuts in application_shortcuts]
            """
        )

        self.assertEqual(result, {"django.forms": 1, "django.shortcuts": 1})

    def test_relative_and_wildcard_imports_do_not_invent_names(self):
        result = usage(
            """
            from .django import local
            from django.shortcuts import *

            local.secret()
            render(None, "home.html")
            """
        )

        self.assertEqual(result, {})
