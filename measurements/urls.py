from django.urls import path
from measurements.views import GenerateAndRedirectView, FetchMeasurementView
from measurements.views import (
    MeasurementVideoListView,
    MeasurementVideoDetailView,
    MeasurementVideoCreateView,
    MeasurementVideoUpdateView,
    MeasurementVideoDeleteView,
)

urlpatterns = [
    path('measurement/generate-and-redirect/', GenerateAndRedirectView.as_view(), name='generate-and-redirect'),
    path('measurement/fetch-measurement/', FetchMeasurementView.as_view(), name='fetch-measurement'),


    # ========================   FOR CREATING AND VIEWING THE MEASUREMENT VIDEOS   ======================


    path('measurement-videos/', MeasurementVideoListView.as_view(), name='measurement_video_list'),
    path('measurement-videos/<int:pk>/', MeasurementVideoDetailView.as_view(), name='measurement_video_detail'),
    path('measurement-videos/create/', MeasurementVideoCreateView.as_view(), name='measurement_video_create'),
    path('measurement-videos/update/<int:pk>/', MeasurementVideoUpdateView.as_view(), name='measurement_video_update'),
    path('measurement-videos/delete/<int:pk>/', MeasurementVideoDeleteView.as_view(), name='measurement_video_delete'),

]
