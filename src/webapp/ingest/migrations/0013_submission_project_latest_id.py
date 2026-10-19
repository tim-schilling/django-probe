from django.contrib.postgres.operations import (
    AddIndexConcurrently,
    RemoveIndexConcurrently,
)
from django.db import migrations, models


class Migration(migrations.Migration):
    # Building the index concurrently keeps submissions writable, and the new one
    # exists before the old one is dropped.
    atomic = False

    dependencies = [
        ("ingest", "0012_submission_stats_indexes"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="submission",
            index=models.Index(
                fields=["project", "-created_at"],
                include=["id"],
                name="submission_project_latest_id",
            ),
        ),
        RemoveIndexConcurrently(
            model_name="submission",
            name="submission_project_latest",
        ),
    ]
