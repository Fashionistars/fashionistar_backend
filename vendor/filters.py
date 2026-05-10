# vendor/filters.py

from django_filters import rest_framework as filters

from store.models import Product
from store.models import CartOrder


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

    



from store.models import CartOrder


class OrderFilter(filters.FilterSet):
    """
    Custom filterset for the Vendor's orders list.
    Allows filtering orders by their current `order_status`.
    """
    # The `field_name` matches the model field, and `lookup_expr` allows for
    # filtering based on a list of statuses, e.g., ?order_status=Pending
    order_status = filters.CharFilter(field_name='order_status', lookup_expr='iexact')

    class Meta:
        model = CartOrder
        fields = ['order_status']



        