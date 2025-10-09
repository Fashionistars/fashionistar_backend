from django.db import models
import uuid
from userauths.models import User
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

class TransactionStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    SUCCESS = 'success', _('Success')
    FAILED = 'failed', _('Failed')

class TransactionType(models.TextChoices):
    CREDIT = 'credit', _('Credit')
    DEBIT = 'debit', _('Debit')





class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('credit', 'Credit'),
        ('debit', 'Debit')
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_transactions')
    vendor = models.ForeignKey("vendor.Vendor", on_delete=models.CASCADE, null=True, blank=True, related_name='vendor_transactions')


    amount = models.DecimalField(max_digits=100, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=100, choices=TransactionStatus.choices, default=TransactionStatus.PENDING)

    paystack_payment_reference = models.CharField(max_length=100, blank=True, null=True)
    paystack_transfer_code = models.CharField(max_length=100, blank=True, null=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    
    # def __str__(self):
    #     entity = self.user.email if self.user else self.vendor.name if self.vendor else "Unknown"
    #     return f"{self.transaction_type} of {self.amount} by {entity}"



    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['vendor']),
            models.Index(fields=['status']),
        ]

    def clean(self):
        if not self.user and not self.vendor:
            raise ValidationError("A transaction must be associated with either a user or a vendor.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} - {self.get_status_display()}"







class BankAccountDetails(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_bank_details')
    vendor = models.ForeignKey("vendor.Vendor", on_delete=models.CASCADE, null=True, blank=True, related_name='vendor_bank_details')

    account_number = models.CharField(max_length=20, blank=True, null=True)  # Added field
    account_full_name = models.CharField(max_length=255, blank=True, null=True) #Added field


    # =====================  CODE TO BE USED LATER FOR PROPER ENCRYIPTION FOR RELEVANT DOCUMENTS AND DETAILS  ==============================

    
    # from fernet_fields import EncryptedTextField

    # account_number = EncryptedTextField()
    # account_full_name = EncryptedTextField()
    
    # =====================  CODE TO BE USED LATER FOR PROPER ENCRYIPTION FOR RELEVANT DOCUMENTS AND DETAILS  ==============================


    bank_name = models.CharField(max_length=255, null=True, blank=True) # Removed choices
    bank_code = models.CharField(max_length=10, blank=True, null=True)  #Added this field

    
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    paystack_Recipient_Code = models.CharField(max_length=100, blank=True, null=True)

    
    class Meta:
        verbose_name_plural = "BankAccountDetails"
        ordering = ["-timestamp"]


    def __str__(self):
        return f"{self.account_name} - {self.bank_name} ({self.account_number})"


    # def __str__(self):
    #     if self.user:
    #         return f"{self.account_number} - {self.bank_name} by {self.account_full_name}"
    #     elif self.vendor:
    #         return f"{self.account_number} - {self.bank_name} by {self.account_full_name}"
    #     else:
    #       return f"{self.account_number} - {self.bank_name} by Unknown"









class WalletTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey("vendor.Vendor", on_delete=models.CASCADE, related_name='wallet_transactions')
    amount = models.DecimalField(max_digits=100, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    status = models.CharField(max_length=100, choices=TransactionStatus.choices, default=TransactionStatus.PENDING)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        if self.transaction_type == TransactionType.DEBIT and self.vendor.wallet_balance < self.amount:
            raise ValidationError("Insufficient wallet balance.")
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.transaction_type} of {self.amount} for {self.vendor.name}"