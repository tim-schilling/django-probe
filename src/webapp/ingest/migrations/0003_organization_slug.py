from django.db import migrations, models
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    Organization = apps.get_model("ingest", "Organization")
    for organization in Organization.objects.filter(slug__isnull=True):
        base = slugify(organization.name) or "org"
        slug = base
        suffix = 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base}-{suffix}"
            suffix += 1
        organization.slug = slug
        organization.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0002_project_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="slug",
            field=models.SlugField(
                max_length=220, null=True, editable=False, db_index=False
            ),
        ),
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organization",
            name="slug",
            field=models.SlugField(
                max_length=220, unique=True, editable=False, db_index=False
            ),
        ),
    ]
