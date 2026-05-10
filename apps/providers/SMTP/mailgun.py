# apps/providers/SMTP/mailgun.py
"""
Mailgun transactional email provider metadata.

The actual delivery backend is Anymail's Mailgun integration:
`anymail.backends.mailgun.EmailBackend`.

Required Django settings:
    ANYMAIL = {
        "MAILGUN_API_KEY": env("MAILGUN_API_KEY"),
        "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN"),
    }

Anymail docs: https://anymail.dev/en/stable/esps/mailgun/
"""

MAILGUN_PROVIDER = {
    "slug": "mailgun",
    "backend_path": "anymail.backends.mailgun.EmailBackend",
    "display_name": "Mailgun",
    "health_label": "mailgun",
    "settings_prefix": "MAILGUN",
    "help_text": "Mailgun — transactional email via Anymail. Requires ANYMAIL[MAILGUN_API_KEY] and MAILGUN_SENDER_DOMAIN.",
}
