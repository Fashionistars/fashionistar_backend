from rest_framework import serializers

from admin_backend.models import Category
from store.models import CartOrderItem, CouponUsers, Product, Tag , DeliveryCouriers, CartOrder, Gallery, ProductFaq, Review,  Specification, Coupon, Color, Size,  Wishlist, Vendor
from addon.models import ConfigSettings
from store.models import Gallery
from userauths.serializer import *
from admin_backend.serializers import CategorySerializer

class ConfigSettingsSerializer(serializers.ModelSerializer):
    """ Serializer for config setting model
    """
    class Meta:
            model = ConfigSettings
            fields = '__all__'


# Define a serializer for the Tag model
class TagSerializer(serializers.ModelSerializer):
    """Serializer for the Tag model.
    """
    class Meta:
        model = Tag
        fields = '__all__'

        # Define a serializer for the Gallery model
class GallerySerializer(serializers.ModelSerializer):
    """Serializer for the Gallery model.
     """
    # Serialize the related Product model

    class Meta:
        model = Gallery
        fields = '__all__'

# Define a serializer for the Specification model
class SpecificationSerializer(serializers.ModelSerializer):
    """Serializer for the Specification model.
    """

    class Meta:
        model = Specification
        fields = '__all__'

# Define a serializer for the Size model
class SizeSerializer(serializers.ModelSerializer):
    """Serializer for the Size model.
    """

    class Meta:
        model = Size
        fields = '__all__'

# Define a serializer for the Color model
class ColorSerializer(serializers.ModelSerializer):
    """Serializer for the Color model.
    """

    class Meta:
        model = Color
        fields = '__all__'


# from cloudinary.uploader import upload
# from cloudinary.utils import cloudinary_url


# Define a serializer for the Product model
class ProductSerializer(serializers.ModelSerializer):
    """Serializer for the Product model.
    """
    gallery = GallerySerializer(many=True, read_only=True, help_text="A list of gallery images associated with the product.")
    color = ColorSerializer(many=True, read_only=True, help_text="A list of colors associated with the product.")
    size = SizeSerializer(many=True, read_only=True, help_text="A list of sizes associated with the product.")
    specification = SpecificationSerializer(many=True, read_only=True, help_text="A list of specifications associated with the product.")
    category = CategorySerializer(many=True, help_text="Categories that the product belongs to")  # If you want nested category representation
    image = serializers.ImageField(required=False, help_text="Image of the product.")  # Optional image field


    class Meta:
        model = Product
        fields = [
            "id", "title", "image", "description", "category", "tags", "brand", "price", "old_price", "shipping_amount", 
            "total_price", "stock_qty", "in_stock", "status", "featured", "hot_deal", "special_offer","views", "orders", 
            "saved", "slug","sku", "date", "gallery", "specification", "size", "color", "category_count", "get_precentage", "product_rating", "rating_count",
            'order_count', "frequently_bought_together",
        ]
    
    def __init__(self, *args, **kwargs):
        super(ProductSerializer, self).__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.method == 'POST':
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None

    def create(self, validated_data):
        categories_data = validated_data.pop('category')
        image_data = validated_data.pop('image', None)

        if image_data:
            upload_data = upload(image_data)
            validated_data['image'] = upload_data.get('url')

        product = Product.objects.create(**validated_data)
        
        # Associate categories with the product
        for category_data in categories_data:
            category, created = Category.objects.get_or_create(**category_data)
            product.category.add(category)
        
        return product






# Define a serializer for the ProductFaq model
class ProductFaqSerializer(serializers.ModelSerializer):
    """Serializer for the ProductFaq model.
    """
    # Serialize the related Product model
    product = ProductSerializer(help_text="Product associated with the FAQ")

    class Meta:
        model = ProductFaq
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(ProductFaqSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new product FAQ, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3


# Define a serializer for the CartOrderItem model
class CartOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for the CartOrderItem model.
    """
    # Serialize the related Product model
    # product = ProductSerializer()  

    class Meta:
        model = CartOrderItem
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super(CartOrderItemSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order item, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CartOrder model
class CartOrderSerializer(serializers.ModelSerializer):
    """Serializer for the CartOrder model.
    """
    # Serialize related CartOrderItem models
    orderitem = CartOrderItemSerializer(many=True, read_only=True, help_text="A list of items included in this cart order.")

    class Meta:
        model = CartOrder
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CartOrderSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3


class VendorSerializer(serializers.ModelSerializer):
    """Serializer for the Vendor model.
     """
    # Serialize related CartOrderItem models
    user = ProtectedUserSerializer(read_only=True, help_text="User associated with the vendor")

    class Meta:
        model = Vendor
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(VendorSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Review model
class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for the Review model.
    """
    # Serialize the related Product model
    product = ProductSerializer(help_text="Product associated with the review")
    profile = ProfileSerializer(help_text="Profile associated with the review")
    
    class Meta:
        model = Review
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(ReviewSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new review, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Wishlist model
class WishlistSerializer(serializers.ModelSerializer):
    """Serializer for the Wishlist model.
    """
    # Serialize the related Product model
    product = ProductSerializer(help_text="Product that is saved in the wishlist")

    class Meta:
        model = Wishlist
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(WishlistSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new wishlist item, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3



# Define a serializer for the Coupon model
class CouponSerializer(serializers.ModelSerializer):
    """Serializer for the Coupon model.
     """

    class Meta:
        model = Coupon
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CouponSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CouponUsers model
class CouponUsersSerializer(serializers.ModelSerializer):
    """Serializer for the CouponUsers model.
     """
    # Serialize the related Coupon model
    coupon =  CouponSerializer(help_text="Coupon associated with the coupon user.")

    class Meta:
        model = CouponUsers
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CouponUsersSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon user, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the DeliveryCouriers model
class DeliveryCouriersSerializer(serializers.ModelSerializer):
    """Serializer for the DeliveryCouriers model.
     """
    class Meta:
        model = DeliveryCouriers
        fields = '__all__'



class SummarySerializer(serializers.Serializer):
    """Serializer for the Dashboard Summary model.
     """
    out_of_stock = serializers.IntegerField(help_text="Number of products that are out of stock")
    orders = serializers.IntegerField(help_text="Total number of orders")
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total revenue generated")
    review = serializers.IntegerField(help_text="Total number of reviews")
    average_review = serializers.DecimalField(max_digits=2, decimal_places=1, help_text="Average rating of all products")
    average_order_value = serializers.DecimalField(max_digits=100, decimal_places=2, help_text="Average amount per order")
    total_sales = serializers.DecimalField(max_digits=100, decimal_places=2, help_text="Total sales amount")
    user_image = serializers.URLField(help_text="URL of the vendor's profile image")

class EarningSummarySerializer(serializers.Serializer):
    """Serializer for the Earning summary model.
    """
    monthly_revenue = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total monthly revenue generated")
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total all time revenue generated")


class CouponSummarySerializer(serializers.Serializer):
    """Serializer for the Coupon summary model.
     """
    total_coupons = serializers.IntegerField(default=0, help_text="Total number of coupons for this vendor")
    active_coupons = serializers.IntegerField(default=0, help_text="Total number of active coupons for this vendor")