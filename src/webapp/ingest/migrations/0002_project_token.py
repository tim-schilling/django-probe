import secrets

from django.db import migrations, models


def backfill_tokens(apps, schema_editor):
    Project = apps.get_model("ingest", "Project")
    for project in Project.objects.filter(token__isnull=True):
        project.token = secrets.token_hex(32)
        project.save(update_fields=["token"])


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="submission",
            name="project_key",
        ),
        migrations.RemoveField(
            model_name="submission",
            name="user",
        ),
        migrations.AddField(
            model_name="project",
            name="token",
            field=models.CharField(max_length=64, null=True, editable=False),
        ),
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="project",
            name="key",
        ),
        migrations.AlterField(
            model_name="project",
            name="token",
            field=models.CharField(max_length=64, unique=True, editable=False),
        ),
        migrations.DeleteModel(
            name="ApiToken",
        ),
    ]
