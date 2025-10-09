# vendor/pagination.py

from rest_framework.pagination import PageNumberPagination

class VendorCatalogPagination(PageNumberPagination):
    """
    Custom pagination class for the vendor's product catalog.

    Sets a default page size of 10 items and allows the client to
    request a different page size using the 'page_size' query parameter.
    """
    page_size = 10  # Default number of items per page
    page_size_query_param = 'page_size'  # Allows client to override page size, e.g., ?page_size=20
    max_page_size = 100  # Sets a maximum limit for the page size