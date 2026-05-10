from django.apps import AppConfig


class PaymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payment"
    verbose_name = "Fashionistar Payment"

    def ready(self) -> None:
        # Wire payment signals (gateway cache bust on PaymentProvider save)
        import apps.payment.signals  # noqa: F401
