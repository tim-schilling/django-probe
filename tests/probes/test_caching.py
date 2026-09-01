from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class CachePageTests(TestCase):
    def test_decorator(self):
        result = counts(
            """
            from django.views.decorators.cache import cache_page

            @cache_page(60)
            def index(request):
                pass
            """
        )
        self.assertEqual(result["probe:cache_page"], 1)

    def test_method_decorator_form(self):
        result = counts(
            """
            from django.utils.decorators import method_decorator
            from django.views.decorators.cache import cache_page

            urlpatterns = [path("", method_decorator(cache_page(60))(View))]
            """
        )
        self.assertEqual(result["probe:cache_page"], 1)

    def test_requires_django_import(self):
        result = counts(
            """
            from myproject.helpers import cache_page

            @cache_page(60)
            def index(request):
                pass
            """
        )
        self.assertNotIn("probe:cache_page", result)
