from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingest", "0008_remove_submission_organization")]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="usage",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="submission",
            name="usage_packages",
            field=models.JSONField(default=list),
        ),
    ]
