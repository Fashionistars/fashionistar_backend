"""
Zoho ZeptoMail transactional email provider metadata.

The actual delivery backend is `zoho_zeptomail.backend.zeptomail_backend.
ZohoZeptoMailEmailBackend`.
"""

ZOHO_PROVIDER = {
    "slug": "zoho",
    "backend_path": "zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend",
    "display_name": "Zoho ZeptoMail",
    "health_label": "zoho",
    "settings_prefix": "ZOHO_ZEPTOMAIL",
}
