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
   
   # Admin URL
   path('admin/', admin.site.urls),
   path("auth/", include("userauths.urls")),
   # New Modular Monolith Auth
   path('api/v2/auth/', include('apps.authentication.urls', namespace='authentication')),
   path("admin_backend/", include("admin_backend.urls")),


   #  VENDORS   /  SHOP   /  SELLER 
   path("", include("vendor.urls")),
   path("", include("vendor.new_urls")),  ######  NEW URLS

   #  CLIENTS   /  CUSTOMER   /  USER 
   path("", include("customer.urls")),
   path("", include("store.urls")),



   path("", include("measurements.urls")),
   path("", include("Blog.urls")),
   path("", include("Homepage.urls")),


   # path("", include('transaction.urls')),
   path("", include('Paystack_Webhoook_Prod.urls')),

]


# ====================================================================================

# ====================================================================================
# *** EDIT 3: CONDITIONAL STATIC FILE SERVING ***
# - Serving media files is fine, though in prod, Cloudinary handles it fully.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)



# - STATIC files MUST only be served by the Django development server when DEBUG=True.
# - When DEBUG=False, Cloudinary/STATICFILES_STORAGE handles it, so this block is not run.
if settings.DEBUG:
   urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
# ====================================================================================