from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.product.models import DeliveryCourier

class Command(BaseCommand):
    help = "Seeds standard DHL and FedEx global courier parameters."

    def handle(self, *args, **options):
        couriers = [
            {
                "name": "DHL Express",
                "base_fee": Decimal("15000.00"),
                "estimated_days_min": 2,
                "estimated_days_max": 5
            },
            {
                "name": "FedEx Priority",
                "base_fee": Decimal("12000.00"),
                "estimated_days_min": 3,
                "estimated_days_max": 7
            }
        ]
        for data in couriers:
            courier, created = DeliveryCourier.objects.get_or_create(
                name=data["name"],
                defaults={
                    "active": True,
                    "base_fee": data["base_fee"],
                    "estimated_days_min": data["estimated_days_min"],
                    "estimated_days_max": data["estimated_days_max"]
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Courier {courier.name} successfully seeded."))
            else:
                self.stdout.write(self.style.WARNING(f"Courier {courier.name} already exists."))
