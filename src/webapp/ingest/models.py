from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models, transaction


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
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="OrganizationMembership",
        related_name="organizations",
    )

    objects = OrganizationManager()

    class Meta:
        ordering = ["name", "id"]

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
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.organization})"


class Submission(models.Model):
    """One report from one client run.

    The data is stored without a fixed schema. ``patterns`` is a flat
    ``{"namespace:name": count}`` dict, so a new pattern adds new keys and never
    requires a migration. This includes patterns from third-party packages that ship
    their own probes. See the README's forward-compatibility notes.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Null for anonymous submissions, which are the default and fully supported path.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submissions",
    )
    # Opaque random UUID chosen by the client. Independent of accounts: an anonymous
    # project can group its own submissions over time without ever signing up.
    project_key = models.UUIDField(null=True, blank=True, db_index=True)
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
        who = self.user or "anonymous"
        return f"{who} @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def total_occurrences(self) -> int:
        return sum(self.patterns.values())


class ApiToken(models.Model):
    """Opt-in credential attaching submissions to an account."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(32)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"token for {self.user}"
