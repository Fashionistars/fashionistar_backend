"""
Brevo transactional email provider metadata.

The actual delivery backend is Anymail's Brevo integration:
`anymail.backends.brevo.EmailBackend`.
"""

BREVO_PROVIDER = {
    "slug": "brevo",
    "backend_path": "anymail.backends.brevo.EmailBackend",
    "display_name": "Brevo",
    "health_label": "brevo",
    "settings_prefix": "BREVO",
}
