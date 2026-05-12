# apps/providers/SMTP/zoho.py
"""
Zoho ZeptoMail transactional email provider metadata.

The actual delivery backend is the zoho-zeptomail library:
`zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend`

Required Django settings:
    ZOHO_ZEPTOMAIL_TOKEN = env("ZOHO_ZEPTOMAIL_TOKEN")
    EMAIL_FROM = "noreply@fashionistar.com"

Library docs: https://pypi.org/project/django-zoho-zeptomail/
"""

ZOHO_PROVIDER = {
    "slug": "zoho",
    "backend_path": "zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend",
    "display_name": "Zoho ZeptoMail",
    "health_label": "zoho",
    "settings_prefix": "ZOHO_ZEPTOMAIL",
    "help_text": "Zoho ZeptoMail — transactional email. Requires ZOHO_ZEPTOMAIL_TOKEN.",
}
