from django.db import models

# Create your models here.
class Collections(models.Model):
    background_image = models.BinaryField()
    image = models.BinaryField()
    
    