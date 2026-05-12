from apps.common.throttling import UserBurstThrottle


class CatalogWriteThrottle(UserBurstThrottle):
    """Catalog uses the shared authenticated burst budget from apps.common."""
