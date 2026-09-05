import uuid

from django.db import migrations, models
import django.db.models.deletion


def populate_submission_uuids(apps, schema_editor):
    submission_model = apps.get_model("ingest", "Submission")
    for submission in submission_model.objects.iterator():
        submission.uuid = uuid.uuid7()
        submission.save(update_fields=["uuid"])


def populate_submission_organizations(apps, schema_editor):
    submission_model = apps.get_model("ingest", "Submission")
    for submission in submission_model.objects.select_related("project").iterator():
        if submission.project_id:
            submission.organization_id = submission.project.organization_id
            submission.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [("ingest", "0005_cli_credential_digest")]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="uuid",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(populate_submission_uuids, migrations.RunPython.noop),
        migrations.RemoveField(model_name="submission", name="id"),
        migrations.RenameField(model_name="submission", old_name="uuid", new_name="id"),
        migrations.AlterField(
            model_name="submission",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid7,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="submissions",
                to="ingest.organization",
            ),
        ),
        migrations.RunPython(
            populate_submission_organizations, migrations.RunPython.noop
        ),
    ]
