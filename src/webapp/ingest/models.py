from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

CLI_AUTH_REQUEST_TTL = timedelta(minutes=10)
#: How long an issued CLI credential stays valid. A credential is a bearer token on
#: a developer's laptop, so it expires on its own rather than living until someone
#: remembers to revoke it.
CLI_CREDENTIAL_TTL = timedelta(days=90)


def hash_cli_token(token: str) -> str:
    """Digest an issued CLI credential for storage.

    A plain SHA-256, deliberately: the token is 32 bytes from `secrets`, so there is
    no low-entropy input for a slow KDF to protect and nothing to gain from salting.
    """
    return hashlib.sha256(token.encode()).hexdigest()


SLUG_COLLISION_RETRIES = 5


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
        if self.slug:
            return super().save(*args, **kwargs)

        # Picking a free slug and inserting it are two steps, so two organizations
        # created with the same name at the same time can choose the same one and
        # the loser hits the unique constraint. Retrying rereads the slugs the
        # winner committed, so the second attempt picks the next suffix.
        for _ in range(SLUG_COLLISION_RETRIES):
            self.slug = self._generate_unique_slug()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                continue
        raise IntegrityError(
            f"could not find a free slug for {self.name!r} after "
            f"{SLUG_COLLISION_RETRIES} attempts"
        )

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
        """Descriptive only: nothing is authorized on it.

        Every action an organization has - creating projects, regenerating tokens,
        adding and removing people - is available to any member. The distinction is
        recorded so it is there to build on once there is enough adoption to need
        it, but do not read it as a permission boundary today.
        """

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


class CliCredentialQuerySet(models.QuerySet):
    def active(self):
        """Credentials that can still authenticate a request."""
        return self.filter(
            token_digest__isnull=False,
            revoked_at__isnull=True,
            token_expires_at__gt=timezone.now(),
        )


class CliCredential(models.Model):
    """A CLI device-login request and, once approved, the resulting credential.

    A request and its credential are the same row at different life stages, so
    state is derived from these fields rather than tracked in a parallel status
    field: pending (`approved_at` and `denied_at` both null, `expires_at` in the
    future), expired (same, but `expires_at` has passed), denied (`denied_at`
    set), approved (`approved_at` set).

    The credential itself is never stored. Approving records only the decision; the
    token is minted when the CLI collects it and only its digest is kept, so a
    reader of this table cannot authenticate as anyone.
    """

    code = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        default=_generate_cli_credential_code,
        help_text="Ephemeral device-flow secret embedded in the verify URL and used for polling.",
    )
    token_digest = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text=(
            "SHA-256 of the issued credential. The credential is shown once, when "
            "the CLI collects it, and is never stored."
        ),
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
    #: When the login *request* stops being approvable, not when the credential
    #: expires; see `token_expires_at` for that.
    expires_at = models.DateTimeField(default=_cli_auth_request_expiry)
    approved_at = models.DateTimeField(null=True, blank=True)
    denied_at = models.DateTimeField(null=True, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = CliCredentialQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_pending(self) -> bool:
        """Still awaiting a decision, and not yet expired."""
        return (
            self.approved_at is None
            and self.denied_at is None
            and self.expires_at > timezone.now()
        )

    @property
    def is_active(self) -> bool:
        """Collected, still within its lifetime, and not revoked."""
        return (
            self.token_digest is not None
            and self.revoked_at is None
            and self.token_expires_at is not None
            and self.token_expires_at > timezone.now()
        )

    @property
    def status(self) -> str:
        """A single word for the account page to show."""
        if self.revoked_at is not None:
            return "revoked"
        if self.token_digest is None:
            return "denied" if self.denied_at is not None else "pending"
        return "active" if self.is_active else "expired"

    def issue_token(self) -> str:
        """Mint a credential for this request, storing only its digest.

        Returns the one and only copy of the token. Callers must hand it straight to
        the CLI: there is no way to recover it afterwards, by design.
        """
        token = secrets.token_hex(32)
        now = timezone.now()
        self.token_digest = hash_cli_token(token)
        self.token_expires_at = now + CLI_CREDENTIAL_TTL
        self.retrieved_at = now
        return token

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
