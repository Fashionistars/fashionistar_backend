from django.db import models
import uuid

from userauths.models import User
from vendor.models import Vendor


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('credit', 'Credit'),
        ('debit', 'Debit')
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=100, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=100, default="pending")
    paystack_payment_reference = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        if self.user:
            return f"{self.transaction_type} of {self.amount} by {self.user.email}"
        elif self.vendor:
            return f"{self.transaction_type} of {self.amount} by {self.vendor.name}"
        else:
          return f"{self.transaction_type} of {self.amount} by Unknown"





