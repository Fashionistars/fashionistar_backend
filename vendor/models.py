from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from userauths.models import User, user_directory_path, Profile
from store import models as store_model
from django.db.models import Max
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.db.models import Avg
import shortuuid


class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor_profile")
    image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg",null=True, blank=True)
    name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    collections = models.ManyToManyField('Homepage.Category', related_name="products",)    # In this collections column,  a vendor is meant to contain one or more differnt collections
    mobile = models.CharField(max_length = 150, null=True, blank=True)
    verified = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)  # Added balance field
    vid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Vendors"

    def vendor_image(self):
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.shop_image.url))

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + str(uniqueid.lower())
        
    def get_average_rating(self):
        return self.vendor_role.aggregate(average_rating=Avg('rating')).get('average_rating', 0)
