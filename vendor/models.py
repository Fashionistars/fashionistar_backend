from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from userauths.models import User, user_directory_path
from django.utils.text import slugify
import shortuuid
from django.db.models import Avg
import uuid

class Vendor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor_profile")
    image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg",null=True, blank=True)
    name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    mobile = models.CharField(max_length=150, null=True, blank=True)
    verified = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    vid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(blank=True, null=True)
    transaction_password = models.CharField(max_length=4, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Vendors"

    def vendor_image(self):
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.name.lower()) + "-" + str(uniqueid.lower())

        # Ensure the instance is saved to the database after modifying fields like 'slug'
        super().save(*args, **kwargs)

    def get_average_rating(self):
        return self.vendor_role.aggregate(average_rating=Avg('rating')).get('average_rating', 0)

    def set_transaction_password(self, password):
        self.transaction_password = password
        self.save()

    def check_transaction_password(self, password):
        return self.transaction_password == password
