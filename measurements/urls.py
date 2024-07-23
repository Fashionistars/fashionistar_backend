from django.urls import path
from measurements.views import GenerateAndRedirectView, FetchMeasurementView

urlpatterns = [
    path('measurements/generate-and-redirect/', GenerateAndRedirectView.as_view(), name='generate-and-redirect'),
    path('measurements/fetch-measurement/', FetchMeasurementView.as_view(), name='fetch-measurement'),
]
