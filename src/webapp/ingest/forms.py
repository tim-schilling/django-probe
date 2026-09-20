from __future__ import annotations

from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from ingest.fake_names import generate_fake_name
from ingest.models import Organization, OrganizationMembership, Project, Submission


def _validate_project_name(
    *,
    name: str,
    organization: Organization,
    exclude_project: Project | None = None,
) -> None:
    queryset = Project.objects.filter(organization=organization, name__iexact=name)
    if exclude_project is not None:
        queryset = queryset.exclude(pk=exclude_project.pk)
    if queryset.exists():
        raise forms.ValidationError(
            "A project with this name already exists in this organization."
        )


class SocialSignupForm(AllauthSocialSignupForm):
    """The form shown if a GitHub sign-in can't auto-complete (e.g. an email
    collision). `disabled` makes Django use the initial value regardless of what's
    posted, so nobody can claim an email they don't control through this form.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "email" in self.fields:
            self.fields["email"].disabled = True
            self.fields["email"].help_text = "Provided by GitHub."


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance._state.adding:
            self.initial["name"] = generate_fake_name()


class ProjectForm(forms.ModelForm):
    def __init__(
        self, *args, organization: Organization, suggest_name: bool = False, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if not self.is_bound and (self.instance._state.adding or suggest_name):
            self.initial["name"] = generate_fake_name()

    def clean_name(self) -> str:
        name = self.cleaned_data["name"]
        _validate_project_name(
            name=name,
            organization=self.organization,
            exclude_project=None if self.instance._state.adding else self.instance,
        )
        return name

    class Meta:
        model = Project
        fields = ["name"]


class ProjectEditForm(forms.ModelForm):
    def __init__(self, *args, user, suggest_name: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = Organization.objects.filter(
            members=user
        ).order_by("name", "id")
        if not self.is_bound and suggest_name:
            self.initial["name"] = generate_fake_name()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        organization = cleaned_data.get("organization")
        if name and organization:
            try:
                _validate_project_name(
                    name=name,
                    organization=organization,
                    exclude_project=self.instance,
                )
            except forms.ValidationError as error:
                self.add_error("name", error)
        return cleaned_data

    class Meta:
        model = Project
        fields = ["name", "organization"]


class MembershipAddForm(forms.Form):
    username = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=OrganizationMembership.Role.choices)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"]
        user_model = get_user_model()
        if not user_model.objects.filter(username=username).exists():
            raise forms.ValidationError("No user has that username.")
        return username


class MembershipRoleForm(forms.Form):
    role = forms.ChoiceField(choices=OrganizationMembership.Role.choices)

    def __init__(self, *args, membership: OrganizationMembership, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership

    def clean_role(self) -> str:
        role = self.cleaned_data["role"]
        if role != OrganizationMembership.Role.OWNER and _is_last_owner(
            self.membership
        ):
            raise forms.ValidationError(
                "An organization must always have at least one owner."
            )
        return role


class MembershipDeleteForm(forms.Form):
    def __init__(self, *args, membership: OrganizationMembership, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if _is_last_owner(self.membership):
            raise forms.ValidationError(
                "An organization must always have at least one owner."
            )
        return cleaned_data

    def save(self) -> None:
        self.membership.delete()


class ProjectDeleteForm(forms.Form):
    delete_submissions = forms.BooleanField(required=False)

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        if project.organization.memberships.count() != 1:
            raise PermissionDenied(
                "Projects can only be deleted from single-member organizations."
            )
        self.project = project
        self.submission_count = project.submissions.count()

    def save(self) -> None:
        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(
                pk=self.project.organization_id
            )
            if organization.memberships.count() != 1:
                raise PermissionDenied(
                    "Projects can only be deleted from single-member organizations."
                )
            project = Project.objects.select_for_update().get(pk=self.project.pk)
            if self.cleaned_data["delete_submissions"]:
                project.submissions.all().delete()
            project.delete()


class OrganizationDeleteForm(forms.Form):
    delete_submissions = forms.BooleanField(required=False)

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        if organization.memberships.count() != 1:
            raise PermissionDenied(
                "Organizations can only be deleted by their sole member."
            )
        self.organization = organization
        self.projects = list(organization.projects.all())
        self.submission_count = Submission.objects.filter(
            project__in=self.projects
        ).count()

    def save(self) -> None:
        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(
                pk=self.organization.pk
            )
            if organization.memberships.count() != 1:
                raise PermissionDenied(
                    "Organizations can only be deleted by their sole member."
                )
            if self.cleaned_data["delete_submissions"]:
                Submission.objects.filter(project__organization=organization).delete()
            organization.delete()


class AccountDeleteForm(forms.Form):
    username = forms.CharField(max_length=150)
    delete_submissions = forms.BooleanField(required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        organizations = (
            Organization.objects.filter(members=user)
            .annotate(member_count=Count("memberships"))
            .prefetch_related("projects")
        )
        self.sole_member_organizations = [
            organization
            for organization in organizations
            if organization.member_count == 1
        ]
        self.shared_organizations = [
            organization
            for organization in organizations
            if organization.member_count > 1
        ]
        self.projects = [
            project
            for organization in self.sole_member_organizations
            for project in organization.projects.all()
        ]
        self.submission_count = Submission.objects.filter(
            project__in=self.projects
        ).count()

    def clean_username(self) -> str:
        username = self.cleaned_data["username"]
        if username != self.user.get_username():
            raise forms.ValidationError(
                "Enter your username to confirm account deletion."
            )
        return username

    def save(self) -> None:
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=self.user.pk)
            organization_ids = list(
                Organization.objects.filter(members=user)
                .annotate(member_count=Count("memberships"))
                .filter(member_count=1)
                .values_list("pk", flat=True)
            )
            organizations = list(
                Organization.objects.select_for_update().filter(pk__in=organization_ids)
            )
            organizations = [
                organization
                for organization in organizations
                if organization.memberships.count() == 1
            ]
            projects = list(
                Project.objects.filter(
                    organization__in=organizations
                ).select_for_update()
            )
            if self.cleaned_data["delete_submissions"]:
                Submission.objects.filter(project__in=projects).delete()
            Organization.objects.filter(
                pk__in=[organization.pk for organization in organizations]
            ).delete()
            user.delete()


def _is_last_owner(membership: OrganizationMembership) -> bool:
    return (
        membership.role == OrganizationMembership.Role.OWNER
        and not OrganizationMembership.objects.filter(
            organization=membership.organization,
            role=OrganizationMembership.Role.OWNER,
        )
        .exclude(pk=membership.pk)
        .exists()
    )
