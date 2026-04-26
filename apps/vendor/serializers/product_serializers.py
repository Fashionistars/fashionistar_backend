from rest_framework import serializers
from django.db import transaction
from store.models import Product, Gallery, Specification, Size, Color, CartOrder
from apps.vendor.models import Vendor
from decimal import Decimal

class GallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['id', 'image', 'active']

class SpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specification
        fields = ['id', 'title', 'content']

class SizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ['id', 'name', 'price']

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ['id', 'name', 'color_code', 'image']

class VendorProductSerializer(serializers.ModelSerializer):
    gallery = GallerySerializer(many=True, read_only=True)
    specification = SpecificationSerializer(many=True, read_only=True)
    product_size = SizeSerializer(many=True, read_only=True)
    product_color = ColorSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'image', 'description', 'category', 'price', 'old_price',
            'shipping_amount', 'stock_qty', 'status', 'featured', 'type',
            'gallery', 'specification', 'product_size', 'product_color'
        ]

    @transaction.atomic
    def create(self, validated_data):
        # Extract nested data from the context (passed from the view's perform_create)
        # This allows us to keep the complex parsing logic while using DRF structure
        request = self.context.get('request')
        vendor = self.context.get('vendor')
        
        product = Product.objects.create(vendor=vendor, **validated_data)
        self._handle_nested_data(product, request)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get('request')
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        self._handle_nested_data(instance, request)
        return instance

    def _handle_nested_data(self, product, request):
        """
        Helper to handle the complex multipart nested data parsing.
        """
        if not request:
            return

        # 1. Gallery
        gallery_images = request.FILES.getlist('gallery[]')
        if gallery_images:
            # For updates, we might want to clear old ones or handle specifically
            # Original code just added new ones
            for img in gallery_images:
                Gallery.objects.create(product=product, image=img)

        # 2. Specifications
        spec_titles = request.POST.getlist('specifications[][title]')
        spec_contents = request.POST.getlist('specifications[][content]')
        if spec_titles:
            # Clear existing for update consistency
            product.specification.all().delete()
            for title, content in zip(spec_titles, spec_contents):
                if title and content:
                    Specification.objects.create(product=product, title=title, content=content)

        # 3. Sizes
        size_names = request.POST.getlist('sizes[][name]')
        size_prices = request.POST.getlist('sizes[][price]')
        if size_names:
            product.product_size.all().delete()
            for name, price in zip(size_names, size_prices):
                if name:
                    Size.objects.create(product=product, name=name, price=Decimal(price or 0))

        # 4. Colors
        color_names = request.POST.getlist('colors[][name]')
        color_codes = request.POST.getlist('colors[][color_code]')
        color_images = request.FILES.getlist('colors[][image]')
        # Note: Handling color images in zip can be tricky if some colors don't have images
        # The original code used a loop with range and try-except
        if color_names:
            product.product_color.all().delete()
            for i in range(len(color_names)):
                name = color_names[i]
                code = color_codes[i] if i < len(color_codes) else ""
                image = None
                # This logic depends on how the client sends files (order must match)
                if i < len(color_images):
                    image = color_images[i]
                
                if name:
                    Color.objects.create(product=product, name=name, color_code=code, image=image)

class VendorProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.title', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'pid', 'title', 'image', 'price', 'old_price', 
            'stock_qty', 'status', 'category_name', 'date'
        ]

class VendorOrderStatusSerializer(serializers.Serializer):
    delivery_status = serializers.ChoiceField(choices=CartOrder._meta.get_field('delivery_status').choices)
    tracking_id = serializers.CharField(required=False, allow_blank=True)
