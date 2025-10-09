# vendor/filters.py

from django_filters import rest_framework as filters
from store.models import Product



STATUS = (
    ("draft", "Draft"),
    ("disabled", "Disabled"),
    ("rejected", "Rejected"),
    ("in_review", "In Review"),
    ("published", "Published"),
)

class ProductFilter(filters.FilterSet):
    """
    Custom filterset for the Vendor's product catalog.

    Allows filtering products by their status and the name of their category.
    The category filter uses a case-insensitive lookup on the category's name.
    """
    # Filter by the exact status choices ('published', 'draft', etc.)
    status = filters.ChoiceFilter(choices=STATUS)

    # Filter by the name of the category. `field_name` specifies the lookup path.
    # `lookup_expr='icontains'` makes the search case-insensitive.
    category = filters.CharFilter(field_name='category__name', lookup_expr='icontains')

    class Meta:
        model = Product
        fields = ['status', 'category']