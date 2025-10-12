from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _
from shortuuid.django_fields import ShortUUIDField
from .managers import CustomUserManager
from django.core.exceptions import ValidationError
from phonenumber_field.modelfields import PhoneNumberField


import logging
# Get logger for application
application_logger = logging.getLogger('application')
    



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









# userauths/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from .managers import CustomUserManager

import logging

# Get logger for application
application_logger = logging.getLogger('application')

class User(AbstractUser):
    """
    Custom user model that uses email or phone number as the unique identifier.
    """
    email = models.EmailField(unique=True, blank=True,  null=True, db_index=True)  #  db_index=True  # Make unique only if not None
    phone = PhoneNumberField(unique=True, null=True, blank=True,  db_index=True)  # db_index=True    # Make unique only if not None
    VENDOR = 'vendor'
    CLIENT = 'client'
    STATUS_CHOICES = [
        (VENDOR, 'Vendor'),
        (CLIENT, 'Client'),
    ]
    role = models.CharField(max_length=20, choices=STATUS_CHOICES, default=CLIENT, db_index=True)  # Index role

    status = models.BooleanField(default=True, db_index=True)  # Added db_index=True
    verified = models.BooleanField(default=False, db_index=True)  # Added db_index=True
    is_active = models.BooleanField(default=False, db_index=True)  # Added db_index=True

    username = None  # Remove username field

    USERNAME_FIELD = 'email'  # Keep as email for now
    REQUIRED_FIELDS = ['phone']

    objects = CustomUserManager()

    class Meta:
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

        indexes = [
            models.Index(fields=['email'], name='user_email_idx'),
            models.Index(fields=['phone'], name='user_phone_idx'),
            models.Index(fields=['email', 'password'], name='user_email_password_idx'),  # for speedy Login
            models.Index(fields=['phone', 'password'], name='user_phone_password_idx'),  # For Login
            models.Index(fields=['role'], name='user_role_idx'), # Added index for role
            models.Index(fields=['verified'], name='user_verified_idx'), # Added index for verified
            models.Index(fields=['is_active'], name='user_is_active_idx'), # Added index for is_active
        ]

    def clean(self):
        """
        Validate that either email or phone is provided, but not both.
        Prevent modifying email, phone, and role after user creation.
        """
        super().clean()

        if not self.pk:  # If there's no primary key, it's a new user

            # Check either email or phone is provided
            if not self.email and not self.phone:
                raise ValidationError({'email': _('Either email or phone must be provided.')})

            # Check both are not provided
            if self.email and self.phone:
                raise ValidationError({
                    'email': _('Cannot provide both email and phone.'),
                    'phone': _('Cannot provide both email and phone.')
                })

            # Check uniqueness for email ONLY if an email is being set and is not NULL
            if self.email and User.objects.filter(email=self.email).exists():
                raise ValidationError({'email': _('This email is already in use.')})

            # Check uniqueness for phone ONLY if a phone is being set and is not NULL
            if self.phone and User.objects.filter(phone=self.phone).exists():
                raise ValidationError({'phone': _('This phone number is already in use.')})

            # Check for Availability of Role and ONLY if Role is being set and is not NULL
            if self.role not in dict(self.STATUS_CHOICES).keys():
                raise ValidationError({'role': _('Invalid role value. Must be either "vendor" or "client".')})

        # If updating an existing user, prevent email/phone/role modification
        else:
            existing_user = User.objects.get(pk=self.pk)

            # If the existing user has an email, prevent changes
            if existing_user.email is not None and self.email != existing_user.email:
                raise ValidationError({'email': _('Email cannot be changed after user creation.')})

            # If the existing user has a phone, prevent changes
            if existing_user.phone is not None and self.phone != existing_user.phone:
                raise ValidationError({'phone': _('Phone cannot be changed after user creation.')})

            # Prevent role modification
            if self.role != existing_user.role:
                raise ValidationError({'role': _('Role cannot be changed after user creation.')})

            # Log the update action
            application_logger.info(f"Details Updated for user: {existing_user.identifying_info}")

        # Always return the cleaned data
        return None

    def save(self, *args, **kwargs):
        """
        Save method to enforce email/phone requirement and uniqueness.
        Ensure email and phone are stored as NULL instead of an empty string.
        """
        self.full_clean()  # Validate before saving (includes clean method)

        if not self.email:
            self.email = None  # Store as NULL instead of an empty string

        if not self.phone:
            self.phone = None  # Store as NULL instead of an empty string

        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.email) if self.email else str(self.phone) if self.phone else "No Email or Phone"

    @property
    def identifying_info(self):
        """
        Return email or phone, prioritizing email if available.
        """
        return str(self.email) if self.email else str(self.phone) if self.phone else "No Email or Phone"

    @property
    def username(self):
        """
        Return username, prioritizing email if available.
        """
        return self.email if self.email else str(self.phone) if self.phone else "No Email or Phone"

    @staticmethod
    def get_username_field():
        return User.USERNAME_FIELD

    # No longer use set_username_field
    # Remove set_username_field

    @property
    def avatar(self):
        """
        Retrieve the avatar image from the associated profile.
        """
        if hasattr(self, 'profile') and self.profile.image:
            return self.profile.image.url
        return 'default/default-user.jpg'  # Default avatar URL - corrected
















# class User(AbstractUser):
#     """
#     Custom user model that uses email or phone number as the unique identifier.
#     """
#     email = models.EmailField(unique=True, blank=True,  null=True, db_index=True)  #  db_index=True  # Make unique only if not None
#     phone = PhoneNumberField(unique=True, null=True, blank=True,  db_index=True)  # db_index=True    # Make unique only if not None
#     VENDOR = 'vendor'
#     CLIENT = 'client'
#     STATUS_CHOICES = [
#         (VENDOR, 'Vendor'),
#         (CLIENT, 'Client'),
#     ]
#     role = models.CharField(max_length=20, choices=STATUS_CHOICES, default=CLIENT, db_index=True)  # Index role
    
#     status = models.BooleanField(default=True, db_index=True)  # Added db_index=True
#     verified = models.BooleanField(default=False, db_index=True)  # Added db_index=True
#     is_active = models.BooleanField(default=False, db_index=True)  # Added db_index=True
   

#     username = None  # Remove username field


#     USERNAME_FIELD = 'email'  # Keep as email for now
#     REQUIRED_FIELDS = ['phone']




#     objects = CustomUserManager()

   

#     class Meta:
#         verbose_name_plural = "Users"
#         ordering = ["-date_joined"]

#         indexes = [
#             models.Index(fields=['email'], name='user_email_idx'),
#             models.Index(fields=['phone'], name='user_phone_idx'),
#             models.Index(fields=['email', 'password'], name='user_email_password_idx'), # for speedy Login
#             models.Index(fields=['phone', 'password'], name='user_phone_password_idx'),  # For Login
#         ]


#     def clean(self):
#         """
#         Validate that either email or phone is provided, but not both.
#         Prevent modifying email, phone, and role after user creation.
#         """
#         super().clean()

#         if not self.pk:  # If there's no primary key, it's a new user

#             # Check either email or phone is provided
#             if not self.email and not self.phone:
#                 raise ValidationError({'email': _('Either email or phone must be provided.')})


#             # Check both are not provided
#             if self.email and self.phone:
#                 raise ValidationError({
#                     'email': _('Cannot provide both email and phone.'),
#                     'phone': _('Cannot provide both email and phone.')
#                 })


#             # Check uniqueness for email ONLY if an email is being set and is not NULL
#             if self.email and User.objects.filter(email=self.email).exists():
#                 raise ValidationError({'email': _('This email is already in use.')})



#             # Check uniqueness for phone ONLY if a phone is being set and is not NULL
#             if self.phone and User.objects.filter(phone=self.phone).exists():
#                 raise ValidationError({'phone': _('This phone number is already in use.')})

            
#             # Check for Availability of Role and ONLY if Role is being set and is not NULL
#             if self.role not in dict(self.STATUS_CHOICES).keys():
#                 raise ValidationError({'role': _('Invalid role value. Must be either "vendor" or "client".')})
          




#         # If updating an existing user, prevent email/phone/role modification
#         else:  
#             existing_user = User.objects.get(pk=self.pk)
            
#             # If the existing user has an email, prevent changes
#             if existing_user.email is not None and self.email != existing_user.email:
#                 raise ValidationError({'email': _('Email cannot be changed after user creation.')})

#             # If the existing user has a phone, prevent changes
#             if existing_user.phone is not None and self.phone != existing_user.phone:
#                 raise ValidationError({'phone': _('Phone cannot be changed after user creation.')})

#             # Prevent role modification
#             if self.role != existing_user.role:
#                 raise ValidationError({'role': _('Role cannot be changed after user creation.')})

#             # Log the update action
#             application_logger.info(f"Details Updated for user: {existing_user.identifying_info}")



#     def save(self, *args, **kwargs):
#         """
#         Save method to enforce email/phone requirement and uniqueness.
#         Ensure email and phone are stored as NULL instead of an empty string.
#         """
#         self.full_clean()  # Validate before saving (includes clean method)

#         if not self.email:
#             self.email = None  # Store as NULL instead of an empty string

#         if not self.phone:
#             self.phone = None  # Store as NULL instead of an empty string

#         super().save(*args, **kwargs)


#     def __str__(self):
#         return str(self.email) if self.email else str(self.phone) if self.phone else "No Email or Phone"


#     @property
#     def identifying_info(self):
#         """
#         Return email or phone, prioritizing email if available.
#         """
#         return str(self.email) if self.email else str(self.phone) if self.phone else "No Email or Phone"


#     @property
#     def username(self):
#         """
#         Return username, prioritizing email if available.
#         """
#         return self.email if self.email else str(self.phone) if self.phone else "No Email or Phone"

#     @staticmethod
#     def get_username_field():
#         return User.USERNAME_FIELD

#     # No longer use set_username_field
#         # Remove set_username_field

#     @property
#     def avatar(self):
#         """
#         Retrieve the avatar image from the associated profile.
#         """
#         if hasattr(self, 'profile') and self.profile.image:
#             return self.profile.image.url
#         return '/static/path/to/default/avatar.jpg'  # Default avatar URL - corrected






























# +++  TODO: BuyerProfile and SellerProfile ( for containing profile picture and individual names incase of NIN OR BVN VERIFICATION IN THE FUTURE), THEN THIS CURRENT "PROFILE" MODEL BELOW WILL BE RENAMED AS "CLIENT" FOR CLIENT RELATED ISSUES
                                                    # OR 
# +++  TODO:  USE ONE PROFILE PICTURE  MODEL FOR  FOR EVERY BODY INCLUDING BUYER, SELLER, ADMIN, STAFF, SUPPORT AND SO ONE FOR UNIQUE AND UNITY WHILE FETCHING PROFILE PICTURE IMAGES, THEN I WILL CREATE A NEW MODEL FOR ""CLIENT" JUST AS "VENDOR"  MODEL FOR ACCESSING DASHBOARD AND NAVIGATING OTHER ACTIVITIES AND SETTINGS JUST EXACTLY LIKE VENDOR                                                 

class Profile(models.Model):
    """
    Profile model associated with the user, containing additional user information.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', db_index=True)  # Add related_name AND db_index
    image = models.ImageField(upload_to=user_directory_path, default='default/default-user.jpg', null=True, blank=True)
    full_name = models.CharField(max_length=1000, null=True, blank=True, db_index=True) # Add index
    about = models.TextField(null=True, blank=True)
    email = models.EmailField(blank=True, null=True, db_index=True)  # Added email field
    phone = PhoneNumberField(null=True, blank=True, db_index=True)  # Added phone field
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
    pid = ShortUUIDField(unique=True, length=10, editable=False, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    qr_code = models.TextField(null=True, blank=True)
    mirrorsize_access_token = models.CharField(max_length=255, null=True, blank=True)
    measurement = models.ForeignKey("measurements.Measurement", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=['user'], name='profile_user_idx'),  # Index for user FK (critical)
            models.Index(fields=['full_name'], name='profile_full_name_idx'), # Index full_name
            models.Index(fields=['email'], name='profile_email_idx'),  # Index email
            models.Index(fields=['phone'], name='profile_phone_idx'),  # Index phone
            models.Index(fields=['country'], name='profile_country_idx'), # Index country
            models.Index(fields=['state'], name='profile_state_idx'), # Index state
            models.Index(fields=['city'], name='profile_city_idx'), # Index city

            # Examples of Composite indexes
            models.Index(fields=['country', 'state'], name='profile_country_state_idx'),  # Example
            models.Index(fields=['country', 'city'], name='profile_country_city_idx'),  # Example
            models.Index(fields=['state', 'city'], name='profile_state_city_idx'),  # Example
            models.Index(fields=['user', 'full_name'], name='profile_user_full_name_idx'),  # Fast lookup by user + name
        ]
   
   
    def __str__(self):
        return str(self.full_name) if self.full_name else self.user.identifying_info # Use identifying_info here    


    def set_transaction_password(self, password):
        from django.contrib.auth.hashers import make_password
        self.transaction_password = make_password(password)
        self.save()

    def check_transaction_password(self, password):
        from django.contrib.auth.hashers import  check_password
        return check_password(password, self.transaction_password)

    def thumbnail(self):
        """
        Generate a thumbnail image for the profile.
        """
        return mark_safe('<img src="/media/%s" width="50" height="50" object-fit:"cover" style="border-radius: 30px; object-fit: cover;" />' % (self.image))


from django.db.models.signals import post_save
from django.dispatch import receiver  # Import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Creates a profile upon user creation"""
    if created:
        try:
            Profile.objects.create(user=instance, email=instance.email, phone=instance.phone)
            application_logger.info(f"New profile created for user: {instance.identifying_info}")
        except Exception as e:
            application_logger.error(f"Error creating profile for user {instance.identifying_info}: {e}")


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Saves the user profile if modified."""
    try:
        instance.profile.save()
        application_logger.info(f"Profile saved for user: {instance.identifying_info}")

    except Exception as e:
        application_logger.error(f"Error saving profile for user {instance.identifying_info}: {e}")





class Tokens(models.Model):
    """
    Model to store user tokens and OTP information.

    Fields:
        email (EmailField): The email address of the user.
        phone (PhoneNumberField): The phone number of the user.
        action (CharField): The action associated with the token (e.g., 'register', 'reset_password').
        token (CharField): The token value.
        otp (CharField): The OTP value.
        exp_date (FloatField): The expiration date of the token.
        date_used (DateTimeField): The date and time when the token was used.
        created_at (DateTimeField): The date and time when the token was created.
        used (BooleanField): Indicates whether the token has been used.
        confirmed (BooleanField): Indicates whether the token has been confirmed.

    Methods:
        __str__(): Returns a string representation of the token.
    """
    email = models.EmailField('email address', null=True, blank=True, db_index=True)
    phone = PhoneNumberField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=20, db_index=True)
    token = models.CharField(max_length=200)
    otp = models.CharField(max_length=6, blank=True, null=True)
    exp_date = models.FloatField(db_index=True)
    date_used = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now=True)
    used = models.BooleanField(default=False, db_index=True)
    confirmed = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['email', 'action', 'exp_date'], name='tokens_email_action_exp_idx'), # Composite index
            models.Index(fields=['phone', 'action', 'exp_date'], name='tokens_phone_action_exp_idx'), # Composite index
            models.Index(fields=['token'], name='tokens_token_idx'), # Index token
        ]

    def __str__(self):
        if self.email:
            return f"Token for {self.email} ({self.action})"
        else:
            return f"Token for {self.phone} ({self.action})"        




















































                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            