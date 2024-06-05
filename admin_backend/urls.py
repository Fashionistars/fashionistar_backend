# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CollectionsViewSet

router = DefaultRouter()
router.register(r'collections', CollectionsViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
