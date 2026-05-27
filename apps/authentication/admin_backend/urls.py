# apps/authentication/admin_backend/urls.py
"""
DRF URL patterns for the authentication admin domain.
Mounted under /api/admin/auth/ by apps/admin_backend/urls.py.
"""

from django.urls import path

from .views import (
    AdminUserUpdateView,
    AdminUserSuspendView,
    AdminUserReactivateView,
    AdminUserVerifyView,
    AdminUserForcePasswordResetView,
    AdminUserRoleUpdateView,
)

urlpatterns = [
    path("users/<str:user_id>/", AdminUserUpdateView.as_view(), name="admin-user-update"),
    path("users/<str:user_id>/suspend/", AdminUserSuspendView.as_view(), name="admin-user-suspend"),
    path("users/<str:user_id>/reactivate/", AdminUserReactivateView.as_view(), name="admin-user-reactivate"),
    path("users/<str:user_id>/verify/", AdminUserVerifyView.as_view(), name="admin-user-verify"),
    path("users/<str:user_id>/force-password-reset/", AdminUserForcePasswordResetView.as_view(), name="admin-user-force-password-reset"),
    path("users/<str:user_id>/update-role/", AdminUserRoleUpdateView.as_view(), name="admin-user-role-update"),
]
