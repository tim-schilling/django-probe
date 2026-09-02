from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from ingest.models import (
    Organization,
    OrganizationMembership,
    Project,
)
from ingest.tests.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
)


class OrganizationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.owner_membership = cls.owner.organization_memberships.get(
            organization=cls.organization
        )

    def test_create_with_owner(self):
        """Creation establishes the required first owner membership."""
        self.assertEqual(self.organization.members.get(), self.owner)
        self.assertEqual(
            self.owner_membership.role,
            OrganizationMembership.Role.OWNER,
        )

    def test_organization_uses_uuid7_primary_key(self):
        self.assertEqual(self.organization.pk.version, 7)

    def test_unique_membership(self):
        """A user has at most one membership in an organization."""
        with self.assertRaises(IntegrityError):
            OrganizationMembershipFactory(
                organization=self.organization,
                user=self.owner,
                role=OrganizationMembership.Role.MEMBER,
            )

    def test_valid_roles(self):
        """Membership roles are limited to the declared choices."""
        member = UserFactory(username="member")
        membership = OrganizationMembership(
            organization=self.organization,
            user=member,
            role="administrator",
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_project_organization(self):
        """Every project belongs to exactly one organization."""
        project = ProjectFactory(
            organization=self.organization,
            name="Website",
        )
        second_project = ProjectFactory(
            organization=self.organization,
            name="Documentation",
        )

        self.assertEqual(project.organization, self.organization)
        self.assertEqual(
            set(self.organization.projects.all()), {project, second_project}
        )
        with self.assertRaises(IntegrityError):
            Project.objects.create(organization=None, name="Unowned")


class OrganizationAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.member = UserFactory(username="member")
        cls.outsider = UserFactory(username="outsider")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        OrganizationMembershipFactory(
            organization=cls.organization,
            user=cls.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        cls.project = ProjectFactory(
            organization=cls.organization,
            name="Website",
        )

    def test_member_access(self):
        """Members see organization projects and submissions from every member."""
        owner_submission = SubmissionFactory(user=self.owner, project=self.project)
        member_submission = SubmissionFactory(user=self.member, project=self.project)
        self.client.force_login(self.member)

        organization_response = self.client.get(
            reverse("organization-detail", args=[self.organization.pk])
        )
        project_response = self.client.get(
            reverse("project-detail", args=[self.organization.pk, self.project.pk])
        )

        self.assertContains(organization_response, self.project.name)
        self.assertEqual(
            list(organization_response.context["recent_submissions"]),
            [member_submission, owner_submission],
        )
        self.assertEqual(
            list(project_response.context["submissions"]),
            [member_submission, owner_submission],
        )

    def test_outsider_access(self):
        """Nonmembers cannot discover an organization or its projects."""
        self.client.force_login(self.outsider)

        organization_response = self.client.get(
            reverse("organization-detail", args=[self.organization.pk])
        )
        project_response = self.client.get(
            reverse("project-detail", args=[self.organization.pk, self.project.pk])
        )

        self.assertEqual(organization_response.status_code, 404)
        self.assertEqual(project_response.status_code, 404)

    def test_cross_organization_lookup(self):
        """A project URL cannot address the project through another organization."""
        other_organization = OrganizationFactory(name="Other team", owner=self.member)
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("project-detail", args=[other_organization.pk, self.project.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_member_permissions(self):
        """Ordinary members cannot manage membership or create projects."""
        self.client.force_login(self.member)

        members_response = self.client.get(
            reverse("organization-members", args=[self.organization.pk])
        )
        project_response = self.client.post(
            reverse("project-create", args=[self.organization.pk]),
            {"name": "New project", "key": str(uuid.uuid4())},
        )

        self.assertEqual(members_response.status_code, 403)
        self.assertEqual(project_response.status_code, 403)


class OrganizationManagementViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.member = UserFactory(username="member")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_create_organization(self):
        """The user creating an organization becomes its first owner."""
        response = self.client.post(
            reverse("organization-create"),
            {"name": "New organization"},
        )

        organization = Organization.objects.get(name="New organization")
        self.assertRedirects(
            response,
            reverse("organization-detail", args=[organization.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            organization.memberships.get(user=self.owner).role,
            OrganizationMembership.Role.OWNER,
        )

    def test_create_project(self):
        """Owners can create projects within their organization."""
        key = uuid.uuid4()

        response = self.client.post(
            reverse("project-create", args=[self.organization.pk]),
            {"name": "Website", "key": str(key)},
        )

        project = Project.objects.get(organization=self.organization)
        self.assertEqual(project.key, key)
        self.assertRedirects(
            response,
            reverse("project-detail", args=[self.organization.pk, project.pk]),
            fetch_redirect_response=False,
        )

    def test_member_lifecycle(self):
        """Owners can add, promote, demote, and remove another member."""
        add_response = self.client.post(
            reverse("organization-member-add", args=[self.organization.pk]),
            {"username": self.member.username, "role": "member"},
        )
        membership = self.member.organization_memberships.get(
            organization=self.organization
        )

        promote_response = self.client.post(
            reverse(
                "organization-member-role",
                args=[self.organization.pk, membership.pk],
            ),
            {"role": "owner"},
        )
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)

        demote_response = self.client.post(
            reverse(
                "organization-member-role",
                args=[self.organization.pk, membership.pk],
            ),
            {"role": "member"},
        )
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.MEMBER)

        remove_response = self.client.post(
            reverse(
                "organization-member-remove",
                args=[self.organization.pk, membership.pk],
            )
        )

        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(promote_response.status_code, 302)
        self.assertEqual(demote_response.status_code, 302)
        self.assertEqual(remove_response.status_code, 302)
        self.assertFalse(
            OrganizationMembership.objects.filter(pk=membership.pk).exists()
        )

    def test_add_member_validation(self):
        """Adding a member requires an existing user who is not already a member."""
        missing_response = self.client.post(
            reverse("organization-member-add", args=[self.organization.pk]),
            {"username": "missing", "role": "member"},
        )
        OrganizationMembershipFactory(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        duplicate_response = self.client.post(
            reverse("organization-member-add", args=[self.organization.pk]),
            {"username": self.member.username, "role": "member"},
        )

        self.assertEqual(missing_response.status_code, 400)
        self.assertContains(
            missing_response,
            "No user has that username",
            status_code=400,
        )
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertContains(
            duplicate_response,
            "already a member",
            status_code=400,
        )

    def test_last_owner_actions(self):
        """The final owner cannot leave, remove themselves, or demote themselves."""
        membership = self.owner.organization_memberships.get(
            organization=self.organization
        )

        leave_response = self.client.post(
            reverse("organization-leave", args=[self.organization.pk]),
            follow=True,
        )
        remove_response = self.client.post(
            reverse(
                "organization-member-remove",
                args=[self.organization.pk, membership.pk],
            ),
            follow=True,
        )
        demote_response = self.client.post(
            reverse(
                "organization-member-role",
                args=[self.organization.pk, membership.pk],
            ),
            {"role": "member"},
            follow=True,
        )

        self.assertContains(leave_response, "must always have at least one owner")
        self.assertContains(remove_response, "must always have at least one owner")
        self.assertContains(demote_response, "must always have at least one owner")
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)

    def test_member_leave(self):
        """An ordinary member can leave an organization."""
        membership = OrganizationMembershipFactory(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("organization-leave", args=[self.organization.pk])
        )

        self.assertRedirects(
            response,
            reverse("account"),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            OrganizationMembership.objects.filter(pk=membership.pk).exists()
        )

    def test_owner_leave_with_successor(self):
        """An owner can leave when another owner remains."""
        second_owner = UserFactory(username="second-owner")
        OrganizationMembershipFactory(
            organization=self.organization,
            user=second_owner,
            role=OrganizationMembership.Role.OWNER,
        )
        membership = self.owner.organization_memberships.get(
            organization=self.organization
        )

        response = self.client.post(
            reverse("organization-leave", args=[self.organization.pk])
        )

        self.assertRedirects(
            response,
            reverse("account"),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            OrganizationMembership.objects.filter(pk=membership.pk).exists()
        )
