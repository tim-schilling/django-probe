from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from ingest.tests.factories import UserFactory


class StyleGuideTests(TestCase):
    def test_style_guide_requires_staff_access(self):
        user = UserFactory(username="member")
        self.client.force_login(user)

        response = self.client.get(reverse("style-guide"))

        self.assertRedirects(
            response,
            f"{reverse('admin:login')}?next={reverse('style-guide')}",
        )

    def test_style_guide_renders_component_catalog(self):
        user = UserFactory(username="reviewer", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("style-guide"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "style_guide.html")
        self.assertContains(response, "Frontend style guide")
        self.assertContains(response, "Color tokens")
        self.assertContains(response, "guide-dialog")
        self.assertContains(response, "js/style-guide.js")
