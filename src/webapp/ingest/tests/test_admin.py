from __future__ import annotations

from django.contrib import admin
from django.test import SimpleTestCase

from ingest.models import CliCredential, Project


class CredentialExposureTests(SimpleTestCase):
    """A CLI token authenticates as its owner, so it stays out of the admin.

    A project token is only an association identifier - it grants no access - so
    listing and searching it is a legitimate support affordance, not a leak.
    """

    def test_cli_credential_tokens_are_not_listed(self):
        options = admin.site._registry[CliCredential]

        self.assertNotIn("token", options.list_display)
        self.assertNotIn("token", options.search_fields)

    def test_cli_credentials_cannot_be_hand_authored(self):
        options = admin.site._registry[CliCredential]

        self.assertIs(options.has_add_permission(None), False)

    def test_project_tokens_stay_available_for_support(self):
        options = admin.site._registry[Project]

        self.assertIn("token", options.list_display)

    def test_project_names_are_not_exposed(self):
        """A project name is the customer's own choice of words, unlike the
        opaque token above - staff have no support reason to read it."""
        options = admin.site._registry[Project]

        self.assertNotIn("name", options.list_display)
        self.assertNotIn("name", options.search_fields)
        self.assertIn("name", options.exclude)

    def test_projects_cannot_be_hand_authored(self):
        options = admin.site._registry[Project]

        self.assertIs(options.has_add_permission(None), False)
