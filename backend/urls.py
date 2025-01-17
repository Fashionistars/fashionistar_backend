from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# drf-yasg imports
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="FASHIONISTAR E-commerce Backend APIs",
      default_version='v1',
      description="This is the API documentation for FASHIONISTAR E-commerce Backend APIs",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="fashionistarclothings@outlook.com"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
   path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
   path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
   path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
   # API V1 Urls
   path("", include("api.urls")),
   # path("", include('transaction.urls')),
   path("", include('Paystack_Webhoook_Prod.urls')),

   # Admin URL
   path('admin/', admin.site.urls),
   path("auth/", include("userauths.urls")),
   path("", include("admin_backend.urls")),

    
   path("", include("measurements.urls")),
   path("", include("Blog.urls")),
   path("", include("Homepage.urls"))
]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)