from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("ingest", "0005_cli_credential_digest")]

    operations = [
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                Lower("name"),
                "organization",
                name="unique_project_name_per_organization",
            ),
        ),
    ]
