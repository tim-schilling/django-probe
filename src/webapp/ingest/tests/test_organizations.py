from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ingest.models import (
    SLUG_COLLISION_RETRIES,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
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

    def test_slug_generated_from_name(self):
        self.assertEqual(self.organization.slug, "django-team")

    def test_slug_collision_gets_a_suffix(self):
        """Two organizations with the same name get distinct slugs."""
        other = OrganizationFactory(name="Django team", owner=self.owner)

        self.assertEqual(other.slug, "django-team-2")

    def test_slug_stable_across_unrelated_saves(self):
        self.organization.name = "Renamed team"
        self.organization.save()

        self.assertEqual(self.organization.slug, "django-team")

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

    def test_project_name_is_unique_per_organization(self):
        ProjectFactory(organization=self.organization, name="Website")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectFactory(organization=self.organization, name="website")

        other_organization = OrganizationFactory(name="Other team", owner=self.owner)
        ProjectFactory(organization=other_organization, name="Website")


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
        """Members see organization projects and all of a project's submissions."""
        first_submission = SubmissionFactory(project=self.project)
        second_submission = SubmissionFactory(project=self.project)
        self.client.force_login(self.member)

        organization_response = self.client.get(
            reverse("organization-detail", args=[self.organization.pk])
        )
        project_response = self.client.get(
            reverse("project-detail", args=[self.organization.pk, self.project.pk])
        )

        self.assertContains(organization_response, self.project.name)
        projects = list(organization_response.context["projects"])
        self.assertEqual(projects, [self.project])
        self.assertEqual(projects[0].latest_submission_id, second_submission.pk)
        self.assertEqual(
            list(project_response.context["page_obj"].object_list),
            [second_submission, first_submission],
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

    def test_member_transfer(self):
        """A member may transfer between organizations they belong to."""
        destination = OrganizationFactory(name="Other team", owner=self.owner)
        OrganizationMembershipFactory(
            organization=destination,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, self.project.pk]),
            {"name": self.project.name, "organization": destination.pk},
        )

        self.assertRedirects(
            response,
            reverse("project-detail", args=[destination.pk, self.project.pk]),
            fetch_redirect_response=False,
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.organization, destination)

    def test_members_can_do_everything_the_organization_offers(self):
        """Membership is the only thing authorization asks about.

        `role` is recorded but not enforced, so a member manages people and projects
        exactly as the creator does. Revisit this test first when roles start
        meaning something.
        """
        self.client.force_login(self.member)

        members_response = self.client.get(
            reverse("organization-members", args=[self.organization.pk])
        )
        project_response = self.client.post(
            reverse("project-create", args=[self.organization.pk]),
            {"name": "New project"},
        )
        regenerate_response = self.client.post(
            reverse(
                "project-token-regenerate",
                args=[self.organization.pk, self.project.pk],
            )
        )

        self.assertEqual(members_response.status_code, 200)
        self.assertEqual(project_response.status_code, 302)
        self.assertEqual(regenerate_response.status_code, 302)

    def test_a_non_member_is_still_shut_out(self):
        """The boundary that does exist: belonging to the organization at all."""
        self.client.force_login(self.outsider)

        for name, args in [
            ("organization-detail", [self.organization.pk]),
            ("organization-members", [self.organization.pk]),
            ("project-create", [self.organization.pk]),
        ]:
            with self.subTest(view=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=args)).status_code, 404
                )


class ProjectSubmissionsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.outsider = UserFactory(username="outsider")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.project = ProjectFactory(organization=cls.organization, name="Website")

    def setUp(self):
        self.client.force_login(self.owner)

    def url(self, project=None) -> str:
        project = project or self.project
        return reverse("project-submissions", args=[self.organization.pk, project.pk])

    def test_lists_submissions_newest_first(self):
        older = SubmissionFactory(project=self.project)
        newer = SubmissionFactory(project=self.project)

        response = self.client.get(self.url())

        self.assertEqual(list(response.context["page_obj"].object_list), [newer, older])

    def test_paginates_at_twenty_five_per_page(self):
        submissions = [SubmissionFactory(project=self.project) for _ in range(30)]
        submissions.reverse()

        first_page = self.client.get(self.url())
        second_page = self.client.get(self.url(), {"page": 2})

        self.assertEqual(
            list(first_page.context["page_obj"].object_list), submissions[:25]
        )
        self.assertEqual(
            list(second_page.context["page_obj"].object_list), submissions[25:]
        )

    def test_empty_state(self):
        response = self.client.get(self.url())

        self.assertContains(response, "No submissions for this project yet.")

    def test_outsider_cannot_view(self):
        self.client.force_login(self.outsider)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)

    def test_cross_organization_lookup(self):
        other_organization = OrganizationFactory(name="Other team", owner=self.owner)

        response = self.client.get(
            reverse(
                "project-submissions", args=[other_organization.pk, self.project.pk]
            )
        )

        self.assertEqual(response.status_code, 404)


class ProjectDetailSetupInstructionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.project = ProjectFactory(organization=cls.organization, name="Website")

    def setUp(self):
        self.client.force_login(self.owner)

    def url(self) -> str:
        return reverse("project-detail", args=[self.organization.pk, self.project.pk])

    def test_shown_by_default_with_no_submissions(self):
        response = self.client.get(self.url())

        self.assertTrue(response.context["show_setup_instructions"])

    def test_hidden_by_default_with_a_recent_submission(self):
        SubmissionFactory(project=self.project)

        response = self.client.get(self.url())

        self.assertFalse(response.context["show_setup_instructions"])

    def test_shown_by_default_when_the_latest_submission_is_old(self):
        submission = SubmissionFactory(project=self.project)
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=36)
        )

        response = self.client.get(self.url())

        self.assertTrue(response.context["show_setup_instructions"])


class OrganizationManagementViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.member = UserFactory(username="member")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_create_organization_form_suggests_a_fake_name(self):
        """A fresh create form is pre-filled with a suggested name, not blank."""
        response = self.client.get(reverse("organization-create"))

        suggested_name = response.context["form"]["name"].value()
        self.assertEqual(len(suggested_name.split(" ")), 3)

    def test_create_project_form_suggests_a_fake_name(self):
        response = self.client.get(
            reverse("project-create", args=[self.organization.pk])
        )

        suggested_name = response.context["form"]["name"].value()
        self.assertEqual(len(suggested_name.split(" ")), 3)

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
        """Owners can create projects within their organization; the token is generated."""
        response = self.client.post(
            reverse("project-create", args=[self.organization.pk]),
            {"name": "Website"},
        )

        project = Project.objects.get(organization=self.organization)
        self.assertTrue(project.token)
        self.assertRedirects(
            response,
            reverse("project-detail", args=[self.organization.pk, project.pk]),
            fetch_redirect_response=False,
        )

    def test_duplicate_project_name_is_rejected(self):
        ProjectFactory(organization=self.organization, name="Website")

        response = self.client.post(
            reverse("project-create", args=[self.organization.pk]),
            {"name": "Website"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "A project with this name already exists in this organization.",
        )
        self.assertEqual(
            Project.objects.filter(organization=self.organization).count(), 1
        )

    def test_edit_project_form_suggests_a_fake_name_on_request(self):
        """The edit form keeps the current name until a suggestion is requested."""
        project = ProjectFactory(organization=self.organization, name="Website")

        unchanged_response = self.client.get(
            reverse("project-edit", args=[self.organization.pk, project.pk])
        )
        suggested_response = self.client.get(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {"suggest": "1"},
        )

        self.assertEqual(unchanged_response.context["form"]["name"].value(), "Website")
        self.assertContains(
            unchanged_response,
            "Changing the organization moves this project and all its submissions.",
        )
        suggested_name = suggested_response.context["form"]["name"].value()
        self.assertNotEqual(suggested_name, "Website")
        self.assertEqual(len(suggested_name.split(" ")), 3)

    def test_rename_project(self):
        """Owners can rename a project without affecting its token."""
        project = ProjectFactory(organization=self.organization, name="Website")
        original_token = project.token

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {
                "name": "Marketing site",
                "organization": self.organization.pk,
            },
        )

        project.refresh_from_db()
        redirect_url = reverse(
            "project-detail", args=[self.organization.pk, project.pk]
        )
        self.assertRedirects(response, redirect_url, fetch_redirect_response=False)
        self.assertEqual(project.name, "Marketing site")
        self.assertEqual(project.token, original_token)

        # Check the success message doesn't contain the organization part.
        redirect_response = self.client.get(redirect_url)
        self.assertContains(redirect_response, "Updated project Marketing site.")
        self.assertNotContains(redirect_response, "Moved to organization")

    def test_rename_project_to_its_own_name_is_allowed(self):
        project = ProjectFactory(organization=self.organization, name="Website")

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {"name": "Website", "organization": self.organization.pk},
        )

        self.assertRedirects(
            response,
            reverse("project-detail", args=[self.organization.pk, project.pk]),
            fetch_redirect_response=False,
        )

    def test_rename_project_to_a_duplicate_name_is_rejected(self):
        ProjectFactory(organization=self.organization, name="Website")
        other_project = ProjectFactory(organization=self.organization, name="Docs")

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, other_project.pk]),
            {"name": "Website", "organization": self.organization.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "A project with this name already exists in this organization.",
        )
        other_project.refresh_from_db()
        self.assertEqual(other_project.name, "Docs")

    def test_transfer_project(self):
        destination = OrganizationFactory(name="Other team", owner=self.owner)
        source_member = UserFactory(username="source-member")
        destination_member = UserFactory(username="destination-member")
        OrganizationMembershipFactory(
            organization=self.organization,
            user=source_member,
            role=OrganizationMembership.Role.MEMBER,
        )
        OrganizationMembershipFactory(
            organization=destination,
            user=destination_member,
            role=OrganizationMembership.Role.MEMBER,
        )
        project = ProjectFactory(organization=self.organization, name="Website")
        submission = SubmissionFactory(project=project)
        original_token = project.token

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {"name": project.name, "organization": destination.pk},
        )

        project.refresh_from_db()
        redirect_url = reverse("project-detail", args=[destination.pk, project.pk])
        self.assertRedirects(response, redirect_url, fetch_redirect_response=False)
        self.assertEqual(project.organization, destination)
        self.assertEqual(project.token, original_token)

        # Check the success message contains the organization part.
        redirect_response = self.client.get(redirect_url)
        self.assertContains(
            redirect_response,
            f"Updated project {project.name}. Moved to organization {destination.name}",
        )

        self.client.force_login(source_member)
        self.assertEqual(
            self.client.get(
                reverse("submission-detail", args=[submission.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "project-detail",
                    args=[self.organization.pk, project.pk],
                )
            ).status_code,
            404,
        )

        self.client.force_login(destination_member)
        self.assertEqual(
            self.client.get(
                reverse("submission-detail", args=[submission.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("project-detail", args=[destination.pk, project.pk])
            ).status_code,
            200,
        )

    def test_transfer_requires_membership(self):
        outsider = UserFactory(username="outsider")
        destination = OrganizationFactory(name="Other team", owner=outsider)
        project = ProjectFactory(organization=self.organization, name="Website")

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {"name": project.name, "organization": destination.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "organization",
            "Select a valid choice. That choice is not one of the available choices.",
        )
        project.refresh_from_db()
        self.assertEqual(project.organization, self.organization)

    def test_transfer_duplicate_name(self):
        destination = OrganizationFactory(name="Other team", owner=self.owner)
        ProjectFactory(organization=destination, name="Website")
        project = ProjectFactory(organization=self.organization, name="website")

        response = self.client.post(
            reverse("project-edit", args=[self.organization.pk, project.pk]),
            {"name": project.name, "organization": destination.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "A project with this name already exists in this organization.",
        )
        project.refresh_from_db()
        self.assertEqual(project.organization, self.organization)

    def test_regenerate_token(self):
        """Owners can regenerate a project's token."""
        project = ProjectFactory(organization=self.organization, name="Website")
        original_token = project.token

        response = self.client.post(
            reverse(
                "project-token-regenerate",
                args=[self.organization.pk, project.pk],
            )
        )

        project.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("project-detail", args=[self.organization.pk, project.pk]),
            fetch_redirect_response=False,
        )
        self.assertNotEqual(project.token, original_token)

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


class OrganizationSlugCollisionTests(TestCase):
    """Choosing a free slug and inserting it are separate steps, so a concurrent
    create can take the chosen slug in between. The insert is what decides."""

    def test_retries_when_the_chosen_slug_is_taken_first(self):
        OrganizationFactory(name="Django")
        organization = Organization(name="Django")

        with mock.patch.object(
            Organization,
            "_generate_unique_slug",
            side_effect=["django", "django-2"],
        ) as generate:
            organization.save()

        self.assertEqual(organization.slug, "django-2")
        self.assertEqual(generate.call_count, 2)

    def test_gives_up_rather_than_retrying_forever(self):
        OrganizationFactory(name="Django")
        organization = Organization(name="Django")

        with (
            mock.patch.object(
                Organization, "_generate_unique_slug", return_value="django"
            ) as generate,
            self.assertRaises(IntegrityError),
        ):
            organization.save()

        self.assertEqual(generate.call_count, SLUG_COLLISION_RETRIES)

    def test_an_uncontended_save_still_takes_the_plain_slug(self):
        organization = OrganizationFactory(name="Django")

        self.assertEqual(organization.slug, "django")

    def test_an_explicit_slug_is_left_alone(self):
        organization = Organization(name="Django", slug="chosen-by-hand")
        organization.save()

        self.assertEqual(organization.slug, "chosen-by-hand")


class ProjectDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(owner=cls.owner)
        cls.project = ProjectFactory(organization=cls.organization)
        cls.submission = SubmissionFactory(project=cls.project)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_default_deletion_retains_submission(self):
        response = self.client.post(
            reverse("project-delete", args=[self.organization.pk, self.project.pk])
        )

        self.assertRedirects(
            response,
            reverse("organization-detail", args=[self.organization.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.project_id)

    def test_opt_in_deletion_deletes_submission(self):
        self.client.post(
            reverse("project-delete", args=[self.organization.pk, self.project.pk]),
            {"delete_submissions": "on"},
        )

        self.assertFalse(Submission.objects.filter(pk=self.submission.pk).exists())

    def test_shared_organization_cannot_delete_project(self):
        OrganizationMembershipFactory(
            organization=self.organization,
            user=UserFactory(username="member"),
        )

        response = self.client.get(
            reverse("project-delete", args=[self.organization.pk, self.project.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_shared_organization_explains_why_deletion_is_unavailable(self):
        """The project page should explain the restriction, not just hide the link."""
        OrganizationMembershipFactory(
            organization=self.organization,
            user=UserFactory(username="member"),
        )

        response = self.client.get(
            reverse("project-detail", args=[self.organization.pk, self.project.pk])
        )

        self.assertNotContains(response, "Delete project")
        self.assertContains(response, "single member")


class OrganizationDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(owner=cls.owner)
        cls.project = ProjectFactory(organization=cls.organization)
        cls.submission = SubmissionFactory(project=cls.project)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_default_deletion_retains_submission(self):
        response = self.client.post(
            reverse("organization-delete", args=[self.organization.pk])
        )

        self.assertRedirects(
            response, reverse("account"), fetch_redirect_response=False
        )
        self.assertFalse(Organization.objects.filter(pk=self.organization.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.project_id)

    def test_opt_in_deletion_deletes_submission(self):
        self.client.post(
            reverse("organization-delete", args=[self.organization.pk]),
            {"delete_submissions": "on"},
        )

        self.assertFalse(Submission.objects.filter(pk=self.submission.pk).exists())

    def test_shared_organization_cannot_delete_organization(self):
        OrganizationMembershipFactory(
            organization=self.organization,
            user=UserFactory(username="member"),
        )

        response = self.client.get(
            reverse("organization-delete", args=[self.organization.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Organization.objects.filter(pk=self.organization.pk).exists())

    def test_sole_member_sees_delete_instead_of_leave(self):
        response = self.client.get(
            reverse("organization-detail", args=[self.organization.pk])
        )

        self.assertContains(response, "Delete organization")
        self.assertNotContains(response, "Leave organization")

    def test_shared_member_sees_leave_instead_of_delete(self):
        OrganizationMembershipFactory(
            organization=self.organization,
            user=UserFactory(username="member"),
        )

        response = self.client.get(
            reverse("organization-detail", args=[self.organization.pk])
        )

        self.assertContains(response, "Leave organization")
        self.assertNotContains(response, "Delete organization")
