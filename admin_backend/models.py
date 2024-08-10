from django.db import models
from django.utils.html import mark_safe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from userauths.models import user_directory_path, User
from shortuuid.django_fields import ShortUUIDField

import os 
import shortuuid






def validate_file_extension(value, field_name):
    ext =os.path.splitext(value.name)[1]
    valid_extensions = {
        'image' :['.png', '.jpg', '.jpeg'],
    }
    allowed_extensions = valid_extensions[field_name]
    if not ext.lower() in [extension.lower() for extension in allowed_extensions]:
        error_msg ={
            'image': 'Unsupported file extension for book cover. Only PNG, JPG and JPEG',
        }
        raise ValidationError(error_msg[field_name])
    
    if field_name == 'image':
        file_size = value.size
        limit_mb = 5
        max_size = limit_mb * 1024 * 1024
        if file_size > max_size:
            raise ValidationError(f'Maximum file size for cover image is {limit_mb} MB')

def validate_image_cover_extension(value):
    return validate_file_extension(value, 'image')


class Collections(models.Model):
    background_image = models.ImageField(upload_to='Gallery/bg_img/',
                                         validators=[validate_image_cover_extension])
    image = models.ImageField(upload_to='Gallery/product_img/', validators=[validate_image_cover_extension])
    
    

# Model for Product Categories
class Category(models.Model):
    title = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to=user_directory_path, default="category.jpg", null=True, blank=True)
    active = models.BooleanField(default=True)
    slug = models.SlugField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Categories"

    def thumbnail(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.title
    
    # Returns the count of products in this category
    def product_count(self):
        from store.models import Product  # Import here to avoid circular import
        product_count = Product.objects.filter(category=self).count()
        return product_count
    
    # Returns the products in this category
    def cat_products(self):
        from store.models import Product  # Import here to avoid circular import

        cat_products = Product.objects.filter(category=self)
        return cat_products

    # Custom save method to generate a slug if it's empty
    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + str(uniqueid.lower())
        super(Category, self).save(*args, **kwargs) 



# Model for Brands
class Brand(models.Model):
    title = models.CharField(max_length=100)
    image = models.ImageField(upload_to=user_directory_path, default="brand.jpg", null=True, blank=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Brands"

    # Returns an HTML image tag for the brand's image
    def brand_image(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.title
    

class Transaction(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, null=False)
    oid = ShortUUIDField(length=10, max_length=25, alphabet="abcdefghijklmnopqrstuvxyz")
    paid = models.DecimalField(decimal_places=2, max_digits=1000)
    methods = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_created=True)
    
