from django.urls import path
from measurements.views import GenerateAndRedirectView, FetchMeasurementView, MeasurementVideoView


urlpatterns = [
    path('measurement/generate-and-redirect/', GenerateAndRedirectView.as_view(), name='generate-and-redirect'),
    path('measurement/fetch-measurement/', FetchMeasurementView.as_view(), name='fetch-measurement'),


    # ========================   FOR CREATING AND VIEWING THE MEASUREMENT VIDEOS   ======================

    path('measurement-videos/', MeasurementVideoView.as_view(), name='measurement_video_list'),
    path('measurement-videos/<int:pk>/', MeasurementVideoView.as_view(), name='measurement_video_detail'),
]
