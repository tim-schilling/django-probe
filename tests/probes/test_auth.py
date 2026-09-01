from __future__ import annotations

from unittest import TestCase

from tests.probes.helpers import counts


class CustomUserModelTests(TestCase):
    def test_abstract_user_subclass(self):
        result = counts(
            """
            from django.contrib.auth.models import AbstractUser

            class User(AbstractUser):
                pass
            """,
            filename="models.py",
        )
        self.assertEqual(result["probe:custom_user_model"], 1)

    def test_abstract_base_user_subclass(self):
        result = counts(
            """
            from django.contrib.auth.base_user import AbstractBaseUser

            class User(AbstractBaseUser):
                pass
            """,
            filename="models.py",
        )
        self.assertEqual(result["probe:custom_user_model"], 1)


class AuthUserModelSettingTests(TestCase):
    SOURCE = 'AUTH_USER_MODEL = "accounts.User"\n'

    def test_counted_in_settings_file(self):
        result = counts(self.SOURCE, filename="config/settings.py")
        self.assertEqual(result["probe:auth_user_model_setting"], 1)

    def test_ignored_elsewhere(self):
        """Gated on django-upgrade's looks_like_settings_file heuristic."""
        result = counts(self.SOURCE, filename="views.py")
        self.assertNotIn("probe:auth_user_model_setting", result)
