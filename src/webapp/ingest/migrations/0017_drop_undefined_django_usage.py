from django.db import migrations

# The API catalog is too large to copy here, so this uses the app's filter.
from ingest.django_api import drop_undefined_django_names

BATCH_SIZE = 1000


def drop_undefined_usage(apps, schema_editor):
    Submission = apps.get_model("ingest", "Submission")
    changed = []
    for submission in Submission.objects.only("id", "usage").iterator(
        chunk_size=BATCH_SIZE
    ):
        usage = drop_undefined_django_names(submission.usage)
        if usage != submission.usage:
            submission.usage = usage
            changed.append(submission)
        if len(changed) >= BATCH_SIZE:
            Submission.objects.bulk_update(changed, ["usage"])
            changed = []
    Submission.objects.bulk_update(changed, ["usage"])


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0016_alter_organizationmembership_role"),
    ]

    operations = [
        migrations.RunPython(
            drop_undefined_usage, migrations.RunPython.noop, elidable=True
        ),
    ]
