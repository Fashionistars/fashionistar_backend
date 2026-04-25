from decimal import Decimal

from django.test import TestCase

from apps.transactions.services import CommissionService


class CommissionServiceTests(TestCase):
    def test_default_commission_is_ten_percent(self):
        self.assertEqual(CommissionService.calculate(Decimal("100000.00"), Decimal("0.10")), Decimal("10000.00"))

    def test_measurement_fee_default_is_one_thousand_naira(self):
        self.assertEqual(CommissionService.MEASUREMENT_FEE_NGN, Decimal("1000.00"))
