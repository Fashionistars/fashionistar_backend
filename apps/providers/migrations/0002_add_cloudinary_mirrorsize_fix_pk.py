# apps/providers/migrations/0002_add_cloudinary_mirrorsize_fix_pk.py
"""
Hand-edited migration — providers 0002

Background
----------
The auto-generated migration contained AlterField operations that attempted to
cast the existing ``id`` column from ``bigint`` to ``uuid`` using
  ALTER COLUMN "id" TYPE uuid USING "id"::uuid
PostgreSQL rejects this because there is no implicit cast from bigint to uuid.

Safe resolution
---------------
These three tables (EmailProviderConfig, SMSProviderConfig, KYCProviderConfig)
are admin-only singleton config rows with zero user data and no FK references
from other tables.  The correct approach is:

  1. Truncate any existing config rows (the post_migrate seeder recreates them).
  2. Drop the old column default and primary-key constraint.
  3. Drop the old bigint id column.
  4. Add a new uuid id column with a gen_random_uuid() default and promote it to
     the primary key.

All four steps run inside a single DDL transaction per table so they are atomic.
If migration is rolled back, the truncate keeps the table empty (acceptable for
singleton config tables that are always re-seeded on startup).
"""

import uuid6
from django.db import migrations, models


# ── Raw SQL helpers ────────────────────────────────────────────────────────────

def _rebuild_pk_as_uuid(table: str) -> list:
    """
    Return a list of (forward_sql, reverse_noop) tuples that rebuild a
    BigAutoField PK as a UUIDField PK for the given table name.

    Reverse is intentionally a no-op because there is no safe way to reverse
    a uuid→bigint conversion; callers should rely on database backups to roll
    back if needed.
    """
    return [
        (
            f"""
            -- Step 1: Clear singleton rows (seeder recreates on next startup)
            TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;
            -- Step 2: Drop the old bigint PK constraint & column
            ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_pkey";
            ALTER TABLE "{table}" DROP COLUMN IF EXISTS "id";
            -- Step 3: Add new uuid PK column
            ALTER TABLE "{table}" ADD COLUMN "id" uuid NOT NULL DEFAULT gen_random_uuid();
            ALTER TABLE "{table}" ADD PRIMARY KEY ("id");
            """,
            migrations.RunSQL.noop,
        )
    ]


# Forward / reverse SQL lists per table
_EMAIL_SQL = _rebuild_pk_as_uuid("providers_emailproviderconfig")
_KYC_SQL   = _rebuild_pk_as_uuid("providers_kycproviderconfig")
_SMS_SQL   = _rebuild_pk_as_uuid("providers_smsproviderconfig")


class Migration(migrations.Migration):
    """
    Providers 0002 — add CloudinaryProviderConfig & MirrorSizeProviderConfig
    tables, and fix Email / SMS / KYC provider config PK type from bigint → uuid.
    """

    dependencies = [
        ("providers", "0001_initial"),
    ]

    operations = [
        # ── 1. Create the two missing provider config tables ─────────────────
        migrations.CreateModel(
            name="CloudinaryProviderConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid6.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="Timestamp when the record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when the record was last updated.",
                    ),
                ),
                (
                    "health_status",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("healthy", "Healthy \u2705"),
                            ("degraded", "Degraded \u26a0\ufe0f"),
                            ("unhealthy", "Unhealthy \u274c"),
                        ],
                        default="unknown",
                        help_text="Last recorded health check result for this provider.",
                        max_length=20,
                        verbose_name="Health Status",
                    ),
                ),
                (
                    "last_health_check",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Last Health Check"
                    ),
                ),
                (
                    "circuit_state",
                    models.CharField(
                        choices=[
                            ("closed", "Closed (Normal)"),
                            ("open", "Open (Provider Failing \u2014 Switch Required)"),
                            ("half_open", "Half-Open (Probing)"),
                        ],
                        default="closed",
                        help_text=(
                            "OPEN means the provider is currently failing. "
                            "Switch to another provider and save to reset the circuit."
                        ),
                        max_length=20,
                        verbose_name="Circuit State",
                    ),
                ),
                (
                    "failure_count",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Resets to 0 when the provider call succeeds.",
                        verbose_name="Consecutive Failure Count",
                    ),
                ),
                (
                    "last_failure_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Last Failure Timestamp"
                    ),
                ),
                (
                    "upload_preset_images",
                    models.CharField(
                        default="fashionistar_images",
                        help_text="Cloudinary upload preset used for all image uploads.",
                        max_length=120,
                        verbose_name="Image Upload Preset",
                    ),
                ),
                (
                    "upload_preset_videos",
                    models.CharField(
                        default="fashionistar_videos",
                        help_text="Cloudinary upload preset used for all video uploads.",
                        max_length=120,
                        verbose_name="Video Upload Preset",
                    ),
                ),
                (
                    "signature_ttl_seconds",
                    models.PositiveIntegerField(
                        default=3300,
                        help_text=(
                            "How long a presigned upload token is valid "
                            "(max 3600 per Cloudinary). "
                            "3300 (55 min) gives safety margin before the 1-hour limit."
                        ),
                        verbose_name="Presign TTL (seconds)",
                    ),
                ),
                (
                    "max_image_bytes",
                    models.PositiveIntegerField(
                        default=10_485_760,
                        help_text="Maximum allowed image upload size in bytes.",
                        verbose_name="Max Image Size (bytes)",
                    ),
                ),
                (
                    "max_video_bytes",
                    models.PositiveIntegerField(
                        default=104_857_600,
                        help_text="Maximum allowed video upload size in bytes.",
                        verbose_name="Max Video Size (bytes)",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Disable to stop accepting media uploads (maintenance mode).",
                        verbose_name="Enabled",
                    ),
                ),
            ],
            options={
                "verbose_name": "Cloudinary Provider Configuration",
                "verbose_name_plural": "Cloudinary Provider Configuration",
            },
        ),
        migrations.CreateModel(
            name="MirrorSizeProviderConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid6.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="Timestamp when the record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when the record was last updated.",
                    ),
                ),
                (
                    "health_status",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("healthy", "Healthy \u2705"),
                            ("degraded", "Degraded \u26a0\ufe0f"),
                            ("unhealthy", "Unhealthy \u274c"),
                        ],
                        default="unknown",
                        help_text="Last recorded health check result for this provider.",
                        max_length=20,
                        verbose_name="Health Status",
                    ),
                ),
                (
                    "last_health_check",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Last Health Check"
                    ),
                ),
                (
                    "circuit_state",
                    models.CharField(
                        choices=[
                            ("closed", "Closed (Normal)"),
                            ("open", "Open (Provider Failing \u2014 Switch Required)"),
                            ("half_open", "Half-Open (Probing)"),
                        ],
                        default="closed",
                        help_text=(
                            "OPEN means the provider is currently failing. "
                            "Switch to another provider and save to reset the circuit."
                        ),
                        max_length=20,
                        verbose_name="Circuit State",
                    ),
                ),
                (
                    "failure_count",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Resets to 0 when the provider call succeeds.",
                        verbose_name="Consecutive Failure Count",
                    ),
                ),
                (
                    "last_failure_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Last Failure Timestamp"
                    ),
                ),
                (
                    "product_name",
                    models.CharField(
                        default="GET_MEASURED",
                        help_text=(
                            "MirrorSize product name used when generating access codes. "
                            "Defaults to 'GET_MEASURED' (the measurement widget)."
                        ),
                        max_length=120,
                        verbose_name="Product Name",
                    ),
                ),
                (
                    "browser_api_base_url",
                    models.URLField(
                        default="https://api.user.mirrorsize.com",
                        help_text="Base URL for MirrorSize browser/widget API.",
                        max_length=255,
                        verbose_name="Browser API Base URL",
                    ),
                ),
                (
                    "user_home_base_url",
                    models.URLField(
                        default="https://user.mirrorsize.com/home",
                        help_text="Base URL for the MirrorSize user home (redirect target).",
                        max_length=255,
                        verbose_name="User Home Base URL",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Disable to deactivate MirrorSize widget integration "
                            "across the platform."
                        ),
                        verbose_name="Enabled",
                    ),
                ),
                (
                    "access_code_ttl_seconds",
                    models.PositiveIntegerField(
                        default=3600,
                        help_text="How long a generated MirrorSize access code remains valid.",
                        verbose_name="Access Code TTL (seconds)",
                    ),
                ),
            ],
            options={
                "verbose_name": "MirrorSize Provider Configuration",
                "verbose_name_plural": "MirrorSize Provider Configuration",
            },
        ),
        # ── 2. Fix PK type: bigint → uuid for the three existing config tables ─
        # PostgreSQL cannot cast bigint to uuid with ALTER COLUMN ... TYPE uuid.
        # Safe path: truncate the singleton-config rows (re-seeded on startup),
        # drop the old id column, add a new uuid id column as the primary key.
        migrations.RunSQL(
            sql=_EMAIL_SQL[0][0],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=_KYC_SQL[0][0],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=_SMS_SQL[0][0],
            reverse_sql=migrations.RunSQL.noop,
        ),
        # ── 3. Sync Django state: tell the ORM the id field is now UUIDField ───
        migrations.AlterField(
            model_name="emailproviderconfig",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                help_text="Timestamp when the record was created.",
            ),
        ),
        migrations.AlterField(
            model_name="emailproviderconfig",
            name="email_backend",
            field=models.CharField(
                choices=[
                    (
                        "anymail.backends.brevo.EmailBackend",
                        "Brevo (Sendinblue)",
                    ),
                    ("anymail.backends.mailgun.EmailBackend", "Mailgun"),
                    (
                        "zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend",
                        "Zoho ZeptoMail",
                    ),
                    (
                        "django.core.mail.backends.smtp.EmailBackend",
                        "SMTP (Gmail / Custom)",
                    ),
                    (
                        "django.core.mail.backends.console.EmailBackend",
                        "Console (dev only)",
                    ),
                ],
                db_index=True,
                default="django.core.mail.backends.smtp.EmailBackend",
                help_text=(
                    "Choose the transactional email backend used by the platform. "
                    "SMTP (Gmail) is acceptable for development or low-volume flows. "
                    "Production environments should use Mailgun, SendGrid, "
                    "Zoho ZeptoMail, or Brevo."
                ),
                max_length=250,
                verbose_name="Active Email Backend",
            ),
        ),
        migrations.AlterField(
            model_name="emailproviderconfig",
            name="id",
            field=models.UUIDField(
                default=uuid6.uuid7, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.AlterField(
            model_name="emailproviderconfig",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, help_text="Timestamp when the record was last updated."
            ),
        ),
        migrations.AlterField(
            model_name="kycproviderconfig",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                help_text="Timestamp when the record was created.",
            ),
        ),
        migrations.AlterField(
            model_name="kycproviderconfig",
            name="id",
            field=models.UUIDField(
                default=uuid6.uuid7, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.AlterField(
            model_name="kycproviderconfig",
            name="provider_slug",
            field=models.CharField(
                choices=[
                    (
                        "smileid",
                        "Smile Identity (West/East Africa \u2014 BVN + NIN + Liveness)",
                    ),
                    ("dojah", "Dojah Nigeria (BVN + NIN + Face Match)"),
                    (
                        "youverify",
                        "Youverify (Identity + Document + CAC Verification)",
                    ),
                ],
                db_index=True,
                default="dojah",
                help_text=(
                    "Select the active KYC identity verification provider. "
                    "Switch here when rotating providers without redeploying."
                ),
                max_length=30,
                verbose_name="KYC Provider",
            ),
        ),
        migrations.AlterField(
            model_name="kycproviderconfig",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, help_text="Timestamp when the record was last updated."
            ),
        ),
        migrations.AlterField(
            model_name="smsproviderconfig",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                help_text="Timestamp when the record was created.",
            ),
        ),
        migrations.AlterField(
            model_name="smsproviderconfig",
            name="id",
            field=models.UUIDField(
                default=uuid6.uuid7, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.AlterField(
            model_name="smsproviderconfig",
            name="sms_backend",
            field=models.CharField(
                choices=[
                    (
                        "apps.providers.SMS.termii.TermiiSMSProvider",
                        "Termii (Nigerian-first)",
                    ),
                    (
                        "apps.providers.SMS.twilio.TwilioSMSProvider",
                        "Twilio (Global / WhatsApp)",
                    ),
                    (
                        "apps.providers.SMS.bulksmsNG.BulksmsNGSMSProvider",
                        "BulkSMS Nigeria",
                    ),
                ],
                db_index=True,
                default="apps.providers.SMS.twilio.TwilioSMSProvider",
                help_text=(
                    "Choose the active SMS provider class for the system. "
                    "NOTE: Ensure the corresponding API credentials (Keys/Secrets) "
                    "are correctly set in your Server Environment Variables before switching."
                ),
                max_length=250,
                verbose_name="Active SMS Provider",
            ),
        ),
        migrations.AlterField(
            model_name="smsproviderconfig",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, help_text="Timestamp when the record was last updated."
            ),
        ),
    ]
