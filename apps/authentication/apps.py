from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = _("Identity Access Management")

    def ready(self):
        try:
            import apps.authentication.signals # noqa
        except ImportError:
            pass