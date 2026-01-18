from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
import logging

logger = logging.getLogger('application')

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager defined with explicit Sync and Async methods.
    
    This manager handles user creation and retrieval using normalized emails
    or phone numbers as unique identifiers. It avoids generic wrappers in favor
    of native Django async support (acreate, aget, asave) for maximum performance.
    """

    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a regular user (sync version).
        
        Ensures email or phone is provided, normalizes data, and handles
        password hashing before saving to the database.
        """
        try:
            if not email and not phone:
                raise ValueError(_('Either an email address or phone number must be set'))
            
            email = self.normalize_email(email) if email else None
            
            user = self.model(email=email, phone=phone, **extra_fields)
            user.set_password(password)
            user.save(using=self._db)
            
            logger.info(f"Created user: {user}")
            return user
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise

    async def acreate_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a regular user (async version).
        
        Native async implementation using `asave()` to prevent I/O blocking.
        This fits perfectly with async views and consumers.
        """
        try:
            if not email and not phone:
                raise ValueError(_('Either an email address or phone number must be set'))
            
            email = self.normalize_email(email) if email else None
            
            user = self.model(email=email, phone=phone, **extra_fields)
            user.set_password(password)
            
            # Using native async save
            await user.asave(using=self._db)
            
            logger.info(f"Created user (async): {user}")
            return user
        except Exception as e:
            logger.error(f"Error creating user (async): {str(e)}")
            raise

    def create_superuser(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a superuser (sync version).
        
        Sets strict default permissions (is_staff, is_superuser) and validates them.
        """
        try:
            extra_fields.setdefault('is_staff', True)
            extra_fields.setdefault('is_superuser', True)
            extra_fields.setdefault('is_active', True)

            if extra_fields.get('is_staff') is not True:
                raise ValueError(_('Superuser must have is_staff=True.'))
            if extra_fields.get('is_superuser') is not True:
                raise ValueError(_('Superuser must have is_superuser=True.'))

            return self.create_user(email, phone, password, **extra_fields)
        except Exception as e:
            logger.error(f"Error creating superuser: {str(e)}")
            raise

    async def acreate_superuser(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a superuser (async version).
        
        Leverages `acreate_user` internally to reuse the async creation logic
        while enforcing superuser privileges.
        """
        try:
            extra_fields.setdefault('is_staff', True)
            extra_fields.setdefault('is_superuser', True)
            extra_fields.setdefault('is_active', True)

            if extra_fields.get('is_staff') is not True:
                raise ValueError(_('Superuser must have is_staff=True.'))
            if extra_fields.get('is_superuser') is not True:
                raise ValueError(_('Superuser must have is_superuser=True.'))

            return await self.acreate_user(email, phone, password, **extra_fields)
        except Exception as e:
            logger.error(f"Error creating superuser (async): {str(e)}")
            raise

    def get_by_natural_key(self, identifier):
        """
        Get user by natural key (sync version).
        
        Queries for either email OR phone matching the identifier.
        """
        try:
            return self.get(Q(email=identifier) | Q(phone=identifier))
        except self.model.DoesNotExist:
            logger.warning(f"No user found for {identifier}")
            raise self.model.DoesNotExist(_('No user with this email or phone number.'))
        except Exception as e:
            logger.error(f"Error getting user by natural key: {str(e)}")
            raise

    async def aget_by_natural_key(self, identifier):
        """
        Get user by natural key (async version).
        
        Uses native `aget` for query execution. This is crucial for avoiding
        SynchronousOnlyOperation errors in async contexts.
        """
        try:
            return await self.aget(Q(email=identifier) | Q(phone=identifier))
        except self.model.DoesNotExist:
            logger.warning(f"No user found for {identifier} (async)")
            raise self.model.DoesNotExist(_('No user with this email or phone number.'))
        except Exception as e:
            logger.error(f"Error getting user by natural key (async): {str(e)}")
            raise
