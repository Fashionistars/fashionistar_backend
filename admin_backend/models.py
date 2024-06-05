from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import os 


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
    background_image = models.ImageField(upload_to='bg_img/',
                                         validators=[validate_image_cover_extension])
    image = models.ImageField(upload_to='product_img/', validators=[validate_image_cover_extension])
    
    
    