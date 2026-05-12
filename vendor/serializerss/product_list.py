# vendor/serializerss/product_list.py

from rest_framework import serializers
from store.models import Product

class VendorProductListSerializer(serializers.ModelSerializer):
    """
    A tailored serializer for the Vendor's product catalog view.

    This serializer provides a concise representation of a product,
    including a hyperlink to its detail view, optimized for list displays.
    """
    # Hyperlink to the product's public detail page.
    # The view_name must match the `name` provided in the store's urls.py.
    product_detail_url = serializers.HyperlinkedIdentityField(
        view_name='home:product-detail', # Correctly namespaced URL
        lookup_field='slug'
    )

    class Meta:
        model = Product
        fields = [
            'pid', # Public ID for frontend edit/delete actions
            'image',
            'title',
            'price',
            'status',
            'in_stock',
            'date',
            'product_detail_url', # Link to the product's detail page
        ]