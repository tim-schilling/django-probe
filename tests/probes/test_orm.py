from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class QuerySetMethodTests(TestCase):
    def test_each_method_counted_separately(self):
        result = counts(
            """
            def view(request):
                qs = Book.objects.filter(a=1).exclude(b=2).annotate(n=Count("x"))
                other = Book.objects.filter(c=3)
                return qs.alias(m=F("n")).extra(where=["1=1"])
            """
        )
        self.assertEqual(result["probe:queryset_filter"], 2)
        self.assertEqual(result["probe:queryset_exclude"], 1)
        self.assertEqual(result["probe:queryset_annotate"], 1)
        self.assertEqual(result["probe:queryset_alias"], 1)
        self.assertEqual(result["probe:queryset_extra"], 1)

    def test_no_cross_crediting(self):
        """A single shared visitor would credit one match to all five probes."""
        self.assertEqual(counts("x = qs.filter(a=1)\n"), {"probe:queryset_filter": 1})


class TemplateLibraryTests(TestCase):
    """`register.filter` is tag registration, the only measured false positive."""

    def test_library_filter_excluded(self):
        result = counts(
            """
            from django import template

            register = template.Library()

            @register.filter(name="upper")
            def do_upper(value):
                return value.upper()
            """,
            filename="templatetags/my_tags.py",
        )
        self.assertEqual(result, {})

    def test_bare_library_import(self):
        result = counts(
            """
            from django.template import Library

            register = Library()

            @register.filter
            def do_upper(value):
                return value.upper()

            def view(request):
                return Book.objects.filter(a=1)
            """
        )
        self.assertEqual(result, {"probe:queryset_filter": 1})

    def test_library_bound_to_attribute(self):
        """`self.library = Library()`, as Django's own template tests do."""
        result = counts(
            """
            from django.template import Library

            class LibraryTests(TestCase):
                def setUp(self):
                    self.library = Library()

                def test_filter(self):
                    @self.library.filter
                    def func():
                        return ""
            """
        )
        self.assertEqual(result, {})

    def test_unrelated_register_still_counts(self):
        """Only names actually bound to a Library are excluded."""
        result = counts("register = get_registry()\nx = register.filter(a=1)\n")
        self.assertEqual(result, {"probe:queryset_filter": 1})
