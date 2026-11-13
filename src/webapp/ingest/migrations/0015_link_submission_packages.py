import re

from django.db import migrations

# Copies of the app's normalization, so this migration doesn't change with it.
NORMALIZED_PACKAGE_NAME_PATTERN = r"^[a-z\d]([a-z\d-]*[a-z\d])?$"
BATCH_SIZE = 10_000


def normalize_package_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def link_packages(apps, schema_editor):
    Submission = apps.get_model("ingest", "Submission")
    PyPIPackage = apps.get_model("ingest", "PyPIPackage")
    Link = Submission.packages.through
    ids = {}
    links = []
    rows = Submission.objects.values_list("id", "dependencies").iterator(
        chunk_size=1000
    )
    for submission_id, dependencies in rows:
        names = {
            name
            for name in map(normalize_package_name, dependencies)
            if re.fullmatch(NORMALIZED_PACKAGE_NAME_PATTERN, name)
        }
        if new := names - ids.keys():
            PyPIPackage.objects.bulk_create(
                [PyPIPackage(name=name) for name in new], ignore_conflicts=True
            )
            ids.update(
                PyPIPackage.objects.filter(name__in=new).values_list("name", "id")
            )
        links.extend(
            Link(submission_id=submission_id, pypipackage_id=ids[name])
            for name in names
        )
        if len(links) >= BATCH_SIZE:
            Link.objects.bulk_create(links, ignore_conflicts=True)
            links = []
    Link.objects.bulk_create(links, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0014_pypipackage"),
    ]

    operations = [
        migrations.RunPython(link_packages, migrations.RunPython.noop),
    ]
