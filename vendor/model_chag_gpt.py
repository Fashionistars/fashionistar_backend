from django.db import models
from django.utils.text import slugify
from django.contrib.auth.hashers import make_password
from django.db.models import Avg, Count, F
from django.db.models.functions import ExtractHour
import shortuuid

class Vendor(models.Model):
    vid = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    transaction_password = models.CharField(max_length=128, blank=True, null=True)

    def save(self, *args, **kwargs):
        base_slug = slugify(self.name)
        self.slug = f"{base_slug}-{shortuuid.uuid()[:4]}"
        while Vendor.objects.filter(slug=self.slug).exists():
            self.slug = f"{base_slug}-{shortuuid.uuid()[:4]}"
        super().save(*args, **kwargs)

    def get_average_rating(self):
        return self.review_product.filter(rating__isnull=False).aggregate(Avg('rating'))['rating__avg'] or 0.0

    def get_new_customers_this_month(self):
        from django.utils.timezone import now
        return self.cartorder_vendor.filter(
            date__month=now().month, date__year=now().year
        ).values('buyer').annotate(order_count=Count('id')).filter(order_count=1).count()

    def get_customer_behavior(self):
        return self.cartorder_vendor.filter(payment_status='paid') \
            .annotate(hour=ExtractHour('date')).values('hour').annotate(order_count=Count('id'))

    def set_transaction_password(self, password):
        if not password.isdigit() or len(password) != 4:
            raise ValueError("Transaction password must be a 4-digit number.")
        self.transaction_password = make_password(password)
        self.save()

class WalletTransaction(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='wallet_transactions', db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['vendor']),
        ]



















































import uuid
import shortuuid
from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now
from django.db.models import Avg, Count, Sum, F
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.db.models.functions import ExtractHour

class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    vid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    wallet_balance = models.DecimalField(default=0.00, max_digits=10, decimal_places=2)
    transaction_password = models.CharField(max_length=128, blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug or Vendor.objects.filter(pk=self.pk, name=self.name).exists() is False:
            base_slug = slugify(self.name)
            unique_slug = base_slug
            counter = 1
            while Vendor.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{shortuuid.uuid()[:4]}"
                counter += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def get_average_rating(self):
        return self.review_product.aggregate(avg_rating=Avg('rating'))['avg_rating'] or 0

    def get_new_customers_this_month(self):
        return self.cartorder_vendor.filter(
            date__month=now().month, date__year=now().year
        ).values('buyer').annotate(order_count=Count('id')).filter(order_count=1).count()

    def get_customer_behavior(self):
        return self.cartorder_vendor.filter(payment_status='paid') \
            .annotate(hour=ExtractHour('date')).values('hour').annotate(order_count=Count('id'))

    def set_transaction_password(self, password):
        if not password.isdigit() or len(password) != 4:
            raise ValueError("Transaction password must be a 4-digit number.")
        self.transaction_password = make_password(password)
        self.save()

    def __str__(self):
        return self.name
