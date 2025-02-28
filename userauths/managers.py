from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.db.models import Q  # Import Q object

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email or phone is the unique identifiers
    for authentication instead of usernames.
    """
    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        if not email and not phone:
            raise ValueError(_('Either an email address or phone number must be set'))

        email = self.normalize_email(email) if email else None  # Ensure None instead of empty string

        user = self.model(email=email, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, phone, password, **extra_fields)

    def get_by_natural_key(self, identifier):
        """
        Override get_by_natural_key to allow authentication by either email or phone.
        """
        try:
            return self.get(Q(email=identifier) | Q(phone=identifier))  # Use Q object for OR query
        except self.model.DoesNotExist:
            raise self.model.DoesNotExist(_('No user with this email or phone number.')) # Raise DoesNotExist with a helpful message
        





