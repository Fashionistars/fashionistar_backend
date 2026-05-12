from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.common.permissions import IsVerifiedUser


class IsCatalogStaffOrReadOnly(BasePermission):
    """
    Public users may read catalog metadata.
    Only trusted staff/admin users may mutate admin-managed commerce metadata.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        if not IsVerifiedUser().has_permission(request, view):
            return False

        role = str(getattr(user, "role", "") or "").upper()
        return bool(
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or role in {"ADMIN", "SUPERUSER", "EDITOR", "MODERATOR"}
        )
