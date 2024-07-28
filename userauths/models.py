from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _
from shortuuid.django_fields import ShortUUIDField
from .managers import CustomUserManager
from django.core.exceptions import ValidationError
from phonenumber_field.modelfields import PhoneNumberField

def user_directory_path(instance, filename):
    """
    Generate a file path for a given user directory.
    """
    try:
        user = None
        
        if hasattr(instance, 'user') and instance.user:
            user = instance.user
        elif hasattr(instance, 'vendor') and hasattr(instance.vendor, 'user') and instance.vendor.user:
            user = instance.vendor.user
        elif hasattr(instance, 'product') and hasattr(instance.product.vendor, 'user') and instance.product.vendor.user:
            user = instance.product.vendor.user

        if user:
            ext = filename.split('.')[-1]
            filename = "%s.%s" % (user.id, ext)
            return 'user_{0}/{1}'.format(user.id, filename)
        else:
            # Handle the case when user is None
            # You can return a default path or raise an exception, depending on your requirements.
            # For example, return a path with 'unknown_user' as the user ID:
            ext = filename.split('.')[-1]
            filename = "%s.%s" % ('file', ext)
            return 'user_{0}/{1}'.format('file', filename)
    except Exception as e:
        raise ValidationError(f"Error generating file path: {str(e)}")

class User(AbstractUser):
    """
    Custom user model that uses email or phone number as the unique identifier.
    """
    email = models.EmailField(unique=True, null=True)
    full_name = models.CharField(max_length=500, null=True, blank=True)
    phone = PhoneNumberField(null=True, blank=True, unique=True)
    VENDOR = 'vendor'
    CLIENT = 'client'
    STATUS_CHOICES = [
        (VENDOR, 'Vendor'),
        (CLIENT, 'Client'),
    ]
    role = models.CharField(max_length=20, choices=STATUS_CHOICES, default=CLIENT)
    status = models.BooleanField(default=True)
    verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email' or 'phone'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        if self.role not in dict(self.STATUS_CHOICES).keys():
            raise ValidationError({'role': 'Invalid role value. Must be either "vendor" or "client".'})

    def save(self, *args, **kwargs):
        if not self.email and not self.phone:
            raise ValueError(_("Either email or phone must be provided."))
        super().save(*args, **kwargs)

    @property
    def username(self):
        return self.email or self.phone

    @staticmethod
    def get_username_field():
        return User.USERNAME_FIELD

    @staticmethod
    def set_username_field(field):
        if field not in ['email', 'phone']:
            raise ValueError(_("Invalid field for USERNAME_FIELD."))
        User.USERNAME_FIELD = field

    @property
    def avatar(self):
        """
        Retrieve the avatar image from the associated profile.
        """
        if hasattr(self, 'profile') and self.profile.image:
            return self.profile.image.url
        return '/path/to/default/avatar.jpg'  # Default avatar URL

class Profile(models.Model):
    """
    Profile model associated with the user, containing additional user information.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='Gallery/accounts/users', default='default/default-user.jpg', null=True, blank=True)
    full_name = models.CharField(max_length=1000, null=True, blank=True)
    about = models.TextField(null=True, blank=True)
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    wallet_balance = models.DecimalField(decimal_places=2, default=0.00, max_digits=1000)
    transaction_password = models.CharField(max_length=4, blank=True, null=True)
    deliveryContact = models.ForeignKey("customer.DeliveryContact", on_delete=models.SET_NULL, null=True, blank=True)
    shippingAddress = models.ForeignKey("customer.ShippingAddress", on_delete=models.SET_NULL, null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    country = models.CharField(max_length=1000, null=True, blank=True)
    city = models.CharField(max_length=500, null=True, blank=True)
    state = models.CharField(max_length=500, null=True, blank=True)
    address = models.CharField(max_length=1000, null=True, blank=True)
    newsletter = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    pid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    qr_code = models.TextField(null=True, blank=True)
    mirrorsize_access_token = models.CharField(max_length=255, null=True, blank=True)
    measurement = models.ForeignKey("measurements.Measurement", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        if self.full_name:
            return str(self.full_name)
        else:
            return str(self.user.full_name)
    
    def set_transaction_password(self, password):
        self.transaction_password = password
        self.save()

    def check_transaction_password(self, password):
        return self.transaction_password == password

    def save(self, *args, **kwargs):
        if self.full_name == "" or self.full_name is None:
            self.full_name = self.user.full_name
        super(Profile, self).save(*args, **kwargs)

    def thumbnail(self):
        """
        Generate a thumbnail image for the profile.
        """
        return mark_safe('<img src="/media/%s" width="50" height="50" object-fit:"cover" style="border-radius: 30px; object-fit: cover;" />' % (self.image))


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

post_save.connect(create_user_profile, sender=User)
post_save.connect(save_user_profile, sender=User)

class Tokens(models.Model):
    email = models.EmailField('email address')
    action = models.CharField(max_length=20)
    token = models.CharField(max_length=200)
    exp_date = models.FloatField()
    date_used = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now=True)
    used = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)
