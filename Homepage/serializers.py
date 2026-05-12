# Homepage/serializers.py

from rest_framework import serializers


from store.models import Product, Gallery, Specification, Size, Color
from admin_backend.models import Category
from vendor.models import Vendor

# ====================================================================
# SERIALIZERS FOR LISTING / RETRIEVING PRODUCTS (READ-ONLY)
# ====================================================================

class HomeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        # Added 'id' so the frontend knows which UUID to use
        fields = ['id', 'name', 'slug']

class HomeGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['image', 'active']

class HomeSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specification
        fields = ['title', 'content']

class HomeSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ['name', 'price']

class HomeColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ['name', 'color_code', 'image']

class HomeVendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['name', 'image', 'vid']

class ProductListDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for LISTING and RETRIEVING products.
    Provides a rich, nested representation of a product and its related data.
    
    This serializer provides a concise representation of a product,
    including a hyperlink to its detail view, optimized for list displays.
    """
    # Hyperlink to the product's public detail page.
    # The view_name must match the `name` provided in the store's urls.py.
    product_detail_url = serializers.HyperlinkedIdentityField(
        view_name='home:product-detail', # Correctly namespaced URL
        lookup_field='slug'
    )
    vendor = HomeVendorSerializer(read_only=True)
    category = HomeCategorySerializer(many=True, read_only=True)
    gallery = HomeGallerySerializer(many=True, read_only=True)
    specification = HomeSpecificationSerializer(many=True, read_only=True)
    size = HomeSizeSerializer(many=True, read_only=True)
    color = HomeColorSerializer(many=True, read_only=True)

    product_rating = serializers.ReadOnlyField()
    rating_count = serializers.ReadOnlyField()
    get_precentage = serializers.ReadOnlyField()
    
    # Adding model methods/properties to the output
    discount_percentage = serializers.FloatField(source='get_precentage', read_only=True)
    average_rating = serializers.FloatField(source='product_rating', read_only=True)

    class Meta:
        model = Product
        fields = [
            'product_detail_url', # Link to the product's detail page
            'pid', # Public ID for frontend edit/delete actions
            'slug', # Public SEO friendly URL for frontend edit/delete actions
            'sku', 'title', 'image', 'description', 'price', 'old_price',
            'shipping_amount', 'total_price', 'stock_qty', 'in_stock', 'status',
            'featured', 'hot_deal', 'date',
            'vendor', 'category', 'gallery', 'specification', 'size', 'color',
            'product_rating', 'rating_count', 'get_precentage',  'discount_percentage', 'average_rating',
            'brand', 'tags','order_count', 'views', 'saved',
        ]






