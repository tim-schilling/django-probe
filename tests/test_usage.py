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
        """Each reference counts once, regardless of how the name was imported."""
        result = usage(
            """
            import django
            import django.db.models as models
            from django.db.models import F, Q
            from django.shortcuts import render as render_page
            from django.views.decorators.http import require_POST
            from django.views.generic import TemplateView

            django.setup()
            field = models.CharField()
            models.F("a")
            render_page(None, "home.html")

            @require_POST
            def submit(request):
                F("b")

            class HomeView(TemplateView):
                pass
            """
        )

        self.assertEqual(
            result,
            {
                "django.setup": 1,
                "django.db.models.CharField": 1,
                "django.db.models.F": 2,
                "django.db.models.Q": 1,
                "django.shortcuts.render": 1,
                "django.views.decorators.http.require_POST": 1,
                "django.views.generic.TemplateView": 1,
            },
        )

    def test_keeps_package_boundaries(self):
        """Packages without an API catalog report attributes the project adds."""
        result = usage(
            """
            import django_extensions
            import django
            import ninja
            from ninja import Schema

            django.setup()
            django_extensions.configure()
            ninja.Router()
            Schema.private_validator()
            """,
            packages=("django", "ninja"),
        )

        self.assertEqual(
            result,
            {
                "django.setup": 1,
                "ninja.Router": 1,
                "ninja.Schema.private_validator": 1,
            },
        )

    def test_stops_at_function_return_values(self):
        result = usage(
            """
            from django.shortcuts import get_object_or_404
            from django.utils import timezone

            get_object_or_404(Book, pk=1).private_recalculate()
            timezone.now().strftime("%Y")
            """
        )

        self.assertEqual(result["django.shortcuts.get_object_or_404"], 1)
        self.assertEqual(result["django.utils.timezone.now"], 1)
        self.assertNotIn("private_recalculate", " ".join(result))
        self.assertNotIn("strftime", " ".join(result))

    def test_resolves_django_singletons(self):
        result = usage(
            """
            from django.contrib import admin
            from django.core.cache import cache
            from django.db import connection, transaction

            admin.site.register(Book)
            cached = cache.get("book")
            cache.set("book", cached)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            with transaction.atomic():
                save_book()
            transaction.on_commit(notify)

            async def save_book_async():
                async with transaction.atomic():
                    await save_book()
            """
        )

        self.assertEqual(
            result,
            {
                "django.contrib.admin.site.register": 1,
                "django.core.cache.cache.get": 1,
                "django.core.cache.cache.set": 1,
                "django.db.connection.cursor": 1,
                "django.db.transaction.atomic": 2,
                "django.db.transaction.on_commit": 1,
            },
        )

    def test_decorators(self):
        """Decorators count on classes, with arguments, and as arguments."""
        result = usage(
            """
            from django.contrib.auth.decorators import login_required
            from django.utils.decorators import method_decorator
            from django.views.decorators.cache import cache_page

            @method_decorator(login_required, name="dispatch")
            class BookView:
                @method_decorator(cache_page(60))
                def get(self, request):
                    pass
            """
        )

        self.assertEqual(
            result,
            {
                "django.contrib.auth.decorators.login_required": 1,
                "django.utils.decorators.method_decorator": 2,
                "django.views.decorators.cache.cache_page": 1,
            },
        )

    def test_descriptors(self):
        """Model fields and cached_property in a class body count."""
        result = usage(
            """
            from django.db import models
            from django.utils.functional import cached_property

            class Book(models.Model):
                title = models.CharField(max_length=100)

                @cached_property
                def slug(self):
                    pass

                @property
                def label(self):
                    pass
            """
        )

        self.assertEqual(
            result,
            {
                "django.db.models.Model": 1,
                "django.db.models.CharField": 1,
                "django.utils.functional.cached_property": 1,
            },
        )

    def test_monkeypatched_attributes(self):
        """Attributes the application adds to Django classes aren't reported."""
        result = usage(
            """
            from django.db import models
            from django.db.models import QuerySet

            QuerySet.private_bulk_archive = archive
            models.QuerySet.private_counter += 1
            del QuerySet.private_bulk_archive
            QuerySet.private_bulk_archive(queryset)
            QuerySet.delete = safe_delete
            """
        )

        self.assertEqual(result, {"django.db.models.QuerySet.delete": 1})

    def test_patched_bases(self):
        """Members of application classes patched into a Django class's bases.

        Only the Django class's own members are reported.
        """
        result = usage(
            """
            from django.views.generic import View

            class AuditMixin:
                def private_audit(self):
                    pass

            View.__bases__ = (AuditMixin, *View.__bases__)
            View.private_audit(view)
            View.as_view()
            """
        )

        self.assertEqual(result, {"django.views.generic.View.as_view": 1})

    def test_inherited_members(self):
        """Members inherited or added by a metaclass resolve through subclasses.

        A reverse relation defined by the application isn't reported.
        """
        result = usage(
            """
            from django.contrib.auth.models import User
            from django.views.generic import TemplateView

            User.objects.filter(is_active=True)
            User.is_authenticated
            User.DoesNotExist
            User.private_profile
            TemplateView.as_view()
            """
        )

        self.assertEqual(
            result,
            {
                "django.contrib.auth.models.User.DoesNotExist": 1,
                "django.contrib.auth.models.User.is_authenticated": 1,
                "django.contrib.auth.models.User.objects.filter": 1,
                "django.views.generic.TemplateView.as_view": 1,
            },
        )

    def test_folds_unknown_and_chained_django_settings(self):
        result = usage(
            """
            from django.conf import settings

            debug = settings.DEBUG
            region = settings.INTERNAL_BILLING_REGION
            logging = settings.LOGGING.get("handlers")
            """
        )

        self.assertEqual(result["django.conf.settings"], 1)
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

    def test_duplicate_unreferenced_import(self):
        """Importing the same unreferenced name twice counts it once."""
        result = usage(
            """
            from django.db.models import Q
            from django.db.models import Q
            """
        )

        self.assertEqual(result, {"django.db.models.Q": 1})

    def test_reference_above_import(self):
        """A function defined above the import isn't resolved.

        The import then counts once as unreferenced.
        """
        result = usage(
            """
            def annotate():
                return F("a")

            from django.db.models import F
            """
        )

        self.assertEqual(result, {"django.db.models.F": 1})

    def test_string_annotation(self):
        """A name only used in a string annotation counts once as unreferenced."""
        result = usage(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                from django.db.models import QuerySet

            def books(queryset: "QuerySet"):
                pass
            """
        )

        self.assertEqual(result, {"django.db.models.QuerySet": 1})

    def test_except_clauses(self):
        """Exception classes in except clauses count as references."""
        result = usage(
            """
            from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
            from django.db import IntegrityError
            from django import forms

            try:
                save()
            except ObjectDoesNotExist:
                pass
            except (PermissionDenied, IntegrityError) as exc:
                pass
            except forms.ValidationError:
                pass
            except Book.DoesNotExist:
                pass
            """
        )

        self.assertEqual(
            result,
            {
                "django.core.exceptions.ObjectDoesNotExist": 1,
                "django.core.exceptions.PermissionDenied": 1,
                "django.db.IntegrityError": 1,
                "django.forms.ValidationError": 1,
            },
        )

    def test_fallback_import(self):
        """The import replaced by the except branch counts once as unreferenced."""
        result = usage(
            """
            try:
                from django.urls import re_path
            except ImportError:
                from django.conf.urls import url as re_path

            re_path("^$", home)
            """
        )

        self.assertEqual(result, {"django.urls.re_path": 1, "django.conf.urls.url": 1})

    def test_module_imports_sharing_a_name(self):
        """Imports binding the same name are used together.

        `django.utils` isn't reported because the shared `django` name is used.
        """
        result = usage(
            """
            import django.db.models
            import django.utils

            django.db.models.F("a")
            """
        )

        self.assertEqual(result, {"django.db.models.F": 1})

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
