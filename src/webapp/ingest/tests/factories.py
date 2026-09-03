from __future__ import annotations

import factory

from ingest.models import (
    CliCredential,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
    User,
)

PASSWORD = "Account-test-password"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda number: f"user-{number}")
    password = PASSWORD

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.objects.create_user(*args, **kwargs)


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda number: f"Organization {number}")

    @classmethod
    def _create(cls, model_class, *args, owner=None, **kwargs):
        if owner is not None:
            return model_class.objects.create_with_owner(owner=owner, **kwargs)
        return super()._create(model_class, *args, **kwargs)


class OrganizationMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrganizationMembership

    organization = factory.SubFactory(OrganizationFactory)
    user = factory.SubFactory(UserFactory)
    role = OrganizationMembership.Role.MEMBER


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda number: f"Project {number}")


class CliCredentialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CliCredential

    label = "test-device"


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    project = None
    schema_version = 2
    client_version = "0.2.0"
    python_version = "3.12.3"
    django_version = "5.1.2"
    files_scanned = 12
    probe_sources = {"django-probe": "0.2.0"}
    patterns = {"probe:queryset_filter": 3}
    dependencies = {"django": "5.1.2"}
