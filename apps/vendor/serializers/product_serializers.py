from rest_framework import serializers


class GallerySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    image = serializers.CharField(read_only=True)
    active = serializers.BooleanField(read_only=True)


class SpecificationSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField()
    content = serializers.CharField()


class SizeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class ColorSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    color_code = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(read_only=True)


class VendorProductSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    pid = serializers.CharField(read_only=True)
    title = serializers.CharField(max_length=255)
    image = serializers.CharField(required=False, allow_blank=True, read_only=True)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    old_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    shipping_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    stock_qty = serializers.IntegerField(min_value=0)
    status = serializers.CharField(required=False, allow_blank=True)
    featured = serializers.BooleanField(required=False)
    type = serializers.CharField(required=False, allow_blank=True)
    gallery = GallerySerializer(many=True, read_only=True)
    specification = SpecificationSerializer(many=True, read_only=True)
    product_size = SizeSerializer(many=True, read_only=True)
    product_color = ColorSerializer(many=True, read_only=True)


class VendorProductListSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    pid = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    image = serializers.CharField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    old_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock_qty = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    category_name = serializers.CharField(source="category.title", read_only=True)
    date = serializers.DateTimeField(read_only=True)


class VendorOrderStatusSerializer(serializers.Serializer):
    delivery_status = serializers.ChoiceField(
        choices=["pending", "processing", "shipped", "fulfilled", "cancelled"]
    )
    tracking_id = serializers.CharField(required=False, allow_blank=True)
