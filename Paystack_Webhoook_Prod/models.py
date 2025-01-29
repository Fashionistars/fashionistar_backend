from django.db import models
import uuid
from userauths.models import User
from vendor.models import Vendor
import json
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from Paystack_Webhoook_Prod.BANKS_LIST import  BANK_CHOICES


class TransactionStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    SUCCESS = 'success', _('Success')
    FAILED = 'failed', _('Failed')

class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('credit', 'Credit'),
        ('debit', 'Debit')
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_transactions')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True, related_name='vendor_transactions')


    amount = models.DecimalField(max_digits=100, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=100, choices=TransactionStatus.choices, default=TransactionStatus.PENDING)

    paystack_payment_reference = models.CharField(max_length=100, blank=True, null=True)
    paystack_transfer_code = models.CharField(max_length=100, blank=True, null=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    
    def __str__(self):
        if self.user:
            return f"{self.transaction_type} of {self.amount} by {self.user.email}"
        elif self.vendor:
            return f"{self.transaction_type} of {self.amount} by {self.vendor.name}"
        else:
          return f"{self.transaction_type} of {self.amount} by Unknown"


class BankAccountDetails(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_bank_details')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True, related_name='vendor_bank_details')

    account_number = models.CharField(max_length=20, blank=True, null=True)  # Added field
    account_full_name = models.CharField(max_length=255, blank=True, null=True) #Added field

    bank_name = models.CharField(max_length=255, null=True, blank=True) # Removed choices
    bank_code = models.CharField(max_length=10, blank=True, null=True)  #Added this field

    
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    paystack_Recipient_Code = models.CharField(max_length=100, blank=True, null=True)

    
    class Meta:
        verbose_name_plural = "BankAccountDetails"
        ordering = ["-timestamp"]

    
    def __str__(self):
        if self.user:
            return f"{self.account_number} - {self.bank_name} by {self.user.email}"
        elif self.vendor:
            return f"{self.account_number} - {self.bank_name} by {self.vendor.name}"
        else:
          return f"{self.account_number} - {self.bank_name} by Unknown"