from django.contrib import admin
from measurements.models import  Measurement


class MeasurementAdmin(admin.ModelAdmin):
    search_fields  = ['user']
    list_display = ['user', 'gender', 'name', 'weight', 'height', 'age', 'measurements', 'created_at' ]


admin.site.register(Measurement, MeasurementAdmin)
