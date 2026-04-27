# apps/measurements/apps.py
"""
Measurements domain AppConfig.

Manages client body measurement profiles that gate custom-tailored
product checkout flows. Products with `requires_measurement=True`
block checkout until the buyer has a valid MeasurementProfile.
"""
from django.apps import AppConfig


class MeasurementsConfig(AppConfig):
    name = "apps.measurements"
    label = "measurements"
    verbose_name = "Measurements"
    default_auto_field = "django.db.models.BigAutoField"
