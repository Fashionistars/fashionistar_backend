from rest_framework.throttling import UserRateThrottle


class CatalogWriteThrottle(UserRateThrottle):
    scope = "catalog_write"
