import hashlib
from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone

# Inlined rather than imported from ingest.models: a migration has to keep doing the
# same thing years from now, whatever the current CLI_CREDENTIAL_TTL happens to be.
CREDENTIAL_TTL = timedelta(days=90)


def hash_existing_tokens(apps, schema_editor):
    """Replace stored credentials with their digests.

    Existing credentials keep working: the digest is derived from the token their
    owner already holds. They are dated from the migration rather than from when
    they were issued, so deploying this doesn't log everyone out at once.
    """
    CliCredential = apps.get_model("ingest", "CliCredential")
    now = timezone.now()
    # Materialized, not a queryset or an iterator: bulk_update re-evaluates a
    # queryset against the database, so it would write back the unmutated rows and
    # silently leave every credential without a digest.
    issued = list(CliCredential.objects.filter(token__isnull=False))
    for credential in issued:
        credential.token_digest = hashlib.sha256(credential.token.encode()).hexdigest()
        credential.approved_at = credential.created_at
        credential.token_expires_at = now + CREDENTIAL_TTL
    CliCredential.objects.bulk_update(
        issued, ["token_digest", "approved_at", "token_expires_at"], batch_size=500
    )


def unhash(apps, schema_editor):
    """Irreversible in substance: a digest cannot become a token again.

    Left as a no-op so the migration can be unapplied for schema reasons. Every CLI
    credential stops working if you do, and each owner must run `django-probe login`
    again.
    """


class Migration(migrations.Migration):
    dependencies = [("ingest", "0004_clicredential")]

    operations = [
        migrations.AddField(
            model_name="clicredential",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clicredential",
            name="token_digest",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text=(
                    "SHA-256 of the issued credential. The credential is shown "
                    "once, when the CLI collects it, and is never stored."
                ),
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="clicredential",
            name="token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(hash_existing_tokens, unhash),
        migrations.RemoveField(model_name="clicredential", name="token"),
    ]
