from django.db import models
from userauths.models import User
# Create your models here.

class Measurement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gender = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=5, decimal_places=2)
    height = models.DecimalField(max_digits=5, decimal_places=2)
    age = models.IntegerField()
    measurements = models.JSONField()  # Store measurement data as JSON
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.created_at}"
    



class MeasurementVideo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    video_url = models.URLField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Measurement Video"






