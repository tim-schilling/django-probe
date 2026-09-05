from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from ingest.models import Organization, OrganizationMembership, Project


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name"]


class ProjectForm(forms.ModelForm):
    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean_name(self) -> str:
        name = self.cleaned_data["name"]
        if Project.objects.filter(
            organization=self.organization, name__iexact=name
        ).exists():
            raise forms.ValidationError(
                "A project with this name already exists in this organization."
            )
        return name

    class Meta:
        model = Project
        fields = ["name"]


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
