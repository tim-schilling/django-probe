from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

CLI_AUTH_REQUEST_TTL = timedelta(minutes=10)


def _cli_auth_request_expiry() -> datetime:
    return timezone.now() + CLI_AUTH_REQUEST_TTL


def _generate_cli_credential_code() -> str:
    return secrets.token_urlsafe(32)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)


class OrganizationManager(models.Manager):
    def create_with_owner(self, *, name: str, owner) -> Organization:
        with transaction.atomic():
            organization = self.create(name=name)
            OrganizationMembership.objects.create(
                organization=organization,
                user=owner,
                role=OrganizationMembership.Role.OWNER,
            )
        return organization


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, editable=False, db_index=False)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="OrganizationMembership",
        related_name="organizations",
    )

    objects = OrganizationManager()

    class Meta:
        ordering = ["name", "id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        return super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> str:
        base = slugify(self.name) or "org"
        slug = base
        suffix = 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    def __str__(self) -> str:
        return self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_membership",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "member"]),
                name="organization_membership_valid_role",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.organization} ({self.get_role_display()})"


class Project(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=200)
    token = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        return super().save(*args, **kwargs)

    def regenerate_token(self) -> None:
        self.token = secrets.token_hex(32)
        self.save(update_fields=["token"])

    def __str__(self) -> str:
        return f"{self.name} ({self.organization})"


class CliCredential(models.Model):
    """A CLI device-login request and, once approved, the resulting credential.

    A request and its credential are the same row at different life stages, so
    state is derived from these fields rather than tracked in a parallel status
    field: pending (`token` and `denied_at` both null, `expires_at` in the
    future), expired (same, but `expires_at` has passed), denied (`denied_at`
    set), approved (`token` set).
    """

    code = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        default=_generate_cli_credential_code,
        help_text="Ephemeral device-flow secret embedded in the verify URL and used for polling.",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text="The long-lived CLI credential, issued once the request is approved.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional human-readable name for the device, e.g. a hostname.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="cli_credentials",
    )
    # Set from `login --org` at request time, before anyone has authenticated. It is
    # only a hint for `cli_auth_verify` to resolve and check membership against - it
    # must never be trusted to imply the requester belongs to that org.
    requested_org_slug = models.CharField(max_length=220, blank=True, editable=False)
    # Only set once an authenticated member of this organization has approved the
    # request; never assigned from unauthenticated input.
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="cli_credentials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_cli_auth_request_expiry)
    denied_at = models.DateTimeField(null=True, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_pending(self) -> bool:
        """Still awaiting a decision, and not yet expired."""
        return (
            self.token is None
            and self.denied_at is None
            and self.expires_at > timezone.now()
        )

    def __str__(self) -> str:
        return self.label or self.code[:8]


class Submission(models.Model):
    """One submission from one client run.

    The data is stored without a fixed schema. ``patterns`` is a flat
    ``{"namespace:name": count}`` dict, so a new pattern adds new keys and never
    requires a migration. This includes patterns from third-party packages that ship
    their own probes. See the README's forward-compatibility notes.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Null for anonymous submissions, which remain supported for manual sharing.
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submissions",
    )

    schema_version = models.PositiveSmallIntegerField()
    client_version = models.CharField(max_length=128)
    python_version = models.CharField(max_length=128)
    django_version = models.CharField(max_length=128, blank=True)
    files_scanned = models.PositiveIntegerField()

    # {distribution: version} of the packages that supplied probes. Without this a
    # zero count is ambiguous: absent pattern, or nothing looking for it?
    probe_sources = models.JSONField(default=dict)
    patterns = models.JSONField(default=dict)
    dependencies = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.project or "anonymous"
        return f"{who} @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def total_occurrences(self) -> int:
        return sum(self.patterns.values())
