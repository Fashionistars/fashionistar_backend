"""
Mailgun transactional email provider metadata.

The actual delivery backend is Anymail's Mailgun integration:
`anymail.backends.mailgun.EmailBackend`.
"""

MAILGUN_PROVIDER = {
    "slug": "mailgun",
    "backend_path": "anymail.backends.mailgun.EmailBackend",
    "display_name": "Mailgun",
    "health_label": "mailgun",
    "settings_prefix": "MAILGUN",
}
