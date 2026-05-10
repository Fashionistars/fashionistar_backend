# apps/providers/SMTP/brevo.py
"""
Brevo transactional email provider metadata.

The actual delivery backend is Anymail's Brevo integration:
`anymail.backends.brevo.EmailBackend`.

Required Django settings:
    ANYMAIL = {
        "BREVO_API_KEY": env("BREVO_API_KEY"),
    }
    EMAIL_FROM = "noreply@fashionistar.com"

Anymail docs: https://anymail.dev/en/stable/esps/brevo/
"""

BREVO_PROVIDER = {
    "slug": "brevo",
    "backend_path": "anymail.backends.brevo.EmailBackend",
    "display_name": "Brevo (Sendinblue)",
    "health_label": "brevo",
    "settings_prefix": "BREVO",
    "help_text": "Brevo (formerly Sendinblue) — transactional email via Anymail. Requires ANYMAIL[BREVO_API_KEY].",
}
