from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingest", "0005_cli_credential_digest")]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="django_settings",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="submission",
            name="django_settings_scanned",
            field=models.BooleanField(default=False),
        ),
    ]
