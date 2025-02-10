from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from userauths.models import User, user_directory_path
from django.utils.text import slugify
import shortuuid
from django.db.models import Avg
import uuid
from django.contrib.auth.hashers import make_password, check_password

class Vendor(models.Model):
    """
    Represents a Vendor in the e-commerce platform.

    Attributes:
        id (UUIDField): Unique identifier for the vendor.
        user (OneToOneField):  Links to the User model, providing authentication and basic user information.
        image (ImageField): Profile image of the vendor's shop.
        name (CharField):  Name of the vendor's shop.
        email (EmailField): Email address for the vendor's shop.
        description (TextField): Detailed description of the vendor's shop.
        mobile (CharField):  Contact phone number for the vendor.
        verified (BooleanField):  Indicates if the vendor's account has been verified.
        active (BooleanField): Indicates if the vendor's shop is currently active.
        wallet_balance (DecimalField):  The current balance in the vendor's wallet.
        vid (ShortUUIDField): A short, unique alphanumeric vendor ID.
        date (DateTimeField):  Timestamp of when the vendor profile was created.
        slug (SlugField):  URL-friendly slug for the vendor's shop name.
        transaction_password (CharField):  Hashed transaction password used for secure operations (e.g., withdrawals). MUST be a 4-digit number when set.

    Methods:
        vendor_image(): Returns an HTML image tag for the vendor's profile image.
        set_transaction_password(password): Hashes the given transaction password and stores it securely.
        check_transaction_password(password): Verifies if the given password matches the stored hashed password.
        get_average_rating(): Calculates and returns the average rating for the vendor's products.
    """
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
    transaction_password = models.CharField(max_length=128, blank=True, null=True, help_text="Hashed transaction password. Must be a 4-digit number when set.")


    # Business Hours
    opening_time = models.TimeField(blank=True, null=True, help_text="Opening time")
    closing_time = models.TimeField(blank=True, null=True, help_text="Closing time")
    # Using ArrayField for multiple days/hours
    business_hours = ArrayField(models.CharField(max_length=50), blank=True, null=True, help_text="e.g., ['Monday: 9 AM - 5 PM', 'Tuesday: 9 AM - 5 PM']")




    class Meta:
        verbose_name_plural = "Vendors"

    def vendor_image(self):
        """
        Returns an HTML image tag for the vendor's image, used in Django Admin.
        """
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        """
        Returns the string representation of the vendor (shop name).
        """
        return str(self.name)

    def save(self, *args, **kwargs):
        """
        Overrides the save method to auto-generate a slug if one doesn't already exist.
        """
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.name.lower()) + "-" + str(uniqueid.lower())

        # Ensure the instance is saved to the database after modifying fields like 'slug'
        super().save(*args, **kwargs)

    def get_average_rating(self):
        """
        Calculates and returns the average rating for the products of this vendor.
        """
        return self.vendor_role.aggregate(average_rating=Avg('rating')).get('average_rating', 0)

    def set_transaction_password(self, password):
         """
        Hashes the given transaction password using bcrypt and stores it securely in the database.

        Args:
            password (str): The plain transaction password to be hashed.
         """
        self.transaction_password = make_password(password)
        self.save()

    def check_transaction_password(self, password):
        """
        Verifies the given transaction password against the stored hashed password.

        Args:
            password (str): The plain transaction password to be verified.

        Returns:
            bool: True if the password matches, False otherwise.
        """
        return check_password(password, self.transaction_password)




        