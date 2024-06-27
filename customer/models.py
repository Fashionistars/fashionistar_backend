from django.db import models

class Wallet(models.Model):
    """
    Wallet model to handle user's wallet balance.
    """
    pass

class ShippingAddress(models.Model):
    """
    ShippingAddress model to store user's shipping address details.
    """
    country = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    local_gov = models.CharField(max_length=500, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=1000, null=True, blank=True)
    suite = models.CharField(max_length=1000, null=True, blank=True)

class DeliveryContact(models.Model):
    """
    DeliveryContact model to store user's delivery contact details.
    """
    email = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.CharField(max_length=100, null=True, blank=True)
    fullname = models.CharField(max_length=500, null=True, blank=True)