from ninja import NinjaAPI
from apps.authentication.apis.auth_views.async_views import auth_router

# Instantiate NinjaAPI
# We can configure auth=None here or per router.
# The router currently has explicit auth settings.
api = NinjaAPI(
    title="Fashionistar Auth API V2",
    version="2.0.0",
    description="Asynchronous Authentication API using Django Ninja",
    urls_namespace='authentication_v2' # distinct namespace
)

# Add Auth Router
# The router defines endpoints like /register, /verify-otp
# If we add it with prefix='', they will be relative to where api.urls is mounted.
api.add_router("", auth_router)
